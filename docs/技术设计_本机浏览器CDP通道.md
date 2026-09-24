# 技术设计：本机浏览器 CDP 通道（go-local-proxy 反连隧道 + 云端 CDP 网关）

> 状态：设计稿 v1；P1–P3（隧道 / 网关 / local 模式）已实现，P4 未开工
> 另：CDP 层采集与 BadCase 证据关联已落地，见 §17
> 关联现状代码：`agents/cdp/`、`agents/midscene_runner/`、`go-local-proxy/`、`local_browser_bridge.py`、`local_proxy_supervisor.py`、`electron-vue3/src/utils/localBrowserProxyClient.js`

## 0. 一句话结论

浏览器实体与 CDP 端点统一归**用户本机的 go-local-proxy** 管理；云端 Agent 的 Python Playwright 与 midscene/gremlins 的 node Playwright **全部改为 `connectOverCDP` 连接**，经"本机 → 云端反连隧道 + 云端 CDP 网关"抵达本机 Chrome。云端不再自己 launch 浏览器（公网站点保留降级）。

## 1. 背景与现状

内网客户环境：云端服务器开出的浏览器访问不了内网系统，浏览器必须开在客户本机。

现状（与目标形态的差距）：

| 环节 | 现状 | 差距 |
|---|---|---|
| 云端 agent 浏览器 | `session_manager._ensure_browser()` 在云端 `chromium.launch()`（带随机 `--remote-debugging-port`） | 浏览器开错机器 |
| midscene/gremlins | `smoke.mjs` / `gremlins_monkey.mjs` 已支持 `cdp_ws_url` 参数化 + `connectOverCDP(cdpWs)` | 已具备"连"的形态，只差可达的 ws 地址 |
| 本机浏览器 | 前端收 `browser_local` 卡片 → fetch `127.0.0.1:8794/browser/start` 在本机开 Chrome | 只开了浏览器；`_browser_pause` 后无回传/续跑通道，agent 无法操作它 |
| go 代理 | `browser_start/stop/status`；`/browser/cdp/*` HTTP 反代（Go ReverseProxy 可透传 WS Upgrade，Host 已改写） | 未重写 `webSocketDebuggerUrl`；仅环回监听，**跨网不可达**——这是唯一缺的通道 |

根因一句话：**缺一条"云端够到本机 127.0.0.1"的通道**。内网机器只能出网、云端无法入站，所以通道方向必须是"本机 → 云端"反连。

## 2. 目标 / 非目标

目标：
1. `agents/cdp/` 全部浏览器操作（snapshot / click / fill / login / explore）作用于本机 Chrome。
2. midscene / gremlins 复用同一浏览器（同一 browser ws 多客户端），探测内网站点。
3. 人工登录留在本机可见浏览器，账密/登录态不出本机。
4. 本机代理不可用时**明确失败**（不静默回退云端 launch 造成"假完成"），公网站点保留云端 launch 降级。
5. 不改客户端分发形态：仍为单二进制 go-local-proxy，不引入 Node/Playwright 依赖到客户机。

非目标：
- 不把 shell/PTY 放进隧道（终端仍走前端 ↔ 本机代理本地 WS，现状不动）。
- 不做通用 TCP/HTTP 正向代理（隧道仅允许 CDP 到"代理自己拉起的 Chrome"）。
- 不在本期改 midscene runner 代码（零改动接入）。

## 3. 总体架构

