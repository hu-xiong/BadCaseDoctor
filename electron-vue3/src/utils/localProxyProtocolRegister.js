/**
 * 首次展开浏览器本机终端面板时，将 badcase-local-proxy 注册到当前用户（Windows HKCU）。
 * Electron：主进程 reg import；纯 Web：触发下载 .reg，用户双击合并一次。
 */
import { detectClientOS, readProxyInstallRecord, readExplicitProxyExePath } from './localProxyInstall.js'
import { LOCAL_PROXY_URL_SCHEME } from './localProxyWake.js'

const LS_OK = 'badcase_local_proxy_protocol_register_ok_v1'

function hasElectronRegister() {
  return (
    typeof window !== 'undefined' &&
    window.badcaseProtocol &&
    typeof window.badcaseProtocol.registerWindows === 'function'
  )
}

function looksLikeWindowsAbsolutePath(p) {
  const s = String(p || '').trim()
  if (!s) return false
  if (/^[a-zA-Z]:[\\/]/.test(s)) return true
  return /^\\\\[^\\]+\\/.test(s)
}

/**
 * @param {string} exePath
 * @param {string} [scheme]
 */
export function buildWindowsProtocolRegContent(exePath, scheme = LOCAL_PROXY_URL_SCHEME) {
  const esc = String(exePath).trim().replace(/\\/g, '\\\\')
  const sch = String(scheme || 'badcase-local-proxy').trim() || 'badcase-local-proxy'
  return (
    `Windows Registry Editor Version 5.00\r\n\r\n` +
    `[HKEY_CURRENT_USER\\Software\\Classes\\${sch}]\r\n` +
    `@="URL:BadCase Local Proxy"\r\n` +
    `"URL Protocol"=""\r\n\r\n` +
    `[HKEY_CURRENT_USER\\Software\\Classes\\${sch}\\shell\\open\\command]\r\n` +
    `@="\\"${esc}\\" \\"%1\\""\r\n`
  )
}

function persistOk() {
  try {
    localStorage.setItem(LS_OK, '1')
  } catch (_) {
    /* ignore */
  }
}

function isAlreadyOk() {
  try {
    return localStorage.getItem(LS_OK) === '1'
  } catch {
    return false
  }
}

/** 供 UI 判断本机是否已执行过协议注册（含下载 .reg 的浏览器流程）。 */
export function isLocalProxyProtocolRegistered() {
  return isAlreadyOk()
}

export function clearProtocolRegisterOk() {
  try {
    localStorage.removeItem(LS_OK)
  } catch (_) {
    /* ignore */
  }
}

/**
 * 从安装记录解析可用于注册表的可执行文件路径（仅当为可信的 Windows 绝对路径）。
 * 优先使用用户显式保存的路径（粘贴 / Electron 选择文件）。
 * @returns {string|null}
 */
export function resolveProxyExePathForProtocol() {
  const explicit = readExplicitProxyExePath()
  if (explicit && looksLikeWindowsAbsolutePath(explicit) && /\.exe$/i.test(explicit)) {
    return explicit
  }
  const rec = readProxyInstallRecord()
  if (!rec || typeof rec !== 'object') return null
  const p = rec.inferredFullPath
  if (typeof p !== 'string' || !looksLikeWindowsAbsolutePath(p)) return null
  if (!/\.exe$/i.test(p.trim())) return null
  return p.trim()
}

/**
 * @param {{ skipIfOk?: boolean, exePath?: string }} [opts]
 * @returns {Promise<{ ok: boolean, reason?: string }>}
 */
export async function tryAutoRegisterLocalProxyProtocol(opts = {}) {
  const skipIfOk = opts.skipIfOk !== false
  if (skipIfOk && isAlreadyOk()) {
    return { ok: true, reason: 'already_ok' }
  }
  if (detectClientOS() !== 'win') {
    return { ok: false, reason: 'not_windows' }
  }

  const exePath =
    typeof opts.exePath === 'string' && opts.exePath.trim()
      ? opts.exePath.trim()
      : resolveProxyExePathForProtocol()
  if (!exePath || !looksLikeWindowsAbsolutePath(exePath) || !/\.exe$/i.test(exePath)) {
    return { ok: false, reason: 'no_exe_path' }
  }

  if (hasElectronRegister()) {
    try {
      const r = await window.badcaseProtocol.registerWindows(exePath, LOCAL_PROXY_URL_SCHEME)
      if (r && r.ok) {
        persistOk()
        return { ok: true }
      }
      return { ok: false, reason: r?.error || 'electron_failed' }
    } catch (e) {
      return { ok: false, reason: String(e?.message || e) }
    }
  }

  try {
    const content = buildWindowsProtocolRegContent(exePath)
    const blob = new Blob(['\ufeff' + content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'badcase-local-proxy-protocol.reg'
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.setTimeout(() => URL.revokeObjectURL(url), 4000)
    persistOk()
    return { ok: true, reason: 'reg_downloaded' }
  } catch (e) {
    return { ok: false, reason: String(e?.message || e) }
  }
}

/**
 * 供 EmbeddedTerminalWorkspace 在挂载时调用（仅浏览器走 go-local-proxy 时有效）。
 * 使用方应先排除 Electron 壳（isElectronShell），桌面终端不依赖本代理。
 */
export async function tryAutoRegisterLocalProxyProtocolOnFirstTerminalOpen() {
  return tryAutoRegisterLocalProxyProtocol()
}
