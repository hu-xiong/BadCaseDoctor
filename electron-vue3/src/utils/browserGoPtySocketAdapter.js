/**
 * 浏览器（非 Electron）下将本机 go-local-proxy 的 /pty WebSocket 包装成与 socket.io 相近的接口，
 * 与 electronPtySocketAdapter 一致：term_start / term_input / term_output（含 b64）。
 */

import { getLocalShellProxyPtyWsUrl } from './localShellProxyClient.js'
import { badcasePtyLog } from './badcasePtyDebug.js'

/**
 * @returns {{ connected: boolean, id: string, on: Function, off: Function, emit: Function, close: Function }}
 */
export function createBrowserGoLocalPtySocket() {
  const handlers = new Map()
  let ws = null
  let closed = false
  /** 仅在曾成功 onopen 后为 true，避免连接失败时误触发 disconnect（界面显示「已断开」） */
  let opened = false

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

  function on(ev, fn) {
    if (typeof fn !== 'function') return
    if (!handlers.has(ev)) handlers.set(ev, [])
    const list = handlers.get(ev)
    if (list.includes(fn)) return
    list.push(fn)
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

  const sock = {
    connected: false,
    id: 'browser-go-local',
    on,
    off,
    emit(event, payload) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      const p = payload && typeof payload === 'object' ? payload : {}
      if (event === 'term_start') {
        badcasePtyLog('→ WS term_start', {
          client_session_id: p.client_session_id,
          cols: p.cols,
          rows: p.rows,
          cwdLen: String(p.cwd || '').length
        })
      } else if (event === 'term_resize') {
        badcasePtyLog('→ WS term_resize', { client_session_id: p.client_session_id, cols: p.cols, rows: p.rows })
      } else if (event === 'term_input') {
        badcasePtyLog('→ WS term_input', { client_session_id: p.client_session_id, b64Len: String(p.b64 || '').length })
      }
      ws.send(JSON.stringify({ event, ...p }))
    },
    close() {
      closed = true
      opened = false
      sock.connected = false
      try {
        if (ws) ws.close()
      } catch (_) {
        /* ignore */
      }
      ws = null
      handlers.clear()
    }
  }

  try {
    ws = new WebSocket(getLocalShellProxyPtyWsUrl())
  } catch (e) {
    console.error('[browserGoPty] WebSocket', e)
    queueMicrotask(() => fire('connect_error', e))
    return sock
  }

  ws.onopen = () => {
    if (closed) return
    opened = true
    sock.connected = true
    fire('connect')
  }
  ws.onerror = (err) => {
    fire('connect_error', err)
  }
  ws.onclose = (ev) => {
    sock.connected = false
    if (closed) {
      return
    }
    if (opened) {
      fire('disconnect')
    } else {
      const detail =
        typeof ev?.code === 'number'
          ? new Error(`WebSocket closed before open (code=${ev.code}${ev.reason ? ` ${ev.reason}` : ''})`)
          : new Error('WebSocket closed before open')
      fire('connect_error', detail)
    }
  }
  ws.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data)
      const name = m.event
      if (!name) return
      const { event: _e, ...rest } = m
      if (name === 'term_output') {
        badcasePtyLog('← WS term_output', {
          client_session_id: rest.client_session_id,
          b64Len: String(rest.b64 || '').length
        })
      } else {
        badcasePtyLog('← WS', name, rest)
      }
      fire(name, rest)
    } catch (e) {
      console.error('[browserGoPty] onmessage', e)
    }
  }

  return sock
}
