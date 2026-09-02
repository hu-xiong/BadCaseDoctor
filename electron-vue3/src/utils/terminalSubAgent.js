/**
 * 终端子 Agent：与 docs/终端子agent.md 对齐的前端抽象（Web：go-local-proxy WS；Electron：IPC 一次性 spawn）。
 */
import { runLocalShellProxyCommand } from './localShellProxyClient.js'
import { isElectronShell } from './electronPtySocketAdapter.js'

// 会话管理
class SessionManager {
  constructor() {
    this.currentSession = null
    this.sessions = new Map()
  }
  
  createSession() {
    const sessionId = `session_${Math.random().toString(36).substr(2, 8)}`
    this.currentSession = sessionId
    this.sessions.set(sessionId, {
      id: sessionId,
      startTime: Date.now(),
      commands: []
    })
    return sessionId
  }
  
  getCurrentSession() {
    if (!this.currentSession) {
      this.createSession()
    }
    return this.currentSession
  }
  
  addCommand(sessionId, command) {
    const session = this.sessions.get(sessionId)
    if (session) {
      session.commands.push({
        command,
        timestamp: Date.now()
      })
    }
  }
  
  listSessions() {
    return Array.from(this.sessions.keys())
  }
}

const sessionManager = new SessionManager()

// 生成日志引用
export function generateLogReference(sessionId, startLine, endLine) {
  return `@log:${sessionId}#L${startLine}-L${endLine}`
}

// 解析日志引用
export function parseLogReference(reference) {
  const pattern = /@log:(session_[a-f0-9]+)#L(\d+)-L(\d+)/
  const match = pattern.exec(reference)
  if (!match) return null
  return {
    sessionId: match[1],
    startLine: parseInt(match[2]),
    endLine: parseInt(match[3])
  }
}

// allow/deny/workspace/网络/子段数 由 ~/.config/agent-terminal/permissions.json 在 go-local-proxy / Electron 执行路径校验；
// 此处为补充硬编码高危模式（与文档「危险模式检测」一致），不替代权限文件。
const DANGER_HINTS = [
  { re: /\brm\s+(-[rfRF]+\s*)+.*(\/\s|$|\/\*)/, reason: 'rm 递归删除路径' },
  { re: /:\(\)\s*\{\s*:\|:&\s*\}\s*;/, reason: 'fork 炸弹' },
  { re: /\bsudo\b/i, reason: 'sudo 提权' },
  { re: /\bdd\s+if=/i, reason: 'dd 块设备写入' },
  { re: /\bchmod\s+[-+]?[rwxXstugoa]*777\b/i, reason: 'chmod 777' },
  { re: />\s*\/dev\/(sd[a-z]|nvme|disk)/i, reason: '重定向到块设备' }
]

/**
 * @param {string} command
 * @returns {{ needConfirm: boolean, reason?: string }}
 */
export function analyzeTerminalRisk(command) {
  const s = String(command || '').trim()
  if (!s) return { needConfirm: false }
  for (const { re, reason } of DANGER_HINTS) {
    if (re.test(s)) return { needConfirm: true, reason }
  }
  return { needConfirm: false }
}

/**
 * Windows cmd 无 pwd；模型常误发单行 pwd。无复合运算符时映射为 cd，以打印当前目录。
 * @param {string} rawCommand
 * @returns {string}
 */
export function normalizeTerminalCommandForClient(rawCommand) {
  const s = String(rawCommand || '').trim()
  if (!s) return s
  const isWin =
    typeof navigator !== 'undefined' &&
    (/Win/i.test(navigator.userAgent || '') || /Win/i.test(navigator.platform || ''))
  if (!isWin) return s
  if (/[&|;\n]/.test(s)) return s
  if (/^pwd\s*$/i.test(s)) return 'cd'
  return s
}

/**
 * 整行仅为 cd（无 && ; | 与换行）：只更新会话 cwd，不启子进程（与文档「cd 更新会话」一致）。
 * @param {string} command
 * @returns {{ arg: string } | null}
 */
export function tryParsePureCdCommand(command) {
  const s = String(command || '').trim()
  if (!s) return null
  if (/[&|;\n]/.test(s)) return null
  if (/^cd\s*$/i.test(s)) return { arg: '' }
  const m = s.match(/^cd\s+(.+)\s*$/i)
  if (!m) return null
  return { arg: String(m[1] || '').trim() }
}