```
用户内网机器                                      云端服务器
┌───────────────────────────────┐               ┌──────────────────────────────────────┐
│ go-local-proxy                │  wss 反连     │ 桥服务 local_browser_bridge.py (aiohttp)│
│  ├─ browserManager 拉 Chrome  │ ───────────►  │  ├─ Tunnel Hub  :  /api/local-proxy/tunnel
│  │    (--remote-debugging)    │  (本机→云)    │  │    (经 nginx wss 升级，认证/注册表)   │
│  ├─ tunnel 客户端(新增)       │               │  ├─ CDP 网关    :  127.0.0.1:9888/cdp/{key}
│  │   └─ 只转发自有 Chrome 端口│               │  ├─ internal API:  127.0.0.1:9888/internal/*
│  └─ /ws /pty /browser/*(保留) │               │  └─ route 表(key→user, TTL)             │
└───────────────▲───────────────┘               └───────────────┬──────────────────────────┘
                │                                               │ 环回 ws
                │                                   ┌───────────┴────────────┐
        (数据帧双向透传, 多路复用 sid)                 │ Flask/Agent (gunicorn)  │
                │                                   │  ├─ session_manager      │
                │                                   │  │    connect_over_cdp ◄─┼── ws://127.0.0.1:9888/cdp/{key}
                │                                   │  ├─ cdp_tool / channel   │
                │                                   │  └─ midscene/gremlins    │
                │                                   │       (cdp_ws_url → 网关)│
                │                                   └─────────────────────────┘
        ┌───────┴─────────────────┐                 前端(Electron, 跑在用户本机):
        │ 用户本机 Chrome(有头)    │                 唤起代理/卡片展示/人工登录提示
        │  127.0.0.1:{random}/…   │
        └─────────────────────────┘
```

数据流：Playwright(云端环回) → CDP 网关 → Tunnel Hub → wss 隧道 → go 代理 → 本机 Chrome DevTools ws，字节透传。

## 4. 关键设计决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | 通道方向 | 本机 → 云端 wss 反连 | 内网不可入站；出网是唯一稳定方向 |
| D2 | 云端 WS 承载 | 独立 asyncio 进程（aiohttp），**不改 Flask/Waitress/gunicorn** | 现有 WSGI 栈无 WS 能力；独立进程可单独重启、状态不受 Flask 多 worker 影响 |
| D3 | Playwright 连接形态 | **ws 直连**网关 `ws://127.0.0.1:9888/cdp/{key}`（不走 `http://…/json/version` 发现） | 绕开 `webSocketDebuggerUrl` 重写问题；midscene runner 已支持吃 ws 参数，零改动 |
| D4 | 多路复用 | 单隧道 + 4 字节 `sid` 二进制帧 | agent / midscene / gremlins 可并发多流；实现量小 |
| D5 | 认证 | 短期 **tunnel-token**（HMAC-SHA256，Flask 签发、桥服务验签） | 与现有 flask_login 会话解耦；桥服务无状态验签 |
| D6 | Agent context 语义 | local 模式复用 `browser.contexts[0]`，**不 new_context** | 保留本机 Chrome 的登录态与用户 tab；免 storage_state 跨网归档 |
| D7 | 浏览器生命周期 | 归 go 代理（start/stop/status/空闲退出/自启），agent 只连接不持有 | 单一属主；复用现有机制 |
| D8 | 失败策略 | 私网地址 + local 通道不可用 → **显式失败/卡片唤起**，不降级云端 launch | 防"云端跑通=假完成"（历史教训） |
| D9 | 客户端依赖 | 隧道客户端编入 go 二进制，新增参数向后兼容 | 维持单二进制分发 |
| D10 | route 寻址 | key 随机 32B，TTL 600s，绑定 user_id，允许同 key 多连接 | 防猜、够 Playwright 多流复用 |

## 5. 隧道协议 v1

### 5.1 连接与认证

- 端点：`wss://<域名>/api/local-proxy/tunnel`（nginx 升级转发到桥服务 `127.0.0.1:9889`）。
- 传输安全：**生产仅允许 wss**（TLS 1.2+，复用站点 443 同域证书）；go 侧默认严格校验证书链与主机名，禁止 `InsecureSkipVerify`；企业 HTTPS 检查（MITM）环境用 `BADCASE_TUNNEL_CA` 注入私有 CA 或配置证书指纹 pinning；明文 `ws://` 仅限环回开发（`--tunnel-insecure` 显式开关）。
- 首帧（text JSON）：
  ```json
  {"op":"hello","v":1,"token":"<tunnel-token>","device":{"platform":"windows","hostname":"...","proxy_version":"x.y.z"}}
  ```
- 应答：`{"op":"hello_ack","ok":true,"user_id":123,"heartbeat_sec":30}`；验签失败 → `ok:false` + 关闭。
- 同账号多设备：**新连接顶掉旧连接**（审计记录）。
- 心跳：ws ping/pong 30s（aiohttp heartbeat）；连续 2 次无 pong → 判定断线。
- 重连：go 侧指数退避 1s→60s（±20% 抖动），直至成功；本地功能不受影响。

