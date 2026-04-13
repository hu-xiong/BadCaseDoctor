/**
 * 连接本机 go-local-proxy（WebSocket），与云端 Flask 分离；仅用于「本地执行命令」路径。
 * 默认：ws://127.0.0.1:8794/ws （与 go-local-proxy 默认 LISTEN 一致）
 *
 * 协议见仓库 go-local-proxy/main.go 注释。
 */

const DEFAULT_WS = 'ws://127.0.0.1:8794/ws'

export function getLocalShellProxyUrl() {
  const u = (import.meta.env.VITE_LOCAL_SHELL_PROXY_WS || '').trim()
  return u || DEFAULT_WS
}

/** HTTP 健康检查（与 go-local-proxy 的 /health 对应，供浏览器 fetch） */
/** 浏览器嵌入式终端：与本机 go-local-proxy 的 /pty WebSocket 对齐（term_* JSON 协议） */
export function getLocalShellProxyPtyWsUrl() {
  const o = (import.meta.env.VITE_LOCAL_SHELL_PROXY_PTY_WS || '').trim()
  if (o) return o
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    // 直连 127.0.0.1:8794：避免 Vite 代理 WebSocket 升级异常；勿用 hostname「localhost」——Windows 上常解析到 IPv6，而 go-local-proxy 默认只监听 127.0.0.1。
    return 'ws://127.0.0.1:8794/pty'
  }
  try {
    const u = new URL(getLocalShellProxyUrl())
    u.pathname = '/pty'
    u.search = ''
    u.hash = ''
    return u.href
  } catch {
    return 'ws://127.0.0.1:8794/pty'
  }
}

export function getLocalShellProxyHealthUrl() {
  const o = (import.meta.env.VITE_LOCAL_SHELL_PROXY_HTTP || '').trim()
  if (o) return o.replace(/\/$/, '') + '/health'
  // 开发模式直连 loopback（与 getLocalShellProxyPtyWsUrl 一致）。Vite 对 /__badcase_local_go 的 HTTP 代理在上游未就绪时
  // 常由 http-proxy 返回 500，易被误判为「健康检查逻辑坏了」；直连则失败为网络错误，且 go /health 已带 CORS *。
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    return 'http://127.0.0.1:8794/health'
  }
  try {
    const u = new URL(getLocalShellProxyUrl())
    u.protocol = u.protocol === 'wss:' ? 'https:' : 'http:'
    u.pathname = '/health'
    u.search = ''
    u.hash = ''
    return u.href
  } catch {
    return 'http://127.0.0.1:8794/health'
  }
}

/**
 * @param {string} cmd shell 一行或多行（Unix 下 bash -lc；Windows 下 cmd /C）
 * @param {{ cwd?: string, timeoutSec?: number, id?: string, confirmed?: boolean }} [opts]
 * @returns {Promise<{ exitCode: number, stdout: string, stderr: string }>}
 */
export function runViaLocalShellProxy(cmd, opts = {}) {
  const url = getLocalShellProxyUrl()
  const id = opts.id != null ? String(opts.id) : `run-${Date.now()}`
  return new Promise((resolve, reject) => {
    let ws
    try {
      ws = new WebSocket(url)
    } catch (e) {
      reject(e)
      return
    }
    let stdout = ''
    let stderr = ''
    const to = window.setTimeout(() => {
      try {
        ws.close()
      } catch (_) {
        /* ignore */
      }
      reject(new Error('local shell proxy timeout'))
    }, ((opts.timeoutSec || 120) + 15) * 1000)

    ws.onopen = () => {
      const runPayload = {
        op: 'run',
        id,
        cmd: String(cmd || ''),
        cwd: opts.cwd || '',
        timeout_sec: Number(opts.timeoutSec) > 0 ? Number(opts.timeoutSec) : 120
      }
      if (opts.confirmed === true) runPayload.confirmed = true
      ws.send(JSON.stringify(runPayload))
    }
    ws.onerror = () => {
      window.clearTimeout(to)
      reject(new Error('WebSocket error'))
    }
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data)
        if (m.op === 'chunk' && m.id === id) {
          if (m.stream === 'stderr') stderr += m.data || ''
          else stdout += m.data || ''
        } else if (m.op === 'done' && m.id === id) {
          window.clearTimeout(to)
          try {
            ws.close()
          } catch (_) {
            /* ignore */
          }
          resolve({ exitCode: Number(m.exit_code) || 0, stdout, stderr })
        } else if (m.op === 'confirm_required' && m.id === id) {
          window.clearTimeout(to)
          try {
            ws.close()
          } catch (_) {
            /* ignore */
          }
          const er = new Error(m.message || 'confirm_required')
          er.code = 'PROXY_CONFIRM_REQUIRED'
          er.reason = m.reason || 'bash_max_subcommands'
          reject(er)
        } else if (m.op === 'error' && (!m.id || m.id === id)) {
          window.clearTimeout(to)
          try {
            ws.close()
          } catch (_) {
            /* ignore */
          }
          reject(new Error(m.message || 'proxy error'))
        }
      } catch (e) {
        window.clearTimeout(to)
        reject(e)
      }
    }
  })
}

