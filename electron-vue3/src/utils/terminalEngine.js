/**
 * 前端终端执行引擎
 * 提供本地命令执行能力，支持实时输出和进程管理
 */

class TerminalEngine {
  constructor() {
    this.processes = new Map()
    this.currentSession = 'default'
    this.isElectron = typeof window !== 'undefined' && window.require
    this.commandHistory = []
    this.historyIndex = -1
  }

  /**
   * 检查是否在Electron环境中
   */
  isElectronEnvironment() {
    return this.isElectron && window.require('electron')
  }

  /**
   * 检查是否在Node.js环境中
   */
  isNodeEnvironment() {
    return typeof process !== 'undefined' && process.versions && process.versions.node
  }

  /**
   * 执行命令 - 优先使用本地执行
   */
  async executeCommand(command, options = {}) {
    const {
      cwd = this.getCurrentWorkingDirectory(),
      timeout = 30000,
      sessionId = 'default',
      realTime = false
    } = options

    // 安全检查
    if (!this.isCommandSafe(command)) {
      throw new Error('危险命令已被阻止')
    }

    // 优先使用本地执行
    if (this.isElectronEnvironment()) {
      return await this.executeInElectron(command, { cwd, timeout, sessionId, realTime })
    } else if (this.isNodeEnvironment()) {
      return await this.executeInNode(command, { cwd, timeout, sessionId, realTime })
    } else {
      // 浏览器环境：尝试使用Web API或模拟执行
      return await this.executeInBrowser(command, { cwd, timeout, sessionId, realTime })
    }
  }

  /**
   * 在Electron环境中执行命令
   */
  async executeInElectron(command, options) {
    const { cwd, timeout, sessionId, realTime } = options
    
    try {
      const { spawn } = window.require('child_process')
      const { promisify } = window.require('util')
      
      return new Promise((resolve, reject) => {
        const child = spawn('sh', ['-c', command], {
          cwd: cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: true
        })

        let stdout = ''
        let stderr = ''
        let isResolved = false

        // 设置超时
        const timeoutId = setTimeout(() => {
          if (!isResolved) {
            isResolved = true
            child.kill('SIGTERM')
            reject(new Error('命令执行超时'))
          }
        }, timeout)

        // 存储进程
        this.processes.set(sessionId, {
          process: child,
          startTime: Date.now(),
          command: command
        })

        // 处理输出
        if (child.stdout) {
          child.stdout.on('data', (data) => {
            const output = data.toString()
            stdout += output
            if (realTime && this.onOutput) {
              this.onOutput(output, 'stdout')
            }
          })
        }

        if (child.stderr) {
          child.stderr.on('data', (data) => {
            const output = data.toString()
            stderr += output
            if (realTime && this.onOutput) {
              this.onOutput(output, 'stderr')
            }
          })
        }

        // 处理进程结束
        child.on('close', (code) => {
          if (!isResolved) {
            isResolved = true
            clearTimeout(timeoutId)
            this.processes.delete(sessionId)
            
            resolve({
              success: true,
              code: code,
              stdout: stdout.trim(),
              stderr: stderr.trim(),
              cwd: cwd
            })
          }
        })

        child.on('error', (error) => {
          if (!isResolved) {
            isResolved = true
            clearTimeout(timeoutId)
            this.processes.delete(sessionId)
            reject(error)
          }
        })
      })
    } catch (error) {
      throw new Error(`Electron执行失败: ${error.message}`)
    }
  }

  /**
   * 在Node.js环境中执行命令
   */
  async executeInNode(command, options) {
    const { cwd, timeout, sessionId, realTime } = options
    
    try {
      const { spawn } = require('child_process')
      
      return new Promise((resolve, reject) => {
        const child = spawn('sh', ['-c', command], {
          cwd: cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: true
        })

        let stdout = ''
        let stderr = ''
        let isResolved = false

        // 设置超时
        const timeoutId = setTimeout(() => {
          if (!isResolved) {
            isResolved = true
            child.kill('SIGTERM')
            reject(new Error('命令执行超时'))
          }
        }, timeout)

        // 存储进程
        this.processes.set(sessionId, {
          process: child,
          startTime: Date.now(),
          command: command
        })

        // 处理输出
        if (child.stdout) {
          child.stdout.on('data', (data) => {
            const output = data.toString()
            stdout += output
            if (realTime && this.onOutput) {
              this.onOutput(output, 'stdout')
            }
          })
        }

        if (child.stderr) {
          child.stderr.on('data', (data) => {
            const output = data.toString()
            stderr += output
            if (realTime && this.onOutput) {
              this.onOutput(output, 'stderr')
            }
          })
        }

        // 处理进程结束
        child.on('close', (code) => {
          if (!isResolved) {
            isResolved = true
            clearTimeout(timeoutId)
            this.processes.delete(sessionId)
            
            resolve({
              success: true,
              code: code,
              stdout: stdout.trim(),
              stderr: stderr.trim(),
              cwd: cwd
            })
          }
        })

        child.on('error', (error) => {
          if (!isResolved) {
            isResolved = true
            clearTimeout(timeoutId)
            this.processes.delete(sessionId)
            reject(error)
          }
        })
      })
    } catch (error) {
      throw new Error(`Node.js执行失败: ${error.message}`)
    }
  }

