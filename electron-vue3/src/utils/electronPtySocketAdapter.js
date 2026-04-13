/**
 * 将 Electron preload 暴露的 window.electronPty 包装成与 socket.io 相近的接口，
 * 供 EmbeddedPtyTerminal 复用同一套 term_start / term_input / term_output 逻辑（本地 shell 不经过 Python）。
 */

import { badcasePtyLog } from './badcasePtyDebug.js'

function utf8StringToB64(str) {
  const u8 = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < u8.length; i += 1) binary += String.fromCharCode(u8[i])
  return btoa(binary)
}

export function isElectronPtyAvailable() {
  return (
    typeof window !== 'undefined' &&
    window.electronPty &&
    typeof window.electronPty.start === 'function'
  )
}

/**
 * 是否在 Electron 壳内运行（终端设计为 node-pty / Node，不依赖 go-local-proxy）。
 * 与 {@link isElectronPtyAvailable} 不同：node-pty 未安装时仍为 true。
 */
export function isElectronShell() {
  if (typeof window === 'undefined') return false
  if (window.electronPty && typeof window.electronPty.isElectron === 'function') {
    try {
      return window.electronPty.isElectron() === true
    } catch {
      return true
    }
  }
  return typeof navigator !== 'undefined' && /Electron/i.test(navigator.userAgent || '')
}

/**
 * @returns {{ connected: boolean, id: string, on: Function, off: Function, emit: Function, close: Function }}
 */
export function createElectronLocalPtySocket() {
  const ep = window.electronPty
  const handlers = new Map()
  let outputUnsub = null
  let exitUnsub = null

  function on(ev, fn) {
    if (typeof fn !== 'function') return
    if (!handlers.has(ev)) handlers.set(ev, [])
    handlers.get(ev).push(fn)
    if (ev === 'connect') {
      queueMicrotask(() => {
        if (sock.connected) {
          try {
            fn()
          } catch (e) {
            console.error(e)
          }
        }
      })
    }
  }

  function off(ev, fn) {
    if (fn === undefined) {
      handlers.delete(ev)
      return
    }
    const list = handlers.get(ev)
    if (!list || typeof fn !== 'function') return
    const i = list.indexOf(fn)
    if (i >= 0) list.splice(i, 1)
  }

  function fire(ev, payload) {
    const list = handlers.get(ev) || []
    for (const fn of [...list]) {
      try {
        fn(payload)
      } catch (e) {
        console.error(e)
      }
    }
  }

  function ensureIpcBridges() {
    if (outputUnsub) return
    outputUnsub = ep.onOutput(({ sessionId, data }) => {
      const chunk = typeof data === 'string' ? data : String(data ?? '')
      const b64 = utf8StringToB64(chunk)
      badcasePtyLog('← electron term_output', { sessionId, utf8Len: chunk.length, b64Len: b64.length })
      fire('term_output', { client_session_id: sessionId, b64 })
    })
    exitUnsub = ep.onExit(({ sessionId }) => {
      fire('term_exit', { client_session_id: sessionId })
    })
  }

  const sock = {
    connected: false,
    id: 'electron-local',
    on,
    off,
    emit(event, payload) {
      if (event === 'term_start') {
        const { client_session_id, cols, rows, cwd, mode } = payload || {}
        badcasePtyLog('→ electron term_start', { client_session_id, cols, rows, cwdLen: String(cwd || '').length })
        if (mode && mode !== 'local') {
          fire('term_error', {
            client_session_id,
            message: 'Electron 桌面端仅支持本地 shell；浏览器内 SSH 已移除。'
          })
          return
        }
        ensureIpcBridges()
        ep.start(client_session_id, {
          cols: cols || 80,
          rows: rows || 24,
          cwd: (cwd && String(cwd).trim()) || undefined
        })
          .then((data) => {
            const d = data && typeof data === 'object' ? data : {}
            fire('term_started', {
              client_session_id,
              pid: d.pid,
              shell: d.shell,
              cwd: d.cwd,
              ...(d.windows_pty ? { windows_pty: d.windows_pty } : {})
            })
          })
          .catch((e) => {
            fire('term_error', {
              client_session_id,
              message: e && e.message ? e.message : String(e)
            })
          })
        return
      }
      if (event === 'term_input') {
        const { b64, client_session_id } = payload || {}
        if (!client_session_id || !b64) return
        try {
          const bin = atob(b64)
          const bytes = new Uint8Array(bin.length)
          for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i)
          ep.write(client_session_id, bytes)
        } catch (e) {
          console.error('[electronPty] term_input', e)
        }
        return
      }
      if (event === 'term_resize') {
        const { client_session_id, cols, rows } = payload || {}
        if (client_session_id && cols && rows) {
          try {
            ep.resize(client_session_id, cols, rows)
          } catch (e) {
            console.error('[electronPty] term_resize', e)
          }
        }
        return
      }
      if (event === 'term_close') {
        const { client_session_id } = payload || {}
        if (client_session_id) {
          try {
            ep.close(client_session_id)
          } catch (e) {
            console.error('[electronPty] term_close', e)
          }
        }
      }
    },
    close() {
      sock.connected = false
      try {
        if (outputUnsub) outputUnsub()
      } catch (_) {
        /* ignore */
      }
      try {
        if (exitUnsub) exitUnsub()
      } catch (_) {
        /* ignore */
      }
      outputUnsub = null
      exitUnsub = null
      handlers.clear()
    }
  }

  queueMicrotask(() => {
    sock.connected = true
    fire('connect')
  })

  return sock
}
