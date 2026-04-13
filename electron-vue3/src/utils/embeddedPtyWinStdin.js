/**
 * Windows ConPTY + PowerShell/PSReadLine：退格常认 BS(0x08)；浏览器 xterm 默认常发 DEL(0x7F)。
 * 仅在发往 PTY 的 stdin 上做 DEL→BS；勿对 xterm 本地 term.write 补「\b \b」——会与 PTY 回显打架，
 * 且会按栅格盲擦，把 PS 提示符一并擦掉。
 */
const DEL = '\u007f'
const BS = '\u0008'

export function normalizeConptyStdinDelToBs(data) {
  if (typeof data !== 'string' || data.length === 0) return data
  if (data.indexOf(DEL) < 0) return data
  return data.replace(/\u007f/g, BS)
}
