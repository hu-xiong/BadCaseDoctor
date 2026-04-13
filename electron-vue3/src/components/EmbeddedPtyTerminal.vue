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
      class="embedded-pty-find-bar etw-vscode-terminal vs-dark"
      @keydown.capture.stop="onFindBarKeydown"
    >
      <input
        ref="findInputRef"
        v-model="findQuery"
        type="search"
        class="embedded-pty-find-input"
        :placeholder="t('embeddedTerminal.findPlaceholder')"
        autocomplete="off"
        spellcheck="false"
      />
      <label class="embedded-pty-find-case">
        <input v-model="findCaseSensitive" type="checkbox" @change="runFindIncremental" />
        <span>{{ t('embeddedTerminal.findCaseSensitive') }}</span>
      </label>
      <button
        type="button"
        class="embedded-pty-find-btn"
        :title="t('embeddedTerminal.findPrev')"
        @click="findPrevClick"
      >
        ↑
      </button>
      <button
        type="button"
        class="embedded-pty-find-btn"
        :title="t('embeddedTerminal.findNext')"
        @click="findNextClick"
      >
        ↓
      </button>
      <span class="embedded-pty-find-status">{{ findMatchStatus }}</span>
      <button
        type="button"
        class="embedded-pty-find-btn embedded-pty-find-close"
        :title="t('embeddedTerminal.findClose')"
        @click="closeFind"
      >
        ×
      </button>
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
/** Windows ConPTY 路径：stdin 将 DEL(0x7F) 换成 BS(0x08)，否则 PSReadLine 常不删字符 */
let windowsConptyStdinDelToBs = false
/** 本地退格标志：当用户在 attachCustomKeyEventHandler 中拦截退格并发送 BS 到 PTY 时设置，用于忽略 PTY 回显的 BS */
let localBackspacePending = false
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
    
    // Windows ConPTY 退格回显处理：
    // 当用户在 attachCustomKeyEventHandler 中拦截退格并发送 BS 到 PTY 时，xterm 没有本地处理退格。
    // PTY 会回显 BS，但 xterm 不应该再次处理这个 BS（因为没有本地字符可删）。
    // 如果收到单个 BS 且 localBackspacePending 为 true，忽略这个 BS。
    if (u8.length === 1 && u8[0] === 0x08 && localBackspacePending) {
      localBackspacePending = false
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

    // Windows ConPTY 退格键处理：
    // 在 win32InputMode 下，xterm 本地处理退格（删除本地字符），但 PTY 也会回显 BS。
    // 这导致双重删除。解决方案：拦截退格键，阻止 xterm 本地处理，只发送 BS 到 PTY。
    // PTY 会处理退格（更新内部状态），并回显 BS。xterm 忽略回显的 BS（因为没有本地字符可删）。
    if (ev.key === 'Backspace' && navIsWindowsHost() && props.mode !== 'ssh') {
      ev.stopPropagation()
      // 发送 BS 到 PTY（让 PTY 更新内部状态）
      emitPtyTermInput('\u0008')
      // 阻止 xterm 本地处理（避免双重删除）
      // 注意：xterm 的 onData 仍会触发，但我们稍后通过 localBackspacePending 忽略 PTY 回显
      // 所以这里返回 false 阻止 xterm 默认处理
      return false
    }

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
  
  // 生成终端引用而不是直接复制文本
  // 格式：@log:session_<id>#L<start>-L<end>
  const sessionId = props.clientSessionId
  const head = t('embeddedTerminal.addToChatPrefillPrefix')
  
  // 这里简化处理，实际应该获取选中的行号范围
  // 由于 xterm.js 没有直接提供行号信息，我们使用简化的引用格式
  const reference = `@log:${sessionId}#L1-L100`
  
  openAiComposerPrefill(`${head}\n\n${reference}`)
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

function updateWindowsConptyStdinNorm(payload) {
  if (props.mode === 'ssh') {
    windowsConptyStdinDelToBs = false
    return
  }
  const backend = String(payload?.windows_pty?.backend || '').toLowerCase()
  if (backend === 'conpty') {
    windowsConptyStdinDelToBs = true
    return
  }
  if (!navIsWindowsHost()) {
    windowsConptyStdinDelToBs = false
    return
  }
  const sid = socket?.id
  if (sid === 'browser-go-local' || sid === 'electron-local') {
    windowsConptyStdinDelToBs = true
    return
  }
  windowsConptyStdinDelToBs = false
}

function emitPtyTermInput(data) {
  if (!socket || !socket.connected) return
  // Windows ConPTY 路径：始终将 DEL(0x7F) 换成 BS(0x08)，确保退格键能正确删除字符。
  let s = data
  if (windowsConptyStdinDelToBs && typeof data === 'string' && data.indexOf('\u007f') >= 0) {
    s = data.replace(/\u007f/g, '\u0008')
  }
  
  // 当发送 BS 到 PTY 时，设置标志以忽略 PTY 回显的 BS（避免双重删除）
  if (s === '\u0008') {
    localBackspacePending = true
  }
  if (badcasePtyDebugEnabled() && termInputDbgCount < TERM_INPUT_DBG_MAX) {
    termInputDbgCount += 1
    const u8 = typeof s === 'string' ? new TextEncoder().encode(s) : new Uint8Array()
    badcasePtyLog('term_input', {
      n: termInputDbgCount,
      socketId: socket?.id,
      utf16Units: typeof s === 'string' ? s.length : 0,
      utf8Bytes: u8.length,
      windowsConptyStdinDelToBs,
      preview: dbgTermInputU8Esc(u8, 56)
    })
  }
  try {
    socket.emit('term_input', {
      b64: stringToUtf8B64(s),
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
  updateWindowsConptyStdinNorm(null)
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
  windowsConptyStdinDelToBs = false
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
  updateWindowsConptyStdinNorm(payload)
  badcasePtyLog('term_started xterm keys', {
    win32InputMode: isXtermWin32InputMode(term),
    windows_pty: payload?.windows_pty,
    delToBsPath: windowsConptyStdinDelToBs,
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
  windowsConptyStdinDelToBs = false
  localBackspacePending = false
  termInputDbgCount = 0
}

function setupTerminal() {
  const host = termHost.value
  if (!host) return
  void mountVscodeIntegratedTerminal(host, {
    win32InputMode: props.mode !== 'ssh' && navIsWindowsHost()
  }).then(({ term: xterm, fit: f, serializeAddon: sa }) => {
    term = xterm
    fit = f
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

    term.onData((data) => {
      emitPtyTermInput(data)
    })

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
        const nl = line.endsWith('\n') ? line : `${line}\r`
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
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 5px 8px;
  background: rgba(58, 61, 65, 0.95);
  border-bottom: 1px solid rgba(62, 62, 66, 0.9);
}

.embedded-pty-find-input {
  flex: 1 1 120px;
  max-width: 420px;
  min-width: 100px;
  font-size: 13px;
  padding: 4px 8px;
  color: #cccccc;
  background: #3c3c3c;
  border: 1px solid #3e3e42;
  border-radius: 2px;
  outline: none;
}

.embedded-pty-find-input:focus {
  border-color: #007fd4;
}

.embedded-pty-find-case {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #cccccc;
  white-space: nowrap;
  user-select: none;
}

.embedded-pty-find-btn {
  flex: 0 0 auto;
  min-width: 28px;
  height: 26px;
  padding: 0 8px;
  font-size: 14px;
  line-height: 1;
  color: #cccccc;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  cursor: pointer;
}

.embedded-pty-find-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.embedded-pty-find-close {
  font-size: 18px;
  padding: 0 6px;
}

.embedded-pty-find-status {
  font-size: 12px;
  color: #9d9d9d;
  min-width: 5em;
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