/**
 * 流式执行 + 可 cancel（需 go-local-proxy 支持 op: cancel）。
 * @param {string} cmd
 * @param {{
 *   cwd?: string,
 *   timeoutSec?: number,
 *   env?: Record<string, string>,
 *   id?: string,
 *   onChunk?: (stream: 'stdout'|'stderr', data: string) => void,
 *   abortSignal?: AbortSignal,
 *   confirmed?: boolean
 * }} [opts]
 * @returns {{ id: string, promise: Promise<{ exitCode: number, stdout: string, stderr: string, cancelled?: boolean }>, cancel: () => void }}
 */
export function runLocalShellProxyCommand(cmd, opts = {}) {
  const url = getLocalShellProxyUrl()
  const id = opts.id != null ? String(opts.id) : `run-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  const onChunk = typeof opts.onChunk === 'function' ? opts.onChunk : null
  const abortSignal = opts.abortSignal
  let ws
  let stdout = ''
  let stderr = ''
  const cancel = () => {
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: 'cancel', id }))
      }
    } catch (_) {
      /* ignore */
    }
  }
  const promise = new Promise((resolve, reject) => {
    if (abortSignal?.aborted) {
      const ab = new Error('Aborted')
      ab.name = 'AbortError'
      reject(ab)
      return
    }
    const onAbort = () => {
      cancel()
      try {
        ws?.close()
      } catch (_) {
        /* ignore */
      }
    }
    if (abortSignal) {
      abortSignal.addEventListener('abort', onAbort, { once: true })
    }
    const timeoutWrapMs = ((opts.timeoutSec || 120) + 20) * 1000
    const to = window.setTimeout(() => {
      cancel()
      done(reject, new Error('local shell proxy timeout'))
    }, timeoutWrapMs)
    const done = (fn, arg) => {
      window.clearTimeout(to)
      if (abortSignal) {
        try {
          abortSignal.removeEventListener('abort', onAbort)
        } catch (_) {
          /* ignore */
        }
      }
      try {
        ws?.close()
      } catch (_) {
        /* ignore */
      }
      fn(arg)
    }
    try {
      ws = new WebSocket(url)
    } catch (e) {
      window.clearTimeout(to)
      if (abortSignal) {
        try {
          abortSignal.removeEventListener('abort', onAbort)
        } catch (_) {
          /* ignore */
        }
      }
      reject(e)
      return
    }
    ws.onopen = () => {
      const runPayload = {
        op: 'run',
        id,
        cmd: String(cmd || ''),
        cwd: opts.cwd || '',
        timeout_sec: Number(opts.timeoutSec) > 0 ? Number(opts.timeoutSec) : 120,
        env: opts.env && typeof opts.env === 'object' ? opts.env : undefined
      }
      if (opts.confirmed === true) {
        runPayload.confirmed = true
      }
      ws.send(JSON.stringify(runPayload))
    }
    ws.onerror = () => done(reject, new Error('WebSocket error'))
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data)
        if (m.op === 'chunk' && m.id === id) {
          const stream = m.stream === 'stderr' ? 'stderr' : 'stdout'
          const piece = m.data || ''
          if (stream === 'stderr') stderr += piece
          else stdout += piece
          onChunk?.(stream, piece)
        } else if (m.op === 'done' && m.id === id) {
          done(resolve, {
            exitCode: Number(m.exit_code) || 0,
            stdout,
            stderr
          })
        } else if (m.op === 'cancelled' && m.id === id) {
          done(resolve, {
            exitCode: -1,
            stdout,
            stderr,
            cancelled: true
          })
        } else if (m.op === 'confirm_required' && m.id === id) {
          const er = new Error(m.message || 'confirm_required')
          er.code = 'PROXY_CONFIRM_REQUIRED'
          er.reason = m.reason || 'bash_max_subcommands'
          done(reject, er)
        } else if (m.op === 'error' && (!m.id || m.id === id)) {
          done(reject, new Error(m.message || 'proxy error'))
        }
      } catch (e) {
        done(reject, e)
      }
    }
  })
  return { id, promise, cancel }
}
