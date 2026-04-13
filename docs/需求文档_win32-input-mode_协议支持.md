# 需求文档：go-local-proxy Win32-Input-Mode 协议支持

**创建时间**：2026-04-13
**状态**：待开发
**优先级**：P0（核心功能）

---

## 1. 背景与目标

### 1.1 问题描述

当前嵌入式终端（EmbeddedPtyTerminal）通过 WebSocket 与 go-local-proxy 通信，存在以下问题：

| 问题 | 当前方案 | 问题 |
|------|---------|------|
| 退格键删除 | 前端 DEL→BS 转换 | 勉强工作，不够优雅 |
| 光标回填（reflow） | xterm.js reflowCursorLine | 可能不工作 |
| Delete 键 | 未处理 | Delete vs Backspace 混淆 |
| 修饰键组合 | 基础处理 | Ctrl+方向键等无法传输 |
| Alt 键序列 | 未处理 | Alt+F4 等被浏览器捕获 |

### 1.2 根本原因

当前方案依赖前端拦截和转换，无法正确处理 Windows ConPTY 的增强输入模式。

### 1.3 解决方案

在 go-local-proxy 实现 win32-input-mode 协议支持，让 PTY 层面的输入处理回归正确架构：

```
当前：xterm.js → 前端拦截 → WS → go-local-proxy → ConPTY
     ↑
     问题出在这里（前端转换不完整）

目标：xterm.js → WS → go-local-proxy（启用win32-input-mode）→ ConPTY
                                                              ↑
                                                    ConPTY 返回详细按键信息
```

---

## 2. Win32-Input-Mode 协议详解

### 2.1 协议概述

Win32-input-mode 是 Windows Console Host (ConPTY) 引入的增强键盘输入协议，让 Windows 终端能发送类似 Unix 终端的详细按键信息。

### 2.2 启用/禁用序列

```
ESC[>4;1m    # 启用 win32-input-mode
ESC[>4m      # 禁用 win32-input-mode，恢复默认模式
```

### 2.3 按键编码格式（VT200/VT400 CSI 序列）

```
CSI 按键码 ; 修饰符 ~
```

**修饰符编码**：
| 修饰键 | 编码值 |
|--------|--------|
| Shift | 2 |
| Alt | 3 |
| Ctrl | 5 |
| Shift+Alt | 4 |
| Shift+Ctrl | 6 |
| Alt+Ctrl | 7 |
| Shift+Alt+Ctrl | 8 |

### 2.4 常见按键序列对照

| 按键 | 普通模式 | win32-input-mode |
|------|---------|------------------|
| Backspace | 0x7F 或 0x08 | 0x7F (DEL) |
| Delete | `ESC[3~` | `CSI 3~` |
| Shift+Delete | `ESC[3~` | `CSI 3;2~` |
| Ctrl+Delete | `ESC[3~` | `CSI 3;5~` |
| Ctrl+右方向键 | 无法传输 | `CSI 1;5C` |
| Ctrl+左方向键 | 无法传输 | `CSI 1;5D` |
| Home | `ESC[H` | `CSI 1H` |
| End | `ESC[F` | `CSI 1F` |
| F1-F12 | `ESCOP` 等 | `CSI 1P` 等 |

### 2.5 INPUT_RECORD 到 VT 序列的转换

ConPTY 使用 Windows 的 `INPUT_RECORD` 结构传输按键信息：

```go
type INPUT_RECORD struct {
    EventType uint16  // KEY_EVENT = 0x0001
    Event     [16]byte
}

type KEY_EVENT_RECORD struct {
    bKeyDown          int32
    wRepeatCount      uint16
    wVirtualKeyCode    uint16
    wVirtualScanCode   uint16
    UnicodeChar       uint16
    dwControlKeyState uint32
}
```

**转换规则**：
1. 根据 `wVirtualKeyCode` 确定基础按键码
2. 根据 `dwControlKeyState` 确定修饰符
3. 组合生成 CSI 序列

---

## 3. 技术实现方案

### 3.1 go-local-proxy 改动

#### 3.1.1 目录结构

```
go-local-proxy/
├── internal/
│   ├── conpty/
│   │   ├── conpty.go          # 现有 ConPTY 封装
│   │   └── conpty_input.go    # 【新增】win32-input-mode 解析
│   └── pty/
│       └── pty_session.go     # 【修改】集成 win32-input-mode
```

#### 3.1.2 核心接口设计

```go
// conpty_input.go

// Win32InputModeHandler 处理 win32-input-mode 协议
type Win32InputModeHandler struct {
    enabled     bool
    ptyRead     io.Reader
    ptyWrite    io.Writer
    // 内部状态
    modifierState uint32
}

// 启用序列检测
var enableSequence = []byte{0x1B, '[', '>', '4', ';', '1', 'm'}
var disableSequence = []byte{0x1B, '[', '>', '4', 'm'}

// Read 实现 io.Reader，处理 ConPTY 输出的增强按键序列
func (h *Win32InputModeHandler) Read(p []byte) (n int, err error)

// ParseInputRecord 解析 Windows INPUT_RECORD
func (h *Win32InputModeHandler) ParseInputRecord(record []byte) ([]byte, error)

// VirtualKeyCodeToCSI 根据虚拟键码转换为 CSI 序列
func VirtualKeyCodeToCSI(vk uint16, modifiers uint32) []byte
```

#### 3.1.3 修饰键状态常量

