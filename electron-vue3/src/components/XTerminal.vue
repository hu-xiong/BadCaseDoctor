<template>
  <div class="terminal-container" ref="termRoot"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const termRoot = ref(null)
let term = null
let fit = null
let socket = null

onMounted(() => {
  term = new Terminal({
    cursorBlink: true,
    scrollback: 1000,
    tabStopWidth: 8,
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#d4d4d4',
      black: '#000000',
      red: '#cd3131',
      green: '#0dbc79',
      yellow: '#e5e510',
      blue: '#2472c8',
      magenta: '#bc3fbc',
      cyan: '#11a8cd',
      white: '#e5e5e5',
      brightBlack: '#666666',
      brightRed: '#f14c4c',
      brightGreen: '#23d18b',
      brightYellow: '#f5f543',
      brightBlue: '#3b8eea',
      brightMagenta: '#d670d6',
      brightCyan: '#29b8db',
      brightWhite: '#e5e5e5'
    }
  })
  
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termRoot.value)
  // 先 fit 一次
  fit.fit()

  // 建立到后端的 WebSocket（示例地址），后端负责启动 pty 并转发数据
  // 修改为实际的WebSocket地址
  socket = new WebSocket('ws://localhost:3000/pty')
  socket.binaryType = 'arraybuffer'

  // 将终端输入发送到后端
  term.onData(data => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(data)
    }
  })

  // 接收后端数据并写入终端
  socket.onmessage = (evt) => {
    // 支持二进制或字符串
    if (typeof evt.data === 'string') {
      term.write(evt.data)
    } else {
      const decoder = new TextDecoder()
      term.write(decoder.decode(evt.data))
    }
  }

  socket.onerror = (error) => {
    console.error('WebSocket error:', error)
    term.write('\r\n\x1b[31m❌ 连接Terminal服务失败\x1b[0m\r\n')
  }

  socket.onclose = () => {
    term.write('\r\n\x1b[33m⚠️  Terminal连接已断开\x1b[0m\r\n')
  }

  // 窗口大小变化时重新 fit
  const resizeHandler = () => {
    if (fit) {
      fit.fit()
      // 通知后端终端大小变化
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          type: 'resize',
          cols: term.cols,
          rows: term.rows
        }))
      }
    }
  }
  window.addEventListener('resize', resizeHandler)

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resizeHandler)
    if (socket) socket.close()
    if (term) term.dispose()
  })
})

onBeforeUnmount(() => {
  // 保证卸载时清理（mounted 内也已注册一次）
  if (socket) socket.close()
  if (term) term.dispose()
})
</script>

<style scoped>
.terminal-container {
  width: 100%;
  height: 100%;
  min-height: 300px; /* 按需调整 */
  background: #1e1e1e;
  padding: 10px;
  border-radius: 4px;
  overflow: hidden;
}

/* 确保xterm终端适应容器 */
.terminal-container :deep(.xterm) {
  height: 100%;
}

.terminal-container :deep(.xterm-viewport) {
  overflow-y: auto;
}
</style>

