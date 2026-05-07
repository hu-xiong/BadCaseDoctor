# 终端「最近命令 / 会话标题」链路梳理（BadCaseDoctor）

> 目的：把“最近命令”和“会话标题（自动标题）”相关的数据流、关键代码位置、边界条件与改动规范固定下来，避免出现控制序列残片（如 `[[0]dir`）被当成命令文本保存与展示的问题。

---

## 一、涉及的功能点

- **最近命令（Recent Commands）**
  - 入口：终端面板菜单「执行最近命令」
  - 展示：当前会话的命令历史弹框；以及 `ProjectDetail.vue` 的全局命令历史弹框
  - 来源：前端捕获“用户提交的命令”后写入 `localStorage`

- **会话标题（Session Title）**
  - 入口：聊天会话列表/顶部栏展示的标题
  - 来源：后端 `generateSessionTitle`（对“用户消息”摘要生成）
  - 终端侧的“命令执行事件”可能被用作自动标题或后续扩展的触发源（通过 `onTermCommandExecuted` 上报）

---

## 二、数据流总览（从按键到 UI）

### 1）用户输入 → xterm 事件

`electron-vue3/src/components/EmbeddedPtyTerminal.vue`

- **主要捕获路径：`term.onKey(...)`**
  - 普通模式：`key` 直接是可打印字符 / `\r` / `\n` / `\x7f`
  - Win32 Input Mode：`key` 可能是形如 `ESC[VK;SC;UC;KD;CS;RS_` 的控制序列（xterm.js win32-input-mode）
    - 通过正则 `^\x1b\[(\d+);(\d+);(\d+);(\d+);(\d+);(\d+)_$` 提取 `UC`（Unicode codepoint）拼回真实字符
    - `VK===13` 视为 Enter，触发提交

- **兜底路径：`term.onData(...)`**
  - 某些环境 `onKey` 不完整时，用 `onData` 逐字符兜底
  - Win32 Input Mode 下，`onData` 也会出现以 `ESC[` 开头、以 `_` 结尾的序列，需要整段跳过或识别 Enter 序列

### 2）命令缓冲 → 提交（Enter）→ 清洗

`electron-vue3/src/components/EmbeddedPtyTerminal.vue`

- **缓冲变量**：`pendingCommand`（不断累积用户输入）
- **提交函数**：`submitPendingCommand(reason)`
  - `rawCmd = pendingCommand.trim()`
  - `cmd = filterCommand(rawCmd).trim()`
  - `cmd` 为空则直接清空并返回（避免“空提交”把防抖时间戳占住）
  - 防抖：120ms 内重复 Enter 触发只保留一次

### 3）写入最近命令存储（localStorage）

`electron-vue3/src/components/EmbeddedTerminalWorkspace.vue`

- **注册表对象**：`termCommandRegistry`
  - `pushCommand(csid, cmd)`
    - `cmd.trim()` 入库
    - 去重：相同命令移到最前
    - 限制：单 session 最多 50 条；总 session 最多 20 个
    - 持久化：`localStorage["etw_cmd_history"]`
  - `getCommands(csid)`：读取列表用于 UI 展示
- **对外暴露**：
  - `globalThis.__termCommandRegistry__ = termCommandRegistry`
  - 供 `ProjectDetail.vue` 的全局弹框跨组件读取

### 4）最近命令 UI 展示与回填执行

- **当前会话弹框**：`EmbeddedTerminalWorkspace.vue`
  - `openCmdHistory()` / `pickHistoryCommand(idx)`
- **全局弹框**：`electron-vue3/src/components/ProjectDetail.vue`
  - `openGlobalCmdHistory(csid)` 从 `globalThis.__termCommandRegistry__` 读取
  - `pickGlobalCmd(idx)` 通过 `termRegistry._activeTerm.write(item.text + '\r')` 回填执行

---

## 三、关键清洗点：为什么会出现 `[[0]dir`

现象（示例）：用户实际输入 `dir`，但最近命令/会话标题处出现 `[[0]dir`、`[0m`、`]0` 等“残片”。

