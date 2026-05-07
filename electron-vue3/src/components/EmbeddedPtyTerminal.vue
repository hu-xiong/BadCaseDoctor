<template>
  <div class="embedded-pty-root">
    <div
      v-if="statusText"
      class="embedded-pty-status"
      :class="{
        'embedded-pty-status--info': statusTone === 'info',
        'embedded-pty-status--ok': statusTone === 'ok',
        'embedded-pty-status--err': statusTone === 'err'
      }"
    >
      {{ statusText }}
    </div>
    <div
      v-if="findVisible"
      ref="findBarRef"
      class="embedded-pty-find-bar"
      @keydown.capture.stop="onFindBarKeydown"
      @mousedown="onFindBarMouseDown"
    >
      <button
        type="button"
        class="embedded-pty-find-btn embedded-pty-find-close"
        :title="t('embeddedTerminal.findClose')"
        @click="closeFind"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
          <path d="M6 4.586L9.293 1.293l1.414 1.414L7.414 6l3.293 3.293-1.414 1.414L6 7.414l-3.293 3.293-1.414-1.414L4.586 6 1.293 2.707l1.414-1.414L6 4.586z"/>
        </svg>
      </button>
      <button
        type="button"
        class="embedded-pty-find-btn"
        :title="t('embeddedTerminal.findNext')"
        @click="findNextClick"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
          <path d="M6 9l4-4H2l4 4z"/>
        </svg>
      </button>
      <button
        type="button"
        class="embedded-pty-find-btn"
        :title="t('embeddedTerminal.findPrev')"
        @click="findPrevClick"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
          <path d="M6 3L2 7h8L6 3z"/>
        </svg>
      </button>
      <button
        type="button"
        class="embedded-pty-find-btn"
        :class="{ active: findCaseSensitive }"
        :title="t('embeddedTerminal.findCaseSensitive')"
        @click="findCaseSensitive = !findCaseSensitive; runFindIncremental()"
      >
        Aa
      </button>
      <span class="embedded-pty-find-status">{{ findMatchStatus }}</span>
      <input
        ref="findInputRef"
        v-model="findQuery"
        type="search"
        class="embedded-pty-find-input"
        :placeholder="t('embeddedTerminal.findPlaceholder')"
        autocomplete="off"
        spellcheck="false"
      />
    </div>
    <div
      ref="xtermWrapRef"
      class="embedded-pty-xterm-wrap"
      :class="{ 'embedded-pty-xterm-wrap-content-width': sizeToContentActive }"
      @contextmenu.prevent="onTermContextMenu"
    >
      <div ref="termHost" class="embedded-pty-xterm-host"></div>
    </div>
    <Teleport to="body">
      <div
        v-if="addToChatVisible && openAiComposerPrefill"
        class="ept-add-to-chat-root"
        :style="{ left: addToChatLeft + 'px', top: addToChatTop + 'px' }"
      >
        <button
          type="button"
          class="ept-add-to-chat-chip"
          :title="t('embeddedTerminal.addToChat')"
          @mousedown.prevent.stop
          @click.prevent.stop="onAddToChatFloaterClick"
        >
          <span class="ept-add-to-chat-label">{{ t('embeddedTerminal.addToChat') }}</span>
          <span class="ept-add-to-chat-kbd">{{ addToChatShortcutLabel }}</span>
        </button>
      </div>
    </Teleport>
    <Teleport to="body">
      <div v-if="ctxMenuVisible" class="etw-terminal-ctx-portal-root">
        <div class="etw-terminal-ctx-menu-backdrop" @mousedown="closeCtxMenu" />
        <div
          class="etw-terminal-ctx-menu-floater etw-vscode-terminal vs-dark monaco-workbench integrated-terminal"
          :style="{ left: ctxMenuX + 'px', top: ctxMenuY + 'px' }"
        >
          <div class="etw-vscode-menu etw-vscode-menu-context" role="menu" @mousedown.stop>
            <button
              type="button"
              class="etw-vscode-menu-item"
              role="menuitem"
              :disabled="!ctxCopyEnabled"
              @click="onCtxCopy"
            >
              {{ t('embeddedTerminal.contextCopy') }}
            </button>
            <button
              type="button"
              class="etw-vscode-menu-item"
              role="menuitem"
              :disabled="!ctxCopyEnabled || !hasSerializeAddon"
              @click="onCtxCopyAsHtml"
            >
              {{ t('embeddedTerminal.contextCopyAsHtml') }}
            </button>
            <button type="button" class="etw-vscode-menu-item" role="menuitem" @click="onCtxPaste">
              {{ t('embeddedTerminal.contextPaste') }}
            </button>
            <button type="button" class="etw-vscode-menu-item" role="menuitem" @click="onCtxSelectAll">
              {{ t('embeddedTerminal.contextSelectAll') }}
            </button>
            <div class="etw-vscode-menu-sep" />
            <button type="button" class="etw-vscode-menu-item" role="menuitem" @click="onCtxClear">
              {{ t('embeddedTerminal.contextClearTerminal') }}
            </button>
            <button type="button" class="etw-vscode-menu-item" role="menuitem" @click="toggleSizeToContent">
              {{
                sizeToContentActive
                  ? t('embeddedTerminal.contextSizeToContentOff')
                  : t('embeddedTerminal.contextSizeToContentOn')
              }}
            </button>
            <button type="button" class="etw-vscode-menu-item" role="menuitem" @click="onCtxFind">
              {{ t('embeddedTerminal.contextFind') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, inject, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  vscodeLoadSearchAddon,
  vscodeLoadWebglIfPossible,
  applyXtermWindowsConptyCursorReflow,
  isXtermWin32InputMode
} from '../vscode-terminal/vscodeIntegratedXterm'
import { mountVscodeIntegratedTerminal } from '../vscode-terminal/vscodeXtermAttach'
import { createVscodeXtermFitLayout } from '../vscode-terminal/vscodeXtermFitLayout'
import {
  integratedTerminalClearViewport,
  integratedTerminalCopySelection,
  integratedTerminalCopySelectionAsHtml,
  integratedTerminalPasteFromClipboard,
  integratedTerminalSelectAll
} from '../vscode-terminal/embeddedTerminalEditActions'
import {
  applyContentWidthMinSize,
  clearContentWidthMinSize,
  computeLongestViewportWrappedLineLength
} from '../vscode-terminal/embeddedTerminalViewportWidth'
import {
  badcasePtyLog,
  badcasePtyLogRawTermOutput,
  badcasePtyNoWebGL,
  badcasePtyCursorTraceEnabled,
  badcasePtyLogCursorTrace,
  badcasePtyDebugEnabled
} from '../utils/badcasePtyDebug.js'
import { normalizeConptyStdinDelToBs } from '../utils/embeddedPtyWinStdin.js'
import { win32InputModeEnabled } from '../composables/useLocalGoProxyStatus'

function ptyPreviewU8(u8, max = 96) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return ''
  const n = Math.min(u8.length, max)
  let s = ''
  for (let i = 0; i < n; i += 1) {
    const c = u8[i]
    if (c >= 32 && c < 127 && c !== 92) s += String.fromCharCode(c)
    else s += `\\x${c.toString(16).padStart(2, '0')}`
  }
  if (u8.length > max) s += '...'
  return s
}

/** badcasePtyDebug=1：stdin 调试预览（含 \\e） */
function dbgTermInputU8Esc(u8, max = 48) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return ''
  const n = Math.min(u8.length, max)
  let o = ''
  for (let i = 0; i < n; i += 1) {
    const c = u8[i]
    if (c === 0x1b) o += '\\e'
    else if (c === 0x0d) o += '\\r'
    else if (c === 0x0a) o += '\\n'
    else if (c >= 32 && c < 127) o += String.fromCharCode(c)
    else o += `\\x${c.toString(16).padStart(2, '0')}`
  }
  if (u8.length > max) o += ` +${u8.length - max}b`
  return o
}

const TERM_INPUT_DBG_MAX = 15
let termInputDbgCount = 0

const props = defineProps({
  clientSessionId: { type: String, default: 'default' },
  mode: { type: String, default: 'local' },
  sshConfig: { type: Object, default: () => ({}) },
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null },
  fontSize: { type: Number, default: 14 },
  railResizeTick: { type: Number, default: 0 },
  railDragging: { type: Boolean, default: false },
  /** 与 v-show 配合：从隐藏切到显示时宿主宽高才非 0，需重新 fit，否则 xterm 黑屏 */
  paneActive: { type: Boolean, default: true }
})

const { t } = useI18n()
const termHost = ref(null)
const xtermWrapRef = ref(null)
const statusText = ref('')
/** 顶栏连接状态语气：warn=默认黄（断开等）；info=蓝灰；ok=绿；err=红 */
const statusTone = ref('info')
const startedOnce = ref(false)

const ctxMenuVisible = ref(false)
const ctxMenuX = ref(0)
const ctxMenuY = ref(0)
const ctxCopyEnabled = ref(false)

const hasSerializeAddon = ref(false)
const sizeToContentActive = ref(false)

const findVisible = ref(false)
const findQuery = ref('')
const findCaseSensitive = ref(false)
const findMatchStatus = ref('')
const findInputRef = ref(null)
const findBarRef = ref(null)

// 搜索栏拖拽状态
let isDraggingFindBar = false
let dragStartX = 0
let dragStartWidth = 0

function onFindBarMouseDown(e) {
  if (e.target.closest('.embedded-pty-find-btn')) return
  const bar = findBarRef.value
  if (!bar) return
  isDraggingFindBar = true
  dragStartX = e.clientX
  dragStartWidth = bar.offsetWidth
  document.addEventListener('mousemove', onFindBarMouseMove)
  document.addEventListener('mouseup', onFindBarMouseUp)
  e.preventDefault()
}