```go
const (
    CAPSLOCK_ON         = 0x0080
    ENHANCED_KEY        = 0x0100
    LEFT_ALT_PRESSED    = 0x0200
    LEFT_CTRL_PRESSED   = 0x0400
    LEFT_SHIFT_PRESSED  = 0x0800
    RIGHT_ALT_PRESSED   = 0x1000
    RIGHT_CTRL_PRESSED  = 0x2000
    RIGHT_SHIFT_PRESSED = 0x4000
)
```

#### 3.1.4 虚拟键码映射表（部分）

```go
var virtualKeyCodeToCSI = map[uint16]uint8{
    0x08: 0x30, // BACKSPACE
    0x09: 0x33, // TAB
    0x0D: 0x34, // ENTER
    0x1B: 0x01, // ESCAPE
    0x21: 0x35, // PAGE UP
    0x22: 0x36, // PAGE DOWN
    0x23: 0x37, // END
    0x24: 0x31, // HOME
    0x25: 0x34, // LEFT
    0x26: 0x35, // UP
    0x27: 0x36, // RIGHT
    0x28: 0x33, // DOWN
    0x2E: 0x33, // DELETE (VK_DELETE)
    // Function keys F1-F12...
}
```

### 3.2 WebSocket 协议改动

#### 3.2.1 消息类型

现有消息类型：
- `term_input` - 终端输入
- `term_output` - 终端输出
- `term_resize` - 终端大小调整

**无需新增消息类型** - win32-input-mode 的数据通过现有的 `term_output` 通道返回。

#### 3.2.2 数据流

```
用户按 Ctrl+右方向键
        ↓
xterm.js 发送数据（或不发送，取决于配置）
        ↓
go-local-proxy ConPTY 接收到 INPUT_RECORD
        ↓
Win32InputModeHandler 解析并转换为 CSI 序列
        ↓
通过 term_output 发送到前端
        ↓
前端 xterm.js 渲染并处理
```

### 3.3 前端改动（EmbeddedPtyTerminal.vue）

#### 3.3.1 xterm.js 配置

```javascript
// mountVscodeIntegratedTerminal 调用时
{
    win32InputMode: true  // 启用 win32-input-mode
}
```

#### 3.3.2 移除前端拦截逻辑

**删除**：
- `attachCustomKeyEventHandler` 中的退格拦截
- `emitPtyTermInput` 中的 DEL→BS 转换
- `writePtyStdoutTransformed` 中的 `localBackspacePending` 处理

**保留**（仍需前端处理）：
- Ctrl+C/V 复制粘贴快捷键
- Find 快捷键
- Alt+F4 等浏览器快捷键的处理

---

## 4. 实现步骤

### 阶段一：基础框架（1-2天）

- [ ] 创建 `go-local-proxy/internal/conpty/conpty_input.go`
- [ ] 实现 `Win32InputModeHandler` 结构体
- [ ] 实现启用/禁用序列检测
- [ ] 编写单元测试

### 阶段二：INPUT_RECORD 解析（2-3天）

- [ ] 实现 `ParseInputRecord` 函数
- [ ] 实现 `VirtualKeyCodeToCSI` 映射
- [ ] 实现修饰键状态解析
- [ ] 集成到 ConPTY Read 流程
- [ ] 测试常见按键（方向键、Home/End、F1-F12）

### 阶段三：集成与调优（1-2天）

- [ ] 前端移除 DEL→BS 转换逻辑
- [ ] 启用 `win32InputMode: true`
- [ ] 测试 PowerShell/PSReadLine 交互
- [ ] 测试 vim/nano 等编辑器
- [ ] 性能测试

### 阶段四：边界情况处理（1天）

- [ ] 超长序列截断
- [ ] 错误恢复
- [ ] 内存泄漏检测
- [ ] 日志完善

---

## 5. 测试计划

### 5.1 单元测试

```go
func TestEnableSequence(t *testing.T) { /* ... */ }
func TestDisableSequence(t *testing.T) { /* ... */ }
func TestVirtualKeyCodeToCSI(t *testing.T) { /* ... */ }
func TestModifierCombinations(t *testing.T) { /* ... */ }
```

### 5.2 集成测试

| 测试场景 | 预期结果 |
|---------|---------|
| 按 Backspace | 正确删除字符 |
| 按 Delete | 删除光标后字符 |
| Ctrl+左/右 | 按单词移动光标 |
| Shift+方向键 | 选择文本 |
| Ctrl+C/V | 复制粘贴 |
| Alt+F4 | 关闭窗口（或忽略） |
| PowerShell 命令行 | PSReadLine 正确响应 |
| vim 编辑模式 | 所有按键正确处理 |

### 5.3 回归测试

- [ ] 现有退格功能不受影响
- [ ] 终端输出渲染正常
- [ ] WebSocket 连接稳定
- [ ] 无内存泄漏

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| ConPTY INPUT_RECORD 格式变化 | 低 | 高 | 锁定 Windows SDK 版本 |
| 性能开销 | 中 | 中 | 异步处理，避免阻塞 |
| 兼容性：旧版 Windows | 低 | 中 | 添加版本检测 |
| 前端 xterm.js 不支持 | 低 | 高 | 测试多个 xterm.js 版本 |

---

## 7. 参考资料

- [xterm.js win32-input-mode 支持 Issue #2357](https://github.com/xtermjs/xterm.js/issues/2357)
- [Windows Console INPUT_RECORD 文档](https://docs.microsoft.com/en-us/windows/console/input-record-str)
- [VT100/VT400 CSI 序列参考](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html)
- [VSCode 终端实现参考](../electron-vue3/third_party/vscode-src/workbench/contrib/terminal/)

---

## 8. 更新日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-13 | v0.1 | 初始文档创建 |