### 5.2 帧格式

| 类型 | WS 帧类型 | 格式 |
|---|---|---|
| 控制帧 | text | JSON，见 5.3 |
| 数据帧 | binary | `[4B sid 大端][CDP ws 消息原始字节]` |

- v1 假定 CDP 消息均为 text（CDP 协议消息本就是 JSON）；本机侧解包后按 text 发入 Chrome ws，反向同理按 binary 封装。
- 单帧上限 8MB（防御）；超限断流并报错。

### 5.3 控制帧

| op | 方向 | 载荷 |
|---|---|---|
| `hello` / `hello_ack` | C→S / S→C | 5.1 |
| `cdp_open` | S→C | `{"op":"cdp_open","sid":1}`：请求打开一条 browser-level CDP 流 |
| `cdp_open_ack` | C→S | `{"op":"cdp_open_ack","sid":1,"ok":true}` 或 `{"ok":false,"error":"browser_not_running"}` |
| `cdp_close` | 双向 | `{"op":"cdp_close","sid":1,"reason":"..."}` |
| `error` | C→S | `{"op":"error","sid":1,"message":"..."}` 流级错误 |

### 5.4 流生命周期

1. Playwright 连上网关 `ws://127.0.0.1:9888/cdp/{key}` → 网关校验 route key → 分配 `sid` → 隧道发 `cdp_open`，**同时缓存** Playwright 在此间隙发出的帧。
2. go 代理收 `cdp_open`：
   - 校验 `browserManager` 正在运行（否则 ack `ok:false`）；
   - GET `http://127.0.0.1:{port}/json/version` 取 `webSocketDebuggerUrl`；
   - ws 连 Chrome → ack `ok:true`。
3. 网关收 ack：
   - `ok:true` → flush 缓存帧，进入双向透传；
   - `ok:false` → 记录审计并**直接关闭** Playwright ws（Playwright 显式报连接失败，符合 D8）。
4. 任一方向断开 → 对端发 `cdp_close` 并清理（Playwright 断开→关 Chrome 侧流；Chrome ws 断开→关 Playwright ws）。

### 5.5 限制

- 单隧道/用户（v1）；同隧道流数上限 16。
- 单隧道 head-of-line：截图等大帧会短暂阻塞其他流 —— 可接受（现有流程 explore 与交互串行），后续可升级双隧道/分片。
- 同一 browser ws 可多客户端（Playwright 各持独立 sessionId），但**操作同一 page 会互相干扰**：业务流程保持 explore 与人工/单测串行（现状即串行）。

## 6. 云端组件

### 6.1 桥服务 `local_browser_bridge.py`（新，独立进程）

两个 listener（同一 aiohttp app 或两个 app）：

| 监听 | 路径 | 用途 |
|---|---|---|
| `BADCASE_BRIDGE_TUNNEL_PORT`（默认 9889，环回；经 nginx 暴露） | `/api/local-proxy/tunnel` | 本机代理反连入口 |
| `BADCASE_CDP_GATEWAY_PORT`（默认 9888，**仅环回，绝不对外**） | `/cdp/{key}` | Playwright/节点 midscene 连接入口 |
| 同上 | `/internal/*` | 给 Flask/Agent 进程的环回 HTTP API |

职责：tunnel 注册表（user_id → 连接）、route 表（key → user_id，TTL 600s）、sid 分配与帧路由、审计日志、心跳与断线清理。

### 6.2 tunnel-token 签发（Flask 侧）

- 新增 `GET /api/client-scripts/local-proxy/tunnel-token`（`@login_required`），返回：
  ```json
  {"url":"wss://api.example.com/api/local-proxy/tunnel","token":"<payload>.<sig>","expires_at":...}
  ```
- token = `base64url({"uid":N,"exp":T}) + "." + HMAC_SHA256(TUNNEL_SECRET, payload)`；TTL 默认 7 天（`BADCASE_TUNNEL_TOKEN_TTL`）。
- `TUNNEL_SECRET` 为 Flask 与桥服务共享的环境变量（≥32 字节随机）。
- 现有 `/api/client-scripts/local-proxy/manifest.json` 保持匿名可访问不变（下载二进制用），token 走新接口。

### 6.3 internal API（给 Flask/Agent 用，仅环回 + `X-Bridge-Key` 头校验同源密钥）