function onFindBarMouseMove(e) {
  if (!isDraggingFindBar) return
  const bar = findBarRef.value
  if (!bar) return
  const delta = dragStartX - e.clientX
  const newWidth = Math.min(600, Math.max(200, dragStartWidth + delta))
  bar.style.width = newWidth + 'px'
}

function onFindBarMouseUp() {
  isDraggingFindBar = false
  document.removeEventListener('mousemove', onFindBarMouseMove)
  document.removeEventListener('mouseup', onFindBarMouseUp)
}

/** 对齐 SearchAddon ISearchDecorationOptions 必填项（overview 在本嵌入 UI 中未展示）。 */
const SEARCH_DECO = {
  matchBackground: '#515c6a',
  matchBorder: '#515c6a',
  matchOverviewRuler: '#264f78',
  activeMatchBackground: '#264f78',
  activeMatchBorder: '#264f78',
  activeMatchColorOverviewRuler: '#264f78'
}

const ptySocketRef = inject('ptySocket', null)
const terminalPasteRef = inject('terminalPaste', null)
const selectionRegistry = inject('terminalSelectionRegistry', null)
const onTermSelectionChange = inject('onTermSelectionChange', null)
const onPtySessionMeta = inject('onPtySessionMeta', null)
const openAiComposerPrefill = inject('openAiComposerPrefill', null)
const termRegistry = inject('termRegistry', null)
const termHistoryRegistry = inject('termHistoryRegistry', null)
const termCommandRegistry = inject('termCommandRegistry', null)
console.log('[EmbeddedPtyTerminal] termCommandRegistry injected:', termCommandRegistry !== null, 'csid:', props.clientSessionId)
const onTermFontSizeApplied = inject('onTermFontSizeApplied', null)
const onRequestAutocomplete = inject('onRequestAutocomplete', null)
const onTermCommandExecuted = inject('onTermCommandExecuted', null)

const addToChatVisible = ref(false)
const addToChatLeft = ref(0)
const addToChatTop = ref(0)
/** 最近一次在终端内松开主键的位置，用于把「添加到对话」贴在选中区域附近 */
let lastTermPointerUp = null
let addToChatFloaterRaf = 0
let termPointerUpBound = false
let xtermViewportScrollEl = null

const addToChatShortcutLabel = computed(() => {
  try {
    const p = String(navigator.platform || '')
    if (/Mac|iPhone|iPod|iPad/i.test(p)) return t('embeddedTerminal.addToChatShortcutMac')
  } catch {
    /* ignore */
  }
  return t('embeddedTerminal.addToChatShortcutWin')
})

let term = null
let fit = null
let fitLayout = null
let serializeAddon = null
let searchAddon = null
let socket = null
let ownSocket = false
let resizeObserver = null
let termHostVisibilityObserver = null
/** 与 scheduleLayout 防抖叠加：宿主尺寸稳定后再双 rAF refit，避免 DevTools/分割条拖拽后画布列宽滞后只剩「PS」 */
let layoutRecoverTimer = null
let handlersBound = false
let initialFitDone = false
/** 已向 WS 发出 term_start、尚未断开：避免 onSyncedDimensions 连发时重复建 PTY（光标/列宽错乱）。 */
let termStartRequested = false
let termStartRetryTimers = []
let _lastSentCols = 0
let _lastSentRows = 0
/**
 * 与同一次布局里多次 fit 合并：用 microtask 把 term_resize 推到「fit + 光标修正」整段同步逻辑之后，
 * 避免 xterm 一帧、WebSocket 又一帧的时序错乱；立即 emitResize（如 term_started）会 bump 代数作废挂起的 microtask。
 */
let layoutResizeFlushGen = 0
/** badcasePtyCursorTrace=1 时：rAF 合并采样，看 cell 宽推算列数 vs term.cols、缓冲区光标 */
let cursorTraceRaf = 0
let cursorTracePhase = 'unspecified'
function scheduleCursorTrace(phase) {
  if (!badcasePtyCursorTraceEnabled()) return
  if (phase) cursorTracePhase = phase
  if (cursorTraceRaf) return
  cursorTraceRaf = requestAnimationFrame(() => {
    cursorTraceRaf = 0
    const ph = cursorTracePhase
    cursorTracePhase = 'unspecified'
    badcasePtyLogCursorTrace(term, termHost.value, {
      phase: ph,
      lastSentCols: _lastSentCols,
      lastSentRows: _lastSentRows,
      socketId: socket?.id,
      startedOnce: startedOnce.value
    })
  })
}
let searchAddonAttachStarted = false
/** fit 成功时的列数；WebGL 延后到首帧 PTY 输出后再挂，避免异步 WebGL 抢在 term.write 之前完成、换渲染器后整屏黑（日志里已有 PS 但看不见）。 */
let webglDeferredCols = null
let webglLoadStarted = false

/** mountVscodeIntegratedTerminal 完成前就可能收到 term_output（尤其新建标签）；此前直接丢弃会导致永久无提示符。 */
let pendingPtyOutput = []
const PENDING_PTY_OUTPUT_MAX_BYTES = 256 * 1024

// 从输出缓冲区解析“最近一次执行的命令”（用于自动更新右侧会话标题，不依赖 stdin onData）
let detectCmdTimer = null
let lastDetectedCmd = ''

function clearDetectCmdTimer() {
  if (detectCmdTimer != null) {
    try {
      clearTimeout(detectCmdTimer)
    } catch {
      /* ignore */
    }
    detectCmdTimer = null
  }
}

function tryDetectLastCommandFromBuffer() {
  if (!term || !onTermCommandExecuted || typeof onTermCommandExecuted !== 'function') return
  try {
    const buf = term.buffer?.active
    if (!buf) return
    const cy = Number(buf.cursorY)
    const start = Number.isFinite(cy) ? Math.max(0, cy - 40) : Math.max(0, buf.length - 40)
    const end = Number.isFinite(cy) ? cy : buf.length - 1
    for (let y = end; y >= start; y -= 1) {
      const line = buf.getLine(y)
      if (!line || line.isWrapped) continue
      const text = String(line.translateToString?.() || '').trimEnd()
      if (!text) continue
      // PowerShell/cmd/*nix：统一用 normalizeCommandText 剥离提示符/控制残片/长前缀
      const cmd = normalizeCommandText(text)
      if (cmd && cmd !== lastDetectedCmd) {
        lastDetectedCmd = cmd
        onTermCommandExecuted({ client_session_id: props.clientSessionId, command: cmd, source: 'user' })
        return
      }
    }
  } catch {
    /* ignore */
  }
}

function scheduleDetectCommandFromBuffer() {
  clearDetectCmdTimer()
  detectCmdTimer = setTimeout(() => {
    detectCmdTimer = null
    tryDetectLastCommandFromBuffer()
  }, 120)
}

/** PS 常在报错前单发 0x0D 回到行首再写错误，盖住「PS> 命令」；若下一包像 PS 错误则在写入前插 0x0A。 */
let ptyHoldLoneCr = false
let ptyHoldLoneCrTimer = null

function pendingPtyOutputTotalBytes() {
  let n = 0
  for (const u of pendingPtyOutput) n += u.length
  return n
}

function enqueuePendingPtyOutput(u8) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return
  while (pendingPtyOutput.length && pendingPtyOutputTotalBytes() + u8.length > PENDING_PTY_OUTPUT_MAX_BYTES) {
    pendingPtyOutput.shift()
  }
  if (pendingPtyOutputTotalBytes() + u8.length <= PENDING_PTY_OUTPUT_MAX_BYTES) {
    pendingPtyOutput.push(u8)
  }
}

function clearPtyHoldLoneCrTimer() {
  if (ptyHoldLoneCrTimer != null) {
    clearTimeout(ptyHoldLoneCrTimer)
    ptyHoldLoneCrTimer = null
  }
}

function resetPtyStdoutCrHold() {
  ptyHoldLoneCr = false
  clearPtyHoldLoneCrTimer()
}

/** 下一包是否像 PowerShell 错误块（避免把 vim 等用的 lone \r 也改成换行）。 */
function likelyPowershellErrorChunkPrefix(u8) {
  if (!(u8 instanceof Uint8Array) || u8.length === 0) return false
  try {
    const dec = new TextDecoder('utf-8', { fatal: false }).decode(u8.subarray(0, Math.min(u8.length, 280)))
    return (
      /is not recognized as the name of/i.test(dec) ||
      /The term '/i.test(dec) ||
      /\bCategoryInfo\b/i.test(dec) ||
      /\bFullyQualifiedErrorId\b/i.test(dec) ||
      /\bParserError\b/i.test(dec) ||
      (/\bAt line:\s*\d+/i.test(dec) && /\bchar:\s*\d+/i.test(dec))
    )
  } catch {
    return false
  }
}

/** 将 lone CR + PS 错误首包 变为 LF+首包，保留上一行提示符与输入。 */
function writePtyStdoutTransformed(u8) {
  if (!term || !(u8 instanceof Uint8Array) || u8.length === 0) return
  try {
    if (ptyHoldLoneCr) {
      ptyHoldLoneCr = false
      clearPtyHoldLoneCrTimer()
      if (likelyPowershellErrorChunkPrefix(u8)) {
        const merged = new Uint8Array(1 + u8.length)
        merged[0] = 0x0a
        merged.set(u8, 1)
        u8 = merged
      } else {
        term.write(new Uint8Array([0x0d]))
      }
    }
    // 同一帧内已是 \r + 错误首行（无中间 \n）时也改成 \n 开头
    if (u8.length >= 2 && u8[0] === 0x0d && u8[1] !== 0x0a && likelyPowershellErrorChunkPrefix(u8.subarray(1))) {
      const fixed = new Uint8Array(u8.length)
      fixed.set(u8, 0)
      fixed[0] = 0x0a
      u8 = fixed
    }
    if (u8.length === 1 && u8[0] === 0x0d) {
      ptyHoldLoneCr = true
      clearPtyHoldLoneCrTimer()
      // PS 首行错误常晚于回显的 \r 数百 ms；56ms 会先刷出 \r 导致修复失效
      ptyHoldLoneCrTimer = setTimeout(() => {
        ptyHoldLoneCrTimer = null
        if (!ptyHoldLoneCr || !term) return
        ptyHoldLoneCr = false
        try {
          term.write(new Uint8Array([0x0d]))
        } catch {
          /* ignore */
        }
      }, 900)
      return
    }
    
    term.write(u8)
  } catch (e) {
    badcasePtyLog('term_output write error', e)
  }
}

