/**
 * 浏览器侧：从同源后端下载本地代理二进制，并写入用户选择的目录（File System Access API）
 * 或退回为触发浏览器下载。无法从网页内直接启动本机进程。
 *
 * 说明：标准 Web API 不会把「另存为」的完整磁盘路径返回给页面；我们仅保存文件名、时间、
 * 当时的终端 cwd，以及「cwd + 文件名」的推断路径（若用户确实存到该目录则一致）。
 * 协议注册等需要真实路径时，使用 readExplicitProxyExePath / persistExplicitProxyExePath（用户粘贴或 Electron 选文件）。
 * 另：可将用户授权的目录句柄存入 IndexedDB，下次免选目录覆盖写入。
 */
import { api } from '../api.js'

const LS_KEY = 'badcase_local_proxy_install_record'
/** 用户确认的本地代理 exe 绝对路径（协议注册等；可由后端代为落盘后写入）。 */
const LS_EXPLICIT_EXE = 'badcase_local_proxy_explicit_exe_v1'
const IDB_NAME = 'badcase-local-proxy'
const IDB_VER = 1
const IDB_STORE = 'handles'

export function detectClientOS() {
  if (typeof navigator === 'undefined') return 'unknown'
  const ua = navigator.userAgent || ''
  if (/Windows NT/i.test(ua)) return 'win'
  if (/Mac OS X|Macintosh/i.test(ua)) return 'darwin'
  if (/Linux/i.test(ua)) return 'linux'
  return 'unknown'
}

/** 用于选择 amd64 / arm64 制品（主要区分 Apple Silicon 与 Intel Mac） */
export function detectClientArch() {
  if (typeof navigator === 'undefined') return 'amd64'
  const ua = navigator.userAgent || ''
  if (/aarch64|arm64/i.test(ua)) return 'arm64'
  return 'amd64'
}

/**
 * 与 badcase_client_binaries.LOCAL_PROXY_ARTIFACTS 命名一致，用于占位符与提示（非实际探测磁盘）。
 * @param {string} [os]
 * @param {string} [arch]
 */
export function getDefaultLocalProxyFilename(os = detectClientOS(), arch = detectClientArch()) {
  const a = arch === 'arm64' ? 'arm64' : 'amd64'
  if (os === 'win') return 'badcase-local-proxy.exe'
  if (os === 'darwin') return `badcase-local-proxy-darwin-${a}`
  if (os === 'linux') return `badcase-local-proxy-linux-${a}`
  return 'badcase-local-proxy'
}

/** 与常见安装器一致：固定安装目录名（非安装器，仅作默认路径提示）。 */
export const RECOMMENDED_LOCAL_PROXY_APP_DIR = 'BadCaseDoctor'

/**
 * 建议安装路径（下载/注册默认值）：Windows 为 C:\Program Files\…；Unix 为 /opt/…。
 * 浏览器无法代用户写入该目录；用户需另存后复制到此处（或管理员安装），除非推断路径显示用户已存到别处。
 */
export function getDefaultLocalProxyPathPlaceholder() {
  const os = detectClientOS()
  const fn = getDefaultLocalProxyFilename()
  if (os === 'win') {
    return `C:\\Program Files\\${RECOMMENDED_LOCAL_PROXY_APP_DIR}\\${fn}`
  }
  if (os === 'darwin' || os === 'linux') {
    return `/opt/${RECOMMENDED_LOCAL_PROXY_APP_DIR}/${fn}`
  }
  return `/opt/${RECOMMENDED_LOCAL_PROXY_APP_DIR}/${fn}`
}

export async function fetchLocalProxyManifest() {
  const { data } = await api.get('/api/client-scripts/local-proxy/manifest.json')
  return data
}

/**
 * @param {unknown[]} artifacts manifest.artifacts
 * @param {string} os win|linux|darwin|unknown
 * @param {string} [arch] amd64|arm64，默认 amd64
 */