| 方法/路径 | 说明 |
|---|---|
| `GET /internal/tunnel_status?user_id=N` | `{online: bool, device: {...}}` |
| `POST /internal/routes` `{user_id}` | 返回 `{route_key, ws_url, expires_at}` |
| `GET /internal/health` | 探活 |

### 6.4 部署

- 新 systemd unit `deploy/badcase-local-bridge.service`（venv 同 Flask，`Restart=on-failure`）。
- nginx（`deploy/nginx.conf`）新增：
  ```nginx
  location = /api/local-proxy/tunnel {
      proxy_pass http://127.0.0.1:9889;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
  }
  ```
- 新依赖：`aiohttp`（纯 Python，无编译依赖）。

## 7. 客户端 go-local-proxy 改造

### 7.1 启动方式

新增参数（未知参数旧版忽略，兼容）：

```
badcase-local-proxy --tunnel-url wss://api.example.com/api/local-proxy/tunnel --tunnel-token <token>
```

前端 `buildLocalProxyStartCommand()` 与安装流程注入这两个参数；`--install-autostart` 注册的自启命令同样带参（token 过期后前端重唤起刷新）。

### 7.2 隧道客户端（新文件 `tunnel.go`）

- gorilla/websocket 拨号 + 重连循环（5.1）。
- 处理 `cdp_open`：**白名单校验**——目标端口必须等于 `browserManager.port` 且 `running`（拒绝任意端口/主机，防跳板）；GET `/json/version` → 连 `ws://127.0.0.1:{port}/devtools/browser/{uuid}`（gorilla 默认不发 Origin，若遇 Chrome origin 校验可加 `--remote-allow-origins` 处理，现场验证项）。
- 按 sid 维护 Chrome ws 映射；数据帧双向 pump；帧损坏/sid 未知 → `error` 控制帧。
- 若 hello 被拒（token 过期）→ 日志提示并停止重试，等待前端重新唤起注入新 token。

### 7.3 与现有机制联动

- 隧道建立 → `idleConnEnter()`；断开 → `idleConnLeave()`（有隧道时不因空闲退出）。
- `browser_start` 被调用时若隧道未连，尝试补连一次（幂等）。
- `/ws`、`/pty`、`/browser/cdp` 本地通道完全保留（单机部署/调试路径）。

## 8. Agent 侧改造（`agents/cdp/`）

### 8.1 连接模式

- 新增 env `CDP_CONNECTION_MODE=auto|local|launch`（默认 `auto`）。
- `auto` 决策：桥服务 `tunnel_status(owner→user)` 在线 → `local`；离线 → 见 8.2。
- 私网判定（`10/8`、`172.16/12`、`192.168/16`、`100.64/10`、`localhost`、`.local`、显式标记）：私网地址 + local 不可用 → **不降级 launch**，走 8.2 唤起或显式失败（D8）。
- 公网地址 + local 不可用 → 保留现状云端 launch（回归安全）。

### 8.2 通道 ensure 与唤起兜底（新模块 `agents/cdp/channel.py`）

`ensure_local_channel(owner_key)`：
1. 查 `tunnel_status`；在线 → `issue_route` → 返回 `ws://127.0.0.1:9888/cdp/{key}`。
2. 离线 → 返回 None；调用方（cdp_tool 的工具入口）保持现有 `client_browser` 卡片流程（`browser_pause_for_client`）唤起前端 → 前端拉起代理（带 tunnel 参数）→ 桥侧隧道上线。
3. Phase 3 先轮询 ≤20s（不改前端）；Phase 4 增加"卡片执行结果回传 + 自动续跑"（见 9.2）。

### 8.3 session_manager 双模式

- 新增 `LocalBrowserSlot{browser, ws_url, route_key}`（按 owner_key 缓存）；`browser_pools` 的 launch/debug_port 逻辑仅 launch 模式使用。
- local 模式 `create()`：
  ```python
  browser = await pw.chromium.connect_over_cdp(ws_url)
  context = browser.contexts[0]          # 不 new_context（D6）
  page = choose_page(context, url)       # host 匹配的已有 tab 优先，否则 new_page
  ```
