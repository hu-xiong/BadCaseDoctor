const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron')
const path = require('path')
const os = require('os')
const fs = require('fs')
const { execFileSync, spawn } = require('child_process')
const isDev = process.env.NODE_ENV === 'development'

// node-pty 支持本地终端
let pty = null
try {
  pty = require('node-pty')
} catch (e) {
  console.warn('[Electron] node-pty not available:', e.message)
}

let mainWindow
const ptyProcesses = new Map()  // sessionId -> ptyInstance

/** 供 xterm ConPTY 光标行随列宽重排（与 VS Code reflowCursorLine 一致） */
function windowsPtyHintForXterm() {
  if (process.platform !== 'win32') return undefined
  const parts = String(os.release() || '').split('.')
  const build = parseInt(parts[2], 10)
  const hint = { backend: 'conpty' }
  if (Number.isFinite(build) && build > 0) hint.build_number = build
  return hint
}

/** Windows：与 go-local-proxy 一致用 PowerShell，才有 PS C:\...>；否则 node-pty 默认 COMSPEC 是 cmd.exe */
function resolveWindowsPtyShell() {
  const windir = process.env.WINDIR || 'C:\\Windows'
  const tryWhere = (name) => {
    try {
      const out = execFileSync('where', [name], { encoding: 'utf8', windowsHide: true })
      const line = String(out || '')
        .split(/\r?\n/)
        .map((s) => s.trim())
        .find(Boolean)
      if (line && fs.existsSync(line)) return line
    } catch {
      /* ignore */
    }
    return ''
  }
  // 与 go-local-proxy pty_spawn_windows 一致（EncodedCommand；\r 盖行由前端 xterm 路径缓解）
  const psInit = [
    '-NoLogo',
    '-NoProfile',
    '-NoExit',
    '-EncodedCommand',
    'JgAgAHsAIAAkAEUAcgByAG8AcgBWAGkAZQB3ACAAPQAgACcATgBvAHIAbQBhAGwAVgBpAGUAdwAnADsAIAB0AHIAeQAgAHsAIABpAGYAIAAoAEcAZQB0AC0ATQBvAGQAdQBsAGUAIABQAFMAUgBlAGEAZABMAGkAbgBlACAALQBFAHIAcgBvAHIAQQBjAHQAaQBvAG4AIABTAGkAbABlAG4AdABsAHkAQwBvAG4AdABpAG4AdQBlACkAIAB7ACAAUwBlAHQALQBQAFMAUgBlAGEAZABMAGkAbgBlAE8AcAB0AGkAbwBuACAALQBQAHIAZQBkAGkAYwB0AGkAbwBuAFMAbwB1AHIAYwBlACAATgBvAG4AZQAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAUwBpAGwAZQBuAHQAbAB5AEMAbwBuAHQAaQBuAHUAZQAgAH0AIAB9ACAAYwBhAHQAYwBoACAAewAgAH0AOwAgAHQAcgB5ACAAewAgAGkAZgAgACgAJABQAFMAUwB0AHkAbABlACkAIAB7ACAAJABQAFMAUwB0AHkAbABlAC4ATwB1AHQAcAB1AHQAUgBlAG4AZABlAHIAaQBuAGcAIAA9ACAAJwBQAGwAYQBpAG4AVABlAHgAdAAnACAAfQAgAH0AIABjAGEAdABjAGgAIAB7ACAAfQAgAH0A'
  ]
  const pw = tryWhere('pwsh.exe')
  if (pw) return { file: pw, args: psInit }
  const ps5 = path.join(windir, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
  if (fs.existsSync(ps5)) return { file: ps5, args: psInit }
  return { file: 'powershell.exe', args: psInit }
}

function resolvePtyShell() {
  if (process.platform === 'win32') return resolveWindowsPtyShell()
  const sh = process.env.SHELL || '/bin/bash'
  return { file: sh, args: [] }
}

/** 嵌入终端默认 cwd：优先 agent-terminal permissions.workspace_root，否则进程 cwd（开发时多为仓库根） */
function getEmbeddedTerminalDefaultCwd() {
  try {
    const f = path.join(os.homedir(), '.config', 'agent-terminal', 'permissions.json')
    if (fs.existsSync(f)) {
      const j = JSON.parse(fs.readFileSync(f, 'utf8'))
      const P = j.permissions || j.Permissions
      const wr = P && String(P.workspace_root || P.workspaceRoot || '').trim()
      if (wr) {
        try {
          if (fs.existsSync(wr)) return wr
        } catch {
          /* ignore */
        }
      }
    }
  } catch {
    /* ignore */
  }
  try {
    return process.cwd()
  } catch {
    return ''
  }
}
/** 终端子 Agent 一次性 exec：requestId -> { cancel } */
const terminalOnceById = new Map()

function createWindow() {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, '../public/logo.svg'),
    title: 'BadCase Doctor',
    show: false
  })

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // 加载应用
  if (isDev) {
    // 开发环境：加载Vite开发服务器
    mainWindow.loadURL('http://localhost:5173')
    // 打开开发者工具
    mainWindow.webContents.openDevTools()
  } else {
    // 生产环境：加载构建后的文件
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // 窗口关闭时清理
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// 应用准备就绪时创建窗口
app.whenReady().then(() => {
  createWindow()

  // 在macOS上，当所有窗口都关闭时，重新创建一个窗口
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

// 当所有窗口都关闭时退出应用
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// 设置应用菜单
const template = [
  {
    label: '文件',
    submenu: [
      {
        label: '新建项目',
        accelerator: 'CmdOrCtrl+N',
        click: () => {
          if (mainWindow) {
            mainWindow.webContents.send('menu-new-project')
          }
        }
      },
      {
        label: '导入Excel',
        accelerator: 'CmdOrCtrl+I',
        click: () => {
          if (mainWindow) {
            mainWindow.webContents.send('menu-import-excel')
          }
        }
      },
      { type: 'separator' },
      {
        label: '退出',
        accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
        click: () => {
          app.quit()
        }
      }
    ]
  },
  {
    label: '编辑',
    submenu: [
      { role: 'undo', label: '撤销' },
      { role: 'redo', label: '重做' },
      { type: 'separator' },
      { role: 'cut', label: '剪切' },
      { role: 'copy', label: '复制' },
      { role: 'paste', label: '粘贴' },
      { role: 'selectall', label: '全选' }
    ]
  },
  {
    label: '视图',
    submenu: [
      { role: 'reload', label: '重新加载' },
      { role: 'forceReload', label: '强制重新加载' },
      { role: 'toggleDevTools', label: '切换开发者工具' },
      { type: 'separator' },
      { role: 'resetZoom', label: '实际大小' },
      { role: 'zoomIn', label: '放大' },
      { role: 'zoomOut', label: '缩小' },
      { type: 'separator' },
      { role: 'togglefullscreen', label: '切换全屏' }
    ]
  },
  {
    label: '帮助',
    submenu: [
      {
        label: '关于',
        click: () => {
          if (mainWindow) {
            mainWindow.webContents.send('menu-about')
          }
        }
      }
    ]
  }
]

const menu = Menu.buildFromTemplate(template)
Menu.setApplicationMenu(menu)

// 处理未捕获的异常
process.on('uncaughtException', (error) => {
  console.error('未捕获的异常:', error)
})

process.on('unhandledRejection', (reason, promise) => {
  console.error('未处理的Promise拒绝:', reason)
})

// ===================== PTY IPC 处理 =====================

// 启动本地 PTY
ipcMain.on('pty-start', (event, { sessionId, cols, rows, cwd }) => {
  if (!pty) {
    event.reply('pty-error', { sessionId, message: 'node-pty 未安装' })
    return
  }
  
  try {
    // 幂等：同一 sessionId 已有 PTY 时不要重复 spawn，否则输出会混在一起导致重复/错行/换行异常
    const existing = ptyProcesses.get(sessionId)
    if (existing) {
      try {
        if (cols && rows && typeof existing.resize === 'function') existing.resize(cols, rows)
      } catch (_) {
        /* ignore */
      }
      event.reply('pty-started', {
        sessionId,
        pid: existing.pid,
        shell: resolvePtyShell().file,
        cwd: cwd || os.homedir(),
        windows_pty: windowsPtyHintForXterm()
      })
      return
    }

    const { file: shell, args: shellArgs } = resolvePtyShell()

    const ptyProcess = pty.spawn(shell, shellArgs, {
      name: 'xterm-256color',
      cols: cols || 80,
      rows: rows || 24,
      cwd: cwd || os.homedir(),
      env: { ...process.env, TERM: 'xterm-256color' }
    })
    
    // 存储进程
    ptyProcesses.set(sessionId, ptyProcess)
    
    // 监听输出
    ptyProcess.onData((data) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pty-output', { sessionId, data })
      }
    })
    
    // 监听退出
    ptyProcess.onExit(() => {
      ptyProcesses.delete(sessionId)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pty-exit', { sessionId })
      }
    })
    
    event.reply('pty-started', {
      sessionId,
      pid: ptyProcess.pid,
      shell,
      cwd: cwd || os.homedir(),
      windows_pty: windowsPtyHintForXterm()
    })
    console.log(`[PTY] Started session ${sessionId}`)
  } catch (e) {
    console.error('[PTY] Failed to start:', e)
    event.reply('pty-error', { sessionId, message: e.message })
  }
})

