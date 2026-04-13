/**
 * 本机代理未响应时：通过自定义 URL Scheme 唤起已注册的 badcase-local-proxy（与 go-local-proxy main 约定）。
 * 需用户在系统内导入注册表 / .desktop / 等（见仓库 scripts/protocol/）。
 *
 * 环境变量：VITE_LOCAL_PROXY_URL_SCHEME（默认 badcase-local-proxy）
 */
import { getLocalShellProxyHealthUrl } from './localShellProxyClient.js'

export const LOCAL_PROXY_URL_SCHEME = (import.meta.env.VITE_LOCAL_PROXY_URL_SCHEME || 'badcase-local-proxy').trim()

export function getLocalProxyWakeUrl() {
  let port = '8794'
  try {
    const u = new URL(getLocalShellProxyHealthUrl())
    port = u.port || '8794'
  } catch {
    /* keep default */
  }
  return `${LOCAL_PROXY_URL_SCHEME}://wakeup?port=${encodeURIComponent(port)}`
}

async function fetchHealthOk() {
  try {
    const r = await fetch(getLocalShellProxyHealthUrl(), { method: 'GET', cache: 'no-store' })
    const text = await r.text()
    return r.ok && text.trim() === 'ok'
  } catch {
    return false
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 通过隐藏 iframe 触发系统已注册的协议处理器（浏览器会可能弹确认框）。
 */
export function tryWakeViaUrlScheme() {
  if (typeof document === 'undefined') return
  const iframe = document.createElement('iframe')
  iframe.style.display = 'none'
  iframe.setAttribute('aria-hidden', 'true')
  iframe.src = getLocalProxyWakeUrl()
  document.body.appendChild(iframe)
  window.setTimeout(() => {
    try {
      document.body.removeChild(iframe)
    } catch (_) {
      /* ignore */
    }
  }, 2500)
}

/**
 * 若 /health 已通则不唤起；否则轮询：唤起 → 等待 → ping 回调 → 再测 health。
 * @param {{ retries?: number, delayMs?: number, ping?: () => void | Promise<void> }} [opts]
 * @returns {Promise<boolean>} 最终是否探测到健康
 */
export async function tryWakeThenPing(opts = {}) {
  const retries = Math.max(1, Number(opts.retries) || 3)
  const delayMs = Math.max(200, Number(opts.delayMs) || 900)
  const ping = typeof opts.ping === 'function' ? opts.ping : async () => {}

  if (await fetchHealthOk()) {
    await ping()
    return true
  }

  for (let i = 0; i < retries; i += 1) {
    tryWakeViaUrlScheme()
    await sleep(delayMs)
    await ping()
    if (await fetchHealthOk()) return true
  }
  return false
}