export function pickArtifactForOs(artifacts, os, arch = 'amd64') {
  const list = Array.isArray(artifacts) ? artifacts : []
  const want = arch === 'arm64' ? 'arm64' : 'amd64'
  if (os === 'darwin') {
    const exact = list.find((a) => a && a.os === 'darwin' && (a.arch || 'amd64') === want)
    if (exact) return exact
    return list.find((a) => a && a.os === 'darwin') || null
  }
  if (os === 'linux') {
    const exact = list.find((a) => a && a.os === 'linux' && (a.arch || 'amd64') === want)
    if (exact) return exact
    return list.find((a) => a && a.os === 'linux') || null
  }
  return list.find((a) => a && a.os === os) || null
}

function extForAccept(filename) {
  const i = filename.lastIndexOf('.')
  if (i <= 0) return '.bin'
  return filename.slice(i).toLowerCase()
}

function buildAcceptForPicker(filename) {
  const ext = extForAccept(filename)
  const dot = ext.startsWith('.') ? ext : `.${ext}`
  return { 'application/octet-stream': [dot] }
}

/** 终端 cwd 与文件名拼接（仅供展示/记录；是否真实路径取决于用户是否在对话框中选到该目录） */
export function joinTerminalCwdFilename(cwd, file) {
  const c = String(cwd || '').trim()
  const f = String(file || '').trim()
  if (!c || !f) return ''
  const sep = /\\/.test(c) ? '\\' : '/'
  return `${c.replace(/[/\\]+$/, '')}${sep}${f}`
}

/** 从完整路径取文件名（浏览器环境无 path.basename） */
export function fileBasename(p) {
  const s = String(p || '').trim().replace(/[/\\]+$/, '')
  if (!s) return ''
  const parts = s.split(/[/\\]/)
  return parts[parts.length - 1] || ''
}

/**
 * 由本机环回上的后端将 blob 写入 targetPath（需已登录）。非环回或远端部署会 403。
 * @param {Blob} blob
 * @param {string} targetPath
 * @returns {Promise<string>} 服务端确认后的绝对路径
 */
export async function saveLocalProxyBlobViaLoopbackBackend(blob, targetPath) {
  const fd = new FormData()
  fd.append('target_path', String(targetPath).trim())
  const name = fileBasename(targetPath) || 'badcase-local-proxy.exe'
  fd.append('file', blob, name)
  try {
    const { data } = await api.post('/api/client-scripts/local-proxy/save', fd, {
      timeout: 180000,
      maxBodyLength: Infinity,
      maxContentLength: Infinity
    })
    if (data && data.ok && data.path) return String(data.path).trim()
    const msg = data?.message || data?.error || 'save_failed'
    const err = new Error(msg)
    err.code = data?.error || 'SERVER_SAVE_FAILED'
    throw err
  } catch (e) {
    const d = e?.response?.data
    const msg = d?.message || d?.error || e?.message || 'save_failed'
    const err = new Error(msg)
    err.code = d?.error || e?.code || 'SERVER_SAVE_FAILED'
    err.status = e?.response?.status
    throw err
  }
}

/**
 * @param {object} rec
 */
export function persistProxyInstallRecord(rec) {
  if (typeof localStorage === 'undefined') return
  try {
    const prev = readProxyInstallRecord()
    const next = {
      ...(prev && typeof prev === 'object' ? prev : {}),
      ...rec,
      savedAt: new Date().toISOString()
    }
    localStorage.setItem(LS_KEY, JSON.stringify(next))
  } catch (e) {
    console.warn('[localProxyInstall] persist record', e)
  }
}

export function readExplicitProxyExePath() {
  if (typeof localStorage === 'undefined') return ''
  try {
    const s = localStorage.getItem(LS_EXPLICIT_EXE)
    return s && typeof s === 'string' ? s.trim() : ''
  } catch {
    return ''
  }
}

/**
 * @param {string} p 完整路径，空字符串表示清除
 */