- `close()` 语义：local 模式仅释放 session/（必要时）我们新建的 tab，**不关 context、不关浏览器**；浏览器停止由 `client_browser(stop)` 显式触发。
- `get_browser_ws_endpoint()`：local 模式每次重新 `issue_route` 返回新 ws（供 midscene 复用浏览器）；launch 模式保持现状（读 `--remote-debugging-port`）。
- 断线重试：捕获 `Target closed / connection closed` → 重新 ensure + 重连一次，仍失败则显式报错（不静默回退）。

### 8.4 login / storage_state 分支

- local 模式：跳过 storage_state 归档/加载（登录态天然留存本机 profile）。
- 登录墙处理（Phase 4 细化）：local 模式不再走账密卡片，返回"请在本机可见浏览器完成登录，完成后点击继续"提示 + 续跑；Phase 3 暂沿用现有 `await_user_credentials` 流程不改。

### 8.5 midscene / gremlins

- `cdp_tool` explore 前置 `ensure_local_channel`，把 `cdp_ws_url`（网关 ws）传入 `midscene_bridge.run_*`；runner 代码零改动。
- **显式校验**：local 模式下 `cdp_ws_url` 为空禁止调用 runner（防 runner 自行 launch 云端浏览器产生假完成）；`midscene_bridge` 调用层直接抛错。
- 结果映射层（`map_midscene_result_to_explore_observation`）不变。

## 9. 前端改造（轻量）

### 9.1 代理注入隧道参数

- 登录后调 `tunnel-token` 接口，`buildLocalProxyStartCommand()` 拼接 `--tunnel-url/--tunnel-token`。
- 托盘/状态区（可选）显示"本机通道：在线/离线"，数据来自桥 `tunnel_status`（经 Flask 转发或直连代理 `/health` 扩展字段）。

### 9.2 browser_local 卡片续跑（Phase 4）

- 仿终端模式：卡片执行完成 → 续跑载荷 `client_browser_results: [{action, url, ok, cdp_ready, error}]` 随下次 POST /react 提交（新增 `agents/client_browser_resume.py`，格式对齐 `client_terminal_resume.py`）。
- 触发时机：`awaitProxyResume` 场景下，前端检测隧道就绪（代理 health/bridge 状态）→ 自动续跑，替代用户手动再发消息。

## 10. 失败与降级矩阵

| 场景 | 通道 | 行为 |
|---|---|---|
| 私网 URL，local 在线 | ✓ | 全流程本机（正常路径） |
| 私网 URL，local 离线 | ✗ | 发 browser_local 卡片唤起；仍不可用 → 显式失败 + 提示安装/启动本机代理 |
| 公网 URL，local 在线 | ✓ | 同样走本机（统一体验；`CDP_CONNECTION_MODE=launch` 可强制旧行为） |
| 公网 URL，local 离线 | ✗ | 云端 launch（现状保留） |
| 隧道中途断开 | 断 | 当前工具调用报错；下一次调用重新 ensure（自动重连已含在 go 侧） |
| token 过期 | ✗ | hello 被拒；前端重唤起刷新 token；期间按"离线"分支处理 |

## 11. 安全设计

- 传输加密：本机→云端全程 TLS（wss 终止于 nginx 443）；nginx→桥服务为同机环回明文（不经网卡，可接受）；**不做应用层二次加密**——帧数据终态需交 agent/LLM 消费，密钥与解密点同属云端信任域，无额外防护收益，徒增调试成本。
- tunnel-token：HMAC 验签 + exp；放 hello 首帧、不进 URL query（不进 nginx 日志）；泄露面 = 单用户单机（可随时换 `TUNNEL_SECRET` 全量失效）。
- 隧道最小能力：**仅** `cdp_open`（且仅代理自有 Chrome 端口）；拒绝一切 host/port 转发请求。
- 网关仅环回监听；nginx 只转发 `/api/local-proxy/tunnel`，不暴露 `/cdp`、`/internal`。
- route key：随机 32B、TTL 600s、绑定 user_id；无效/过期立即断。
- internal API：环回 + `X-Bridge-Key`（`BRIDGE_INTERNAL_KEY` 环境变量）。
- 审计日志：hello/顶替、cdp_open/close、错误、每流字节数。

## 12. 可观测性