根因：终端输入或回显中混入了 **ANSI 控制序列**（CSI/OSC/DCS…），如果只删除了 `ESC`（0x1B）本身，或对 `ESC[` 的解析过于简化（遇到 `?`/中间字符/嵌套 `[` 就提前停止），就会把 `[`、`0`、`]` 等字符残留在字符串里，最终被当成“命令文本”写入 `termCommandRegistry`。

典型来源：

- **PSReadLine / PowerShell** 会输出多种控制序列（含括号/私有模式参数）
- **xterm / conpty** 在特定模式下会把按键编码成控制序列
- **OSC 标题序列**（`ESC ] 0 ; <title> BEL` 或 `ESC \` 终止）如果未剥离，也会污染“纯文本命令”

防线：`filterCommand(raw)` 必须做到 **完整剥离控制序列**，而不是“遇到不认识的字符就 break”。

---

## 四、当前实现的约束与规范（改动必须遵守）

### 1）命令识别只认“用户提交”

- 命令历史只应在 **Enter 提交** 时写入（`submitPendingCommand`）
- 不要从“stdout 回显”猜命令并直接入库，除非有严格可验证的 prompt/echo 规则（否则会把提示符、错误块、控制码当成命令）

### 2）清洗应当“一处做对，全链路受益”

推荐策略：

- 在 `EmbeddedPtyTerminal.vue` 的 `filterCommand()` 统一剥离
  - 覆盖 CSI/OSC/DCS/SOS/PM/APC + 常见单字节 ESC 序列
  - 再清掉剩余 C0 控制字符（`\x00-\x1F`、`\x7F`）
- `termCommandRegistry` 层不要再做“半吊子清洗”，避免双重规则不一致

### 3）不要把调试输出当功能依赖

目前相关位置有较多 `console.log`（例如 pushCommand、submitPendingCommand 的 charCode 调试）。这些可以保留用于诊断，但：

- **禁止** UI/逻辑依赖调试日志的存在
- 如果要长期保留，建议由 `localStorage` 开关控制（项目里已有类似的 debug 开关实践）

### 4）Win32 Input Mode 变更要同时覆盖 onKey/onData

任何对 Win32 输入模式正则或处理流程的修改，必须检查：

- `onKey` 的 Win32 序列解析是否仍能正确提取 `UC`
- `onData` 的兜底是否仍能跳过序列、识别 Enter、避免重复提交
- 防抖与“空提交不更新时间戳”的逻辑是否仍成立

---

## 五、排查指南（复现 / 定位）

### 1）快速复现

- PowerShell 下执行：`dir`
- 观察「执行最近命令」弹框是否出现 `[[0]dir` 类残片

### 2）打开调试输出

在浏览器控制台观察：

- `submitPendingCommand` 的 `rawCmd` 与 `filtered` 是否一致
- 如果 `rawCmd` 出现不可见字符，可看 `codes:`（charCode 列表）

### 3）判定污染发生在哪一段

- `rawCmd` 已污染：说明输入捕获层（onKey/onData）或 pendingCommand 拼接层有问题
- `rawCmd` 干净但 `filtered` 脏：说明 `filterCommand` 清洗规则有 bug
- `cmd` 干净但弹框脏：说明存储或展示层被二次加工（应避免）

---

## 六、相关文件索引（高频改动点）

- `electron-vue3/src/components/EmbeddedPtyTerminal.vue`
  - `pendingCommand`、`submitPendingCommand`、`filterCommand`
  - `term.onKey` / `term.onData`（Win32 Input Mode 处理）
- `electron-vue3/src/components/EmbeddedTerminalWorkspace.vue`
  - `termCommandRegistry`（localStorage：`etw_cmd_history`）
  - 当前会话命令历史弹框与回填执行
- `electron-vue3/src/components/ProjectDetail.vue`
  - 全局命令历史弹框（读取 `globalThis.__termCommandRegistry__`）
- `electron-vue3/src/components/SimpleChatPanel.vue`、`electron-vue3/src/api.js`
  - 会话标题读取与 `generateSessionTitle` 调用（与“最近命令”不同链路，但可能在产品层面联动）

---

## 七、补全：Windows 本机 PTY 链路（go-local-proxy / ConPTY）

这一段是“终端真实 I/O 的来源”。它不直接负责“最近命令”的入库，但它会影响：

- 前端 xterm 收到的 **stdout/stderr 回显里包含哪些 ANSI/OSC 控制序列**
- Win32 Input Mode 下，前端发送的输入序列长什么样（以及为什么你会看到很多 `ESC[` 的东西）
- Electron 启动的进程是否有 Console（影响 `WriteConsoleInput` 能否工作）

### 1）整体路径（端到端）

- **前端（浏览器/Electron 渲染进程）**
  - `EmbeddedPtyTerminal.vue` 挂载 xterm 并建立到本机服务的 WebSocket
  - 发送事件：
    - `term_start`（带 `client_session_id`、`cols/rows`、`cwd`、`mode`）
    - `term_input`（输入字节做 base64）
    - `term_resize`、`term_close`
  - 接收事件：
    - `term_started`（回传 cwd，Windows 还会带 `windows_pty`）
    - `term_output`（stdout/stderr 字节 base64）
    - `term_error`、`term_exit`

- **本机服务（Go）**：`go-local-proxy`
  - HTTP：`/health`
  - WebSocket：`/pty`（终端）与 `/ws`（run 指令，和终端链路不同）

### 2）WebSocket 协议（/pty）

`go-local-proxy/pty_ws.go`

- **入站** `ptyWireIn`：
  - `event`: `term_start` / `term_input` / `term_resize` / `term_close`
  - `client_session_id`: 前端会话 id（用于复用同一 PTY）
  - `b64`: `term_input` 的原始字节 base64

- **出站** `ptyWireOut`：
  - `event`: `term_started` / `term_output` / `term_error` / `term_exit`
  - `b64`: `term_output` 的原始输出字节 base64（**这里就是你在 xterm 里看到的一切回显**）

### 3）会话管理与输出转发

`go-local-proxy/pty_sessions.go`

- `term_start` 会进入 `ptySessionMap.start(...)`
  - 同一个 `client_session_id` 若进程仍活着且 cwd 一致，会复用并只做 resize
  - 否则 stop 旧会话并 spawn 新 shell
  - 立即回 `term_started`

- stdout 读取 goroutine：
  - `sh.Stdout.Read(buf)` 读到 bytes 后：
    - 若 `pipeStdoutUTF16 == true`，会走 `transformPtyConsoleOutput`（管道回退时的 UTF-16 处理启发式）
    - 否则认为 **ConPTY 输出是 UTF-8**，原样转发
  - `term_output` = base64(out) 发回前端

> 重要约束：这里不应做“去 ANSI 控制码”的处理。xterm 需要 ANSI 才能正确渲染颜色/光标/清屏等。  
> 但这也意味着：如果这些控制序列不小心流入了“命令文本抽取”（前端的 `pendingCommand/filterCommand`），就会出现 `[[0]dir` 这类污染。

### 4）Windows 侧：ConPTY + `WriteConsoleInput` 为什么会失败/降级

你日志里的两行：

- `[conpty] AttachConsole failed: Access is denied. (may be GUI app, no console)`
- `[conpty] Opened CONIN$ directly, handle: ...`

对应实现：`go-local-proxy/internal/conpty/conpty.go`

- `ConPty.Start(...)` 在创建伪控制台进程后，会尝试拿到 console input 句柄用于 `WriteConsoleInput`：
  - 先 `AttachConsole(ATTACH_PARENT_PROCESS)` 试图附加到父进程的 console
    - Electron 启动的 GUI 进程常常 **没有 console** 或禁止附加，因而报 `Access is denied`
  - 失败则 fallback：直接 `windows.Open("CONIN$", ...)`

这影响的点：

- **Win32 Input Mode 的“特殊键注入”**（方向键、F1-F12、Home/End 等）在某些场景需要 `WriteConsoleInput` 才能稳定工作
- 如果 input handle 无效，`WriteConsoleInput` 会报 invalid handle（日志里有打印）

另外：`go-local-proxy/main.go` 的 `init()` 会调用 `AllocConsole()`，目的是：

- 给 GUI 启动的进程“分配一个 console”，让 `CONIN$`/`WriteConsoleInput` 有更大概率可用

### 5）Win32 Input Mode：谁启用、序列长什么样

这一块是“输入方向”：

- **启用序列**：`ESC[>4;1m`
- **禁用序列**：`ESC[>4m`

实现位置：

- `go-local-proxy/internal/conpty/conpty_stdin_transform.go`
  - `InputTransformer.Transform` 会识别启用/禁用序列，并做 `DEL(0x7f) -> BS(0x08)` 以适配 PSReadLine 的退格行为
- 前端 xterm 侧（`mountVscodeIntegratedTerminal(... win32InputMode ...)`）决定是否发送这些序列

当 Win32 Input Mode 启用时，**前端看到的按键数据**会更像控制序列（例如 `ESC[VK;SC;UC;KD;CS;RS_`），这也是为什么：

- `EmbeddedPtyTerminal.vue` 里必须在 `onKey/onData` 识别并还原 `UC` 才能拼回真正的命令文本
- 同时 `filterCommand()` 必须能完整剥离 ANSI/OSC/DCS 等控制序列，否则会把残片写入历史

### 6）明确边界：哪些地方可以改、哪些地方不要动

- **可以改**
  - `go-local-proxy`：会话复用、cwd 规范化、resize、UTF-16 回退启发式的条件判定（但要保留 debug 能力）
  - `conpty_stdin_transform`：输入转换（DEL→BS、启用禁用序列识别）
  - 前端 `EmbeddedPtyTerminal.vue`：命令捕获/清洗（只影响“最近命令/自动标题等元信息”）

- **不要动（或需要非常谨慎）**
  - 不要在 Go 输出转发链路里 strip ANSI：会破坏终端渲染
  - 不要用 stdout 回显去“猜命令并入库”：会把提示符/错误块/控制码混进历史

---

## 七、补全：Windows 本机 PTY 链路（go-local-proxy / ConPTY）

这一段是“终端真实 I/O 的来源”。它不直接负责“最近命令”的入库，但它会影响：

- 前端 xterm 收到的 **stdout/stderr 回显里包含哪些 ANSI/OSC 控制序列**
- Win32 Input Mode 下，前端发送的输入序列长什么样（以及为什么你会看到很多 `ESC[` 的东西）
- Electron 启动的进程是否有 Console（影响 `WriteConsoleInput` 能否工作）

### 1）整体路径（端到端）

- **前端（浏览器/Electron 渲染进程）**
  - `EmbeddedPtyTerminal.vue` 挂载 xterm 并建立到本机服务的 WebSocket
  - 发送事件：
    - `term_start`（带 `client_session_id`、`cols/rows`、`cwd`、`mode`）
    - `term_input`（输入字节做 base64）
    - `term_resize`、`term_close`
  - 接收事件：
    - `term_started`（回传 cwd，Windows 还会带 `windows_pty`）
    - `term_output`（stdout/stderr 字节 base64）
    - `term_error`、`term_exit`

- **本机服务（Go）**：`go-local-proxy`
  - HTTP：`/health`
  - WebSocket：`/pty`（终端）与 `/ws`（run 指令，和终端链路不同）

### 2）WebSocket 协议（/pty）

`go-local-proxy/pty_ws.go`

- **入站** `ptyWireIn`：
  - `event`: `term_start` / `term_input` / `term_resize` / `term_close`
  - `client_session_id`: 前端会话 id（用于复用同一 PTY）
  - `b64`: `term_input` 的原始字节 base64

- **出站** `ptyWireOut`：
  - `event`: `term_started` / `term_output` / `term_error` / `term_exit`
  - `b64`: `term_output` 的原始输出字节 base64（**这里就是你在 xterm 里看到的一切回显**）

### 3）会话管理与输出转发

`go-local-proxy/pty_sessions.go`

- `term_start` 会进入 `ptySessionMap.start(...)`
  - 同一个 `client_session_id` 若进程仍活着且 cwd 一致，会复用并只做 resize
  - 否则 stop 旧会话并 spawn 新 shell
  - 立即回 `term_started`

- stdout 读取 goroutine：
  - `sh.Stdout.Read(buf)` 读到 bytes 后：
    - 若 `pipeStdoutUTF16 == true`，会走 `transformPtyConsoleOutput`（管道回退时的 UTF-16 处理启发式）
    - 否则认为 **ConPTY 输出是 UTF-8**，原样转发
  - `term_output` = base64(out) 发回前端

> 重要约束：这里不应做“去 ANSI 控制码”的处理。xterm 需要 ANSI 才能正确渲染颜色/光标/清屏等。  
> 但这也意味着：如果这些控制序列不小心流入了“命令文本抽取”（前端的 `pendingCommand/filterCommand`），就会出现 `[[0]dir` 这类污染。

### 4）Windows 侧：ConPTY + `WriteConsoleInput` 为什么会失败/降级

你日志里的两行：

- `[conpty] AttachConsole failed: Access is denied. (may be GUI app, no console)`
- `[conpty] Opened CONIN$ directly, handle: ...`

对应实现：`go-local-proxy/internal/conpty/conpty.go`

- `ConPty.Start(...)` 在创建伪控制台进程后，会尝试拿到 console input 句柄用于 `WriteConsoleInput`：
  - 先 `AttachConsole(ATTACH_PARENT_PROCESS)` 试图附加到父进程的 console
    - Electron 启动的 GUI 进程常常 **没有 console** 或禁止附加，因而报 `Access is denied`
  - 失败则 fallback：直接 `windows.Open("CONIN$", ...)`

这影响的点：

- **Win32 Input Mode 的“特殊键注入”**（方向键、F1-F12、Home/End 等）在某些场景需要 `WriteConsoleInput` 才能稳定工作
- 如果 input handle 无效，`WriteConsoleInput` 会报 invalid handle（日志里有打印）

另外：`go-local-proxy/main.go` 的 `init()` 会调用 `AllocConsole()`，目的是：

- 给 GUI 启动的进程“分配一个 console”，让 `CONIN$`/`WriteConsoleInput` 有更大概率可用

### 5）Win32 Input Mode：谁启用、序列长什么样

这一块是“输入方向”：

- **启用序列**：`ESC[>4;1m`
- **禁用序列**：`ESC[>4m`

实现位置：

- `go-local-proxy/internal/conpty/conpty_stdin_transform.go`
  - `InputTransformer.Transform` 会识别启用/禁用序列，并做 `DEL(0x7f) -> BS(0x08)` 以适配 PSReadLine 的退格行为
- 前端 xterm 侧（`mountVscodeIntegratedTerminal(... win32InputMode ...)`）决定是否发送这些序列

当 Win32 Input Mode 启用时，**前端看到的按键数据**会更像控制序列（例如 `ESC[VK;SC;UC;KD;CS;RS_`），这也是为什么：

- `EmbeddedPtyTerminal.vue` 里必须在 `onKey/onData` 识别并还原 `UC` 才能拼回真正的命令文本
- 同时 `filterCommand()` 必须能完整剥离 ANSI/OSC/DCS 等控制序列，否则会把残片写入历史

### 6）明确边界：哪些地方可以改、哪些地方不要动

- **可以改**
  - `go-local-proxy`：会话复用、cwd 规范化、resize、UTF-16 回退启发式的条件判定（但要保留 debug 能力）
  - `conpty_stdin_transform`：输入转换（DEL→BS、启用禁用序列识别）
  - 前端 `EmbeddedPtyTerminal.vue`：命令捕获/清洗（只影响“最近命令/自动标题等元信息”）

- **不要动（或需要非常谨慎）**
  - 不要在 Go 输出转发链路里 strip ANSI：会破坏终端渲染
  - 不要用 stdout 回显去“猜命令并入库”：会把提示符/错误块/控制码混进历史