  /**
   * 在浏览器环境中执行命令（本地模拟）
   */
  async executeInBrowser(command, options) {
    const { cwd, timeout, sessionId, realTime } = options
    
    // 解析命令
    const [cmd, ...args] = command.trim().split(/\s+/)
    
    // 模拟常用命令
    switch (cmd) {
      case 'pwd':
        return {
          success: true,
          code: 0,
          stdout: cwd,
          stderr: '',
          cwd: cwd
        }
        
      case 'ls':
      case 'dir':
        const lsOutput = this.generateFileList(cwd)
        return {
          success: true,
          code: 0,
          stdout: lsOutput,
          stderr: '',
          cwd: cwd
        }
        
      case 'echo':
        const message = args.join(' ')
        return {
          success: true,
          code: 0,
          stdout: message,
          stderr: '',
          cwd: cwd
        }
        
      case 'date':
        return {
          success: true,
          code: 0,
          stdout: new Date().toString(),
          stderr: '',
          cwd: cwd
        }
        
      case 'whoami':
        return {
          success: true,
          code: 0,
          stdout: 'browser-user',
          stderr: '',
          cwd: cwd
        }
        
      case 'clear':
      case 'cls':
        return {
          success: true,
          code: 0,
          stdout: '',
          stderr: '',
          cwd: cwd
        }
        
      case 'cd':
        const newDir = args[0] || '~'
        let targetDir = cwd
        
        if (newDir === '~') {
          targetDir = '/Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor'
        } else if (newDir.startsWith('/')) {
          targetDir = newDir
        } else if (newDir === '..') {
          const parts = cwd.split('/')
          parts.pop()
          targetDir = parts.join('/') || '/'
        } else {
          targetDir = cwd.endsWith('/') ? cwd + newDir : cwd + '/' + newDir
        }
        
        return {
          success: true,
          code: 0,
          stdout: `Changed directory to: ${targetDir}`,
          stderr: '',
          cwd: targetDir
        }
        
      case 'cat':
        if (args.length === 0) {
          return {
            success: false,
            code: 1,
            stdout: '',
            stderr: 'cat: missing file operand',
            cwd: cwd
          }
        }
        return {
          success: true,
          code: 0,
          stdout: `Content of ${args[0]}:\nThis is a simulated file content.`,
          stderr: '',
          cwd: cwd
        }
        
      case 'mkdir':
        if (args.length === 0) {
          return {
            success: false,
            code: 1,
            stdout: '',
            stderr: 'mkdir: missing operand',
            cwd: cwd
          }
        }
        return {
          success: true,
          code: 0,
          stdout: `Directory '${args[0]}' created successfully`,
          stderr: '',
          cwd: cwd
        }
        
      case 'touch':
        if (args.length === 0) {
          return {
            success: false,
            code: 1,
            stdout: '',
            stderr: 'touch: missing file operand',
            cwd: cwd
          }
        }
        return {
          success: true,
          code: 0,
          stdout: `File '${args[0]}' created successfully`,
          stderr: '',
          cwd: cwd
        }
        
      case 'grep':
        if (args.length < 2) {
          return {
            success: false,
            code: 1,
            stdout: '',
            stderr: 'grep: missing pattern or file',
            cwd: cwd
          }
        }
        return {
          success: true,
          code: 0,
          stdout: `Found pattern "${args[0]}" in ${args[1]}`,
          stderr: '',
          cwd: cwd
        }
        
      case 'ps':
        return {
          success: true,
          code: 0,
          stdout: `PID TTY          TIME CMD
    1 ?        00:00:01 browser
    2 ?        00:00:00 terminal`,
          stderr: '',
          cwd: cwd
        }
        
      case 'top':
        return {
          success: true,
          code: 0,
          stdout: `top - ${new Date().toLocaleTimeString()}
Tasks: 2 total, 1 running, 1 sleeping
%Cpu(s): 5.2 us, 2.1 sy, 0.0 ni, 92.7 id
MiB Mem: 8192.0 total, 2048.0 free`,
          stderr: '',
          cwd: cwd
        }
        
      case 'help':
        return {
          success: true,
          code: 0,
          stdout: `可用命令:
  pwd     - 显示当前目录
  ls      - 列出文件
  echo    - 显示文本
  date    - 显示日期
  whoami  - 显示用户名
  clear   - 清屏
  cd      - 改变目录
  cat     - 显示文件内容
  mkdir   - 创建目录
  touch   - 创建文件
  grep    - 搜索文本
  ps      - 显示进程
  top     - 显示系统状态
  help    - 显示帮助`,
          stderr: '',
          cwd: cwd
        }
        
      default:
        return {
          success: false,
          code: 127,
          stdout: '',
          stderr: `bash: ${cmd}: command not found`,
          cwd: cwd
        }
    }
  }
  