export function persistExplicitProxyExePath(p) {
  if (typeof localStorage === 'undefined') return
  try {
    const t = String(p || '').trim()
    if (!t) localStorage.removeItem(LS_EXPLICIT_EXE)
    else localStorage.setItem(LS_EXPLICIT_EXE, t)
  } catch (e) {
    console.warn('[localProxyInstall] persist explicit exe path', e)
  }
}

export function readProxyInstallRecord() {
  if (typeof localStorage === 'undefined') return null
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return null
    const j = JSON.parse(raw)
    return j && typeof j === 'object' ? j : null
  } catch {
    return null
  }
}

/**
 * 从文件路径取父目录（浏览器侧无 path 模块，仅按最后一个 / 或 \\ 分割）。
 * @param {string} filePath
 * @returns {string}
 */
export function dirnameFromFilePath(filePath) {
  const s = String(filePath || '').trim()
  if (!s) return ''
  const i = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'))
  if (i <= 0) return ''
  return s.slice(0, i)
}

/**
 * 从安装记录推断「代理 exe 所在目录」（展示/另存为上下文用）。
 * 嵌入式终端默认 cwd 不再使用此值：未指定时应由 go-local-proxy 使用其**进程启动目录**。
 * @returns {string}
 */
export function getSuggestedWebTerminalCwdFromProxyInstall() {
  const explicit = readExplicitProxyExePath()
  if (explicit) {
    const d = dirnameFromFilePath(explicit)
    if (d) return d
  }
  const rec = readProxyInstallRecord()
  const inf = rec && typeof rec.inferredFullPath === 'string' ? rec.inferredFullPath.trim() : ''
  if (inf) {
    const d = dirnameFromFilePath(inf)
    if (d) return d
  }
  return ''
}

function idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VER)
    req.onerror = () => reject(req.error)
    req.onsuccess = () => resolve(req.result)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(IDB_STORE)) {
        req.result.createObjectStore(IDB_STORE)
      }
    }
  })
}

async function idbPutDirHandle(dirHandle) {
  const db = await idbOpen()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.objectStore(IDB_STORE).put(dirHandle, 'proxyDir')
  })
}

async function idbGetDirHandle() {
  const db = await idbOpen()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly')
    const rq = tx.objectStore(IDB_STORE).get('proxyDir')
    rq.onsuccess = () => resolve(rq.result ?? null)
    rq.onerror = () => reject(rq.error)
  })
}

async function tryWriteBlobToDirHandle(dirHandle, filename, blob) {
  const fh = await dirHandle.getFileHandle(filename, { create: true })
  const w = await fh.createWritable()
  await w.write(blob)
  await w.close()
}

async function ensureDirWritable(dirHandle) {
  const q = await dirHandle.queryPermission({ mode: 'readwrite' })
  if (q === 'granted') return true
  const r = await dirHandle.requestPermission({ mode: 'readwrite' })
  return r === 'granted'
}

/**
 * @param {string} filename
 * @param {(pct: number, phase: string) => void} [onProgress]
 *   phase: fetch — pct 0–84 为已读比例，85 表示网络下载完成；-1 与 fetch 同用表示 Content-Length 未知
 *   phase: pick_save — 等待用户选择保存位置（另存为/选文件夹），pct 忽略
 *   phase: write — 正在写入磁盘
 *   phase: done — 全部结束，pct 100
 */
async function fetchProxyBinaryWithProgress(filename, onProgress) {
  const url = `/api/client-scripts/bin/${encodeURIComponent(filename)}`
  const res = await fetch(url, { method: 'GET', credentials: 'include', cache: 'no-store' })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (j?.message) msg = j.message
      else if (j?.error) msg = j.error
    } catch (_) {
      /* ignore */
    }
    throw new Error(msg)
  }
  const total = parseInt(res.headers.get('Content-Length') || '0', 10) || 0
  const reader = res.body?.getReader()
  if (!reader) {
    const blob = await res.blob()
    onProgress?.(85, 'fetch')
    return blob
  }
  const chunks = []
  let loaded = 0
  onProgress?.(0, 'fetch')
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.byteLength
    if (total > 0) {
      onProgress?.(Math.min(84, Math.round((loaded / total) * 84)), 'fetch')
    } else {
      onProgress?.(-1, 'fetch')
    }
  }
  onProgress?.(85, 'fetch')
  return new Blob(chunks)
}