// 输入数据（string 或 Uint8Array/Buffer：二进制 stdin 避免 UTF-16 字符串破坏 0x08/0x7F 等控制字节）
ipcMain.on('pty-input', (event, { sessionId, data }) => {
  const ptyProcess = ptyProcesses.get(sessionId)
  if (ptyProcess) {
    try {
      let chunk = data
      if (chunk instanceof Uint8Array && !Buffer.isBuffer(chunk)) {
        chunk = Buffer.from(chunk)
      }
      ptyProcess.write(chunk)
    } catch (e) {
      console.error('[PTY] Write error:', e)
    }
  }
})

// 调整大小
ipcMain.on('pty-resize', (event, { sessionId, cols, rows }) => {
  const ptyProcess = ptyProcesses.get(sessionId)
  if (ptyProcess) {
    try {
      ptyProcess.resize(cols, rows)
    } catch (e) {
      console.error('[PTY] Resize error:', e)
    }
  }
})

// 关闭 PTY
ipcMain.on('pty-close', (event, { sessionId }) => {
  const ptyProcess = ptyProcesses.get(sessionId)
  if (ptyProcess) {
    try {
      ptyProcess.kill()
    } catch (e) {
      console.error('[PTY] Kill error:', e)
    }
    ptyProcesses.delete(sessionId)
  }
})

