/**
 * 经 go-local-proxy 在客户本机启动 Chrome（CDP）。
 * HTTP: http://127.0.0.1:8794/browser/start|stop|status
 * 或 WebSocket op: browser_start / browser_stop / browser_status
 */
import { getLocalShellProxyHealthUrl, getLocalShellProxyUrl } from './localShellProxyClient.js'

export function getLocalBrowserHttpBase() {
  try {
    const h = getLocalShellProxyHealthUrl()
    const u = new URL(h)
    u.pathname = '/browser'
    u.search = ''
    u.hash = ''
    return u.href.replace(/\/$/, '')
  } catch {
    return 'http://127.0.0.1:8794/browser'
  }
}

/** @returns {Promise<{ok:boolean,running:boolean,cdp_port?:number,cdp_http?:string,message?:string}>} */
export async function localBrowserStatus() {
  const r = await fetch(`${getLocalBrowserHttpBase()}/status`, { method: 'GET' })
  if (!r.ok) throw new Error(`browser status HTTP ${r.status}`)
  return r.json()
}

/**
 * @param {{ headless?: boolean, url?: string, cdpPort?: number }} [opts]
 */
export async function localBrowserStart(opts = {}) {
  const r = await fetch(`${getLocalBrowserHttpBase()}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      headless: !!opts.headless,
      url: opts.url || '',
      cdp_port: opts.cdpPort || 0
    })
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok || j.ok === false) {
    throw new Error(j.message || `browser start HTTP ${r.status}`)
  }
  return j
}

export async function localBrowserStop() {
  const r = await fetch(`${getLocalBrowserHttpBase()}/stop`, { method: 'POST' })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.message || `browser stop HTTP ${r.status}`)
  return j
}

/**
 * WebSocket 方式（与 shell run 同一 /ws）
 * @param {'browser_start'|'browser_stop'|'browser_status'} op
 * @param {object} [extra]
 */
export function localBrowserViaWs(op, extra = {}) {
  const url = getLocalShellProxyUrl()
  const id = `br-${Date.now()}`
  return new Promise((resolve, reject) => {
    let ws
    try {
      ws = new WebSocket(url)
    } catch (e) {
      reject(e)
      return
    }
    const to = window.setTimeout(() => {
      try {
        ws.close()
      } catch (_) {}
      reject(new Error('local browser ws timeout'))
    }, 20000)
    ws.onopen = () => {
      ws.send(JSON.stringify({ op, id, headless: false, ...extra }))
    }
    ws.onerror = () => {
      window.clearTimeout(to)
      reject(new Error('WebSocket error'))
    }
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data)
        if (m.id && m.id !== id) return
        if (m.op === 'error') {
          window.clearTimeout(to)
          ws.close()
          reject(new Error(m.message || 'browser error'))
          return
        }
        if (m.op === 'browser_ok' || m.op === 'browser_status') {
          window.clearTimeout(to)
          let data = m.data
          if (typeof data === 'string' && data.trim().startsWith('{')) {
            try {
              data = JSON.parse(data)
            } catch (_) {}
          }
          ws.close()
          resolve(data || { message: m.message, op: m.op })
        }
      } catch (e) {
        window.clearTimeout(to)
        reject(e)
      }
    }
  })
}