function flushPendingPtyOutput() {
  if (!term || pendingPtyOutput.length === 0) return
  const chunks = pendingPtyOutput
  pendingPtyOutput = []
  for (const u8 of chunks) {
    try {
      badcasePtyLogRawTermOutput(u8, { phase: 'flush_pending', sid: props.clientSessionId })
      badcasePtyLog('term_output write (flushed pending)', { bytes: u8.length, head: ptyPreviewU8(u8, 64) })
      writePtyStdoutTransformed(u8)
    } catch (e) {
      badcasePtyLog('term_output pending flush error', e)
    }
  }
  scheduleCursorTrace('flush-pending-output')
  try {
    flushWebglAttach('term_output')
  } catch {
    /* ignore */
  }
}

function flushWebglAttach(trigger) {
  if (webglLoadStarted || !term) return
  // 浏览器 + go-local-proxy：WebGL 在首帧输出后挂载仍会整屏黑（Canvas 已写入 PS，切 WebGL 后纹理不同步）。Electron node-pty 仍可用 WebGL。
  const canvasOnly = badcasePtyNoWebGL() || socket?.id === 'browser-go-local'
  if (canvasOnly) {
    webglLoadStarted = true
    badcasePtyLog('PTY canvas renderer (WebGL skipped)', {
      trigger,
      reason: badcasePtyNoWebGL() ? 'badcasePtyNoWebGL' : 'browser-go-local'
    })
    try {
      fit?.fit?.()
      const last = term.rows > 0 ? term.rows - 1 : 0
      term?.refresh?.(0, last)
    } catch {
      /* ignore */
    }
    return
  }
  let cols = webglDeferredCols
  if (!Number.isFinite(cols) || cols < 2) {
    cols = Number(term.cols)
    if (!Number.isFinite(cols) || cols < 2) cols = 80
  }
  webglLoadStarted = true
  badcasePtyLog('WebGL attach (after first paint), trigger=', trigger, 'cols=', cols)
  void vscodeLoadWebglIfPossible(term).then(() => {
    badcasePtyLog('WebGL addon load finished')
    try {
      fit?.fit?.()
      const last = term.rows > 0 ? term.rows - 1 : 0
      term?.refresh?.(0, last)
    } catch {
      /* ignore */
    }
  })
}

/** 小于此列宽不向 PTY 发 resize：ConPTY/PSReadLine 在个位数列下会乱套，且易与 xterm 光标错位（代理侧无需改）。 */
const PTY_RESIZE_MIN_COLS = 16

function flushEmitResizeFromLayoutIfChanged() {
  if (!socket || !term || !socket.connected) return
  const cols = Number(term.cols)
  const rows = Number(term.rows)
  if (!Number.isFinite(cols) || cols < 2) return
  if (cols < PTY_RESIZE_MIN_COLS) return
  if (cols === _lastSentCols && rows === _lastSentRows) return
  _lastSentCols = cols
  _lastSentRows = rows
  socket.emit('term_resize', {
    cols,
    rows,
    client_session_id: props.clientSessionId
  })
  badcasePtyLog('term_resize emit (layout)', { cols, rows, csid: props.clientSessionId })
  scheduleCursorTrace('term_resize-layout')
}

function emitResize() {
  layoutResizeFlushGen += 1
  if (!socket || !term || !socket.connected) return
  const cols = Number(term.cols)
  const rows = Number(term.rows)
  if (!Number.isFinite(cols) || cols < 2) return
  if (cols < PTY_RESIZE_MIN_COLS) return
  _lastSentCols = cols
  _lastSentRows = rows
  socket.emit('term_resize', {
    cols,
    rows,
    client_session_id: props.clientSessionId
  })
  badcasePtyLog('term_resize emit (immediate)', { cols, rows, csid: props.clientSessionId })
  scheduleCursorTrace('term_resize-immediate')
}

function scheduleEmitResizeToPtyFromLayout() {
  if (!socket || !term || !socket.connected) return
  layoutResizeFlushGen += 1
  const gen = layoutResizeFlushGen
  queueMicrotask(() => {
    if (gen !== layoutResizeFlushGen) return
    flushEmitResizeFromLayoutIfChanged()
  })
}

function clearPtyLayoutResizeEmitTimer() {
  layoutResizeFlushGen += 1
}

function fitNowAndSyncPty(retryDepth = 0) {
  fitLayout?.fitNow(retryDepth)
}

function scheduleLayout(ms) {
  fitLayout?.schedule(ms)
}

function refreshTermFull() {
  if (!term) return
  try {
    const last = term.rows > 0 ? term.rows - 1 : 0
    term.refresh(0, last)
  } catch {
    /* ignore */
  }
}

function fitNowRecoverRender() {
  fitLayout?.clearTimers?.()
  fitNowAndSyncPty(0)
  refreshTermFull()
  requestAnimationFrame(() => {
    fitNowAndSyncPty(0)
    refreshTermFull()
    requestAnimationFrame(() => {
      fitNowAndSyncPty(0)
      refreshTermFull()
    })
  })
}

function scheduleLayoutWithRecover(ms = 72) {
  scheduleLayout(ms)
  if (layoutRecoverTimer != null) clearTimeout(layoutRecoverTimer)
  layoutRecoverTimer = setTimeout(() => {
    layoutRecoverTimer = null
    nextTick(() => fitNowRecoverRender())
  }, Math.max(48, ms) + 140)
}

function clampCtxMenuPosition(x, y) {
  const pad = 6
  const mw = 280
  const mh = 420
  const vw = typeof window !== 'undefined' ? window.innerWidth : 800
  const vh = typeof window !== 'undefined' ? window.innerHeight : 600
  return {
    x: Math.min(Math.max(pad, x), Math.max(pad, vw - mw - pad)),
    y: Math.min(Math.max(pad, y), Math.max(pad, vh - mh - pad))
  }
}

function closeCtxMenu() {
  ctxMenuVisible.value = false
}

function onTermContextMenu(e) {
  if (!term) return
  term.focus()
  const { x, y } = clampCtxMenuPosition(e.clientX, e.clientY)
  ctxMenuX.value = x
  ctxMenuY.value = y
  try {
    ctxCopyEnabled.value = !!(typeof term.hasSelection === 'function' && term.hasSelection())
  } catch {
    ctxCopyEnabled.value = false
  }
  ctxMenuVisible.value = true
}

function onCtxCopy() {
  void integratedTerminalCopySelection(term)
  closeCtxMenu()
}

function onCtxPaste() {
  void integratedTerminalPasteFromClipboard(term)
  closeCtxMenu()
}

function onCtxSelectAll() {
  integratedTerminalSelectAll(term)
  closeCtxMenu()
}

function onCtxClear() {
  integratedTerminalClearViewport(term)
  closeCtxMenu()
}

function onCtxCopyAsHtml() {
  void integratedTerminalCopySelectionAsHtml(term, serializeAddon)
  closeCtxMenu()
}

function toggleSizeToContent() {
  closeCtxMenu()
  const host = termHost.value
  const wrap = xtermWrapRef.value
  if (!term || !host || !wrap || !fitLayout) return
  if (sizeToContentActive.value) {
    clearContentWidthMinSize(host)
    sizeToContentActive.value = false
    nextTick(() => fitLayout.fitNow(0))
    return
  }
  const cols = computeLongestViewportWrappedLineLength(term)
  if (cols <= term.cols) return
  applyContentWidthMinSize(term, host, cols)
  sizeToContentActive.value = true
  nextTick(() => fitLayout.fitNow(0))
}

function onCtxFind() {
  closeCtxMenu()
  openFind()
}

function openFind() {
  findVisible.value = true
  nextTick(() => {
    try {
      findInputRef.value?.focus?.()
      findInputRef.value?.select?.()
    } catch {
      /* ignore */
    }
    runFindIncremental()
  })
}

function closeFind() {
  findVisible.value = false
  findQuery.value = ''
  findMatchStatus.value = ''
  try {
    searchAddon?.clearDecorations?.()
  } catch {
    /* ignore */
  }
  try {
    term?.focus?.()
  } catch {
    /* ignore */
  }
}

function onFindBarKeydown(ev) {
  if (ev.key === 'Escape') {
    ev.preventDefault()
    closeFind()
    return
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.code === 'KeyF') {
    ev.preventDefault()
    findInputRef.value?.focus?.()
  }
  if (ev.key === 'Enter') {
    ev.preventDefault()
    if (ev.shiftKey) findPrevClick()
    else findNextClick()
  }
}

function runFindIncremental() {
  if (!searchAddon || !findVisible.value) return
  const q = String(findQuery.value || '')
  if (!q.trim()) {
    try {
      searchAddon.clearDecorations()
    } catch {
      /* ignore */
    }
    findMatchStatus.value = ''
    return
  }
  try {
    searchAddon.findNext(q, {
      decorations: SEARCH_DECO,
      caseSensitive: findCaseSensitive.value,
      incremental: true
    })
  } catch {
    /* ignore */
  }
}

function findNextClick() {
  if (!searchAddon) return
  const q = String(findQuery.value || '').trim()
  if (!q) return
  try {
    searchAddon.findNext(q, {
      decorations: SEARCH_DECO,
      caseSensitive: findCaseSensitive.value,
      incremental: false
    })
  } catch {
    /* ignore */
  }
}

