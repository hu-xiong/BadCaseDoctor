const http = require('http')
const express = require('express')
const WebSocket = require('ws')
const pty = require('node-pty')

const app = express()
const server = http.createServer(app)
const wss = new WebSocket.Server({ server, path: '/pty' })

// 存储所有活动的终端会话
const sessions = new Map()

wss.on('connection', (ws) => {
  console.log('New terminal connection')
  
  // 选择 shell，根据平台
  const shell = process.platform === 'win32' ? 'powershell.exe' : process.env.SHELL || 'bash'
  const ptyProcess = pty.spawn(shell, [], {
    name: 'xterm-color',
    cols: 80,
    rows: 24,
    cwd: process.env.HOME || process.cwd(),
    env: process.env
  })

  // 生成会话ID
  const sessionId = Date.now().toString()
  sessions.set(sessionId, { pty: ptyProcess, ws })

  // pty -> ws (终端输出发送到前端)
  ptyProcess.on('data', (data) => {
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data)
      }
    } catch (e) {
      console.error('Error sending data to client:', e)
    }
  })

  // pty 进程退出
  ptyProcess.on('exit', (code, signal) => {
    console.log(`PTY process exited with code ${code}, signal ${signal}`)
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(`\r\n[Process exited with code ${code}]\r\n`)
        ws.close()
      }
    } catch (e) {
      // ignore
    }
    sessions.delete(sessionId)
  })

  // ws -> pty (前端输入发送到终端)
  ws.on('message', (msg) => {
    try {
      // 检查是否是JSON格式的控制消息
      if (typeof msg === 'string') {
        try {
          const data = JSON.parse(msg)
          if (data.type === 'resize') {
            // 调整终端大小
            ptyProcess.resize(data.cols, data.rows)
            return
          }
        } catch (e) {
          // 不是JSON，当作普通输入处理
        }
      }
      // msg 是来自前端的按键/输入
      ptyProcess.write(msg.toString())
    } catch (e) {
      console.error('Error writing to PTY:', e)
    }
  })

  ws.on('close', () => {
    console.log('Client disconnected')
    try {
      ptyProcess.kill()
    } catch (e) {
      console.error('Error killing PTY process:', e)
    }
    sessions.delete(sessionId)
  })

  ws.on('error', (error) => {
    console.error('WebSocket error:', error)
    try {
      ptyProcess.kill()
    } catch (e) {
      // ignore
    }
    sessions.delete(sessionId)
  })

  // 发送欢迎消息
  ws.send('\x1b[1;32mWelcome to BadCase Doctor Terminal\x1b[0m\r\n')
  ws.send(`Connected to ${shell}\r\n\r\n`)
})

// 健康检查端点
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    activeSessions: sessions.size,
    uptime: process.uptime()
  })
})

const PORT = process.env.TERMINAL_PORT || 3000
server.listen(PORT, () => {
  console.log(`✅ Terminal WebSocket server listening on ws://localhost:${PORT}/pty`)
  console.log(`📊 Health check available at http://localhost:${PORT}/health`)
})

// 优雅关闭
process.on('SIGINT', () => {
  console.log('\n⚠️  Shutting down terminal server...')
  // 关闭所有终端会话
  sessions.forEach((session) => {
    try {
      session.pty.kill()
      session.ws.close()
    } catch (e) {
      // ignore
    }
  })
  sessions.clear()
  server.close(() => {
    console.log('✅ Server closed')
    process.exit(0)
  })
})

