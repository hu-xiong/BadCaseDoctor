/**
 * 嵌入式 PTY 排障：浏览器控制台执行
 *   localStorage.setItem('badcasePtyDebug', '1'); location.reload()
 * 关闭：removeItem('badcasePtyDebug')
 * 怀疑 WebGL 黑屏：localStorage.setItem('badcasePtyNoWebGL', '1'); location.reload()
 *
 * 查「ll 报错后提示符/输入行不见」：每条 term_output 打 UTF-8 + 转义可见形式（不依赖 DEV）：
 *   localStorage.setItem('badcasePtyRawOutput', '1'); location.reload()
 * 关闭：removeItem('badcasePtyRawOutput')
 *
 * 查「光标与换行/提示符不同步」：打 xterm 缓冲区光标、cell 像素、宿主宽与 term.cols 推算列数差：
 *   localStorage.setItem('badcasePtyCursorTrace', '1'); location.reload()
 * 建议与 badcasePtyDebug=1 同开；关闭：removeItem('badcasePtyCursorTrace')
 *
 * badcasePtyDebug=1 时还会：xterm 挂载后 / term_started 后各打一条 win32InputMode 状态；
 * 以及前 15 条 term_input 的 UTF-8 字节长 + 转义预览（判断退格/方向键编码是否进 WS）。
 */

export function badcasePtyDebugEnabled() {
  try {
    if (localStorage.getItem('badcasePtyDebug') === '0') return false
    if (localStorage.getItem('badcasePtyDebug') === '1') return true
    return !!import.meta.env?.DEV
  } catch {
    return !!import.meta.env?.DEV
  }
}

export function badcasePtyNoWebGL() {
  try {
    return localStorage.getItem('badcasePtyNoWebGL') === '1'
  } catch {
    return false
  }
}

/** 每条 term_output 打印原始字节中的 ESC/CR/LF 等，用于区分「Socket 里就没提示符行」vs「有清行序列导致 xterm 擦掉」 */
export function badcasePtyRawOutputEnabled() {
  try {
    return localStorage.getItem('badcasePtyRawOutput') === '1'
  } catch {
    return false
  }
}

function u8ToUtf8Lossy(u8) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return ''
  try {
    return new TextDecoder('utf-8', { fatal: false }).decode(u8)
  } catch {
    return ''
  }
}

/** 把不可见字节展开为 \e \r \n 与 \xNN，便于肉眼搜 CSI（如 \e[K 清到行尾、\e[1A 上移一行） */
function u8ToEscapeVisible(u8, maxLen = 800) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return ''
  const n = Math.min(u8.length, maxLen)
  let s = ''
  for (let i = 0; i < n; i += 1) {
    const c = u8[i]
    if (c === 0x1b) s += '\\e'
    else if (c === 0x0d) s += '\\r'
    else if (c === 0x0a) s += '\\n'
    else if (c === 0x09) s += '\\t'
    else if (c >= 32 && c < 127) s += String.fromCharCode(c)
    else s += `\\x${c.toString(16).padStart(2, '0')}`
  }
  if (u8.length > maxLen) s += ` …(+${u8.length - maxLen} bytes)`
  return s
}

export function badcasePtyLogRawTermOutput(u8, meta = {}) {
  if (!badcasePtyRawOutputEnabled()) return
  const utf8 = u8ToUtf8Lossy(u8)
  const esc = u8ToEscapeVisible(u8)
  console.warn('[badcase-pty] raw term_output', {
    bytes: u8.length,
    ...meta,
    utf8Preview: utf8.slice(0, 500),
    escapePreview: esc
  })
}

export function badcasePtyLog(...args) {
  if (badcasePtyDebugEnabled()) {
    // 用 warn：避免控制台只开「错误/警告」时看不到 log；setItem 返回 undefined 属正常，需整页刷新后再看终端行为也可
    console.warn('[badcase-pty]', ...args)
  }
}

export function badcasePtyCursorTraceEnabled() {
  try {
    return localStorage.getItem('badcasePtyCursorTrace') === '1'
  } catch {
    return false
  }
}

/**
 * 深度定位「PTY 列宽 / fit 列宽 / 渲染 cell」与「缓冲区光标」是否一致。
 * 若 inferredColsFromHost 与 term.cols 差大：多为宿主被 min-width 撑开、padding、或字体未就绪导致 fit 列数失真。
 * 若 term.cols 与 lastSentCols 长期不等：term_resize 未跟上或 emitResize 被跳过。
 */
export function badcasePtyLogCursorTrace(term, hostEl, meta = {}) {
  if (!badcasePtyCursorTraceEnabled()) return
  const row = {
    t: typeof performance !== 'undefined' ? Math.round(performance.now()) : Date.now(),
    ...meta
  }
  try {
    if (hostEl && typeof hostEl.clientWidth === 'number') {
      row.hostClientW = hostEl.clientWidth
      row.hostClientH = hostEl.clientHeight
    }
  } catch {
    /* ignore */
  }
  if (!term) {
    console.warn('[badcase-pty][cursor-trace]', row)
    return
  }
  row.termCols = term.cols
  row.termRows = term.rows
  try {
    const el = term.element
    if (el && typeof el.clientWidth === 'number') {
      row.termElClientW = el.clientWidth
      row.termElClientH = el.clientHeight
    }
  } catch {
    /* ignore */
  }
  try {
    const b = term.buffer?.active
    if (b) {
      row.cx = b.cursorX
      row.cy = b.cursorY
      row.baseY = b.baseY
      row.vy = b.viewportY
      const ln = typeof b.getLine === 'function' ? b.getLine(b.cursorY) : null
      if (ln && typeof ln.translateToString === 'function') {
        const s = ln.translateToString(true)
        row.cursorLineLen = s.length
        row.cursorLineTail = s.slice(Math.max(0, s.length - 140))
      }
    }
  } catch (e) {
    row.bufferReadErr = String(e && e.message ? e.message : e)
  }
  try {
    const core = term._core
    const css = core?._renderService?.dimensions?.css
    const cw = css?.cell?.width
    const ch = css?.cell?.height
    row.cellCssW = cw
    row.cellCssH = ch
    if (typeof cw === 'number' && cw > 0 && typeof row.hostClientW === 'number' && row.hostClientW > 0) {
      row.inferredColsFromHost = Math.max(1, Math.floor(row.hostClientW / cw))
      row.hostVsTermColsDelta = row.inferredColsFromHost - (Number(term.cols) || 0)
    }
    if (typeof cw === 'number' && cw > 0 && typeof row.termElClientW === 'number' && row.termElClientW > 0) {
      row.inferredColsFromTermEl = Math.max(1, Math.floor(row.termElClientW / cw))
      row.termElVsTermColsDelta = row.inferredColsFromTermEl - (Number(term.cols) || 0)
    }
  } catch (e) {
    row.renderDimsErr = String(e && e.message ? e.message : e)
  }
  console.warn('[badcase-pty][cursor-trace]', row)
}