  /**
   * 生成文件列表（浏览器环境模拟）
   */
  generateFileList(cwd) {
    const baseFiles = [
      'app.py',
      'config.py',
      'requirements.txt',
      'package.json',
      'README.md',
      'badcase_doctor.db',
      'static/',
      'templates/',
      'uploads/',
      'node_modules/',
      'src/',
      'dist/'
    ]
    
    // 根据目录调整文件列表
    if (cwd.includes('src')) {
      return 'App.vue\nmain.js\nrouter/\nstore/\ncomponents/\nassets/'
    } else if (cwd.includes('static')) {
      return 'css/\njs/\nimages/\nfonts/'
    } else if (cwd.includes('components')) {
      return 'Dashboard.vue\nLogin.vue\nProjectDetail.vue\nTerminal.vue\nChat.vue'
    }
    
    return baseFiles.join('\n')
  }

  /**
   * 终止进程
   */
  async killProcess(sessionId = 'default') {
    const processInfo = this.processes.get(sessionId)
    
    if (processInfo) {
      try {
        processInfo.process.kill('SIGTERM')
        this.processes.delete(sessionId)
        return { success: true, message: '进程已终止' }
      } catch (error) {
        return { success: false, error: error.message }
      }
    }

    // 如果没有找到进程，返回成功（可能已经结束）
    return { success: true, message: '进程不存在或已结束' }
  }

  /**
   * 获取进程状态
   */
  getProcessStatus(sessionId = 'default') {
    const processInfo = this.processes.get(sessionId)
    
    if (processInfo) {
      return {
        active: true,
        pid: processInfo.process.pid,
        command: processInfo.command,
        startTime: processInfo.startTime,
        running: !processInfo.process.killed
      }
    }

    return { active: false }
  }

  /**
   * 命令安全检查
   */
  isCommandSafe(command) {
    const dangerousCommands = [
      'rm -rf /',
      'shutdown',
      'reboot',
      'sudo rm -rf',
      'format',
      'del /f /s /q',
      'format c:',
      'mkfs',
      'dd if=/dev/zero'
    ]

    const lowerCommand = command.toLowerCase()
    return !dangerousCommands.some(dangerous => lowerCommand.includes(dangerous))
  }

  /**
   * 添加命令到历史记录
   */
  addToHistory(command) {
    if (command && command.trim()) {
      this.commandHistory.unshift(command.trim())
      // 限制历史记录数量
      if (this.commandHistory.length > 100) {
        this.commandHistory = this.commandHistory.slice(0, 100)
      }
      this.historyIndex = -1
    }
  }

  /**
   * 获取历史记录
   */
  getHistory() {
    return [...this.commandHistory]
  }

  /**
   * 获取历史记录中的上一个命令
   */
  getPreviousCommand() {
    if (this.commandHistory.length === 0) return ''
    
    if (this.historyIndex < this.commandHistory.length - 1) {
      this.historyIndex++
    }
    
    return this.commandHistory[this.historyIndex] || ''
  }

  /**
   * 获取历史记录中的下一个命令
   */
  getNextCommand() {
    if (this.historyIndex > 0) {
      this.historyIndex--
      return this.commandHistory[this.historyIndex]
    } else if (this.historyIndex === 0) {
      this.historyIndex = -1
      return ''
    }
    
    return ''
  }

  /**
   * 重置历史索引
   */
  resetHistoryIndex() {
    this.historyIndex = -1
  }

  /**
   * 设置实时输出回调
   */
  setOutputCallback(callback) {
    this.onOutput = callback
  }

  /**
   * 获取当前工作目录
   */
  getCurrentWorkingDirectory() {
    if (this.isElectronEnvironment() || this.isNodeEnvironment()) {
      try {
        return process.cwd()
      } catch (error) {
        return '/Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor'
      }
    }
    // 浏览器环境使用默认目录
    return '/Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor'
  }

  /**
   * 改变工作目录
   */
  changeWorkingDirectory(path) {
    if (this.isElectronEnvironment() || this.isNodeEnvironment()) {
      try {
        process.chdir(path)
        return true
      } catch (error) {
        return false
      }
    }
    return false
  }

  /**
   * 清理所有进程
   */
  cleanup() {
    for (const [sessionId, processInfo] of this.processes) {
      try {
        processInfo.process.kill('SIGTERM')
      } catch (error) {
        console.warn(`清理进程 ${sessionId} 失败:`, error)
      }
    }
    this.processes.clear()
  }
}

// 创建单例实例
const terminalEngine = new TerminalEngine()

export default terminalEngine