ipcMain.handle('embedded-terminal-default-cwd', async () => ({
  cwd: getEmbeddedTerminalDefaultCwd()
}))

// 清理所有 PTY
app.on('before-quit', () => {
  for (const [sessionId, ptyProcess] of ptyProcesses) {
    try {
      ptyProcess.kill()
    } catch (e) {}
  }
  ptyProcesses.clear()
})

// ===================== 终端子 Agent：一次性命令（非交互 PTY）=====================
function _normalizePermPattern(p) {
  let s = String(p || '').trim()
  const low = s.toLowerCase()
  if (low.startsWith('bash(') && s.endsWith(')')) {
    s = s.slice(5, -1).trim()
  }
  return s
}

function _permGlobToRegExp(globPat) {
  const p = _normalizePermPattern(globPat)
  if (!p) return null
  let out = '^'
  for (let i = 0; i < p.length; i++) {
    const c = p[i]
    if (c === '*') out += '.*'
    else if (c === '?') out += '.'
    else if ('.^$+()[]{}|\\'.includes(c)) out += `\\${c}`
    else out += c
  }
  out += '$'
  try {
    return new RegExp(out, 'i')
  } catch {
    return null
  }
}

function _cwdUnderWorkspaceRoot(cwd, workspaceRoot) {
  const wr = String(workspaceRoot || '').trim()
  if (!wr) return true
  const c = String(cwd || '').trim()
  if (!c) return true
  try {
    const wc = path.resolve(c) + path.sep
    const wrAbs = path.resolve(wr) + path.sep
    return wc.toLowerCase().startsWith(wrAbs.toLowerCase())
  } catch {
    return true
  }
}

