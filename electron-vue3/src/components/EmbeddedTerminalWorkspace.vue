<template>
  <div
    ref="etwRootRef"
    class="etw-root etw-vscode-terminal monaco-workbench vs-dark"
    :style="rootWorkbenchStyle"
  >
    <!-- pane-body 必须作为 monaco-workbench 的子节点，否则 integratedTerminalPanel.css 里大量选择器不生效（会话列会变成系统默认按钮白底） -->
    <div class="pane-body integrated-terminal etw-terminal-pane-fill">
    <!-- VS Code panel title strip + 业务：代理条 / 白名单 -->
    <div class="etw-panel-title">
      <div class="etw-panel-title-left">
        <span class="etw-pane-title-text">{{ t('embeddedTerminal.tab') }}</span>
        <span v-if="terminalCfg?.ai_whitelist_enabled" class="etw-top-pill">
          {{ t('embeddedTerminal.whitelistOn') }}
        </span>
        <WebLocalGoProxyBar :working-directory="effectiveWorkingDirectory" :project-id="projectId" />
      </div>
      <div class="etw-panel-title-right">
        <div class="monaco-toolbar etw-terminal-tabs-toolbar etw-panel-terminal-toolbar">
          <button
            type="button"
            class="action-item codicon codicon-add"
            :title="t('embeddedTerminal.newTab')"
            @click="addTab()"
          />
          <div class="etw-terminal-menu-anchor etw-vscode-menu-anchor">
            <button
              type="button"
              class="action-item codicon codicon-ellipsis"
              :title="t('common.more')"
              @click="toggleMoreMenu"
            />
            <div v-if="showMoreMenu" class="etw-vscode-menu etw-vscode-menu-wide" @click="showMoreMenu = false">
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="clearActive()">
                {{ t('embeddedTerminal.clearScreen') }}
              </button>
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="closeActiveTab()">
                {{ t('embeddedTerminal.closeTab') }}
              </button>
              <div class="etw-vscode-menu-sep" />
              <button type="button" class="etw-vscode-menu-item" @click.stop="openQuickEditor()">
                {{ t('embeddedTerminal.editQuickCommands') }}
              </button>
              <button type="button" class="etw-vscode-menu-item" :disabled="auditExporting" @click.stop="exportAuditCsv()">
                {{ t('embeddedTerminal.exportAudit') }}
              </button>
              <button
                v-if="openAiComposerPrefill"
                type="button"
                class="etw-vscode-menu-item"
                @click.stop="onOpenChatForCommands"
              >
                {{ t('embeddedTerminal.openChatForCommands') }}
              </button>
              <button
                v-if="openNewBadcaseFromTerminal"
                type="button"
                class="etw-vscode-menu-item"
                :disabled="!hasTerminalSelection"
                @click.stop="createBadcaseFromTerminal"
              >
                {{ t('embeddedTerminal.createBadcaseFromTerminal') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 路径由 Shell 在 xterm 内绘制（如 PS C:\...>），与 Cursor 一致；cwd 仅通过 term_start 传入 -->
    <!-- 对齐 terminalTabbedView：terminal-outer-container = 编辑区 | sash | tabs-container -->
    <div ref="terminalOuterRef" class="terminal-outer-container etw-terminal-outer-fill">
      <div class="terminal-groups-container">
        <div class="terminal-split-pane etw-terminal-main-pane">
          <div class="terminal-wrapper etw-terminal-editor-wrapper">
            <EmbeddedPtyTerminal
              v-for="t in tabs"
              v-show="activeTabId === t.id"
              :key="t.id"
              :client-session-id="t.id"
              :mode="t.mode"
              :ssh-config="t.ssh"
              :working-directory="effectiveWorkingDirectory"
              :project-id="projectId"
              :rail-resize-tick="sessionRailResizeTick"
              :rail-dragging="sessionRailDragging"
              :pane-active="activeTabId === t.id"
            />
          </div>
        </div>
      </div>

      <div
        class="etw-vscode-sash"
        role="separator"
        aria-orientation="vertical"
        :aria-valuenow="sessionRailWidthPx"
        :aria-valuemin="tabsListMinW"
        :aria-valuemax="tabsListMaxW"
        :title="t('embeddedTerminal.resizeSessionRail')"
        @mousedown.prevent="onSessionRailResizeStart"
      />

      <div class="tabs-container has-text" :style="tabsColumnStyle">
        <div class="tabs-list-container">
          <div
            ref="tabsListRef"
            class="tabs-list"
            :class="{ 'etw-tabs-list--scrollable': tabsListScrollable }"
            role="tablist"
            :aria-label="t('embeddedTerminal.sessions')"
          >
            <div
              v-for="tab in tabs"
              :key="tab.id"
              class="etw-terminal-tab-row"
              role="presentation"
              @mouseenter="onRailItemEnter($event, tab)"
              @mouseleave="onRailItemLeave"
            >
              <button
                type="button"
                role="tab"
                class="terminal-tabs-entry monaco-list-row"
                :class="{ 'is-active': activeTabId === tab.id }"
                :aria-selected="activeTabId === tab.id"
                :title="tab.label"
                @click="selectTerminalTab(tab.id)"
                @keydown.enter.prevent="selectTerminalTab(tab.id)"
                @keydown.space.prevent="selectTerminalTab(tab.id)"
              >
                <span class="codicon" :class="embeddedTerminalTabCodicon(tab)" aria-hidden="true" />
                <span class="terminal-tab-label">{{ tab.label }}</span>
              </button>
              <div class="etw-terminal-tab-row-actions">
                <button
                  type="button"
                  class="etw-terminal-tab-action codicon codicon-split-horizontal"
                  :title="t('embeddedTerminal.splitTerminal')"
                  @click.stop="splitTerminal()"
                />
                <button
                  type="button"
                  class="etw-terminal-tab-action codicon codicon-trash"
                  :title="t('embeddedTerminal.killTerminal')"
                  @click.stop="closeTabById(tab.id)"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>

    <div
      v-if="railTooltip.visible"
      class="etw-session-tooltip"
      :style="{ top: railTooltip.top + 'px', left: railTooltip.left + 'px' }"
      role="tooltip"
    >
      <div class="etw-session-tooltip-title">{{ railTooltip.title }}</div>
      <div v-if="railTooltip.pid" class="etw-session-tooltip-line">Process ID (PID): {{ railTooltip.pid }}</div>
      <div v-if="railTooltip.shell" class="etw-session-tooltip-line">Command line: {{ railTooltip.shell }}</div>
      <div v-if="railTooltip.cwd" class="etw-session-tooltip-line">Cwd: {{ railTooltip.cwd }}</div>
      <div v-if="railTooltip.clientSessionId" class="etw-session-tooltip-line">Session: {{ railTooltip.clientSessionId }}</div>
    </div>

    <div v-if="showQuickEditor" class="etw-modal-overlay" @click.self="showQuickEditor = false">
      <div class="etw-modal">
        <div class="etw-modal-title">{{ t('embeddedTerminal.editQuickCommands') }}</div>
        <p class="small text-muted mb-2">{{ t('embeddedTerminal.quickEditHint') }}</p>
        <textarea v-model="quickEditText" class="form-control etw-quick-edit-ta" rows="8" />
        <div class="etw-modal-actions">
          <button type="button" class="btn btn-sm btn-secondary" @click="showQuickEditor = false">{{ t('common.cancel') }}</button>
          <button type="button" class="btn btn-sm btn-primary" @click="saveQuickCommands">{{ t('common.save') }}</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, provide, computed, inject, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import '@vscode/codicons/dist/codicon.css'
/* 必须先于 integratedTerminalPanel：否则子组件里引入的 xterm.css 会后到，盖住面板里对 .xterm-shadow 等的覆盖 */
import '@xterm/xterm/css/xterm.css'
import '../vscode-terminal-ui/vscodeIntegratedTerminalPanel.css'
import {
  integratedTerminalWorkbenchDarkVars,
  TerminalTabsListSizes,
  embeddedTerminalTabCodicon
} from '../vscode-terminal-ui'
import { api, BACKEND_BASE_URL } from '../api.js'
import EmbeddedPtyTerminal from './EmbeddedPtyTerminal.vue'
import WebLocalGoProxyBar from './WebLocalGoProxyBar.vue'
import {
  createElectronLocalPtySocket,
  isElectronPtyAvailable,
  isElectronShell
} from '../utils/electronPtySocketAdapter.js'
import { createBrowserGoLocalPtySocket } from '../utils/browserGoPtySocketAdapter.js'
import { localGoProxyOk } from '../composables/useLocalGoProxyStatus'

const { t } = useI18n()

const rootWorkbenchStyle = computed(() => integratedTerminalWorkbenchDarkVars())
const tabsListMinW = TerminalTabsListSizes.WideViewMinimumWidth
const tabsListMaxW = TerminalTabsListSizes.MaximumWidth

const props = defineProps({
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null }
})

/** Electron：主进程推断的默认 cwd（permissions.workspace_root 或 process.cwd），在 onMounted 里异步填入 */
const electronDefaultCwd = ref('')

/**
 * 浏览器：未手动指定目录时不传 cwd → go-local-proxy 起 PTY 时用**代理进程自身的当前目录**
 *（即你在哪个目录下启动的 badcase-local-proxy，Shell 默认就在那里；不再强行用 exe 所在目录）。
 * Electron：未传时用主进程默认 cwd。
 */
const effectiveWorkingDirectory = computed(() => {
  void electronDefaultCwd.value
  const manual = String(props.workingDirectory || '').trim()
  if (manual) return manual
  if (isElectronShell()) return String(electronDefaultCwd.value || '').trim()
  return ''
})

const terminalCtl = inject('terminalCtl', null)
const openAiComposerPrefill = inject('openAiComposerPrefill', null)
const openNewBadcaseFromTerminal = inject('openNewBadcaseFromTerminal', null)

const socketRef = ref(null)
const terminalPasteRef = ref({ token: 0, csid: '', text: '' })
provide('ptySocket', socketRef)

/** 浏览器：/health 已绿但 /pty WebSocket 曾失败或已断开时，延迟重建，避免与首次握手竞态 */
let browserPtyReconnectTimer = null

function clearBrowserPtyReconnectTimer() {
  if (browserPtyReconnectTimer != null) {
    clearTimeout(browserPtyReconnectTimer)
    browserPtyReconnectTimer = null
  }
}

function onBrowserGoLocalWsDisconnect() {
  if (isElectronShell() || isElectronPtyAvailable()) return
  if (localGoProxyOk.value !== true) return
  scheduleBrowserGoLocalPtyReconnect('ws-disconnect')
}

function scheduleBrowserGoLocalPtyReconnect(reason) {
  if (isElectronShell() || isElectronPtyAvailable()) return
  if (localGoProxyOk.value !== true) return
  const cur = socketRef.value
  if (!cur || cur.id !== 'browser-go-local' || cur.connected) return
  clearBrowserPtyReconnectTimer()
  browserPtyReconnectTimer = window.setTimeout(() => {
    browserPtyReconnectTimer = null
    if (localGoProxyOk.value !== true) return
    const s = socketRef.value
    if (!s || s.id !== 'browser-go-local' || s.connected) return
    try {
      s.off?.('disconnect', onBrowserGoLocalWsDisconnect)
    } catch (_) {
      /* ignore */
    }
    try {
      s.close()
    } catch (_) {
      /* ignore */
    }
    socketRef.value = createBrowserGoLocalPtySocket()
    try {
      socketRef.value.on?.('disconnect', onBrowserGoLocalWsDisconnect)
    } catch (_) {
      /* ignore */
    }
    console.log('[EmbeddedTerminalWorkspace] 已自动重连本机 /pty WebSocket（' + String(reason) + '）')
  }, 450)
}

watch(localGoProxyOk, (ok, prevOk) => {
  if (ok !== true || prevOk !== false) return
  scheduleBrowserGoLocalPtyReconnect('proxy-health-recovered')
})
provide('terminalPaste', terminalPasteRef)

const selectionMap = new Map()
const terminalSelectionRegistry = {
  register(csid, getter) {
    selectionMap.set(csid, getter)
  },
  unregister(csid) {
    selectionMap.delete(csid)
  }
}
provide('terminalSelectionRegistry', terminalSelectionRegistry)

const selectionVersion = ref(0)
function bumpTerminalSelection() {
  selectionVersion.value += 1
}
provide('onTermSelectionChange', bumpTerminalSelection)

function getActiveSelection() {
  const id = activeTabId.value
  if (!id) return ''
  const g = selectionMap.get(id)
  try {
    return g ? String(g() || '') : ''
  } catch (_) {
    return ''
  }
}

const hasTerminalSelection = computed(() => {
  selectionVersion.value
  activeTabId.value
  return !!getActiveSelection().trim()
})

const SESSION_RAIL_W_KEY = 'embeddedTerminalSessionRailW'

const tabs = ref([])
const activeTabId = ref(null)
const ptySessionMeta = ref({})
const sessionRailResizeTick = ref(0)

provide('onPtySessionMeta', (meta) => {
  if (!meta || typeof meta !== 'object') return
  const sid = String(meta.client_session_id || '').trim()
  if (!sid) return
  ptySessionMeta.value = {
    ...ptySessionMeta.value,
    [sid]: {
      ...ptySessionMeta.value[sid],
      ...meta,
      updatedAt: Date.now()
    }
  }
})

const railTooltip = ref({
  visible: false,
  top: 0,
  left: 0,
  title: '',
  pid: '',
  shell: '',
  cwd: '',
  clientSessionId: ''
})

function onRailItemEnter(e, tab) {
  const el = e?.currentTarget
  if (!el || typeof el.getBoundingClientRect !== 'function') return
  const r = el.getBoundingClientRect()
  const sid = tab?.id ? String(tab.id) : ''
  const meta = sid ? ptySessionMeta.value[sid] : null
  const label = (tab?.label ? String(tab.label) : '').trim() || (sid ? `Session ${sid.slice(0, 6)}` : 'Session')
  railTooltip.value = {
    visible: true,
    top: Math.round(r.top + 2),
    left: Math.round(r.right + 10),
    title: label,
    pid: meta?.pid != null ? String(meta.pid) : '',
    shell: meta?.shell ? String(meta.shell) : '',
    cwd: meta?.cwd ? String(meta.cwd) : '',
    clientSessionId: sid
  }
}

function onRailItemLeave() {
  railTooltip.value = { ...railTooltip.value, visible: false }
}

/** 右侧标签列宽度（px），对齐 TerminalTabsListSizes，可拖动 sash 调整 */
const sessionRailWidthPx = ref(TerminalTabsListSizes.DefaultWidth)
const sessionRailDragging = ref(false)
const terminalOuterRef = ref(null)
const tabsListRef = ref(null)
const tabsListScrollable = ref(false)
let tabsListResizeObserver = null

function updateTabsListScrollable() {
  nextTick(() => {
    const el = tabsListRef.value
    if (!el) {
      tabsListScrollable.value = false
      return
    }
    tabsListScrollable.value = el.scrollHeight > Math.ceil(el.clientHeight) + 1
  })
}
const etwRootRef = ref(null)

function focusEmbeddedTerminalArea() {
  nextTick(() => {
    const root = etwRootRef.value
    try {
      root?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
    } catch (_) {
      try {
        root?.scrollIntoView?.(true)
      } catch (_) {
        /* ignore */
      }
    }
    const ta =
      root?.querySelector?.('.xterm-helper-textarea') ||
      root?.querySelector?.('.xterm textarea') ||
      root?.querySelector?.('textarea')
    try {
      ta?.focus?.({ preventScroll: true })
    } catch (_) {
      try {
        ta?.focus?.()
      } catch (_) {
        /* ignore */
      }
    }
  })
}

const tabsColumnStyle = computed(() => ({
  width: `${sessionRailWidthPx.value}px`,
  flex: `0 0 ${sessionRailWidthPx.value}px`,
  minWidth: `${TerminalTabsListSizes.WideViewMinimumWidth}px`
}))

function clampSessionRail(n, outerEl) {
  const minRail = TerminalTabsListSizes.WideViewMinimumWidth
  const maxRail = TerminalTabsListSizes.MaximumWidth
  const minTerm = 140
  if (!outerEl || typeof outerEl.getBoundingClientRect !== 'function') {
    return Math.max(minRail, Math.min(maxRail, n))
  }
  const w = outerEl.getBoundingClientRect().width
  const maxBySplit = Math.max(minRail, w - minTerm - 8)
  return Math.max(minRail, Math.min(Math.min(maxRail, maxBySplit), n))
}

function onSessionRailResizeStart(e) {
  const outerEl = terminalOuterRef.value
  if (!outerEl) return
  const startX = e.clientX
  const startW = sessionRailWidthPx.value
  sessionRailDragging.value = true

  function onMove(ev) {
    const next = Math.round(startW + (startX - ev.clientX))
    sessionRailWidthPx.value = clampSessionRail(next, outerEl)
    sessionRailResizeTick.value += 1
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    sessionRailResizeTick.value += 1
    sessionRailDragging.value = false
    try {
      localStorage.setItem(SESSION_RAIL_W_KEY, String(sessionRailWidthPx.value))
    } catch (_) {
      /* ignore */
    }
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

const auditExporting = ref(false)
const terminalCfg = ref(null)
const showQuickEditor = ref(false)
const quickEditText = ref('')
const quickCmdVersion = ref(0)

function openQuickEditor() {
  quickEditText.value = quickCommands.value.join('\n')
  showQuickEditor.value = true
}

function saveQuickCommands() {
  const lines = quickEditText.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 12)
  try {
    localStorage.setItem('embeddedTerminalQuickCmds', JSON.stringify(lines))
    quickCmdVersion.value += 1
    showQuickEditor.value = false
  } catch (e) {
    console.error(e)
  }
}

const quickCommands = computed(() => {
  quickCmdVersion.value
  try {
    const raw = localStorage.getItem('embeddedTerminalQuickCmds')
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr) && arr.length) return arr.slice(0, 12).map((x) => String(x))
    }
  } catch (_) {
    /* ignore */
  }
  const win = /Win/i.test(navigator.platform || '') || /Windows/i.test(navigator.userAgent || '')
  return win ? ['cd', 'dir', 'echo %USERNAME%'] : ['pwd', 'ls -la', 'echo $USER']
})