function findPrevClick() {
  if (!searchAddon) return
  const q = String(findQuery.value || '').trim()
  if (!q) return
  try {
    searchAddon.findPrevious(q, {
      decorations: SEARCH_DECO,
      caseSensitive: findCaseSensitive.value
    })
  } catch {
    /* ignore */
  }
}

function attachIntegratedTerminalKeyChordHandler() {
  if (!term || typeof term.attachCustomKeyEventHandler !== 'function') return
  term.attachCustomKeyEventHandler((ev) => {
    if (ev.type !== 'keydown') return true
    if (ev.altKey) return true

    // 退格键现在由 go-local-proxy 处理（DEL→BS 转换），xterm 让其默认处理

    if (ev.key === 'Escape' && findVisible.value) {
      ev.preventDefault()
      ev.stopPropagation()
      closeFind()
      return false
    }

    if ((ev.ctrlKey || ev.metaKey) && ev.code === 'KeyF' && !ev.shiftKey) {
      ev.preventDefault()
      ev.stopPropagation()
      openFind()
      return false
    }

    // Ctrl+Space：打开补全（使用 Workspace 层候选）
    if ((ev.ctrlKey || ev.metaKey) && ev.code === 'Space') {
      ev.preventDefault()
      ev.stopPropagation()
      try {
        if (onRequestAutocomplete && typeof onRequestAutocomplete === 'function') {
          onRequestAutocomplete({
            client_session_id: props.clientSessionId,
            prefix: pendingCommand || ''
          })
        }
      } catch {
        /* ignore */
      }
      return false
    }

    const copyChord =
      (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyC') ||
      (ev.ctrlKey && !ev.shiftKey && ev.code === 'Insert')
    const pasteChord =
      (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyV') ||
      (ev.shiftKey && !ev.ctrlKey && !ev.metaKey && ev.code === 'Insert')

    if (copyChord) {
      ev.preventDefault()
      ev.stopPropagation()
      void integratedTerminalCopySelection(term)
      return false
    }
    if (pasteChord) {
      ev.preventDefault()
      ev.stopPropagation()
      void integratedTerminalPasteFromClipboard(term)
      return false
    }

    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && !ev.shiftKey && ev.code === 'KeyL') {
      const raw = term && typeof term.getSelection === 'function' ? String(term.getSelection() || '') : ''
      if (raw.trim() && openAiComposerPrefill) {
        ev.preventDefault()
        ev.stopPropagation()
        addToChatFromSelection()
        addToChatVisible.value = false
        return false
      }
    }
    return true
  })
}

const ADD_TO_CHAT_PTR_TTL_MS = 900
const ADD_TO_CHAT_CHIP_W = 168
const ADD_TO_CHAT_CHIP_H = 30

function clampAddToChatPosition(left, top) {
  const margin = 6
  const w = ADD_TO_CHAT_CHIP_W
  const h = ADD_TO_CHAT_CHIP_H
  const maxL = Math.max(margin, window.innerWidth - w - margin)
  const maxT = Math.max(margin, window.innerHeight - h - margin)
  return {
    left: Math.min(Math.max(margin, left), maxL),
    top: Math.min(Math.max(margin, top), maxT)
  }
}

function tryPositionAddToChatFromBufferRange() {
  if (!term || typeof term.getSelectionPosition !== 'function') return false
  const range = term.getSelectionPosition()
  const rect = term.element?.getBoundingClientRect?.()
  const cell = term.dimensions?.css?.cell
  const buf = term.buffer?.active
  if (!range || !rect || !cell || !buf) return false
  const cw = Number(cell.width)
  const ch = Number(cell.height)
  if (!Number.isFinite(cw) || cw <= 0 || !Number.isFinite(ch) || ch <= 0) return false

  const sx = range.start.x
  const sy = range.start.y
  const ex = range.end.x
  const ey = range.end.y
  const yTop = Math.min(sy, ey)
  const xRight = Math.max(sx, ex)
  const viewportRow = yTop - buf.viewportY
  if (!Number.isFinite(viewportRow) || viewportRow < 0 || viewportRow >= term.rows) return false

  const anchorLeft = rect.left + xRight * cw + 4
  const anchorTop = rect.top + viewportRow * ch - 6
  const pos = clampAddToChatPosition(anchorLeft - ADD_TO_CHAT_CHIP_W, anchorTop - ADD_TO_CHAT_CHIP_H - 4)
  addToChatLeft.value = pos.left
  addToChatTop.value = pos.top
  return true
}

function positionAddToChatFloater() {
  if (!term || !openAiComposerPrefill) return
  const raw = typeof term.getSelection === 'function' ? String(term.getSelection() || '') : ''
  if (!raw.trim()) {
    addToChatVisible.value = false
    return
  }

  const now = Date.now()
  if (
    lastTermPointerUp &&
    now - lastTermPointerUp.t <= ADD_TO_CHAT_PTR_TTL_MS &&
    Number.isFinite(lastTermPointerUp.x) &&
    Number.isFinite(lastTermPointerUp.y)
  ) {
    const pos = clampAddToChatPosition(lastTermPointerUp.x + 6, lastTermPointerUp.y - ADD_TO_CHAT_CHIP_H - 8)
    addToChatLeft.value = pos.left
    addToChatTop.value = pos.top
    addToChatVisible.value = true
    return
  }

  if (tryPositionAddToChatFromBufferRange()) {
    addToChatVisible.value = true
    return
  }

  const r = term.element?.getBoundingClientRect?.()
  if (r) {
    const pos = clampAddToChatPosition(r.right - ADD_TO_CHAT_CHIP_W - 10, r.top + 10)
    addToChatLeft.value = pos.left
    addToChatTop.value = pos.top
    addToChatVisible.value = true
  }
}

function scheduleSyncAddToChatFloater() {
  if (!openAiComposerPrefill) {
    addToChatVisible.value = false
    return
  }
  if (addToChatFloaterRaf) cancelAnimationFrame(addToChatFloaterRaf)
  addToChatFloaterRaf = requestAnimationFrame(() => {
    addToChatFloaterRaf = 0
    positionAddToChatFloater()
  })
}

function onTermPointerUp(ev) {
  if (!term || ev.button !== 0) return
  requestAnimationFrame(() => {
    try {
      if (typeof term.hasSelection === 'function' && term.hasSelection()) {
        lastTermPointerUp = { x: ev.clientX, y: ev.clientY, t: Date.now() }
        scheduleSyncAddToChatFloater()
      }
    } catch {
      /* ignore */
    }
  })
}

function onAddToChatViewportScroll() {
  if (addToChatVisible.value) scheduleSyncAddToChatFloater()
}

function bindAddToChatDomListeners() {
  if (!term?.element || termPointerUpBound) return
  term.element.addEventListener('pointerup', onTermPointerUp, true)
  termPointerUpBound = true
  try {
    const vp = term.element.querySelector?.('.xterm-viewport')
    if (vp) {
      vp.addEventListener('scroll', onAddToChatViewportScroll, { passive: true })
      xtermViewportScrollEl = vp
    }
  } catch {
    /* ignore */
  }
}

function unbindAddToChatDomListeners() {
  if (term?.element && termPointerUpBound) {
    try {
      term.element.removeEventListener('pointerup', onTermPointerUp, true)
    } catch {
      /* ignore */
    }
  }
  termPointerUpBound = false
  if (xtermViewportScrollEl) {
    try {
      xtermViewportScrollEl.removeEventListener('scroll', onAddToChatViewportScroll)
    } catch {
      /* ignore */
    }
    xtermViewportScrollEl = null
  }
}

function addToChatFromSelection() {
  if (!openAiComposerPrefill || !term || typeof term.getSelection !== 'function') return
  const raw = String(term.getSelection() || '').trim()
  if (!raw) return
  
  // 计算选中的行号范围
  let startLine = 1
  let endLine = 1
  
  // 尝试获取选中范围
  if (typeof term.getSelectionPosition === 'function') {
    try {
      const range = term.getSelectionPosition()
      if (range) {
        // xterm.js 的行号从 0 开始，转换为从 1 开始
        startLine = Math.min(range.start.y, range.end.y) + 1
        endLine = Math.max(range.start.y, range.end.y) + 1
      }
    } catch (e) {
      // 若获取失败，使用默认值
    }
  }
  
  // 生成与 Trae 相同的终端引用样式
  // 格式：📱 Terminal <start>-<end>
  const reference = `📱 Terminal ${startLine}-${endLine}`
  
  openAiComposerPrefill(reference)
}

function onAddToChatFloaterClick() {
  addToChatFromSelection()
  addToChatVisible.value = false
}

function stringToUtf8B64(str) {
  const u8 = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < u8.length; i += 1) binary += String.fromCharCode(u8[i])
  return btoa(binary)
}

function navIsWindowsHost() {
  try {
    return typeof navigator !== 'undefined' && /Windows/i.test(String(navigator.userAgent || ''))
  } catch {
    return false
  }
}

function emitPtyTermInput(data) {
  if (!socket || !socket.connected) return
  // 退格键转换现在由 go-local-proxy 处理（DEL→BS），前端直接透传
  if (badcasePtyDebugEnabled() && termInputDbgCount < TERM_INPUT_DBG_MAX) {
    termInputDbgCount += 1
    const u8 = typeof data === 'string' ? new TextEncoder().encode(data) : new Uint8Array()
    badcasePtyLog('term_input', {
      n: termInputDbgCount,
      socketId: socket?.id,
      utf16Units: typeof data === 'string' ? data.length : 0,
      utf8Bytes: u8.length,
      preview: dbgTermInputU8Esc(u8, 56)
    })
  }
  try {
    socket.emit('term_input', {
      b64: stringToUtf8B64(data),
      client_session_id: props.clientSessionId
    })
  } catch (e) {
    badcasePtyLog('term_input emit error', e)
  }
}

function b64ToUint8Array(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i)
  return out
}