function _countShellSegments(line) {
  const s0 = String(line || '').trim()
  if (!s0) return 0
  const s = s0.replace(/\|\|/g, '\x01').replace(/&&/g, '\x01')
  let n = 1
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (ch === '|' || ch === ';' || ch === '\x01') n++
  }
  return n
}

function _domainAllowedNode(host, allowed) {
  const h = String(host || '').trim().toLowerCase()
  if (!h) return false
  for (const a of allowed) {
    const d = String(a || '').trim().toLowerCase()
    if (!d) continue
    if (h === d || h.endsWith('.' + d)) return true
  }
  return false
}

function _commandMatchesAnyAllowNode(line, allow) {
  if (!Array.isArray(allow) || allow.length === 0) return false
  const s = String(line || '').trim()
  if (!s) return false
  for (const a of allow) {
    const re = _permGlobToRegExp(a)
    if (re && re.test(s)) return true
  }
  return false
}

function _firstBareHostnameAfterNetTool(line) {
  const trim = String(line || '').trim()
  const reTool = /\b(curl|wget|fetch|Invoke-WebRequest|iwr)\b/i
  const m0 = trim.match(reTool)
  if (!m0 || m0.index === undefined) return ''
  const tail = trim.slice(m0.index + m0[0].length).trim()
  const argvExtra = new Set([
    '-X',
    '--request',
    '-d',
    '--data',
    '--data-binary',
    '-H',
    '--header',
    '-o',
    '--output',
    '-T',
    '--upload-file'
  ])
  const fields = tail.split(/\s+/).filter(Boolean)
  let i = 0
  while (i < fields.length && fields[i].startsWith('-')) {
    const base = fields[i].split('=')[0]
    i++
    if (argvExtra.has(base)) {
      if (i >= fields.length) return ''
      i++
    }
  }
  if (i >= fields.length) return ''
  const remainder = fields.slice(i).join(' ')
  const reBare =
    /(?:^|\s)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9]){1,}))(?:\/|\?|#|:\d{1,5}|$)/i
  const mh = remainder.match(reBare)
  return mh && mh[1] ? mh[1] : ''
}

function _checkNetworkDomainsNode(command, allowed) {
  if (!Array.isArray(allowed) || allowed.length === 0) return null
  const line = String(command || '').trim()
  if (!line) return null
  if (!/\b(curl|wget|fetch|Invoke-WebRequest|iwr)\b/i.test(line)) return null
  const low = line.toLowerCase()
  const hasHTTP = low.includes('http://') || low.includes('https://')
  if (hasHTTP) {
    const re = /https?:\/\/([a-zA-Z0-9][-a-zA-Z0-9.]*[a-zA-Z0-9]|[a-zA-Z0-9])/gi
    for (;;) {
      const m = re.exec(line)
      if (m === null) break
      if (!_domainAllowedNode(m[1], allowed)) {
        return 'URL 域名不在 permissions.network_allowed_domains'
      }
    }
    return null
  }
  const host = _firstBareHostnameAfterNetTool(line)
  if (!host) return null
  if (!_domainAllowedNode(host, allowed)) {
    return 'URL 域名不在 permissions.network_allowed_domains'
  }
  return null
}

/** 与 go-local-proxy permissions.go 对齐：~/.config/agent-terminal/permissions.json（可选）
 * @returns {null|string|{ needConfirm: true, reason: string }} */
