终端子Agent（Terminal Sub-Agent）统一设计方案
1. 设计目标与原则
1.1 目标
为AI测试运维系统提供统一的本地命令执行能力，支持Web版和Electron桌面版。

实现会话管理（工作目录、环境变量）、流式输出、超时/取消、安全权限控制。

保持前端代码复用，Web与桌面端对上层透明。

借鉴Claude Code泄露的安全机制，提供生产级的命令权限管理。

1.2 原则
单一职责：终端子Agent只负责执行Shell命令，不解析语义，不主动调用其他服务。

平台适配：Web端通过独立本地代理（Go），桌面端通过Electron主进程直接调用node-pty。

协议统一：两种实现对外暴露相同的JSON消息格式，前端通过环境判断切换通信通道。

安全默认：默认拒绝危险操作，通过白名单/黑名单/工作区限制/网络隔离构建纵深防御。

2. 整体架构
text
┌─────────────────────────────────────────────────────────────────┐
│                        用户电脑                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    前端 (Vue)                              │  │
│  │   - 对话界面                                               │  │
│  │   - 终端面板（xterm.js）                                   │  │
│  └─────────────┬───────────────────────────┬─────────────────┘  │
│                │                           │                     │
│     Web模式    │ WebSocket                 │ Electron模式        │
│                │                           │ IPC                 │
│  ┌─────────────▼─────────────┐  ┌───────────▼─────────────────┐ │
│  │   Go本地代理               │  │   Electron主进程            │ │
│  │   (独立进程)               │  │   (node-pty)                │ │
│  │   - 监听localhost:3456     │  │   - 通过IPC暴露API           │ │
│  │   - 执行命令               │  │   - 会话管理                 │ │
│  │   - 安全沙箱               │  │   - 安全沙箱                 │ │
│  └───────────────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                │
                │ HTTPS (主Agent API)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    云端主Agent (Python Flask)                    │
│   - 三段式决策                                                   │
│   - 工具调用规划                                                 │
│   - 长期记忆管理                                                 │
└─────────────────────────────────────────────────────────────────┘
说明：

Web版必须依赖本地代理（Go实现），用户需下载并运行一次。

Electron桌面版内置终端能力，无需额外进程。

前端通过抽象层统一调用，运行时自动选择通信方式。

3. 终端子Agent功能定义
功能	说明
命令执行	执行单条Shell命令，返回stdout/stderr/exit_code
流式输出	实时推送命令输出块，支持大文件查看
会话管理	维护当前工作目录（cwd）和环境变量
超时控制	每条命令可设置最大执行时间（默认60秒）
命令取消	支持主动取消正在运行的命令（SIGTERM）
脚本编排	顺序执行多个命令（可选，stop_on_error）
安全权限	基于白名单/黑名单、工作区限制、网络白名单、子命令数量限制
危险命令拦截	自动检测rm -rf /, sudo等，要求二次确认
4. 通信协议（统一抽象）
4.1 请求格式（前端 → 子Agent）
json
{
  "request_id": "uuid",
  "type": "exec",
  "command": "ls -la",
  "cwd": "/home/user",        // 可选，覆盖会话cwd
  "timeout": 30,              // 秒
  "env": {"KEY": "value"},    // 可选临时环境变量
  "stream": true,
  "confirmed": false          // 是否已通过二次确认
}
4.2 响应格式（子Agent → 前端）
流式输出：

json
{"request_id":"uuid","type":"stdout","data":"total 48\n"}
{"request_id":"uuid","type":"stderr","data":"warning\n"}
命令结束：

json
{"request_id":"uuid","type":"exit","exit_code":0,"duration_ms":123}
需要二次确认：

json
{"request_id":"uuid","type":"confirm_required","reason":"dangerous_command","details":"rm -rf /"}
取消确认：