- 桥服务：在线隧道数、活跃流数、open 失败原因分布、每流字节/时长（日志 + 可选 Prometheus，`observability/` 既有设施）。
- go 代理：隧道连接/断开/重连、cdp_open 拒绝原因（日志，沿用现有 `log.Printf` 风格）。
- Flask/Agent：`[CDP] mode=local|launch` 打点（与现有 `[CDP]` 日志风格一致），浏览器卡片状态机增加 `waiting_tunnel`。

## 13. 分阶段落地与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| P1 | 桥服务骨架（hello/心跳/注册表）+ go 隧道客户端 + 记账接口 + Flask token 签发 + 前端注入 | 本机代理上线：桥日志/`tunnel_status` 可见；kill 代理后自动重连；token 伪造被拒 |
| P2 | CDP 网关 + `cdp_open` 透传 | 脚本验证：`connect_over_cdp("ws://127.0.0.1:9888/cdp/{key}")` → 打开**内网**页面，`page.title()`/截图成功 |
| P3 | session_manager local 模式 + cdp_tool/channel 接线 + midscene `cdp_ws_url` 切换 + 降级矩阵 | 对话触发内网站点探测：snapshot/点击/巡检全通；日志确认无云端 launch；公网 launch 回归不退化 |
| P4 | 卡片续跑闭环 + 人工登录提示 + 审计/指标 + 单机模式 `/json/version` 重写 | 内网全流程免手动续跑；代理未装时提示可执行；指标可查 |

## 14. 测试计划

- 协议单测（Go）：hello/cdp_open 白名单/帧分片解析/重连退避。
- 桥服务单测（Python）：token 验签、route TTL、sid 路由、ack false 关流。
- 端到端（开发机模拟"云端"）：网关跑本机 + 代理隧道指本机，跑 P2 验收脚本。
- 真实验证：云服务器 + 内网机器；explore 全链路 + 手工登录场景。
- 断线演练：kill 代理 / 断网 30s → 工具报错一次 → 恢复后下次调用成功。
- 安全：伪造 token、跨用户 route、非 Chrome 端口 cdp_open、直连 9888 外部地址（应拒绝）。
- 回归：公网站点云端 launch 模式全套用例。

## 15. 风险与已知坑

| 风险 | 说明 | 对策 |
|---|---|---|
| 大帧带宽/延迟 | CDP 截图、DOM 快照跨公网 | 复用浏览器减少重连；截图压缩/降质可后置；head-of-line 监控 |
| Chrome origin/Host 校验 | 新版 Chrome 对 CDP ws 有 origin 检查 | 本机直连 127.0.0.1 规避；必要时 `--remote-allow-origins`（现场验证） |
| 企业内网出站限制 | 个别内网禁 wss/仅白名单出站 | 现场验证项；预留"隧道走 443 同域"（当前设计已同域） |
| 企业 HTTPS 检查（MITM） | 出口代理做 TLS 解密导致 wss 证书校验失败 | `BADCASE_TUNNEL_CA` 注入企业根证书或指纹 pinning；不提供跳过校验的全局开关 |
| Playwright 断线不自动重连 | 隧道抖动会断当前调用 | 工具层捕获重连一次；桥侧记录断因 |
| 多设备/多代理 | v1 单隧道/用户 | 新顶旧 + 审计；多设备留 v2 |
| midscene 与 agent 并发操作同 page | 互相干扰 | 业务流程保持串行（现状）；文档约束 |
| 旧版代理二进制 | 未响应 `cdp_open` | 桥侧对旧版：hello 携带 `proxy_version`，网关对 <最低版本给明确报错提示升级 |

## 16. 改动文件清单

新增：
- `local_browser_bridge.py`（桥服务：hub + 网关 + internal API）
- `agents/cdp/channel.py`（ensure/issue_route/status）
- `agents/client_browser_resume.py`（续跑载荷，P4）
- `go-local-proxy/tunnel.go`（隧道客户端）
- `deploy/badcase-local-bridge.service`