/**
 * @param {string} base 当前工作目录
 * @param {string} arg cd 参数（可含引号）
 */
function normalizeCdPath(base, arg) {
  let t = String(arg || '').trim()
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    t = t.slice(1, -1).trim()
  }
  const b = String(base || '').trim()
  if (!t || t === '.') return b
  const useWin =
    /\\/.test(b) ||
    /\\/.test(t) ||
    /^[A-Za-z]:[\\/]/i.test(b) ||
    /^[A-Za-z]:[\\/]/i.test(t) ||
    (typeof navigator !== 'undefined' && /Win/i.test(navigator.userAgent || ''))
  const split = useWin ? /[/\\]+/ : /\//
  const sep = useWin ? '\\' : '/'
  const abs =
    (!useWin && t.startsWith('/')) ||
    (useWin && (/^[A-Za-z]:[\\/]/i.test(t) || t.startsWith('\\\\')))
  const mergePop = (parts) => {
    const st = []
    for (const p of parts) {
      if (!p || p === '.') continue
      if (p === '..') st.pop()
      else st.push(p)
    }
    return st
  }
  if (abs) {
    if (!useWin && t.startsWith('/')) {
      const st = mergePop(t.split(split).filter(Boolean))
      return '/' + st.join('/')
    }
    if (/^[A-Za-z]:[\\/]/i.test(t)) {
      const drive = t.slice(0, 2).toUpperCase()
      const rest = t.slice(2).replace(/^[/\\]+/, '')
      const st = mergePop(rest.split(split).filter(Boolean))
      return drive + sep + st.join(sep)
    }
    if (t.startsWith('\\\\')) {
      return t
    }
  }
  const baseParts = b ? b.split(split).filter(Boolean) : []
  const relParts = t.split(split).filter(Boolean)
  const st = mergePop([...baseParts, ...relParts])
  if (!useWin && b.startsWith('/')) {
    return '/' + st.join('/')
  }
  if (useWin && baseParts.length && /^[A-Za-z]:$/i.test(baseParts[0])) {
    const drive = baseParts[0].slice(0, 2).toUpperCase()
    const restStack = mergePop([...baseParts.slice(1), ...relParts])
    return drive + sep + restStack.join(sep)
  }
  return st.join(sep)
}

function applySessionCd(session, mergedCwd, cdArg) {
  const next = normalizeCdPath(mergedCwd, cdArg)
  session.cwd = next
  const msg = `工作目录已更新: ${next || '(空)'}\n`
  return msg
}

/**
 * @param {{
 *   command: string,
 *   exitCode: number,
 *   stdout?: string,
 *   stderr?: string,
 *   cancelled?: boolean,
 *   error?: string,
 *   proxyDown?: boolean
 * }} p
 */
export function formatTerminalResultBlock(p) {
  const cmd = String(p.command || '').trim()
  const lines = [`命令: ${cmd}`]
  if (p.proxyDown) {
    lines.push('状态: 本地代理未就绪，未能自动执行。请在本机终端手动运行上述命令。')
    return lines.join('\n')
  }
  if (p.error) {
    lines.push(`状态: 失败 — ${p.error}`)
    return lines.join('\n')
  }
  if (p.cancelled) {
    lines.push('状态: 已取消')
  } else {
    lines.push(`退出码: ${p.exitCode}`)
  }
  const out = String(p.stdout || '')
  const err = String(p.stderr || '')
  if (out) lines.push('--- stdout ---\n' + out)
  if (err) lines.push('--- stderr ---\n' + err)
  return lines.join('\n')
}

