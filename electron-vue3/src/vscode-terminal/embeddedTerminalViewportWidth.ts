/**
 * 简化版「随内容加宽」：对齐 VS Code `toggleSizeToContentWidth` 思路（terminalInstance.ts），
 * 不实现 Workbench 水平滚动条与 fixed-dims 全套，仅 minWidth + fit + term_resize。
 */
import type { Terminal } from '@xterm/xterm'

export function computeLongestViewportWrappedLineLength(term: Terminal): number {
  const buf = term.buffer.active
  const vy = buf.viewportY
  const processed = new Set<number>()
  let maxLen = term.cols

  for (let i = 0; i < term.rows; i += 1) {
    const y = vy + i
    if (y >= buf.length || processed.has(y)) continue
    const line = buf.getLine(y)
    if (!line) continue

    let y0 = y
    while (y0 > 0) {
      const l = buf.getLine(y0)
      if (!l?.isWrapped) break
      y0 -= 1
    }

    let total = 0
    let yy = y0
    while (yy < buf.length) {
      const l = buf.getLine(yy)
      if (!l) break
      processed.add(yy)
      total += l.translateToString(false).length
      yy += 1
      const next = buf.getLine(yy)
      if (!next?.isWrapped) break
    }
    maxLen = Math.max(maxLen, total)
  }

  return Math.min(Math.max(maxLen + 2, term.cols), 2048)
}

export function getTerminalCellWidthPx(term: Terminal): number {
  const w = term.dimensions?.css?.cell?.width
  if (w && w > 0) return w
  return 8
}

export function applyContentWidthMinSize(term: Terminal, hostEl: HTMLElement, cols: number): void {
  const cw = getTerminalCellWidthPx(term)
  const padH = 28
  hostEl.style.minWidth = `${Math.ceil(cols * cw + padH)}px`
}

export function clearContentWidthMinSize(hostEl: HTMLElement | null | undefined): void {
  if (hostEl) hostEl.style.minWidth = ''
}