function newTabId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `t-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function selectTerminalTab(id) {
  if (!id) return
  if (!tabs.value.some((x) => x.id === id)) return
  activeTabId.value = id
}

function addTab() {
  const id = newTabId()
  const mode = 'local'
  const ssh = {}
  const kind = 'local'
  const label = t('embeddedTerminal.tabLocal')
  tabs.value.push({ id, mode, ssh, label, kind })
  activeTabId.value = id
}

function addAgentTab() {
  const id = newTabId()
  tabs.value.push({
    id,
    mode: 'local',
    ssh: {},
    label: t('embeddedTerminal.sessionAgent'),
    kind: 'agent'
  })
  activeTabId.value = id
  return id
}

const showMoreMenu = ref(false)

function closeAllMenus() {
  showMoreMenu.value = false
}

function toggleMoreMenu() {
  showMoreMenu.value = !showMoreMenu.value
}

function onDocPointerDown(e) {
  const el = e?.target
  if (!el) return
  if (el.closest && el.closest('.etw-vscode-menu-anchor')) return
  closeAllMenus()
}

/** 对齐 VS Code「拆分终端」：本嵌入场景为新建会话（非同一组内真分屏）。 */
function splitTerminal() {
  addTab()
}

function closeTabById(id) {
  if (!id || !tabs.value.some((x) => x.id === id)) return
  const wasActive = activeTabId.value === id
  tabs.value = tabs.value.filter((x) => x.id !== id)
  if (!tabs.value.length) {
    activeTabId.value = null
    return
  }
  if (wasActive) {
    activeTabId.value = tabs.value[tabs.value.length - 1].id
  }
}

function closeActiveTab() {
  const id = activeTabId.value
  if (!id) return
  closeTabById(id)
}

function clearActive() {
  if (!activeTabId.value) return
  const win = /Win/i.test(navigator.platform || '') || /Windows/i.test(navigator.userAgent || '')
  const text = win ? 'cls\r' : 'clear\n'
  terminalPasteRef.value = { token: Date.now(), csid: activeTabId.value, text }
}

/**
 * 投递命令到终端（优先 Agent 会话）
 * @param {string} cmd
 * @param {{ preferAgent?: boolean }} opts
 */
function injectCommand(cmd, opts = {}) {
  const preferAgent = opts.preferAgent !== false
  let targetId = activeTabId.value
  if (preferAgent) {
    let ag = tabs.value.find((x) => x.kind === 'agent')
    if (!ag) {
      addAgentTab()
      ag = tabs.value.find((x) => x.kind === 'agent')
    }
    if (ag) targetId = ag.id
  }
  if (!targetId) {
    addTab()
    targetId = activeTabId.value
  }
  activeTabId.value = targetId
  const raw = String(cmd || '')
  const line = raw.includes('\n') && !raw.endsWith('\r') ? raw.replace(/\n/g, '\r\n') + '\r' : `${raw}\r`
  terminalPasteRef.value = { token: Date.now(), csid: targetId, text: line }
}

function onOpenChatForCommands() {
  if (openAiComposerPrefill) {
    openAiComposerPrefill(
      t('embeddedTerminal.defaultComposerPrompt')
    )
  }
}

function createBadcaseFromTerminal() {
  if (!openNewBadcaseFromTerminal) return
  const raw = getActiveSelection().trim()
  if (!raw) return
  openNewBadcaseFromTerminal(`【终端选中输出】\n${raw}`)
}

async function exportAuditCsv() {
  if (auditExporting.value) return
  auditExporting.value = true
  try {
    const res = await fetch(`${BACKEND_BASE_URL}/api/terminal/audit/export`, { credentials: 'include' })
    if (!res.ok) throw new Error(String(res.status))
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'terminal_audit.csv'
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error(e)
  } finally {
    auditExporting.value = false
  }
}

async function loadTerminalConfig() {
  try {
    const { data } = await api.get('/api/terminal/config')
    if (data.success) terminalCfg.value = data
  } catch (_) {
    /* ignore */
  }
}

function quickRun(cmd) {
  if (!activeTabId.value) {
    addTab()
  }
  terminalPasteRef.value = { token: Date.now(), csid: activeTabId.value, text: `${cmd}\r` }
}

watch(
  tabs,
  (list) => {
    if (!list.length) {
      activeTabId.value = null
      return
    }
    if (!list.some((x) => x.id === activeTabId.value)) {
      activeTabId.value = list[list.length - 1].id
    }
  },
  { deep: true }
)

watch(
  [tabs, sessionRailWidthPx, sessionRailResizeTick],
  () => updateTabsListScrollable(),
  { deep: true, flush: 'post' }
)

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.addEventListener('pointerdown', onDocPointerDown, { capture: true })
    try {
      const raw = localStorage.getItem(SESSION_RAIL_W_KEY)
      if (raw != null) {
        const n = parseInt(raw, 10)
        if (Number.isFinite(n)) {
          nextTick(() => {
            sessionRailWidthPx.value = clampSessionRail(n, terminalOuterRef.value)
          })
        }
      }
    } catch (_) {
      /* ignore */
    }
  }
  loadTerminalConfig()
  if (isElectronShell() && typeof window !== 'undefined' && window.electronTerminalAgent?.getEmbeddedTerminalDefaultCwd) {
    try {
      const r = await window.electronTerminalAgent.getEmbeddedTerminalDefaultCwd()
      const c = r && r.cwd != null ? String(r.cwd).trim() : ''
      if (c) electronDefaultCwd.value = c
    } catch (_) {
      /* ignore */
    }
  }
  if (isElectronPtyAvailable()) {
    console.log('[EmbeddedTerminalWorkspace] Electron 本地 PTY（不经 Python 终端服务）')
    socketRef.value = createElectronLocalPtySocket()
  } else {
    console.log('[EmbeddedTerminalWorkspace] 浏览器本机终端 → go-local-proxy /pty')
    socketRef.value = createBrowserGoLocalPtySocket()
    try {
      socketRef.value.on?.('disconnect', onBrowserGoLocalWsDisconnect)
    } catch (_) {
      /* ignore */
    }
  }
  if (!tabs.value.length) {
    addTab()
  }

  nextTick(() => {
    updateTabsListScrollable()
    const el = tabsListRef.value
    if (el && typeof ResizeObserver !== 'undefined') {
      tabsListResizeObserver = new ResizeObserver(() => updateTabsListScrollable())
      tabsListResizeObserver.observe(el)
    }
  })

  if (terminalCtl) {
    terminalCtl.value = {
      injectCommand,
      focusTerminal: focusEmbeddedTerminalArea
    }
  }
})

onBeforeUnmount(() => {
  clearBrowserPtyReconnectTimer()
  try {
    socketRef.value?.off?.('disconnect', onBrowserGoLocalWsDisconnect)
  } catch (_) {
    /* ignore */
  }
  if (tabsListResizeObserver) {
    try {
      tabsListResizeObserver.disconnect()
    } catch (_) {
      /* ignore */
    }
    tabsListResizeObserver = null
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointerdown', onDocPointerDown, { capture: true })
  }
  if (socketRef.value) {
    try {
      socketRef.value.close()
    } catch (_) {
      /* ignore */
    }
    socketRef.value = null
  }
  if (terminalCtl) {
    terminalCtl.value = null
  }
})
</script>

<style scoped>
.etw-root {
  display: flex;
  flex-direction: column;
  /* 嵌入 ProjectDetail 底栏等小高度区域时，min-height:280px 会撑破父级 flex，xterm 宿主高度可变成 0 → write 成功但画布不可见 */
  flex: 1 1 0;
  min-height: 0;
  height: 100%;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

/* VS Code 风格 hover tooltip（会话条目） */
.etw-session-tooltip {
  position: fixed;
  z-index: 2600;
  max-width: min(520px, 55vw);
  padding: 10px 12px;
  background: #252526;
  border: 1px solid #3e3e42;
  border-radius: 8px;
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.45);
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.45;
  pointer-events: none;
}
.etw-session-tooltip-title {
  font-weight: 600;
  margin: 0 0 6px;
  color: #e5e7eb;
}
.etw-session-tooltip-line {
  white-space: pre-wrap;
  word-break: break-word;
  color: #c7c7c7;
}

.etw-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.etw-modal {
  background: #2d2d2d;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 16px;
  min-width: 320px;
  max-width: 90vw;
}

.etw-modal-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #eee;
}

.etw-quick-edit-ta {
  font-size: 12px;
  font-family: ui-monospace, monospace;
  margin-bottom: 12px;
}

.etw-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