function checkAgentTerminalPermissionsNode(command, cwd, opts = {}) {
  const confirmed = opts.confirmed === true
  try {
    const f = path.join(os.homedir(), '.config', 'agent-terminal', 'permissions.json')
    if (!fs.existsSync(f)) return null
    const raw = fs.readFileSync(f, 'utf8')
    const j = JSON.parse(raw)
    const P = j.permissions || j.Permissions
    if (!P) return null
    if (!_cwdUnderWorkspaceRoot(cwd, P.workspace_root || P.workspaceRoot)) {
      return 'cwd 不在 permissions.workspace_root 允许范围内'
    }
    const line = String(command || '').trim()
    const maxSeg = Number(P.bash_max_subcommands ?? P.bashMaxSubcommands ?? 0)
    const allowArr = Array.isArray(P.allow) ? P.allow : []
    const autoTrust = !!(P.auto_confirm_trusted ?? P.autoConfirmTrusted)
    const skipBashMaxTrust =
      autoTrust && allowArr.length > 0 && _commandMatchesAnyAllowNode(line, allowArr)
    if (maxSeg > 0 && !confirmed && !skipBashMaxTrust) {
      const n = _countShellSegments(line)
      if (n > maxSeg) return { needConfirm: true, reason: 'bash_max_subcommands' }
    }
    const netDom = P.network_allowed_domains || P.networkAllowedDomains
    const netErr = _checkNetworkDomainsNode(line, Array.isArray(netDom) ? netDom : [])
    if (netErr) return netErr
    const deny = Array.isArray(P.deny) ? P.deny : []
    for (const d of deny) {
      const re = _permGlobToRegExp(d)
      if (re && re.test(line)) return '命令命中 permissions.deny'
    }
    const allow = allowArr
    if (allow.length === 0) return null
    for (const a of allow) {
      const re = _permGlobToRegExp(a)
      if (re && re.test(line)) return null
    }
    return '命令未匹配 permissions.allow'
  } catch {
    return null
  }
}

/** 与 go-local-proxy checkAgentTerminalWorkspaceCwd 对齐（纯 cd 更新会话前校验目标 cwd） */
function checkAgentTerminalWorkspaceCwdNode(cwd) {
  try {
    const f = path.join(os.homedir(), '.config', 'agent-terminal', 'permissions.json')
    if (!fs.existsSync(f)) return null
    const raw = fs.readFileSync(f, 'utf8')
    const j = JSON.parse(raw)
    const P = j.permissions || j.Permissions
    if (!P) return null
    if (!_cwdUnderWorkspaceRoot(cwd, P.workspace_root || P.workspaceRoot)) {
      return 'cwd 不在 permissions.workspace_root 允许范围内'
    }
    return null
  } catch {
    return null
  }
}

ipcMain.handle('terminal-check-workspace-cwd', async (event, targetCwd) => {
  const err = checkAgentTerminalWorkspaceCwdNode(String(targetCwd || '').trim())
  if (typeof err === 'string') {
    return { ok: false, error: err }
  }
  return { ok: true }
})