/**
 * 从后端拉取代理二进制（不保存）。
 * @returns {Promise<{ blob: Blob, filename: string }>}
 */
export async function fetchLocalProxyBinaryBlob(artifact, onProgress) {
  const filename = (artifact?.filename || 'badcase-local-proxy.exe').trim()
  const blob = await fetchProxyBinaryWithProgress(filename, onProgress)
  return { blob, filename }
}

/**
 * 将已下载的 blob 落到本机（复用 IndexedDB 目录 / Electron 另存为 / FSA / 浏览器下载）。
 * @param {{
 *   terminalCwd?: string,
 *   projectId?: string|number|null,
 *   tryReuseDir?: boolean,
 *   explicitFullPath?: string,
 *   onProgress?: (pct: number, phase: 'fetch'|'pick_save'|'write'|'done') => void
 * }} [opts]
 * @returns {Promise<{ mode: string, filename: string }>}
 */
export async function saveLocalProxyBlobWithoutFetch(blob, filename, opts = {}) {
  const terminalCwd = String(opts.terminalCwd || '').trim()
  const projectId = opts.projectId != null ? opts.projectId : null
  const tryReuse = opts.tryReuseDir !== false
  const onProgress = typeof opts.onProgress === 'function' ? opts.onProgress : null
  const fn = String(filename || 'badcase-local-proxy.exe').trim()
  const explicitFullPath = String(opts.explicitFullPath || '').trim()

  const saveMeta = (mode, savedFileName, extra = {}) => {
    const inferredFullPath = joinTerminalCwdFilename(terminalCwd, savedFileName)
    persistProxyInstallRecord({
      mode,
      fileName: savedFileName,
      terminalCwdAtSave: terminalCwd,
      projectId,
      inferredFullPath: inferredFullPath || undefined,
      ...extra
    })
  }

  /** 用户在弹窗中确认的完整路径：优先 Electron 桥；否则由本机 Flask（环回）代为写入 */
  if (explicitFullPath) {
    onProgress?.(-1, 'write')
    const baseName = fileBasename(explicitFullPath) || fn
    if (
      typeof window !== 'undefined' &&
      window.badcaseLocalProxy &&
      typeof window.badcaseLocalProxy.saveProxyBlob === 'function'
    ) {
      try {
        const ab = await blob.arrayBuffer()
        const r = await window.badcaseLocalProxy.saveProxyBlob(baseName, ab, explicitFullPath)
        if (r && r.ok && r.path) {
          persistProxyInstallRecord({
            mode: 'ipc_target_path',
            fileName: baseName,
            terminalCwdAtSave: terminalCwd,
            projectId,
            inferredFullPath: r.path,
            rememberedFolder: false
          })
          onProgress?.(100, 'done')
          return { mode: 'ipc_target_path', filename: baseName }
        }
      } catch (e) {
        console.warn('[localProxyInstall] explicit path via preload failed, try loopback API', e)
      }
    }
    try {
      const written = await saveLocalProxyBlobViaLoopbackBackend(blob, explicitFullPath)
      persistProxyInstallRecord({
        mode: 'server_target_path',
        fileName: baseName,
        terminalCwdAtSave: terminalCwd,
        projectId,
        inferredFullPath: written,
        rememberedFolder: false
      })
      onProgress?.(100, 'done')
      return { mode: 'server_target_path', filename: baseName }
    } catch (e) {
      throw e
    }
  }

  if (tryReuse && typeof indexedDB !== 'undefined') {
    try {
      const dir = await idbGetDirHandle()
      if (dir && (await ensureDirWritable(dir))) {
        onProgress?.(-1, 'write')
        await tryWriteBlobToDirHandle(dir, fn, blob)
        saveMeta('fsa_reuse', fn, { rememberedFolder: true })
        onProgress?.(100, 'done')
        return { mode: 'fsa_reuse', filename: fn }
      }
    } catch (e) {
      console.warn('[localProxyInstall] reuse dir handle failed', e)
    }
  }

  /** Electron 预加载桥：无 explicitFullPath 时主进程弹出「另存为」。 */
  if (
    typeof window !== 'undefined' &&
    window.badcaseLocalProxy &&
    typeof window.badcaseLocalProxy.saveProxyBlob === 'function'
  ) {
    try {
      onProgress?.(-1, 'pick_save')
      const ab = await blob.arrayBuffer()
      const r = await window.badcaseLocalProxy.saveProxyBlob(fn, ab)
      if (r && r.ok && r.path) {
        persistProxyInstallRecord({
          mode: 'electron_save',
          fileName: fn,
          terminalCwdAtSave: terminalCwd,
          projectId,
          inferredFullPath: r.path,
          rememberedFolder: false
        })
        onProgress?.(100, 'done')
        return { mode: 'electron_save', filename: fn }
      }
    } catch (e) {
      console.warn('[localProxyInstall] Electron 另存为失败，尝试浏览器保存', e)
    }
  }

  let fsaStartIn = null
  try {
    fsaStartIn = await idbGetDirHandle()
  } catch (_) {
    fsaStartIn = null
  }

  if (typeof window !== 'undefined' && typeof window.showSaveFilePicker === 'function') {
    try {
      onProgress?.(-1, 'pick_save')
      const handle = await window.showSaveFilePicker({
        suggestedName: fn,
        startIn: fsaStartIn || 'downloads',
        types: [{ description: fn, accept: buildAcceptForPicker(fn) }]
      })
      onProgress?.(-1, 'write')
      const w = await handle.createWritable()
      await w.write(blob)
      await w.close()
      const savedName = handle.name || fn
      saveMeta('saveAs', savedName, { rememberedFolder: false })
      onProgress?.(100, 'done')
      return { mode: 'saveAs', filename: savedName }
    } catch (e) {
      if (e && e.name === 'AbortError') throw e
      console.warn('[localProxyInstall] showSaveFilePicker failed, try folder / download', e)
    }
  }

  if (typeof window !== 'undefined' && window.showDirectoryPicker) {
    try {
      onProgress?.(-1, 'pick_save')
      const dir = await window.showDirectoryPicker({
        id: 'badcase-local-proxy',
        mode: 'readwrite',
        startIn: fsaStartIn || 'downloads'
      })
      onProgress?.(-1, 'write')
      await tryWriteBlobToDirHandle(dir, fn, blob)
      try {
        await idbPutDirHandle(dir)
      } catch (e) {
        console.warn('[localProxyInstall] idb put dir', e)
      }
      saveMeta('fsa', fn, { rememberedFolder: true })
      onProgress?.(100, 'done')
      return { mode: 'fsa', filename: fn }
    } catch (e) {
      if (e && e.name === 'AbortError') throw e
      console.warn('[localProxyInstall] directory picker / write failed, fallback download', e)
    }
  }

  onProgress?.(-1, 'write')
  const a = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  a.href = objectUrl
  a.download = fn
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 2500)
  saveMeta('download', fn, { rememberedFolder: false })
  onProgress?.(100, 'done')
  return { mode: 'download', filename: fn }
}

/**
 * 下载并保存（内部 = fetch + saveLocalProxyBlobWithoutFetch）。未展示安装条款时优先用 fetch + 自研弹窗 + save。
 * @param {object} artifact
 * @param {{
 *   terminalCwd?: string,
 *   projectId?: string|number|null,
 *   tryReuseDir?: boolean,
 *   onProgress?: (pct: number, phase: 'fetch'|'pick_save'|'write'|'done') => void
 * }} [opts]
 * @returns {Promise<{ mode: string, filename: string }>}
 */
export async function downloadProxyToUserFolder(artifact, opts = {}) {
  const { blob, filename } = await fetchLocalProxyBinaryBlob(artifact, opts.onProgress)
  return saveLocalProxyBlobWithoutFetch(blob, filename, opts)
}