json
{"request_id":"uuid","type":"cancelled"}
4.3 会话控制
json
{"type":"session","action":"set_cwd","path":"/new/path"}
{"type":"session","action":"set_env","key":"MY_VAR","value":"123"}
4.4 前端抽象接口
typescript
interface ITerminalAgent {
  exec(command: string, onData: (type: 'stdout'|'stderr', data: string) => void, options?: {cwd?: string, timeout?: number}): Promise<{exitCode: number}>;
  cancel(requestId: string): void;
  setCwd(path: string): void;
  setEnv(key: string, value: string): void;
}
Web版实现：WebSocket连接ws://localhost:3456。
Electron版实现：通过window.electronAPI调用IPC。

5. 安全权限系统（借鉴Claude Code）
5.1 核心概念
采用 allow（白名单） + deny（黑名单） + 工作区限制 + 网络白名单 的四层防御。

deny规则优先级最高：即使命中allow，如果同时命中deny，也拒绝执行。

支持模式匹配：使用通配符*匹配命令及参数。

配置文件：默认~/.config/agent-terminal/permissions.json，用户可自定义。

5.2 配置文件结构
json
{
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(echo *)",
      "Bash(pwd)",
      "Bash(whoami)",
      "Bash(env)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(sudo *)",
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(nc *)",
      "Bash(telnet *)",
      "Bash(chmod 777 *)",
      "Bash(dd *)",
      "Bash(:(){ :|:& };:)"
    ],
    "workspace_root": "/home/user/project",
    "network_allowed_domains": ["github.com", "api.openai.com"],
    "bash_max_subcommands": 50,
    "auto_confirm_trusted": false
  }
}
5.3 各配置项详解
配置项	类型	说明
allow	array	白名单命令列表，支持通配符。如Bash(git push *)
deny	array	黑名单命令列表，优先级高于allow
workspace_root	string	工作区根目录，所有命令的cwd必须在此目录下（或子目录），空表示不限制
network_allowed_domains	array	网络白名单，仅允许访问这些域名（通过检测命令中的URL或拦截socket）
bash_max_subcommands	integer	安全检查允许的最大子命令数量（管道/分号/与或链），默认50。超过则需用户二次确认
auto_confirm_trusted	boolean	是否自动执行完全匹配allow的命令（不弹二次确认）
5.4 安全检查流程
text
收到命令
   │
   ▼
1. 正则拆分命令管道/子命令，计数 > bash_max_subcommands？
   │
   ├── 是 → 返回 confirm_required
   │
   ▼
2. 遍历deny规则，是否匹配？
   │
   ├── 是 → 拒绝执行，返回错误
   │
   ▼
3. 遍历allow规则，是否匹配？
   │
   ├── 否 → 拒绝执行，返回错误（未授权命令）
   │
   ▼
4. 检查 workspace_root：解析命令中涉及的文件路径（如 `cat /etc/passwd`），判断是否在允许范围内
   │
   ├── 越界 → 拒绝执行，返回错误
   │
   ▼
5. 检查网络白名单（如果命令包含 curl/wget 等）：提取URL中的域名，判断是否在白名单内
   │
   ├── 不在白名单 → 拒绝执行，返回错误
   │
   ▼
6. 危险模式检测（硬编码高风险模式：rm -rf /、sudo、chmod 777等）
   │
   ├── 命中 → 返回 confirm_required
   │
   ▼
7. 若 auto_confirm_trusted 为 true 且命令完全匹配某 allow 条目 → 自动执行
   │
   ▼
8. 否则执行命令，返回流式输出
5.5 二次确认流程
当子Agent返回confirm_required时，前端弹出确认框（内容含命令和风险原因）。用户确认后，前端重新发送相同请求，但附加字段"confirmed": true。子Agent收到确认后，跳过危险/越权检查，直接执行（但仍受基本deny规则限制，不可绕过）。

6. 会话管理与状态维护
每个前端连接（WebSocket或IPC会话）对应一个独立会话，包含：