function createWebTerminalAgent(localProxyOkRef) {
  const session = { cwd: '', env: {} }
  const active = new Map()

  return {
    setCwd(path) {
      session.cwd = String(path || '').trim()
    },
    setEnv(key, value) {
      session.env[String(key)] = String(value)
    },
    cancel(requestId) {
      const id = String(requestId || '')
      const h = active.get(id)
      if (h) h.cancel()
    },
    async exec(command, onData, options = {}) {
      const cmd = String(command || '').trim()
      if (!cmd) throw new Error('empty command')
      if (options.abortSignal?.aborted) {
        return { exitCode: -1, stdout: '', stderr: '', cancelled: true, requestId: '' }
      }

      const sessionId = sessionManager.getCurrentSession()
      sessionManager.addCommand(sessionId, cmd)

      const mergedCwd = String(options.cwd || session.cwd || '').trim()
      const cdOnly = tryParsePureCdCommand(cmd)
      if (cdOnly) {
        const msg = applySessionCd(session, mergedCwd, cdOnly.arg)
        if (typeof onData === 'function') onData('stdout', msg)
        return { exitCode: 0, stdout: msg, stderr: '', requestId: '', sessionId }
      }
      const timeout = Math.min(86400, Math.max(1, Number(options.timeout) || 60))
      const risk = analyzeTerminalRisk(cmd)
      if (risk.needConfirm && !options.confirmed) {
        const err = new Error('confirm_required')
        err.code = 'confirm_required'
        err.reason = risk.reason
        err.details = cmd
        throw err
      }

      const proxyUp =
        typeof localProxyOkRef === 'function'
          ? localProxyOkRef()
          : localProxyOkRef && typeof localProxyOkRef === 'object' && 'value' in localProxyOkRef
            ? !!localProxyOkRef.value
            : true

      if (!proxyUp) {
        return {
          exitCode: -1,
          stdout: '',
          stderr: '',
          proxyDown: true,
          requestId: '',
          sessionId
        }
      }

      let confirmedFlag = options.confirmed === true
      let stdout = ''
      let stderr = ''
      
      for (let attempt = 0; attempt < 4; attempt++) {
        const { id, promise, cancel } = runLocalShellProxyCommand(cmd, {
          cwd: mergedCwd,
          timeoutSec: timeout,
          env: { ...session.env, ...(options.env || {}) },
          abortSignal: options.abortSignal,
          confirmed: confirmedFlag,
          onChunk: (stream, data) => {
            if (stream === 'stdout') stdout += data
            if (stream === 'stderr') stderr += data
            if (typeof onData === 'function') onData(stream, data)
          }
        })
        active.set(id, { cancel })
        try {
          const r = await promise
          // 发送日志到后端
          if (typeof window !== 'undefined' && window.api?.logTerminalOutput) {
            window.api.logTerminalOutput({
              sessionId,
              stdout: r.stdout || stdout,
              stderr: r.stderr || stderr
            })
          }
          return { ...r, requestId: id, sessionId }
        } catch (e) {
          if (e && e.code === 'PROXY_CONFIRM_REQUIRED' && !confirmedFlag) {
            const msg = `本地策略：子命令/管道段数较多（bash_max_subcommands）。\n确认在了解风险后仍要执行？\n\n${cmd.slice(0, 500)}`
            const ok =
              typeof window !== 'undefined' &&
              window.confirm(msg)
            if (!ok) {
              return {
                exitCode: -1,
                stdout: '',
                stderr: '用户取消子命令段数确认',
                cancelled: false,
                requestId: id,
                sessionId
              }
            }
            confirmedFlag = true
            continue
          }
          throw e
        } finally {
          active.delete(id)
        }
      }
      return { exitCode: -1, stdout: '', stderr: '子命令确认重试次数过多', cancelled: false, requestId: '', sessionId }
    }
  }
}

