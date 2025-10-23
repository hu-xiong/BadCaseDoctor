# 前端终端执行引擎使用说明

## 概述

前端终端执行引擎是一个完全本地化的命令执行系统，能够根据运行环境自动选择最佳的执行方式：

1. **Electron环境**: 使用本地Node.js子进程执行
2. **Node.js环境**: 直接使用Node.js子进程执行  
3. **浏览器环境**: 使用本地命令模拟执行

## 核心特性

### 智能环境检测
- 自动检测运行环境（Electron/Node.js/浏览器）
- 根据环境选择最优执行策略
- 完全本地化执行，无需网络依赖

### 安全防护
- 危险命令黑名单过滤
- 命令超时保护
- 进程生命周期管理

### 实时交互
- 支持实时输出流
- 命令历史记录
- 自动补全支持
- 多行命令输入

## 使用方法

### 基本用法

```javascript
import terminalEngine from './utils/terminalEngine.js'

// 执行简单命令
const result = await terminalEngine.executeCommand('ls -la', {
  cwd: '/path/to/directory',
  timeout: 30000,
  sessionId: 'my-session'
})

console.log(result.stdout)
console.log(result.stderr)
console.log(result.code)
```

### 实时输出

```javascript
// 设置实时输出回调
terminalEngine.setOutputCallback((output, type) => {
  console.log(`[${type}] ${output}`)
})

// 执行命令并接收实时输出
await terminalEngine.executeCommand('ping google.com', {
  realTime: true
})
```

### 进程管理

```javascript
// 终止进程
await terminalEngine.killProcess('my-session')

// 获取进程状态
const status = terminalEngine.getProcessStatus('my-session')
console.log(status.active) // true/false
```

### 命令历史

```javascript
// 添加命令到历史
terminalEngine.addToHistory('ls -la')

// 获取历史记录
const history = terminalEngine.getHistory()

// 导航历史
const prevCmd = terminalEngine.getPreviousCommand()
const nextCmd = terminalEngine.getNextCommand()
```

## Vue组件集成

### Terminal组件

```vue
<template>
  <Terminal 
    :initial-working-dir="/path/to/directory"
    :session-id="unique-session-id"
  />
</template>

<script>
import Terminal from './components/Terminal.vue'

export default {
  components: {
    Terminal
  }
}
</script>
```

### 自定义集成

```vue
<script>
import terminalEngine from './utils/terminalEngine.js'

export default {
  setup() {
    const executeCommand = async (command) => {
      try {
        const result = await terminalEngine.executeCommand(command)
        return result
      } catch (error) {
        console.error('命令执行失败:', error)
      }
    }
    
    return {
      executeCommand
    }
  }
}
</script>
```

## 配置选项

### executeCommand 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| command | string | - | 要执行的命令 |
| cwd | string | process.cwd() | 工作目录 |
| timeout | number | 30000 | 超时时间(毫秒) |
| sessionId | string | 'default' | 会话ID |
| realTime | boolean | false | 是否启用实时输出 |

### 环境变量

- `NODE_ENV`: 环境模式 (development/production)
- `ELECTRON_IS_DEV`: Electron开发模式标识

## 安全考虑

### 危险命令过滤

系统会自动阻止以下类型的危险命令：
- `rm -rf /` - 删除根目录
- `shutdown` - 系统关机
- `reboot` - 系统重启
- `sudo rm -rf` - 管理员删除命令
- `format` - 格式化命令
- `mkfs` - 文件系统创建
- `dd if=/dev/zero` - 磁盘清零

### 超时保护

所有命令都有超时保护，默认30秒。超时后会自动终止进程。

### 进程隔离

每个会话的进程都是独立的，可以单独管理和终止。

## 错误处理

### 常见错误类型

1. **命令执行失败**: 命令本身返回非零退出码
2. **超时错误**: 命令执行时间超过限制
3. **权限错误**: 没有执行权限
4. **路径错误**: 工作目录不存在
5. **安全错误**: 命令被安全策略阻止

### 错误处理示例

```javascript
try {
  const result = await terminalEngine.executeCommand('ls /nonexistent')
} catch (error) {
  if (error.message.includes('超时')) {
    console.log('命令执行超时')
  } else if (error.message.includes('权限')) {
    console.log('权限不足')
  } else {
    console.log('执行失败:', error.message)
  }
}
```

## 性能优化

### 进程复用

对于长时间运行的命令，建议使用会话ID来管理进程生命周期。

### 输出缓冲

实时输出模式下，系统会自动缓冲输出以提高性能。

### 内存管理

系统会自动清理已结束的进程，防止内存泄漏。

## 调试和测试

### 测试页面

访问 `/terminal-test` 路由可以打开终端测试页面，用于验证功能。

### 调试模式

在开发环境中，终端引擎会输出详细的调试信息。

### 日志记录

所有命令执行都会记录到控制台，便于调试。

## 扩展开发

### 添加新的执行环境

```javascript
// 在 terminalEngine.js 中添加新的环境检测
isCustomEnvironment() {
  return typeof window !== 'undefined' && window.customAPI
}

// 添加对应的执行方法
async executeInCustom(command, options) {
  // 自定义执行逻辑
}
```

### 自定义安全策略

```javascript
// 扩展危险命令列表
const customDangerousCommands = [
  'custom-dangerous-command'
]

// 在 isCommandSafe 方法中添加检查
```

## 常见问题

### Q: 浏览器环境支持哪些命令？
A: 浏览器环境支持常用命令的本地模拟，包括pwd、ls、echo、date、whoami、clear、cd、help等。

### Q: 如何启用实时输出？
A: 设置 `realTime: true` 并配置输出回调函数。

### Q: 命令历史记录在哪里存储？
A: 命令历史记录存储在内存中，页面刷新后会丢失。

### Q: 如何自定义工作目录？
A: 通过 `cwd` 参数指定，或使用 `changeWorkingDirectory` 方法。

### Q: 支持哪些操作系统？
A: 支持所有Node.js支持的操作系统，包括Windows、macOS、Linux。