字段	类型	说明
id	string	会话唯一标识
cwd	string	当前工作目录（初始为用户HOME或workspace_root）
env	map[string]string	环境变量（继承父进程，可扩展）
history	[]CommandRecord	可选，命令执行历史
执行cd命令的处理：子Agent解析命令，若匹配cd /path，则更新会话的cwd，不实际执行子Shell。其他命令则使用当前cwd作为工作目录。

7. 部署与分发
7.1 Web版本地代理（Go）
编译：GOOS=windows GOARCH=amd64 go build -o agent.exe（其他平台类似）

分发：提供下载链接（2-5MB），用户双击运行，自动监听localhost:3456。

生命周期：用户手动关闭，或由前端通过自定义URL协议唤起。

配置文件：默认读取同目录下的permissions.json，用户可修改。

7.2 Electron桌面版
无需额外代理：主进程直接使用node-pty。

预加载脚本暴露API：

javascript
contextBridge.exposeInMainWorld('electronAPI', {
  execCommand: (command, onData) => ipcRenderer.invoke('terminal:exec', command, onData),
  cancel: (requestId) => ipcRenderer.send('terminal:cancel', requestId),
  setCwd: (path) => ipcRenderer.send('terminal:setCwd', path),
  setEnv: (key, value) => ipcRenderer.send('terminal:setEnv', key, value)
});
安全配置：读取用户目录下的permissions.json，同样实现权限控制。

打包：node-pty包含原生模块，需使用electron-rebuild确保兼容。

8. 与主Agent的集成
主Agent通过三段式XML中的<tool>terminal</tool>调用终端能力。

工具定义（主Agent System Prompt）：

xml
<tool>
  <name>terminal</name>
  <description>执行本地Shell命令，返回输出和退出码。支持工作目录和超时。</description>
  <parameters>
    <param name="command" type="string" required="true"/>
    <param name="cwd" type="string" required="false"/>
    <param name="timeout" type="integer" required="false"/>
  </parameters>
</tool>
前端处理流程：

解析主Agent返回的<decision>，提取tool和params。

调用ITerminalAgent.exec，传入command、cwd、timeout。

若收到confirm_required，弹窗询问用户，用户确认后重新发送（带confirmed: true）。

收集输出（流式或最终），构造新消息：“命令xxx的输出：\n{output}”。

将新消息发送给主Agent继续推理。

9. 错误处理与降级
场景	处理方式
Web版未连接本地代理	前端显示下载引导，并提供“复制命令手动执行”降级方案
Electron版node-pty初始化失败	降级为模拟终端（仅展示命令，不实际执行）或提示重启应用
命令执行超时	子Agent杀死进程，返回exit_code=-1，stderr含“timeout”
命令被用户取消	返回exit_code=-1，error="cancelled"
危险命令需确认	前端弹窗，用户确认后重试
违反allow/deny规则	返回错误信息：“命令不被允许：xxx”
路径越界	返回错误：“命令试图访问不允许的目录”
网络越界	返回错误：“命令试图访问未授权的域名”
10. 未来扩展点
远程SSH执行：增加type: "ssh"，连接远程服务器执行命令。

文件操作API：增加upload、download、edit等工具，由主Agent调度。

插件系统：允许用户自定义命令宏（如agent fix展开为多个步骤）。

会话持久化：将会话状态保存到磁盘，重启后恢复cwd和env。

安全审计日志：记录所有执行过的命令、结果、决策，便于事后审计。

11. 总结
本方案统一了Web和Electron环境下的终端子Agent实现，通过：

平台适配：Web用Go代理，Electron用node-pty，前端抽象层统一调用。

安全权限：借鉴Claude Code的allow/deny/workspace/网络白名单/子命令数量限制，构建纵深防御。

会话管理：维护cwd、env，支持cd命令透传。

流式输出、超时、取消等基础能力。

与主Agent无缝集成：通过三段式XML工具调用。

该方案兼顾了产品化可用性（Web零门槛、桌面原生体验）和生产级安全性（多层权限控制），适合一人公司快速落地并逐步完善。