function createElectronTerminalAgent() {
  const api = typeof window !== 'undefined' ? window.electronTerminalAgent : null
  const session = { cwd: '', env: {} }
  if (!api || typeof api.execOnce !== 'function') {
    return null
  }
  return {
    setCwd(path) {
      session.cwd = String(path || '').trim()
    },
    setEnv(key, value) {
      session.env[String(key)] = String(value)
    },
    cancel(requestId) {
      try {
        api.cancel?.(String(requestId || ''))
      } catch (_) {
        /* ignore */
      }
    },
    async exec(command, onData, options = {}) {
      const cmd = String(command || '').trim()
      if (!cmd) throw new Error('empty command')
      if (options.abortSignal?.aborted) {
        return { exitCode: -1, stdout: '', stderr: '', cancelled: true, requestId: '' }
      }

      const sessionId = sessionManager.getCurrentSession()
      sessionManager.addCommand(sessionId, cmd)

      const mergedCwd = String(options.cwd || session.cwd || '').trim()
      const cdOnly = tryParsePureCdCommand(cmd)
      if (cdOnly) {
        const newCwd = normalizeCdPath(mergedCwd, cdOnly.arg)
        if (typeof api.checkWorkspaceCwd === 'function') {
          try {
            const chk = await api.checkWorkspaceCwd(newCwd)
            if (chk && chk.ok === false) {
              const errText = String(
                chk.error || 'cwd 不在 permissions.workspace_root 允许范围内'
              )
              if (typeof onData === 'function') onData('stderr', errText + '\n')
              return {
                exitCode: -1,
                stdout: '',
                stderr: errText,
                requestId: '',
                sessionId
              }
            }
          } catch (e) {
            const errText = `校验工作区失败: ${String(e?.message || e)}`
            if (typeof onData === 'function') onData('stderr', errText + '\n')
            return {
              exitCode: -1,
              stdout: '',
              stderr: errText,
              requestId: '',
              sessionId
            }
          }
        }
        const msg = applySessionCd(session, mergedCwd, cdOnly.arg)
        if (typeof onData === 'function') onData('stdout', msg)
        return { exitCode: 0, stdout: msg, stderr: '', requestId: '', sessionId }
      }
      const risk = analyzeTerminalRisk(cmd)
      if (risk.needConfirm && !options.confirmed) {
        const err = new Error('confirm_required')
        err.code = 'confirm_required'
        err.reason = risk.reason
        err.details = cmd
        throw err
      }
      const payload = {
        command: cmd,
        cwd: mergedCwd,
        timeoutSec: Math.min(86400, Math.max(1, Number(options.timeout) || 60)),
        env: { ...session.env, ...(options.env || {}) }
      }
      let res = await api.execOnce(payload)
      if (res?.needConfirm === true && options.confirmed !== true) {
        const msg = `本地策略：子命令/管道段数较多（bash_max_subcommands）。\n确认在了解风险后仍要执行？\n\n${cmd.slice(0, 500)}`
        const ok = typeof window !== 'undefined' && window.confirm(msg)
        if (!ok) {
          return {
            exitCode: -1,
            stdout: '',
            stderr: '用户取消子命令段数确认',
            cancelled: false,
            requestId: String(res?.requestId || ''),
            sessionId
          }
        }
        res = await api.execOnce({ ...payload, confirmed: true })
      }
      const stdout = String(res?.stdout || '')
      const stderr = String(res?.stderr || '')
      if (typeof onData === 'function') {
        if (stdout) onData('stdout', stdout)
        if (stderr) onData('stderr', stderr)
      }
      
      // 发送日志到后端
      if (typeof window !== 'undefined' && window.api?.logTerminalOutput) {
        window.api.logTerminalOutput({
          sessionId,
          stdout,
          stderr
        })
      }
      
      return {
        exitCode: Number(res?.exitCode),
        stdout,
        stderr,
        cancelled: !!res?.cancelled,
        requestId: String(res?.requestId || ''),
        sessionId
      }
    }
  }
}

/**
 * @param {{ value?: boolean } | (() => boolean)} [localProxyOkRef] 浏览器下是否已探测到本机代理（可选）
 */
export function createTerminalAgent(localProxyOkRef) {
  if (isElectronShell()) {
    const e = createElectronTerminalAgent()
    if (e) return e
  }
  return createWebTerminalAgent(localProxyOkRef)
}

function buildQueueOutcome(command, partial) {
  const text = formatTerminalResultBlock({ command, ...partial })
  const cancelled = !!partial.cancelled
  const proxyDown = !!partial.proxyDown
  const hasError = partial.error != null && String(partial.error).trim() !== ''
  const ec =
    partial.exitCode === undefined || partial.exitCode === null
      ? -1
      : Number(partial.exitCode)
  const ok = !proxyDown && !cancelled && !hasError && ec === 0
  return {
    text,
    ok,
    cancelled,
    proxyDown,
    command: String(command || ''),
    cwd: String(partial.cwd || ''),
    exitCode: ec,
    stdout: String(partial.stdout || ''),
    stderr: String(partial.stderr || ''),
    error: partial.error != null ? String(partial.error) : ''
  }
}