/**
 * 仅取当前 xterm 行列；无效时回退默认。
 * term_start 必须在首次 fit（initialFitDone）之后发出，否则会用 80×24 建 PTY，与真实面板列宽不一致，导致光标/首字符错位。
 */
function clampTermGrid() {
  let cols = Number(term?.cols)
  let rows = Number(term?.rows)
  if (!Number.isFinite(cols) || cols < 2) cols = 80
  if (!Number.isFinite(rows) || rows < 1) rows = 24
  return { cols, rows }
}

function clearTermStartRetryTimers() {
  for (const id of termStartRetryTimers) {
    try {
      clearTimeout(id)
    } catch {
      /* ignore */
    }
  }
  termStartRetryTimers = []
}

function ptyWireSid(payload) {
  if (!payload || typeof payload !== 'object') return ''
  const v = payload.client_session_id ?? payload.ClientSessionID
  return v != null ? String(v) : ''
}

function ptyWireB64(payload) {
  if (!payload || typeof payload !== 'object') return ''
  const v = payload.b64 ?? payload.B64
  return v != null ? String(v) : ''
}

function requestTermStart() {
  if (props.mode === 'ssh') return
  if (!socket || !term || !socket.connected) return
  if (startedOnce.value) return
  if (termStartRequested) return
  if (!initialFitDone) {
    badcasePtyLog('requestTermStart skipped (await initial fit)', { csid: props.clientSessionId })
    return
  }
  const host = termHost.value
  if (!host || host.clientWidth < 16 || host.clientHeight < 16) {
    badcasePtyLog('requestTermStart skipped (host not laid out)', {
      csid: props.clientSessionId,
      w: host?.clientWidth,
      h: host?.clientHeight
    })
    return
  }
  try {
    fit?.fit?.()
  } catch {
    /* ignore */
  }
  const { cols, rows } = clampTermGrid()
  badcasePtyLog('requestTermStart', {
    csid: props.clientSessionId,
    cols,
    rows,
    initialFitDone,
    cwdLen: String(props.workingDirectory || '').length
  })
  const pid = props.projectId != null && props.projectId !== '' ? Number(props.projectId) : undefined
  const base = {
    client_session_id: props.clientSessionId,
    cols,
    rows,
    cwd: (props.workingDirectory || '').trim() || undefined,
    mode: props.mode,
    project_id: Number.isFinite(pid) ? pid : undefined
  }
  if (props.mode === 'ssh') {
    const c = props.sshConfig || {}
    base.ssh = {
      host: (c.host || '').trim(),
      port: Number(c.port) || 22,
      username: (c.username || '').trim(),
      password: c.password || '',
      key_text: (c.key_text || '').trim() || undefined
    }
  }
  termStartRequested = true
  badcasePtyLog('term_start emit', { cols, rows, csid: props.clientSessionId })
  scheduleCursorTrace('pre-term-start')
  try {
    socket.emit('term_start', base)
  } catch (e) {
    termStartRequested = false
    badcasePtyLog('term_start emit error', e)
  }
}

function scheduleInitialFit() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      fitNowAndSyncPty()
      setTimeout(() => fitNowAndSyncPty(), 280)
    })
  })
}

function scheduleTermStart() {
  clearTermStartRetryTimers()
  requestTermStart()
  for (const ms of [100, 250, 500, 800, 1600]) {
    termStartRetryTimers.push(
      setTimeout(() => {
        requestTermStart()
      }, ms)
    )
  }
}

function onPtyConnect() {
  badcasePtyLog('socket connect', { csid: props.clientSessionId })
  statusText.value = ''
  statusTone.value = 'info'
  nextTick(() => {
    fitNowAndSyncPty()
    requestAnimationFrame(() => {
      fitNowAndSyncPty()
      if (initialFitDone && !startedOnce.value && !termStartRequested) scheduleTermStart()
    })
  })
}

function onPtyConnectError(err) {
  console.error('[EmbeddedPtyTerminal] onPtyConnectError:', err)
  statusText.value = t('embeddedTerminal.connectError')
  statusTone.value = 'err'
}

function onPtyDisconnect() {
  termInputDbgCount = 0
  pendingPtyOutput = []
  resetPtyStdoutCrHold()
  clearPtyLayoutResizeEmitTimer()
  clearTermStartRetryTimers()
  termStartRequested = false
  statusText.value = t('embeddedTerminal.disconnected')
  statusTone.value = 'warn'
  startedOnce.value = false
  if (term) {
    term.write(`\r\n\x1b[33m${t('embeddedTerminal.disconnected')}\x1b[0m\r\n`)
  }
}

function onPtyTermStarted(payload) {
  const sid = ptyWireSid(payload)
  if (sid && sid !== props.clientSessionId) return
  resetPtyStdoutCrHold()
  startedOnce.value = true
  const resolvedCwd = String(payload?.cwd || '').trim() || String(props.workingDirectory || '').trim()
  badcasePtyLog('term_started', {
    csid: props.clientSessionId,
    cwd: resolvedCwd,
    termCols: term?.cols,
    termRows: term?.rows
  })
  try {
    if (onPtySessionMeta && typeof onPtySessionMeta === 'function') {
      onPtySessionMeta({
        client_session_id: props.clientSessionId,
        pid: payload?.pid,
        shell: payload?.shell,
        cwd: resolvedCwd || undefined,
        mode: props.mode
      })
    }
  } catch {
    /* ignore */
  }
  statusText.value = ''
  statusTone.value = 'ok'
  try {
    applyXtermWindowsConptyCursorReflow(term, payload?.windows_pty)
    if (
      props.mode !== 'ssh' &&
      !payload?.windows_pty &&
      typeof navigator !== 'undefined' &&
      /Windows/i.test(navigator.userAgent) &&
      socket?.id === 'browser-go-local'
    ) {
      applyXtermWindowsConptyCursorReflow(term, { backend: 'conpty' })
    }
  } catch {
    /* ignore */
  }
  badcasePtyLog('term_started xterm keys', {
    win32InputMode: isXtermWin32InputMode(term),
    windows_pty: payload?.windows_pty,
    uaWindows: navIsWindowsHost()
  })
  emitResize()
  nextTick(() => {
    try {
      fitNowAndSyncPty()
      term?.focus?.()
      term?.scrollToBottom?.()
      if (term?.rows > 0) {
        term?.refresh?.(0, term.rows - 1)
      }
    } catch {
      /* ignore */
    }
  })
  setTimeout(() => {
    try {
      emitResize()
      term?.focus?.()
    } catch {
      /* ignore */
    }
  }, 120)
  setTimeout(() => flushWebglAttach('term_started-timeout'), 1000)
}

function onPtyTermOutput(payload) {
  if (!payload || ptyWireSid(payload) !== props.clientSessionId) return
  const b64 = ptyWireB64(payload)
  if (!b64) {
    badcasePtyLog('term_output skip', { hasB64: false, hasTerm: !!term, sid: ptyWireSid(payload) })
    return
  }
  let u8
  try {
    u8 = b64ToUint8Array(b64)
  } catch (e) {
    badcasePtyLog('term_output decode error', e)
    return
  }
  if (!term) {
    enqueuePendingPtyOutput(u8)
    badcasePtyLog('term_output buffered (xterm not ready)', { bytes: u8.length, sid: ptyWireSid(payload) })
    return
  }
  try {
    badcasePtyLogRawTermOutput(u8, { phase: 'write', sid: props.clientSessionId })
    badcasePtyLog('term_output write', { bytes: u8.length, head: ptyPreviewU8(u8, 64) })
    writePtyStdoutTransformed(u8)
    scheduleCursorTrace('post-term-output')
    flushWebglAttach('term_output')
    // 输出回显后尝试从 buffer 里解析最近命令（适配 Win32 输入模式等 stdin 不可见的情况）
    scheduleDetectCommandFromBuffer()
  } catch (e) {
    badcasePtyLog('term_output write error', e)
  }
}

function onPtyTermError(payload) {
  if (!payload || ptyWireSid(payload) !== props.clientSessionId) return
  termStartRequested = false
  const msg = payload.message || t('embeddedTerminal.ptyError')
  statusText.value = msg
  statusTone.value = 'err'
  if (term) term.write(`\r\n\x1b[31m${msg}\x1b[0m\r\n`)
}

function onPtyTermExit(payload) {
  const sid = ptyWireSid(payload)
  if (sid && sid !== props.clientSessionId) return
  if (term) term.write(`\r\n\x1b[90m[exit]\x1b[0m\r\n`)
}

function bindSocketHandlers() {
  if (handlersBound || !socket) return
  handlersBound = true
  socket.on('connect', onPtyConnect)
  socket.on('connect_error', onPtyConnectError)
  socket.on('disconnect', onPtyDisconnect)
  socket.on('term_started', onPtyTermStarted)
  socket.on('term_output', onPtyTermOutput)
  socket.on('term_error', onPtyTermError)
  socket.on('term_exit', onPtyTermExit)
}

function unbindSocketHandlers() {
  if (!handlersBound || !socket) return
  socket.off('connect', onPtyConnect)
  socket.off('connect_error', onPtyConnectError)
  socket.off('disconnect', onPtyDisconnect)
  socket.off('term_started', onPtyTermStarted)
  socket.off('term_output', onPtyTermOutput)
  socket.off('term_error', onPtyTermError)
  socket.off('term_exit', onPtyTermExit)
  handlersBound = false
  termInputDbgCount = 0
}