ipcMain.handle('terminal-exec-once', async (event, payload) => {
  const requestId = `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  const command = String(payload?.command || '').trim()
  if (!command) {
    return { requestId, exitCode: -1, stdout: '', stderr: 'empty command', cancelled: false }
  }
  const cwd = String(payload?.cwd || '').trim() || os.homedir()
  const permRes = checkAgentTerminalPermissionsNode(command, cwd, {
    confirmed: payload?.confirmed === true
  })
  if (permRes && typeof permRes === 'object' && permRes.needConfirm) {
    return {
      requestId,
      exitCode: -2,
      needConfirm: true,
      confirmReason: String(permRes.reason || 'bash_max_subcommands'),
      stdout: '',
      stderr: '',
      cancelled: false
    }
  }
  if (typeof permRes === 'string') {
    return { requestId, exitCode: -1, stdout: '', stderr: permRes, cancelled: false }
  }
  const timeoutSec = Math.min(86400, Math.max(1, Number(payload?.timeoutSec) || 60))
  const envExtra = payload?.env && typeof payload.env === 'object' ? payload.env : {}
  const env = { ...process.env, ...envExtra }

  let child = null
  let settled = false
  let stdout = ''
  let stderr = ''
  let timeoutTimer = null

  return await new Promise((resolve) => {
    const settle = (out) => {
      if (settled) return
      settled = true
      if (timeoutTimer) clearTimeout(timeoutTimer)
      terminalOnceById.delete(requestId)
      resolve(out)
    }

    const killTree = () => {
      if (!child || child.killed) return
      try {
        if (process.platform === 'win32' && child.pid) {
          spawn('taskkill', ['/pid', String(child.pid), '/f', '/t'], { windowsHide: true })
        } else {
          child.kill('SIGTERM')
        }
      } catch (_) {}
    }

    timeoutTimer = setTimeout(() => {
      killTree()
      settle({
        requestId,
        exitCode: -1,
        stdout,
        stderr: stderr + (stderr ? '\n' : '') + '[timeout]',
        cancelled: true
      })
    }, timeoutSec * 1000)

    try {
      if (process.platform === 'win32') {
        child = spawn(process.env.COMSPEC || 'cmd.exe', ['/d', '/s', '/c', command], {
          cwd,
          env,
          windowsHide: true
        })
      } else {
        child = spawn('/bin/bash', ['-lc', command], { cwd, env })
      }
    } catch (e) {
      settle({
        requestId,
        exitCode: -1,
        stdout: '',
        stderr: String(e.message || e),
        cancelled: false
      })
      return
    }

    terminalOnceById.set(requestId, { cancel: killTree })

    child.stdout?.on('data', (d) => {
      stdout += d.toString()
    })
    child.stderr?.on('data', (d) => {
      stderr += d.toString()
    })
    child.on('error', (e) => {
      stderr += String(e.message || e)
      settle({
        requestId,
        exitCode: -1,
        stdout,
        stderr,
        cancelled: false
      })
    })
    child.on('close', (code, signal) => {
      const cancelled = signal != null
      const exitCode = typeof code === 'number' ? code : -1
      settle({
        requestId,
        exitCode,
        stdout,
        stderr,
        cancelled
      })
    })
  })
})

ipcMain.on('terminal-exec-cancel', (event, requestId) => {
  const id = String(requestId || '').trim()
  if (!id) return
  const rec = terminalOnceById.get(id)
  if (rec && typeof rec.cancel === 'function') rec.cancel()
})

/** 停止生成 / 用户中止：杀掉当前所有一次性终端子进程 */
ipcMain.on('terminal-exec-cancel-all', () => {
  const ids = [...terminalOnceById.keys()]
  for (const id of ids) {
    const rec = terminalOnceById.get(id)
    if (rec && typeof rec.cancel === 'function') {
      try {
        rec.cancel()
      } catch (_) {
        /* ignore */
      }
    }
  }
})

// ===================== badcase-local-proxy URL 协议（当前用户 HKCU）=====================
function buildWindowsProtocolRegContent(exePath, scheme) {
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

const BADCASE_PROXY_INSTALL_DIR = 'BadCaseDoctor'

function defaultPathForLocalProxySave(filename) {
  const base = path.basename(String(filename || '').replace(/[/\\]/g, '')) || 'badcase-local-proxy.exe'
  if (process.platform === 'win32') {
    const pf = process.env.ProgramFiles || 'C:\\Program Files'
    return path.join(pf, BADCASE_PROXY_INSTALL_DIR, base)
  }
  if (process.platform === 'darwin') {
    return path.join('/opt', BADCASE_PROXY_INSTALL_DIR, base)
  }
  return path.join('/opt', BADCASE_PROXY_INSTALL_DIR, base)
}

function arrayBufferToBuffer(arrayBuffer) {
  if (arrayBuffer instanceof ArrayBuffer) {
    return Buffer.from(new Uint8Array(arrayBuffer))
  }
  if (Buffer.isBuffer(arrayBuffer)) {
    return arrayBuffer
  }
  if (arrayBuffer && arrayBuffer.buffer instanceof ArrayBuffer) {
    return Buffer.from(new Uint8Array(arrayBuffer.buffer))
  }
  return null
}

/**
 * 另存本地代理：可传 targetPath 直接写入；否则弹出「另存为」（默认 Program Files\\BadCaseDoctor 等）。
 */
ipcMain.handle('badcase-save-local-proxy', async (event, { filename, arrayBuffer, targetPath }) => {
  const buf = arrayBufferToBuffer(arrayBuffer)
  if (!buf) {
    return { ok: false, error: 'invalid_payload' }
  }

  const tp = String(targetPath || '').trim()
  if (tp) {
    try {
      const abs = path.normalize(tp)
      const dir = path.dirname(abs)
      fs.mkdirSync(dir, { recursive: true })
      fs.writeFileSync(abs, buf)
      return { ok: true, path: abs }
    } catch (e) {
      console.error('[badcase-save-local-proxy] direct write', e)
      return { ok: false, error: e.message || String(e) }
    }
  }

  const base = path.basename(String(filename || '').replace(/[/\\]/g, '')) || 'badcase-local-proxy.exe'
  const defaultPath = defaultPathForLocalProxySave(base)
  const win = BrowserWindow.getFocusedWindow() || mainWindow
  const dialogOpts = {
    title: '保存本地代理',
    defaultPath,
    buttonLabel: '保存'
  }
  if (process.platform === 'win32') {
    dialogOpts.filters = [{ name: 'Executable', extensions: ['exe'] }]
  }
  const r = await dialog.showSaveDialog(win || undefined, dialogOpts)
  if (r.canceled || !r.filePath) {
    return { ok: false, error: 'cancelled' }
  }
  try {
    fs.writeFileSync(r.filePath, buf)
    return { ok: true, path: r.filePath }
  } catch (e) {
    console.error('[badcase-save-local-proxy]', e)
    return { ok: false, error: e.message || String(e) }
  }
})

ipcMain.handle('badcase-pick-proxy-exe', async () => {
  if (process.platform !== 'win32') {
    return { ok: false, error: 'not_windows' }
  }
  const win = BrowserWindow.getFocusedWindow() || mainWindow
  const r = await dialog.showOpenDialog(win || undefined, {
    title: '选择 badcase-local-proxy.exe',
    filters: [{ name: 'Executable', extensions: ['exe'] }],
    properties: ['openFile']
  })
  if (r.canceled || !r.filePaths || !r.filePaths.length) {
    return { ok: false, error: 'cancelled' }
  }
  return { ok: true, path: r.filePaths[0] }
})

ipcMain.handle('badcase-register-local-proxy-protocol', async (event, exePath, scheme) => {
  if (process.platform !== 'win32') {
    return { ok: false, error: 'not_windows' }
  }
  const p = String(exePath || '').trim()
  if (!p.toLowerCase().endsWith('.exe')) {
    return { ok: false, error: 'invalid_exe' }
  }
  if (!fs.existsSync(p)) {
    return { ok: false, error: 'not_found' }
  }
  const tmp = path.join(os.tmpdir(), `badcase-local-proxy-protocol-${Date.now()}.reg`)
  try {
    const content = buildWindowsProtocolRegContent(p, scheme)
    fs.writeFileSync(tmp, '\ufeff' + content, 'utf16le')
    execFileSync('reg', ['import', tmp], { windowsHide: true })
    return { ok: true }
  } catch (e) {
    console.error('[badcase-protocol] reg import failed:', e)
    return { ok: false, error: e.message || String(e) }
  } finally {
    try {
      fs.unlinkSync(tmp)
    } catch (_) {
      /* ignore */
    }
  }
})