/**
 * @param {ReturnType<typeof createTerminalAgent>} agent
 * @param {{ command: string, cwd?: string, timeout?: number, stop_on_error?: boolean }} item
 * @param {{ confirmFn?: (msg: string) => boolean, abortSignal?: AbortSignal }} [opts]
 * @returns {Promise<{ text: string, ok: boolean, cancelled: boolean, proxyDown?: boolean } | null>}
 */
export async function runTerminalQueueItem(agent, item, opts = {}) {
  const { confirmFn, abortSignal } = opts || {}
  const rawCommand = String(item.command || '').trim()
  if (!rawCommand) return null
  const command = normalizeTerminalCommandForClient(rawCommand)
  const displayCommand =
    command !== rawCommand ? `${rawCommand}（本机执行: ${command}）` : rawCommand
  const cwd = String(item.cwd || '').trim()
  const timeout = Math.min(86400, Math.max(1, Number(item.timeout) || 60))

  const tryExec = async (confirmed) => {
    return agent.exec(
      command,
      () => {},
      { cwd: cwd || undefined, timeout, confirmed, abortSignal }
    )
  }

  try {
    const r = await tryExec(false)
    return buildQueueOutcome(displayCommand, {
      cwd,
      exitCode: r.exitCode,
      stdout: r.stdout,
      stderr: r.stderr,
      cancelled: r.cancelled,
      proxyDown: r.proxyDown
    })
  } catch (e) {
    const aborted = e && (e.name === 'AbortError' || e.code === 20)
    if (aborted) {
      return buildQueueOutcome(displayCommand, {
        cwd,
        exitCode: -1,
        error: '用户停止生成，命令已中止',
        cancelled: true
      })
    }
    if (e && e.code === 'confirm_required') {
      const msg = `即将执行可能高风险的命令：\n${rawCommand}\n原因：${e.reason || '策略命中'}\n\n是否继续？`
      const okDlg =
        typeof confirmFn === 'function'
          ? confirmFn(msg)
          : typeof window !== 'undefined' &&
            window.confirm(
              `即将执行可能高风险的命令：\n${rawCommand}\n原因：${e.reason || '策略命中'}\n\n是否继续？`
            )
      if (!okDlg) {
        return buildQueueOutcome(displayCommand, {
          cwd,
          exitCode: -1,
          error: '用户拒绝执行（confirm_required）'
        })
      }
      try {
        const r = await tryExec(true)
        return buildQueueOutcome(displayCommand, {
          cwd,
          exitCode: r.exitCode,
          stdout: r.stdout,
          stderr: r.stderr,
          cancelled: r.cancelled,
          proxyDown: r.proxyDown
        })
      } catch (e2) {
        if (e2 && (e2.name === 'AbortError' || e2.code === 20)) {
          return buildQueueOutcome(displayCommand, {
            cwd,
            exitCode: -1,
            error: '用户停止生成，命令已中止',
            cancelled: true
          })
        }
        return buildQueueOutcome(displayCommand, {
          cwd,
          exitCode: -1,
          error: String(e2?.message || e2)
        })
      }
    }
    return buildQueueOutcome(displayCommand, {
      cwd,
      exitCode: -1,
      error: String(e?.message || e)
    })
  }
}

/**
 * 子 Agent 结果 → 主 Agent 请求体字段 client_terminal_results
 * @param {Array<{ command?: string, cwd?: string, exitCode?: number, stdout?: string, stderr?: string, ok?: boolean, cancelled?: boolean, proxyDown?: boolean, error?: string }>} outcomes
 */
export function toClientTerminalResultsPayload(outcomes) {
  const list = Array.isArray(outcomes) ? outcomes : []
  return list
    .filter((o) => o && String(o.command || '').trim())
    .map((o) => ({
      command: String(o.command || ''),
      cwd: String(o.cwd || ''),
      exit_code: Number(o.exitCode ?? -1),
      ok: !!o.ok,
      cancelled: !!o.cancelled,
      proxy_down: !!o.proxyDown,
      stdout: String(o.stdout || ''),
      stderr: String(o.stderr || ''),
      error: String(o.error || '')
    }))
}
