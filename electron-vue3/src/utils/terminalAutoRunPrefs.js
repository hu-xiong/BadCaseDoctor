/**
 * 本机终端命令自动执行策略（localStorage，与 Cursor「Auto-Run」概念对齐）。
 */

const LS_MODE = 'badcase_terminal_auto_run_mode'
const LS_ALLOW = 'badcase_terminal_cmd_allowlist'

/** @typedef {'ask' | 'allowlist' | 'everything'} TerminalAutoRunMode */

const DEFAULT_ALLOWLIST = [
  'cd',
  'npm',
  'npx',
  'yarn',
  'pnpm',
  'git',
  'echo',
  'dir',
  'ls',
  'pwd',
  'type',
  'where',
  'cls',
  'copy',
  'move',
  'del',
  'mkdir',
  'rmdir',
  'cat',
  'curl',
  'wget',
  'node',
  'python',
  'pip',
  'pip3',
  'go',
  'cargo',
  'dotnet',
  'mvn',
  'gradle',
  'docker',
  'kubectl',
  'chmod',
  'grep',
  'find',
  'scp',
  'ssh',
  'powershell',
  'pwsh',
  'cmd',
  'rustc',
  'gcc',
  'g++',
  'clang',
  'sudo',
  'apt',
  'brew'
]

/** @returns {TerminalAutoRunMode} */
export function getTerminalAutoRunMode() {
  try {
    const v = localStorage.getItem(LS_MODE)
    if (v === 'ask' || v === 'allowlist' || v === 'everything') return v
  } catch {
    /* ignore */
  }
  return 'everything'
}

/** @param {TerminalAutoRunMode} m */
export function setTerminalAutoRunMode(m) {
  try {
    if (m === 'ask' || m === 'allowlist' || m === 'everything') {
      localStorage.setItem(LS_MODE, m)
    }
  } catch {
    /* ignore */
  }
}

/** @returns {Set<string>} */
export function getTerminalAllowlistSet() {
  try {
    const raw = localStorage.getItem(LS_ALLOW)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr) && arr.length) {
        return new Set(arr.map((x) => String(x).toLowerCase().trim()).filter(Boolean))
      }
    }
  } catch {
    /* ignore */
  }
  return new Set(DEFAULT_ALLOWLIST.map((x) => x.toLowerCase()))
}

/**
 * 将首个 shell 词加入白名单（小写存储）。
 * @param {string} cmd
 */
export function addFirstTokenToTerminalAllowlist(cmd) {
  const tok = firstShellToken(cmd)
  if (!tok) return
  const s = getTerminalAllowlistSet()
  s.add(tok)
  try {
    localStorage.setItem(LS_ALLOW, JSON.stringify([...s].sort()))
  } catch {
    /* ignore */
  }
}

/**
 * 取命令第一个词（粗略，与 allowlist 匹配用）。
 * @param {string} cmd
 * @returns {string} lowercase
 */
export function firstShellToken(cmd) {
  const m = String(cmd || '')
    .trim()
    .match(/^(\S+)/)
  if (!m) return ''
  return m[1].replace(/^["'`]|["'`]$/g, '').toLowerCase()
}

/**
 * @param {string} cmd
 * @returns {boolean}
 */
export function canRunUnderTerminalAllowlist(cmd) {
  const t = firstShellToken(cmd)
  if (!t) return false
  return getTerminalAllowlistSet().has(t)
}