修改：
- `go-local-proxy/main.go`（参数解析：`--tunnel-url/--tunnel-token`；启动隧道；与 idle 联动）
- `routers/client_scripts.py`（新增 `tunnel-token` 接口）
- `agents/cdp/session_manager.py`（local 模式：connect_over_cdp / contexts[0] / close 语义 / get_browser_ws_endpoint）
- `agents/cdp/settings.py`（`CDP_CONNECTION_MODE`、私网判定）
- `agents/tools/cdp_tool.py`（explore 前置 ensure；卡片兜底保留）
- `agents/cdp/midscene_bridge.py`（local 模式禁止空 `cdp_ws_url` 调用）
- `agents/cdp/login_flow.py`（local 模式人工登录分支，P4）
- `electron-vue3/src/utils/localProxyStartAndResume.js`（注入 tunnel 参数；续跑触发，P4）
- `deploy/nginx.conf`（`/api/local-proxy/tunnel` upgrade 透传）
- `requirements.txt`（+ aiohttp）
- `README.md`（能力表补充"跨网 CDP 通道"）

不动：
- `agents/midscene_runner/*`（零改动）
- `go-local-proxy/browser_chrome.go`、`/ws`、`/pty`（保留）
- 单机部署路径（`local_proxy_supervisor.py` + `/browser/cdp`）保留为开发/单机模式

## 17. CDP 层采集与 BadCase 证据关联（已落地）

> 本节与上文"设计稿"不同：**已实现并在跑**。目标是让"Agent 操作本机浏览器的过程"成为可回看的证据——被测系统的对话报文（LLM 出入参）+ 页面快照/节点 + 步骤流水，落到具体一条 BadCase 上。

### 17.1 采集运行单元（CdpTestRun）

一次 CDP 测试任务 = 一行 `cdp_test_runs`，也是采集证据的归属单元。字段分工：

| 字段 | 内容 |
|---|---|
| `project_id` / `user_id` | 归属（权限与证据过滤的唯一依据） |
| `cdp_session_id` | 主会话；一任务可能开多个 tab/session |
| `steps_json` | 步骤流水（action / success / summary / ref / duration_ms / url） |
| `spec_json.cdp_session_ids` | 该运行涉及的全部浏览器会话 ID |
| `spec_json.snapshots` | UI 节点快照（见 17.5 边界） |
| `pass_count` / `fail_count` | 由 steps 统计 |

入口：`open_cdp_test_run(db=db, ...)`（**注意 `db` 必须按关键字传**，其余调用方用位置参会拿到未注册的 `db_extensions.db`）、`ensure_cdp_test_task(engine, user_input=..., tool_action=..., result_context=...)`，run_id 经 `result_context['cdp_test_run_id']` 在链路里传递（`get_active_run_id`）。

### 17.2 报文归属：请求级冻结

采集器 `agents/cdp/llm_capture.py` 的归属不是"会话级"而是**请求级**——同一条会话中途换项目/换 run，历史与在途报文不会被改写：

1. `LlmCapture.set_context(project_id, cdp_run_id, declared)` 只影响**后续**请求；`None` 清空归属，不回填历史。
2. 每个 Playwright `request` 事件把当前上下文快照存入 `WeakKeyDictionary`（以 request 对象为键）；`response` 事件取回该快照写入 `record.project_id` / `record.cdp_run_id` / `record.declared`。
3. **未观察到 request 开始**（例如采集器接入时请求已在途）→ 归属为空，不猜测、不回填；这类记录不会被任何项目/运行的证据查询命中（防串号）。
4. `requestfinished` / `requestfailed` 清理快照，避免 WeakKeyDictionary 之外的悬挂；`detach()` 摘监听器但不取消已开始的 body 读取。

上下文更新链路：`react_simplified` / `langgraph_bridge` 注入 `project_id`、`user_id`、`userId`、`result_context` → `cdp_tool` 入口先 `assert_owned(session_id, owner_key)` 校验会话归属，再 `ensure_llm_capture(..., project_id, cdp_run_id)` → `session_manager` 在建会话（`create(project_id=..., cdp_run_id=...)`）与后续 `attach` 新 page 时同步上下文。**校验先于更新**：拿不到归属的调用直接返回 `CdpError`，不会被写进别人的运行里。`batch` 子动作只提供操作参数，不能覆盖调用方的归属。

### 17.3 落盘与回读

- 路径：`observability/llm_exchange/`（`BADCASE_LLM_EXCHANGE_DIR` 可改）
  - `llm_exchange_YYYYMMDD.jsonl`（按天全量）
  - `session_<sid>.jsonl`（按会话）
  - 总开关 `BADCASE_LLM_CAPTURE_ENABLED`
