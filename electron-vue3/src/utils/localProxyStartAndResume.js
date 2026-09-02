/**
 * 安装本地代理后的唤起 / 终端启动，以及代理上线后重试 browser_local 卡片。
 */
import { detectClientOS, readExplicitProxyExePath, readProxyInstallRecord } from './localProxyInstall.js'
import { tryWakeThenPing, tryWakeViaUrlScheme } from './localProxyWake.js'

/**
 * @returns {string} 优先用户确认路径，其次安装记录推断路径
 */
export function resolveInstalledLocalProxyPath() {
  const explicit = String(readExplicitProxyExePath() || '').trim()
  if (explicit) return explicit
  const rec = readProxyInstallRecord()
  const inferred = rec && typeof rec.inferredFullPath === 'string' ? rec.inferredFullPath.trim() : ''
  return inferred
}

/**
 * @param {string} exePath
 * @returns {string}
 */
export function buildLocalProxyStartCommand(exePath) {
  const p = String(exePath || '').trim()
  if (!p) return ''
  const os = detectClientOS()
  if (os === 'win') {
    // PowerShell：后台启动，避免阻塞嵌入终端会话
    return `Start-Process -FilePath ${JSON.stringify(p)}`
  }
  const q = JSON.stringify(p)
  return `chmod +x ${q} 2>/dev/null; nohup ${q} >/tmp/badcase-local-proxy.log 2>&1 &`
}

/**
 * 尝试让本机代理上线：协议唤醒 →（可选）终端注入启动命令 → 轮询 health。
 * @param {{
 *   ping?: () => void | Promise<void>,
 *   injectCommand?: (cmd: string) => void,
 *   ensureTerminalVisible?: () => void | Promise<void>,
 *   exePath?: string,
 *   retries?: number,
 *   delayMs?: number
 * }} [opts]
 * @returns {Promise<boolean>}
 */
export async function tryStartInstalledLocalProxy(opts = {}) {
  const ping = typeof opts.ping === 'function' ? opts.ping : async () => {}
  const retries = Math.max(2, Number(opts.retries) || 10)
  const delayMs = Math.max(300, Number(opts.delayMs) || 900)

  // 优先让同机 Flask 托管拉起（自动探测 health），失败再走协议唤醒 / 终端命令
  try {
    const res = await fetch('/api/client-scripts/local-proxy/supervisor/ensure', {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' }
    })
    if (res.ok) {
      try {
        await ping()
      } catch {
        /* ignore */
      }
      const wokeViaFlask = await tryWakeThenPing({ retries: 4, delayMs: 400, ping })
      if (wokeViaFlask) return true
    }
  } catch {
    /* Flask 未托管或不在本机时忽略 */
  }

  const woke = await tryWakeThenPing({ retries: 2, delayMs: 500, ping })
  if (woke) return true

  const exePath = String(opts.exePath || resolveInstalledLocalProxyPath() || '').trim()
  const startCmd = buildLocalProxyStartCommand(exePath)
  if (startCmd && typeof opts.injectCommand === 'function') {
    try {
      if (typeof opts.ensureTerminalVisible === 'function') {
        await opts.ensureTerminalVisible()
      }
    } catch {
      /* ignore */
    }
    try {
      opts.injectCommand(startCmd)
    } catch {
      /* ignore */
    }
  } else {
    tryWakeViaUrlScheme()
  }

  return tryWakeThenPing({ retries, delayMs, ping })
}

/**
 * 重试消息上 waiting_proxy / error 的 browser 卡片。
 * @param {object} aiMessage
 * @returns {Promise<{ retried: number, ok: number, texts: string[] }>}
 */
export async function retryWaitingBrowserLocalCards(aiMessage) {
  const cards = Array.isArray(aiMessage?.clientBrowserLocalCards)
    ? aiMessage.clientBrowserLocalCards
    : []
  const waiting = cards.filter(
    (c) => c && (c.status === 'waiting_proxy' || c.status === 'error' || c.status === 'queued')
  )
  if (!waiting.length) return { retried: 0, ok: 0, texts: [] }

  const {
    localBrowserStart,
    localBrowserStop,
    localBrowserStatus
  } = await import('./localBrowserProxyClient.js')

  let ok = 0
  const texts = []
  for (const card of waiting) {
    card.status = 'running'
    card.error = ''
    try {
      let res
      if (card.action === 'stop') res = await localBrowserStop()
      else if (card.action === 'status') res = await localBrowserStatus()
      else res = await localBrowserStart({ url: card.url, headless: card.headless })
      card.status = 'done'
      card.result = res
      ok += 1
      texts.push(
        `browser ${card.action || 'start'}${card.url ? ` ${card.url}` : ''}: ok` +
          (res?.cdp_http ? ` cdp=${res.cdp_http}` : '')
      )
    } catch (e) {
      card.status = 'error'
      card.error = e && e.message ? e.message : String(e)
      texts.push(`browser ${card.action || 'start'}: fail — ${card.error}`)
    }
  }
  return { retried: waiting.length, ok, texts }
}

/** 自定义事件：对话卡请求打开安装流程（WebLocalGoProxyBar 监听） */
export const EVT_OPEN_LOCAL_PROXY_INSTALL = 'badcase-open-local-proxy-install'
/** 自定义事件：安装/唤醒后代理已就绪（可选，供调试） */
export const EVT_LOCAL_PROXY_BECAME_OK = 'badcase-local-proxy-became-ok'

export function dispatchOpenLocalProxyInstall() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(EVT_OPEN_LOCAL_PROXY_INSTALL))
}

export function dispatchLocalProxyBecameOk(detail = {}) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(EVT_LOCAL_PROXY_BECAME_OK, { detail }))
}
