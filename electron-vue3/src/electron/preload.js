/**
 * Electron Preload Script
 * 暴露 PTY IPC 接口给渲染进程
 */
const { contextBridge, ipcRenderer } = require('electron')

// 检测是否在 Electron 环境中
const isElectron = true

// 暴露 PTY API
contextBridge.exposeInMainWorld('electronPty', {
  isElectron: () => isElectron,
  
  // 启动 PTY
  start: (sessionId, options) => {
    return new Promise((resolve, reject) => {
      const { cols, rows, cwd } = options || {}
      
      // 监听启动成功
      const onStarted = (_, data) => {
        if (data.sessionId === sessionId) {
          ipcRenderer.removeListener('pty-started', onStarted)
          ipcRenderer.removeListener('pty-error', onError)
          resolve(data)
        }
      }
      
      // 监听错误
      const onError = (_, data) => {
        if (data.sessionId === sessionId) {
          ipcRenderer.removeListener('pty-started', onStarted)
          ipcRenderer.removeListener('pty-error', onError)
          reject(new Error(data.message))
        }
      }
      
      ipcRenderer.on('pty-started', onStarted)
      ipcRenderer.on('pty-error', onError)
      ipcRenderer.send('pty-start', { sessionId, cols, rows, cwd })
    })
  },
  
  // 输入数据：string 或 Uint8Array（与 node-pty 二进制 stdin 对齐，勿仅走 UTF-16 字符串）
  write: (sessionId, data) => {
    ipcRenderer.send('pty-input', { sessionId, data })
  },
  
  // 调整大小
  resize: (sessionId, cols, rows) => {
    ipcRenderer.send('pty-resize', { sessionId, cols, rows })
  },
  
  // 关闭 PTY
  close: (sessionId) => {
    ipcRenderer.send('pty-close', { sessionId })
  },
  
  // 监听输出
  onOutput: (callback) => {
    const handler = (_, data) => callback(data)
    ipcRenderer.on('pty-output', handler)
    return () => ipcRenderer.removeListener('pty-output', handler)
  },
  
  // 监听退出
  onExit: (callback) => {
    const handler = (_, data) => callback(data)
    ipcRenderer.on('pty-exit', handler)
    return () => ipcRenderer.removeListener('pty-exit', handler)
  }
})

contextBridge.exposeInMainWorld('badcaseProtocol', {
  registerWindows: (exePath, scheme) =>
    ipcRenderer.invoke('badcase-register-local-proxy-protocol', exePath, scheme || 'badcase-local-proxy'),
  pickProxyExe: () => ipcRenderer.invoke('badcase-pick-proxy-exe')
})

contextBridge.exposeInMainWorld('electronTerminalAgent', {
  execOnce: (payload) => ipcRenderer.invoke('terminal-exec-once', payload),
  cancel: (requestId) => ipcRenderer.send('terminal-exec-cancel', requestId),
  cancelAll: () => ipcRenderer.send('terminal-exec-cancel-all'),
  checkWorkspaceCwd: (targetCwd) => ipcRenderer.invoke('terminal-check-workspace-cwd', targetCwd),
  getEmbeddedTerminalDefaultCwd: () => ipcRenderer.invoke('embedded-terminal-default-cwd')
})

contextBridge.exposeInMainWorld('badcaseLocalProxy', {
  /**
   * @param {string} filename 文件名（用于无 targetPath 时另存为对话框的默认名）
   * @param {ArrayBuffer} arrayBuffer
   * @param {string} [targetPath] 若传入完整目标路径则直接写入，不再弹出系统另存为
   */
  saveProxyBlob: (filename, arrayBuffer, targetPath) =>
    ipcRenderer.invoke('badcase-save-local-proxy', { filename, arrayBuffer, targetPath })
})
