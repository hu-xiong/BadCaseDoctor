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
 * 拉取本机代理隧道参数（云端 CDP 通道；需登录）。未配置/失败返回 null，代理按本地模式启动。
 * @returns {Promise<{url:string,token:string}|null>}
 */
export async function fetchTunnelParams() {
  try {
    const r = await fetch('/api/client-scripts/local-proxy/tunnel-token', {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' }
    })
    if (!r.ok) return null
    const j = await r.json().catch(() => ({}))
    const url = String((j && j.url) || '').trim()
    const token = String((j && j.token) || '').trim()
    if (!url || !token) return null
    return { url, token }
  } catch {
    return null
  }
}

/**
 * 查询当前登录用户的本机代理隧道是否在线（云端桥服务视角；见 /local-proxy/tunnel-status）。
 * 后端未就绪/未登录返回 null（未知，调用方不要据此阻断流程）。
 * @returns {Promise<{online:boolean, device?:object, bridge?:object}|null>}
 */
export async function fetchTunnelStatus() {
  try {
    const r = await fetch('/api/client-scripts/local-proxy/tunnel-status', {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' }
    })
    if (!r.ok) return null
    const j = await r.json().catch(() => null)
    if (!j || typeof j !== 'object' || typeof j.online !== 'boolean') return null
    return j
  } catch {
    return null
  }
}

/**
 * 轮询等待隧道在线（用于注入隧道参数后等待运行中的代理重连）。
 * @param {{retries?:number, delayMs?:number, probe?:() => Promise<any>}} [opts]
 * @returns {Promise<boolean>} 在线 true；超时/未知 false
 */
export async function waitTunnelOnline(opts = {}) {
  const probe = typeof opts.probe === 'function' ? opts.probe : fetchTunnelStatus
  const retries = Math.max(1, Number(opts.retries) || 8)
  const delayMs = Math.max(300, Number(opts.delayMs) || 1000)
  for (let i = 0; i < retries; i++) {
    const st = await probe()
    if (st && st.online) return true
    if (i < retries - 1) await new Promise((r) => setTimeout(r, delayMs))
  }
  return false
}

/**
 * 代理「本地 health 已就绪但云端隧道离线」时，把隧道参数补投给运行中的代理：
 * 新实例持久化配置后自行退出（--install-autostart 分支探测 health 后 exit 0），
 * 运行中实例的隧道 watcher 轮询到新配置后重连。
 * @param {{injectCommand?: (cmd:string)=>void, ensureTerminalVisible?: ()=>void|Promise<void>, exePath?:string}} [opts]
 * @returns {Promise<boolean>} 是否成功下发命令
 */
export async function injectTunnelConfigToRunningProxy(opts = {}) {
  if (typeof opts.injectCommand !== 'function') return false
  const exePath = String(opts.exePath || resolveInstalledLocalProxyPath() || '').trim()
  const tunnel = await fetchTunnelParams()
  if (!exePath || !tunnel) return false
  const cmd = buildLocalProxyStartCommand(exePath, tunnel, { installAutostart: false })
  if (!cmd) return false
  try {
    if (typeof opts.ensureTerminalVisible === 'function') await opts.ensureTerminalVisible()
  } catch {
    /* ignore */
  }
  try {
    opts.injectCommand(cmd)
    return true
  } catch {
    return false
  }
}

/** PowerShell 单引号参数字面量 */
function psQuote(v) {
  return `'${String(v).replace(/'/g, "''")}'`
}

/** POSIX shell 单引号参数字面量 */
function shQuote(v) {
  return `'${String(v).replace(/'/g, "'\\''")}'`
}

/**
 * 背景启动本机代理，并附带 --install-autostart：首次安装时一次性注册
 * 「开机自启」（Windows 注册表 Run 键 / macOS LaunchAgent / Linux systemd 用户服务），
 * 之后用户无需再手动点击启动或安装。该参数幂等，旧版二进制会忽略未知参数。
 * @param {string} exePath
 * @param {{url:string,token:string}|null} [tunnel] 隧道参数（见 fetchTunnelParams）；旧版二进制忽略未知参数
 * @param {{installAutostart?:boolean}} [opts] installAutostart=false 时不注册开机自启（仅补投隧道参数）
 * @returns {string}
 */
export function buildLocalProxyStartCommand(exePath, tunnel, opts = {}) {
  const p = String(exePath || '').trim()
  if (!p) return ''
  const installAutostart = opts.installAutostart !== false
  const os = detectClientOS()
  const tunnelPairs =
    tunnel && tunnel.url && tunnel.token ? [['--tunnel-url', tunnel.url], ['--tunnel-token', tunnel.token]] : []
  const autostartArgs = installAutostart ? ['--install-autostart'] : []
  if (os === 'win') {
    // PowerShell：后台启动 + 隐藏窗口，避免阻塞嵌入终端会话；--install-autostart 注册 Run 键
    const argList = [...autostartArgs, ...tunnelPairs.map(([k, v]) => `${psQuote(k)},${psQuote(v)}`)].join(',')
    return `Start-Process -FilePath ${JSON.stringify(p)} -ArgumentList ${argList} -WindowStyle Hidden`
  }
  const q = JSON.stringify(p)
  // macOS：浏览器下载会带 com.apple.quarantine（自启/首次执行可能被 Gatekeeper 拦截），先尝试清除
  const dequarantine = os === 'darwin' ? `xattr -d com.apple.quarantine ${q} 2>/dev/null; ` : ''
  const tunnelArgs = tunnelPairs.map(([k, v]) => ` ${shQuote(k)} ${shQuote(v)}`).join('')
  const autostartFlag = autostartArgs.length ? ' --install-autostart' : ''
  return `${dequarantine}chmod +x ${q} 2>/dev/null; nohup ${q}${autostartFlag}${tunnelArgs} >/tmp/badcase-local-proxy.log 2>&1 &`
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
  const tunnel = await fetchTunnelParams()
  const startCmd = buildLocalProxyStartCommand(exePath, tunnel)
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
/** 自定义事件：browser_local 卡片因本机代理离线进入 waiting_proxy（对话卡监听并自动尝试唤醒） */
export const EVT_BROWSER_LOCAL_PROXY_DOWN = 'badcase-browser-local-proxy-down'

export function dispatchOpenLocalProxyInstall() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(EVT_OPEN_LOCAL_PROXY_INSTALL))
}

export function dispatchLocalProxyBecameOk(detail = {}) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(EVT_LOCAL_PROXY_BECAME_OK, { detail }))
}

export function dispatchBrowserLocalProxyDown(detail = {}) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(EVT_BROWSER_LOCAL_PROXY_DOWN, { detail }))
}
