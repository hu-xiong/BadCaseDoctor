/**
 * 将单行 Shell 命令拆成片段，供聊天内「Cursor 式」终端卡片语法着色（仅展示，非执行解析）。
 * @returns {{ kind: 'ws'|'kw'|'str'|'op'|'flag'|'plain', text: string }[]}
 */
const KEYWORDS = new Set([
  'cd',
  'npm',
  'npx',
  'yarn',
  'pnpm',
  'git',
  'node',
  'deno',
  'bun',
  'cargo',
  'go',
  'make',
  'docker',
  'kubectl',
  'python',
  'pip',
  'pip3',
  'conda',
  'echo',
  'cat',
  'ls',
  'dir',
  'rm',
  'mkdir',
  'rmdir',
  'curl',
  'wget',
  'powershell',
  'pwsh',
  'cmd',
  'rustc',
  'gcc',
  'g++',
  'clang',
  'dotnet',
  'mvn',
  'gradle',
  'chmod',
  'chown',
  'sudo',
  'apt',
  'brew',
  'scp',
  'ssh',
  'grep',
  'sed',
  'awk',
  'find',
  'which',
  'where',
  'type',
  'cls',
  'copy',
  'move',
  'del'
])

export function shellCommandHighlightParts(input) {
  const s = String(input ?? '')
  const parts = []
  let i = 0

  const push = (kind, text) => {
    if (!text) return
    const last = parts[parts.length - 1]
    if (last && last.kind === kind && kind === 'plain') {
      last.text += text
      return
    }
    parts.push({ kind, text })
  }

  while (i < s.length) {
    const c = s[i]
    if (/\s/.test(c)) {
      let j = i
      while (j < s.length && /\s/.test(s[j])) j++
      push('ws', s.slice(i, j))
      i = j
      continue
    }
    if (c === '"' || c === "'") {
      const q = c
      let j = i + 1
      while (j < s.length) {
        if (s[j] === '\\' && j + 1 < s.length) {
          j += 2
          continue
        }
        if (s[j] === q) {
          j++
          break
        }
        j++
      }
      push('str', s.slice(i, j))
      i = j
      continue
    }
    if (s.startsWith('&&', i) || s.startsWith('||', i)) {
      push('op', s.slice(i, i + 2))
      i += 2
      continue
    }
    if (';&|'.includes(c)) {
      push('op', c)
      i++
      continue
    }
    if (c === '>' || c === '<') {
      let j = i + 1
      if (j < s.length && s[j] === c) j++
      push('op', s.slice(i, j))
      i = j
      continue
    }

    let j = i
    while (j < s.length) {
      if (/\s/.test(s[j])) break
      if ('"\';><&|'.includes(s[j])) break
      if (s.startsWith('&&', j) || s.startsWith('||', j)) break
      j++
    }
    const token = s.slice(i, j)
    if (!token) {
      i++
      continue
    }
    const low = token.toLowerCase()
    if (KEYWORDS.has(low)) push('kw', token)
    else if (/^--?[\w-]+$/.test(token)) push('flag', token)
    else push('plain', token)
    i = j
  }

  return parts.length ? parts : [{ kind: 'plain', text: s }]
}