function setupTerminal() {
  const host = termHost.value
  if (!host) return
  const enableWin32 = navIsWindowsHost() && win32InputModeEnabled.value
  void mountVscodeIntegratedTerminal(host, {
    win32InputMode: enableWin32
  }).then(({ term: xterm, fit: f, serializeAddon: sa }) => {
    term = xterm
    fit = f
    // 字体大小：在首次 mount 后立即应用；后续由 watch 触发
    try {
      if (props.fontSize && typeof term.setOption === 'function') {
        term.setOption('fontSize', props.fontSize)
      }
    } catch {
      /* ignore */
    }
    try {
      if (onTermFontSizeApplied && typeof onTermFontSizeApplied === 'function') {
        onTermFontSizeApplied({ client_session_id: props.clientSessionId, fontSize: props.fontSize })
      }
    } catch {
      /* ignore */
    }
    serializeAddon = sa
    searchAddon = null
    hasSerializeAddon.value = !!sa

    function bindSearchAddonResultsListener(sra) {
      if (!sra?.onDidChangeResults) return
      sra.onDidChangeResults((e) => {
        if (!findVisible.value) return
        const n = e?.resultCount ?? 0
        if (n <= 0) {
          findMatchStatus.value = t('embeddedTerminal.findNoResults')
          return
        }
        const cur = typeof e.resultIndex === 'number' && e.resultIndex >= 0 ? String(e.resultIndex + 1) : '—'
        findMatchStatus.value = t('embeddedTerminal.findMatchStatus', { current: cur, total: n })
      })
    }

    function tryAttachSearchAddonAfterFit(cols) {
      if (searchAddonAttachStarted || !term) return
      if (!Number.isFinite(cols) || cols < 2) return
      searchAddonAttachStarted = true
      void vscodeLoadSearchAddon(term).then((sra) => {
        searchAddon = sra
        bindSearchAddonResultsListener(sra)
      })
    }

    function tryAttachWebglAfterFit(cols) {
      if (webglLoadStarted || !term) return
      if (!Number.isFinite(cols) || cols < 2) return
      webglDeferredCols = cols
      if (badcasePtyNoWebGL() || socket?.id === 'browser-go-local') {
        flushWebglAttach('fit-canvas-only')
        return
      }
      badcasePtyLog('WebGL deferred until first term_output (or 1s timeout), cols=', cols)
    }

    fitLayout = createVscodeXtermFitLayout(term, fit, () => termHost.value, {
      /**
       * 必须为 0：此前 reserveBottomRows=1 会在每次 fit 后 `term.resize(cols, rows-1)` 缩小缓冲区行数。
       * 在 PowerShell 报错等大量输出或紧随其后的 refit 时，xterm 可能裁掉/合并视口底部一行，
       * 表现成「PS> 命令」那一行被错误块顶掉或消失（用户输入与提示符不应丢）。
       * 若需提示符离底边略远，用 wrap 的 padding-bottom 等纯布局手段，勿再减少逻辑行数。
       */
      reserveBottomRows: 0,
      onSyncedDimensions(cols, rows) {
        initialFitDone = true
        badcasePtyLog('onSyncedDimensions', { cols, rows, paneActive: props.paneActive })
        scheduleCursorTrace('onSyncedDimensions')
        tryAttachWebglAfterFit(cols)
        tryAttachSearchAddonAfterFit(cols)
        if (socket?.connected && Number.isFinite(cols) && cols >= 2) {
          if (cols !== _lastSentCols || rows !== _lastSentRows) {
            scheduleEmitResizeToPtyFromLayout()
          }
        }
        // 首帧 fit 完成后 initialFitDone=true；若 socket 已连上但尚未 term_start，在此补齐（避免 connect 早于 fit 时黑屏）。
        if (socket?.connected && !startedOnce.value && !termStartRequested) {
          scheduleTermStart()
        }
      }
    })

    badcasePtyLog('xterm mounted (stdin keys)', {
      win32InputMode: isXtermWin32InputMode(term),
      mountRequestedWin32: props.mode !== 'ssh' && navIsWindowsHost(),
      mode: props.mode,
      uaWindows: navIsWindowsHost()
    })

    // 记录用户当前输入的命令，供“自动会话标题/历史”等使用
    // 注意：Win32 输入模式下 onData 可能主要是控制序列，因此以 onKey 为主，onData 仅做兜底/调试
    let pendingCommand = ''
    let _lastSubmitAt = 0
    let _dbgOnDataN = 0
    const _DBG_ONDATA_MAX = 20

    function dbgPreviewOnData(str) {
      const s = String(str || '')
      let out = ''
      for (let i = 0; i < Math.min(s.length, 80); i += 1) {
        const ch = s[i]
        const code = ch.charCodeAt(0)
        if (ch === '\r') out += '\\\\r'
        else if (ch === '\n') out += '\\\\n'
        else if (ch === '\t') out += '\\\\t'
        else if (code === 0x1b) out += '\\\\e'
        else if (code < 32) out += `\\\\x${code.toString(16).padStart(2, '0')}`
        else out += ch
      }
      if (s.length > 80) out += '…'
      return out
    }

    // 过滤掉 ANSI 控制序列（CSI/OSC/DCS 等）与不可见控制字符，只保留纯文本命令
    // 参考：ECMA-48 / xterm 控制序列；此处宁可“多删”控制码，避免把残片（如 [[0]）写入最近命令/会话标题
    function filterCommand(raw) {
      const s = String(raw || '')
      if (!s) return ''
      // CSI: ESC [ ... final(@-~)
      // OSC: ESC ] ... (BEL | ESC \)
      // DCS/SOS/PM/APC: ESC P/X/^/_ ... ESC \
      // 以及一些单字节 ESC 序列（尽量覆盖常见场景）
      let withoutAnsi = s
        .replace(
          /\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[PX^_].*?(?:\x1b\\)|[()][0-2AB]|[=><])/gs,
          ''
        )
        // 去掉剩余的 C0 控制字符（保留 \t 也没意义，命令里通常不需要）
        .replace(/[\x00-\x1F\x7F]/g, '')

      // 若上游把 ESC(0x1b) 吃掉了，可能会残留“裸 CSI/OSC 碎片”（例如 `[[0m`、`[?25l`、`]0;title`）。
      // 这些应当主要出现在字符串开头；这里仅剥离“前缀”以避免误删用户命令里合法的 `[`。
      try {
        for (let guard = 0; guard < 12; guard += 1) {
          const before = withoutAnsi
          // 裸 CSI（无 ESC）：[ ... final
          withoutAnsi = withoutAnsi.replace(/^(?:\[[0-?]*[ -/]*[@-~])+/s, '')
          // 裸 OSC（无 ESC）：] ... (BEL | ST)；ST 用 `\` 近似表示（极少见）
          withoutAnsi = withoutAnsi.replace(/^\][^\x07\\]*(?:\x07|\\)/s, '')
          // 常见残片：连续的 `[`（如 `[[0`）
          withoutAnsi = withoutAnsi.replace(/^(?:\[{2,}[0-9;?]*)+/s, '')
          if (withoutAnsi === before) break
        }
      } catch {
        /* ignore */
      }
      return withoutAnsi
    }

    function normalizeCommandText(raw) {
      let s = filterCommand(raw).trim()
      if (!s) return ''
      // 去掉提示符前缀（如果命令被错误地带上了 prompt）
      s = s.replace(/^(?:\([^)]*\)\s*)*PS\s+[A-Za-z]:[^\r\n>]*>\s*/i, '')
      s = s.replace(/^[A-Za-z]:[^\r\n>]*>\s*/i, '')
      s = s.replace(/^[#$>]\s+/, '')
      // 若出现“链式启动命令”（常见：cd ...; node ... / && ...），只保留最后一段，避免最近命令/标题被长前缀污染
      try {
        const parts = s.split(/(?:\s*&&\s*|\s*;\s*)/g).map((x) => String(x || '').trim()).filter(Boolean)
        if (parts.length > 1) s = parts[parts.length - 1]
        // 连续的 `cd ...` / `pushd ...` 前缀（某些拼接会出现多段），也尝试剥离到最后一段
        for (let guard = 0; guard < 4; guard += 1) {
          const before = s
          s = s.replace(/^(?:cd|pushd)\s+[^&;]+(?:\s*&&\s*|\s*;\s*)/i, '').trim()
          if (s === before) break
        }
      } catch {
        /* ignore */
      }
      return s.trim()
    }

    function submitPendingCommand(reason) {
      const now = Date.now()
      const rawCmd = pendingCommand.trim()
      // 过滤掉 CSI/ESC 序列 + 裸残片 + 可能混入的提示符，只保留实际输入的命令
      const cmd = normalizeCommandText(rawCmd)
      // 详细日志：显示每个字符的 charCode
      const charCodes = Array.from(rawCmd).map(c => c.charCodeAt(0)).join(',')
      console.log('[submitPendingCommand]', reason, 'rawCmd:', JSON.stringify(rawCmd), 'len:', rawCmd.length, 'codes:', charCodes, 'filtered:', JSON.stringify(cmd))

      // 可能出现：onKey 只捕获到 Enter，但字符在 onData 才到。
      // 若这里先提交了空命令并刷新 _lastSubmitAt，会把紧随其后的真实命令提交“防抖”掉。
      if (!cmd) {
        pendingCommand = ''
        return
      }
      // 防抖：某些平台 Enter 可能触发 \r\n 两次回调
      if (now - _lastSubmitAt < 120) {
        pendingCommand = ''
        return
      }
      _lastSubmitAt = now
      if (cmd && termCommandRegistry) {
        termCommandRegistry.pushCommand(props.clientSessionId, cmd)
      }
      try {
        if (cmd && onTermCommandExecuted && typeof onTermCommandExecuted === 'function') {
          console.log('[EmbeddedPtyTerminal] submit:', reason, props.clientSessionId, 'cmd=', cmd)
          onTermCommandExecuted({ client_session_id: props.clientSessionId, command: cmd, source: 'user' })
        } else if (!cmd) {
          console.log('[EmbeddedPtyTerminal] submit:', reason, props.clientSessionId, '(empty cmd)')
        }
      } catch {
        /* ignore */
      }

      // 延迟读取 buffer（避免在 onData 回调中直接访问 term.buffer 导致状态冲突）
      if (termHistoryRegistry) {
        nextTick(() => {
          try {
            const buf = term.buffer.active
            const cursorY = buf.cursorY
            let prevDir = null
            for (let y = cursorY - 1; y >= 0; y--) {
              const line = buf.getLine(y)
              if (!line || line.isWrapped) continue
              const text = line.translateToString().trim()
              if (!text) continue
              // 匹配 Windows PowerShell 提示符: PS C:\Users\...>
              const psPrompt = text.match(/PS ([A-Za-z]:[^\s>]+)/)
              if (psPrompt) {
                prevDir = psPrompt[1]
                break
              }
            }
            if (prevDir) termHistoryRegistry.pushDir(props.clientSessionId, prevDir)
            // 注册命令位置到滚动位置栈
            const termScrollRegistry = globalThis.__termScrollRegistry__
            if (termScrollRegistry) {
              termScrollRegistry.pushCommandPos(props.clientSessionId, cursorY)
            }
          } catch (e) {
            // ignore
          }
        })
      }

      pendingCommand = ''
    }

    // 优先 onKey：它提供 xterm 处理后的字符（更接近用户真实输入）
    try {
      if (typeof term.onKey !== 'function') {
        console.warn('[EmbeddedPtyTerminal] term.onKey is not a function; key capture disabled', props.clientSessionId)
      }
      let _dbgOnKeyN = 0
      const _DBG_ONKEY_MAX = 30
      term.onKey(({ key, domEvent }) => {
        if (_dbgOnKeyN < _DBG_ONKEY_MAX) {
          _dbgOnKeyN += 1
          console.log(
            '[EmbeddedPtyTerminal] onKey#' + _dbgOnKeyN,
            props.clientSessionId,
            dbgPreviewOnData(key),
            domEvent?.code || domEvent?.key || ''
          )
        }
        const k = typeof key === 'string' ? key : ''
      
        if (!k) return
        // Win32 Input Mode: 解析 CSI 序列提取实际字符
        // 格式: \e[<VK>;<SC>;<UC>;<KD>;<CS>;<RS>_  (VK=虚拟键码, SC=扫描码, UC=Unicode码点)
        const win32Match = k.match(/^\x1b\[(\d+);(\d+);(\d+);(\d+);(\d+);(\d+)_$/)
        if (win32Match) {
          const vk = parseInt(win32Match[1], 10)
          const uc = parseInt(win32Match[3], 10)
          const kd = parseInt(win32Match[4], 10) // 1=按下, 0=释放
          // 只处理按下事件
          if (kd !== 1) return
          // Enter 键 (VK_RETURN = 13)
          if (vk === 13) {
            submitPendingCommand('Win32Key_Enter')
            return
          }
          // Backspace (VK_BACK = 8)
          if (vk === 8) {
            pendingCommand = pendingCommand.slice(0, -1)
            return
          }
          // 可打印字符 (Unicode 码点 >= 32)
          if (uc >= 32) {
            pendingCommand += String.fromCharCode(uc)
          }
          return
        }
        // 普通模式处理
        // Enter
        if (k === '\r' || k === '\n') {
          submitPendingCommand('onKey')
          return
        }
        // Backspace（不同平台可能是 \x7f 或 \b）
        if (k === '\x7f' || k === '\b') {
          pendingCommand = pendingCommand.slice(0, -1)
          return
        }
        // Ctrl+U 清行
        if (domEvent && (domEvent.ctrlKey || domEvent.metaKey) && (domEvent.code === 'KeyU' || domEvent.key === 'u')) {
          pendingCommand = ''
          return
        }
        // 可打印字符（包含空格）
        if (k.length === 1 && k.charCodeAt(0) >= 32) {
          pendingCommand += k
        }
      })
    } catch {
      /* ignore */
    }

    // onData：保留作兜底（某些环境 onKey 不完整）+ 调试
    term.onData((data) => {
      if (_dbgOnDataN < _DBG_ONDATA_MAX) {
        _dbgOnDataN += 1
        console.log('[EmbeddedPtyTerminal] onData#' + _dbgOnDataN, props.clientSessionId, dbgPreviewOnData(data))
      }
      // 记录输入字符（可打印字符、退格、Enter）
      // 说明：xterm 的 onData 可能一次回调多个字符（如一次回调 "ls"、或 "\r\n"），这里逐字符解析更稳
      // 注意：Win32 Input Mode 下，字符和 Enter 都是 CSI 序列（如 \e[68;32;100;1;0;1_），需要跳过
      const s = typeof data === 'string' ? data : ''
      for (let i = 0; i < s.length; i += 1) {
        const ch = s[i]
        // Win32 Input Mode: 检测 CSI 序列（以 ESC[ 开头，以 _ 结尾）
        if (ch === '\x1b' && s[i + 1] === '[') {
          // 跳过整个 CSI 序列
          const endIdx = s.indexOf('_', i)
            if (endIdx !== -1) {
            // 检查是否是 Enter 键的 CSI 序列 (ESC[13;...)
            const seq = s.slice(i, endIdx + 1)
            if (seq.startsWith('\x1b[13;')) {
              submitPendingCommand('Win32_Enter')
            }
            i = endIdx
            continue
          }
        }
        if (ch === '\r') {
          submitPendingCommand('\\r')
          continue
        }
        if (ch === '\n') {
          submitPendingCommand('\\n')
          continue
        }
        if (ch === '\x7f') {
          pendingCommand = pendingCommand.slice(0, -1)
          continue
        }
        const code = ch.charCodeAt(0)
        if (code >= 32) {
          pendingCommand += ch
        }
      }
      emitPtyTermInput(data)
    })

    // 注册 terminal 实例，供菜单操作使用
    if (termRegistry && typeof termRegistry.register === 'function') {
      termRegistry.register(props.clientSessionId, term)
    }

    if (onTermSelectionChange) {
      term.onSelectionChange(() => {
        try {
          onTermSelectionChange()
        } catch {
          /* ignore */
        }
        scheduleSyncAddToChatFloater()
      })
    } else {
      term.onSelectionChange(() => {
        scheduleSyncAddToChatFloater()
      })
    }

    bindAddToChatDomListeners()
    attachIntegratedTerminalKeyChordHandler()

    flushPendingPtyOutput()
    badcasePtyLog('xterm open, initial cols/rows', term.cols, term.rows)

    scheduleInitialFit()
    // WebSocket 常在 mountVscodeIntegratedTerminal 完成前就 onopen；此前 onPtyConnect / watch 里的
    // scheduleTermStart 会因 !term 全部空跑。若随后 fit 迟迟未触发 onSyncedDimensions，可能永不 term_start → 黑屏。
    nextTick(() => {
      flushPendingPtyOutput()
      if (socket?.connected && !startedOnce.value && !termStartRequested) {
        if (initialFitDone) {
          badcasePtyLog('xterm mounted: retry scheduleTermStart (socket was early)')
          scheduleTermStart()
        } else {
          badcasePtyLog('xterm mounted: defer term_start until initial fit (socket was early)')
          fitNowAndSyncPty()
        }
      }
    })
  })
}

function resolveSocket() {
  if (props.mode === 'ssh') {
    ownSocket = false
    socket = null
    statusText.value = t('embeddedTerminal.sshDisabled')
    statusTone.value = 'err'
    return
  }
  if (ptySocketRef && ptySocketRef.value) {
    socket = ptySocketRef.value
    ownSocket = false
    statusText.value = socket.connected ? '' : t('embeddedTerminal.connecting')
    statusTone.value = 'info'
    return
  }
  ownSocket = false
  socket = null
  statusText.value = t('embeddedTerminal.noPtySocket')
  statusTone.value = 'err'
}

function connectFlow() {
  statusText.value = t('embeddedTerminal.connecting')
  statusTone.value = 'info'
  resolveSocket()
  if (!socket) return
  bindSocketHandlers()
  if (socket.connected) {
    nextTick(() => {
      fitNowAndSyncPty()
      if (initialFitDone && !startedOnce.value && !termStartRequested) scheduleTermStart()
    })
  }
}

let onWinResize = null

onMounted(() => {
  // 用于确认 HMR/缓存是否命中最新组件代码（仅一次）
  try {
    console.log('[EmbeddedPtyTerminal] mounted:', props.clientSessionId, 'mode=', props.mode)
  } catch {
    /* ignore */
  }
  setupTerminal()

  try {
    const fonts = typeof document !== 'undefined' ? document.fonts : null
    if (fonts && typeof fonts.ready?.then === 'function') {
      fonts.ready.then(() => fitNowAndSyncPty())
    }
  } catch {
    /* ignore */
  }

  if (selectionRegistry && typeof selectionRegistry.register === 'function') {
    selectionRegistry.register(props.clientSessionId, () =>
      term && typeof term.getSelection === 'function' ? term.getSelection() : ''
    )
  }

  if (ptySocketRef) {
    watch(
      () => [ptySocketRef.value, props.mode],
      () => {
        unbindSocketHandlers()
        const hadOwn = ownSocket
        const prevSock = socket
        socket = null
        ownSocket = false
        if (hadOwn && prevSock) {
          try {
            prevSock.close()
          } catch {
            /* ignore */
          }
        }

        if (props.mode === 'ssh') {
          socket = null
          ownSocket = false
          statusText.value = t('embeddedTerminal.sshDisabled')
          statusTone.value = 'err'
          return
        }

        const s = ptySocketRef.value
        if (!s) {
          statusText.value = t('embeddedTerminal.noPtySocket')
          statusTone.value = 'err'
          return
        }
        socket = s
        ownSocket = false
        statusText.value = s.connected ? '' : t('embeddedTerminal.connecting')
        statusTone.value = 'info'
        bindSocketHandlers()
        if (socket.connected) {
          nextTick(() => {
            fitNowAndSyncPty()
            if (initialFitDone && !startedOnce.value && !termStartRequested) scheduleTermStart()
          })
        }
      },
      { immediate: true }
    )
  } else {
    connectFlow()
  }

  if (terminalPasteRef) {
    watch(
      terminalPasteRef,
      (sig) => {
        if (!sig || !socket || !socket.connected || sig.csid !== props.clientSessionId) return
        const line = String(sig.text || '')
        if (!line) return
        // 统一为“至少一个换行触发执行”，但避免重复追加导致 `\r\r`（清屏会出现双提示符）
        const nl = /(\r\n|\n|\r)$/.test(line) ? line : `${line}\r`

 
        emitPtyTermInput(nl)
      },
      { deep: true }
    )
  }

  onWinResize = () => {
    closeCtxMenu()
    scheduleLayoutWithRecover(96)
  }
  window.addEventListener('resize', onWinResize)

  if (typeof ResizeObserver !== 'undefined' && termHost.value) {
    resizeObserver = new ResizeObserver(() => scheduleLayoutWithRecover(64))
    resizeObserver.observe(termHost.value)
  }

  if (typeof IntersectionObserver !== 'undefined' && termHost.value) {
    termHostVisibilityObserver = new IntersectionObserver(
      (entries) => {
        const e = entries && entries[0]
        if (!e?.isIntersecting) return
        const w = e.intersectionRect?.width ?? 0
        const h = e.intersectionRect?.height ?? 0
        if (w < 12 || h < 12) return
        nextTick(() => fitNowRecoverRender())
      },
      { threshold: [0, 0.02, 0.1] }
    )
    termHostVisibilityObserver.observe(termHost.value)
  }
})

watch(
  () => props.fontSize,
  (n) => {
    if (!term) return
    const next = Number(n)
    if (!Number.isFinite(next) || next < 8) return
    try {
      term.setOption('fontSize', next)
    } catch {
      /* ignore */
    }
    nextTick(() => fitNowRecoverRender())
    try {
      if (onTermFontSizeApplied && typeof onTermFontSizeApplied === 'function') {
        onTermFontSizeApplied({ client_session_id: props.clientSessionId, fontSize: next })
      }
    } catch {
      /* ignore */
    }
  }
)

watch(() => props.railResizeTick, () => scheduleLayoutWithRecover(80))

watch(
  () => props.paneActive,
  (active) => {
    if (!active) {
      addToChatVisible.value = false
      return
    }
    if (!term) return
    nextTick(() => {
      fitNowRecoverRender()
      setTimeout(() => fitNowRecoverRender(), 120)
      // 从 v-show 隐藏切到当前 tab 时才有非零 clientRect，此前可能从未 term_start
      if (socket?.connected && !startedOnce.value && !termStartRequested) {
        setTimeout(() => scheduleTermStart(), 140)
      }
    })
  }
)

watch(
  () => props.railDragging,
  (dragging) => {
    if (dragging) return
    nextTick(() => fitNowRecoverRender())
    setTimeout(() => fitNowRecoverRender(), 200)
  }
)

let findQueryDebounce = null

watch(findQuery, () => {
  if (!findVisible.value) return
  if (findQueryDebounce) clearTimeout(findQueryDebounce)
  findQueryDebounce = setTimeout(() => {
    findQueryDebounce = null
    runFindIncremental()
  }, 120)
})

onBeforeUnmount(() => {
  if (cursorTraceRaf) {
    try {
      cancelAnimationFrame(cursorTraceRaf)
    } catch {
      /* ignore */
    }
    cursorTraceRaf = 0
  }
  clearDetectCmdTimer()
  pendingPtyOutput = []
  resetPtyStdoutCrHold()
  clearPtyLayoutResizeEmitTimer()
  clearTermStartRetryTimers()
  termStartRequested = false
  if (layoutRecoverTimer != null) {
    clearTimeout(layoutRecoverTimer)
    layoutRecoverTimer = null
  }
  if (termHostVisibilityObserver) {
    try {
      if (termHost.value) termHostVisibilityObserver.unobserve(termHost.value)
    } catch {
      /* ignore */
    }
    try {
      termHostVisibilityObserver.disconnect()
    } catch {
      /* ignore */
    }
    termHostVisibilityObserver = null
  }
  if (findQueryDebounce) clearTimeout(findQueryDebounce)
  closeFind()
  try {
    clearContentWidthMinSize(termHost.value)
  } catch {
    /* ignore */
  }
  unbindSocketHandlers()
  if (selectionRegistry && typeof selectionRegistry.unregister === 'function') {
    selectionRegistry.unregister(props.clientSessionId)
  }
  if (termRegistry && typeof termRegistry.unregister === 'function') {
    termRegistry.unregister(props.clientSessionId)
  }
  if (termHistoryRegistry && typeof termHistoryRegistry.unregister === 'function') {
    termHistoryRegistry.unregister(props.clientSessionId)
  }
  if (termCommandRegistry && typeof termCommandRegistry.unregister === 'function') {
    termCommandRegistry.unregister(props.clientSessionId)
  }
  if (onWinResize) window.removeEventListener('resize', onWinResize)
  if (resizeObserver && termHost.value) {
    try {
      resizeObserver.unobserve(termHost.value)
    } catch {
      /* ignore */
    }
    resizeObserver = null
  }
  fitLayout?.dispose()
  fitLayout = null
  if (socket && socket.connected) {
    try {
      socket.emit('term_close', { client_session_id: props.clientSessionId })
    } catch {
      /* ignore */
    }
  }
  if (ownSocket && socket) {
    socket.close()
    socket = null
  }
  if (addToChatFloaterRaf) {
    cancelAnimationFrame(addToChatFloaterRaf)
    addToChatFloaterRaf = 0
  }
  unbindAddToChatDomListeners()
  addToChatVisible.value = false
  if (term) {
    term.dispose()
    term = null
  }
})
</script>

<style scoped>
.embedded-pty-root {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  border-radius: 4px;
  overflow: hidden;
}

.embedded-pty-status {
  flex: 0 0 auto;
  padding: 6px 10px;
  font-size: 12px;
  color: #f0c674;
  background: rgba(0, 0, 0, 0.35);
}

.embedded-pty-status--info {
  color: #9cdcfe;
}

.embedded-pty-status--ok {
  color: #89d185;
}

.embedded-pty-status--err {
  color: #f48771;
}

.embedded-pty-find-bar {
  position: absolute;
  top: 8px;
  right: 0;
  display: flex;
  flex-direction: row-reverse;
  align-items: center;
  gap: 4px;
  padding: 4px 12px 4px 8px;
  background: #252526;
  border: 1px solid #3c3c3c;
  border-radius: 4px 0 0 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  z-index: 100;
  width: 200px;
  min-width: 200px;
  max-width: 600px;
  user-select: none;
}

/* 左侧拖拽区域 */
.embedded-pty-find-bar::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
  background: transparent;
  z-index: 10;
}

.embedded-pty-find-bar:hover::before {
  background: rgba(255, 255, 255, 0.05);
}

.embedded-pty-find-input {
  width: 80px;
  flex: 1;
  min-width: 60px;
  font-size: 13px;
  padding: 2px 6px;
  color: #cccccc;
  background: #3c3c3c;
  border: 1px solid #5c5c5c;
  border-radius: 2px;
  outline: none;
}

.embedded-pty-find-input:focus {
  border-color: #007acc;
}

.embedded-pty-find-status {
  font-size: 12px;
  color: #808080;
  padding: 0 4px;
  min-width: 48px;
  text-align: center;
}

.embedded-pty-find-btn {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #808080;
  background: transparent;
  border: none;
  border-radius: 3px;
  cursor: pointer;
}

.embedded-pty-find-btn:hover {
  color: #cccccc;
  background: rgba(255, 255, 255, 0.1);
}

.embedded-pty-find-btn.active {
  color: #4ec9b0;
}

.embedded-pty-find-close {
  margin-left: 2px;
}

.embedded-pty-xterm-wrap {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  box-sizing: border-box;
  /* 顶部略留白：少一行栅格后单格变高，首行易贴顶；底部仍 0 以免再现底边 padding 条 */
  padding: 8px 6px 0;
  /* 过窄时横向滚动，避免 fit 出个位数列却给 ConPTY 发 term_resize */
  overflow-x: auto;
  overflow-y: hidden;
}

.embedded-pty-xterm-wrap.embedded-pty-xterm-wrap-content-width {
  overflow-x: auto;
}

.embedded-pty-xterm-wrap.embedded-pty-xterm-wrap-content-width :deep(.xterm-viewport) {
  overflow-x: auto;
}

.embedded-pty-xterm-host {
  width: 100%;
  height: 100%;
  min-width: 17rem;
  min-height: 0;
}

.embedded-pty-xterm-host :deep(.xterm) {
  height: 100%;
  width: 100%;
}

.embedded-pty-xterm-wrap :deep(.xterm-viewport) {
  overflow-y: auto;
  overflow-x: hidden;
}

/* Teleport 根：不拦截终端区点击；子层各自 pointer-events */
.etw-terminal-ctx-portal-root {
  position: fixed;
  inset: 0;
  z-index: 10048;
  pointer-events: none;
}

.etw-terminal-ctx-portal-root .etw-terminal-ctx-menu-backdrop {
  pointer-events: auto;
}

.etw-terminal-ctx-portal-root .etw-terminal-ctx-menu-floater {
  pointer-events: auto;
}

.ept-add-to-chat-root {
  position: fixed;
  z-index: 10050;
  pointer-events: none;
}

.ept-add-to-chat-chip {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  min-height: 28px;
  font-size: 12px;
  line-height: 1.2;
  color: #e6e6e6;
  background: #2d2d30;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 4px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.ept-add-to-chat-chip:hover {
  background: #3c3c3c;
  border-color: rgba(255, 255, 255, 0.2);
}

.ept-add-to-chat-label {
  font-weight: 500;
}

.ept-add-to-chat-kbd {
  font-size: 11px;
  color: #a8a8a8;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
