/**
 * FitAddon + PTY 尺寸同步（VS Code 由 TerminalInstance 承担；此处为嵌入式场景薄封装）。
 */
import type { Terminal } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'

const LAYOUT_RAF_MAX = 24

function renderServiceReady(term: Terminal | null): boolean {
  try {
    const core = (term as unknown as { _core?: { _renderService?: { dimensions?: { css?: { cell?: { width?: number } } } } } })
      ._core
    const w = core?._renderService?.dimensions?.css?.cell?.width ?? 0
    return w > 0
  } catch {
    return false
  }
}

export interface VscodeXtermFitLayoutOptions {
  /** 在 fit 成功且 cols/rows 有效后调用（用于 term_resize） */
  onSyncedDimensions: (cols: number, rows: number) => void
  /**
   * FitAddon 算出满屏行数后再减少的逻辑行数（仍占满宿主高度，底部为栅格内留白，非外层 padding）。
   * 用于避免提示符贴住容器底边；PTY `term_resize` 与 xterm 行数一致。
   */
  reserveBottomRows?: number
}

export function createVscodeXtermFitLayout(
  term: Terminal,
  fit: FitAddon,
  getHostEl: () => HTMLElement | null | undefined,
  opts: VscodeXtermFitLayoutOptions
) {
  let layoutTimer: ReturnType<typeof setTimeout> | null = null
  let layoutRaf = 0

  function clearTimers() {
    if (layoutTimer != null) {
      clearTimeout(layoutTimer)
      layoutTimer = null
    }
    if (layoutRaf) {
      cancelAnimationFrame(layoutRaf)
      layoutRaf = 0
    }
  }

  function fitNow(retryDepth = 0): boolean {
    const el = getHostEl()
    if (!term || !el) return false
    if ((el.clientWidth || 0) < 8 || (el.clientHeight || 0) < 8) return false

    if (!renderServiceReady(term)) {
      if (retryDepth >= LAYOUT_RAF_MAX) return false
      layoutRaf = requestAnimationFrame(() => {
        layoutRaf = 0
        fitNow(retryDepth + 1)
      })
      return false
    }

    try {
      fit.fit()
    } catch {
      return false
    }

    const reserve = Math.max(0, Math.floor(Number(opts.reserveBottomRows) || 0))
    if (
      reserve > 0 &&
      Number.isFinite(term.rows) &&
      term.rows > reserve + 1 &&
      typeof term.resize === 'function'
    ) {
      try {
        term.resize(term.cols, Math.max(2, term.rows - reserve))
      } catch {
        /* ignore */
      }
    }

    if (Number.isFinite(term.cols) && term.cols >= 2) {
      opts.onSyncedDimensions(term.cols, term.rows)
    }
    return true
  }

  function schedule(ms: number) {
    if (layoutTimer != null) clearTimeout(layoutTimer)
    layoutTimer = setTimeout(() => {
      layoutTimer = null
      fitNow(0)
    }, ms)
  }

  function dispose() {
    clearTimers()
  }

  return { fitNow, schedule, dispose, clearTimers }
}