- 单条记录关键字段：`exchange_id`、`ts`、`session_id`、`project_id`、`cdp_run_id`、`url`、`request`（含 declared model）、`response`、`model_mismatch`、`error`。
- 回读 `read_session_exchanges(sid, limit, project_id=..., cdp_run_id=...)`：**逐行扫描 + 精确过滤**（指定后不含缺失/空归属记录），`limit` 为正时内存只留最后 N 条。

### 17.4 证据 API

| 方法/路径 | 说明 |
|---|---|
| `GET /api/agent/badcases/<id>/evidence` | 读证据：`{run_ids, runs[], unavailable_run_ids}` |
| `PUT /api/agent/badcases/<id>/evidence` | 写关联：`{"run_ids":[...]}`，**只改 `bad_case.cdp_run_ids`，不动表单其他字段** |
| `GET /api/agent/cdp-test-runs` | 候选列表：`project_id` / `react_request_id` / `chat_session_id` 三选一 |

约束：

- 权限：读走 `_model_for_user_collaborator_access`（负责人 + 协作者可读写，viewer/无关用户 403，未登录 401，不存在 404）；候选列表按 `has_project_permission` 过滤，**跨项目运行不返回**。
- 写入：最多 10 个、必须合法 UUID、去重保序；**存在性与项目归属校验在同一个请求内完成，失败整体拒绝（原子）**，不允许把别的项目的运行挂上来。
- 读取：已被删除或已不属于当前项目的 run 不泄露内容，只出现在 `unavailable_run_ids`。
- 返回体最小化：候选列表只给 `id/title/status/created_at/cdp_session_id`（`spec_json` 不外发）；证据内 `exchanges` 最多 20 条（`exchanges_truncated` 标记），`steps` 只取白名单字段。
- **URL 一律脱敏**（`_evidence_url`：去 userinfo / query / fragment），页面的表单 field 值、节点 `value`、`selector_hint` **不落库**——证据用于"复现路径"，不搬运用户输入。

### 17.5 快照落库边界

`append_cdp_test_step` 每次落一份快照到 `spec_json.snapshots`，硬上限防爆库：只留**最近 5 份**，每份**最多 200 个节点**（超出置 `truncated`），节点只存 `ref/role/name/disabled`；`title` 截 300 字符。

### 17.6 前端

BadCase 详情（`NewBadcase.vue`）新增子 tab：**基本信息 / 采集参数 / UI节点**。表单始终 `v-show` 保留实例（切子页不丢未保存内容），右栏仅在"基本信息"显示；`BadcaseEvidencePanel.vue` 负责候选选择、关联列表、报文与快照展示、空态。保存只提交 `run_ids`，保存后提示"证据关联已保存；基本信息未改动"。候选来源锁定在**已保存的 BadCase 所属项目**（`savedEvidenceContext`），防止未保存状态下跨项目选错。

### 17.7 测试与验收

- `tests/test_badcase_evidence.py`：证据读写、权限矩阵、非法载荷 400、跨项目原子拒绝、已删/越权运行不外泄、候选列表权限、快照边界与脱敏、真实文件证据的 project+run+session 三重过滤。
- `tests/test_llm_capture.py`：归属冻结（请求级快照）、`set_context` 不清洗历史、在途请求归属为空、`read_session_exchanges` 过滤语义。
- 手工：本机代理拉起 Chrome → 对话触发探测 → 详情页关联运行 → 「采集参数」看到脱敏 URL 与 `model_mismatch`、「UI节点」看到节点表 → 解绑回空态。

### 17.8 本期涉及文件

- 新增：`electron-vue3/src/components/BadcaseEvidencePanel.vue`、`tests/test_badcase_evidence.py`
- 修改：`agents/cdp/llm_capture.py`、`agents/cdp/session_manager.py`、`agents/cdp/test_task.py`、`agents/cdp/postprocess.py`、`agents/tools/cdp_tool.py`、`agents/langgraph_bridge.py`、`agents/react_simplified.py`、`routers/agent.py`、`models/orm.py`（`bad_case.cdp_run_ids` + 迁移）、`app_services/db_schema.py`、`electron-vue3/src/components/NewBadcase.vue`、`electron-vue3/src/api.js`
