<template>
  <div
    ref="etwRootRef"
    class="etw-root etw-vscode-terminal monaco-workbench vs-dark"
    :style="rootWorkbenchStyle"
  >
    <!-- 命令历史弹窗（嵌入终端区域内，顶部下拉） -->
    <div v-if="showCmdHistory" class="etw-cmd-history-host" @click.self="showCmdHistory = false">
      <div class="etw-cmd-history-panel">
        <div class="etw-cmd-history-search-row">
          <span class="etw-cmd-history-search-icon codicon codicon-search"></span>
          <input
            ref="cmdSearchInput"
            v-model="cmdSearchText"
            class="etw-cmd-history-search-input"
            :placeholder="t('embeddedTerminal.searchPlaceholder')"
            @keydown="onCmdSearchKeydown"
          />
        </div>
        <div class="etw-cmd-history-divider"></div>
        <div ref="cmdHistoryListRef" class="etw-cmd-history-list">
          <div
            v-for="(cmd, idx) in filteredCmdHistory"
            :key="idx"
            class="etw-cmd-history-item"
            :class="{ 'etw-cmd-history-item--selected': idx === cmdHistorySelected }"
            @click="pickHistoryCommand(idx)"
            @mouseenter="cmdHistorySelected = idx"
          >
            <span class="etw-cmd-history-num">{{ cmd.index }}</span>
            <span class="etw-cmd-history-text">{{ cmd.text }}</span>
          </div>
          <div v-if="!filteredCmdHistory.length" class="etw-cmd-history-empty">
            {{ t('embeddedTerminal.noCommandHistory') }}
          </div>
        </div>
      </div>
    </div>

    <!-- pane-body 必须作为 monaco-workbench 的子节点，否则 integratedTerminalPanel.css 里大量选择器不生效（会话列会变成系统默认按钮白底） -->
    <div class="pane-body integrated-terminal etw-terminal-pane-fill">
    <!-- 补全弹窗（覆盖在终端区域内） -->
    <div v-if="showAutocomplete" class="etw-autocomplete-host" @mousedown.self="closeAutocomplete()">
      <div class="etw-autocomplete-panel" @mousedown.stop>
        <div class="etw-autocomplete-head">
          <span class="codicon codicon-symbol-keyword etw-autocomplete-icon" />
          <span class="etw-autocomplete-title">{{ t('embeddedTerminal.autocompleteTitle') || '命令补全' }}</span>
          <span class="etw-autocomplete-hint">{{ t('embeddedTerminal.autocompleteHint') || '↑↓ 选择，Enter 填入，Esc 关闭（Ctrl+Space 打开）' }}</span>
        </div>
        <div class="etw-autocomplete-divider" />
        <div ref="acListRef" class="etw-autocomplete-list">
          <button
            v-for="(opt, idx) in autocompleteOptions"
            :key="opt + '-' + idx"
            type="button"
            class="etw-autocomplete-item"
            :class="{ 'is-active': idx === autocompleteSelected }"
            @mouseenter="autocompleteSelected = idx"
            @click="applyAutocomplete(idx)"
          >
            {{ opt }}
          </button>
          <div v-if="!autocompleteOptions.length" class="etw-autocomplete-empty">
            {{ t('embeddedTerminal.autocompleteEmpty') || '没有可用补全项' }}
          </div>
        </div>
      </div>
    </div>
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
          <div class="etw-plus-chevron-anchor etw-vscode-menu-anchor">
            <button
              type="button"
              class="action-item codicon codicon-chevron-down"
              :title="t('common.more')"
              @click.stop="togglePlusMenu"
            />
            <div v-if="showPlusMenu" class="etw-vscode-menu etw-vscode-menu-wide" @click="showPlusMenu = false">
              <button type="button" class="etw-vscode-menu-item" @click.stop="openTerminalSettingsTabFromPlusMenu()">
                {{ t('embeddedTerminal.terminalSettingsMenu') }}
              </button>
              <button type="button" class="etw-vscode-menu-item" @click.stop="openQuickEditorFromPlusMenu()">
                {{ t('embeddedTerminal.editQuickCommands') }}
              </button>
            </div>
          </div>
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
              <div class="etw-vscode-menu-sep" />
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="scrollHistoryUp()">
                {{ t('embeddedTerminal.scrollPrev') }}
              </button>
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="scrollHistoryDown()">
                {{ t('embeddedTerminal.scrollNext') }}
              </button>
              <div class="etw-vscode-menu-sep" />
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="goToRecentDir()">
                {{ t('embeddedTerminal.goToRecentDir') }}
              </button>
              <button type="button" class="etw-vscode-menu-item" :disabled="!activeTabId" @click.stop="goToRecentCmd()">
                {{ t('embeddedTerminal.goToRecentCmd') }}
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
              :font-size="fontSize"
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
                @dblclick.prevent.stop="startRenameTab(tab.id)"
              >
                <span class="codicon" :class="embeddedTerminalTabCodicon(tab)" aria-hidden="true" />
                <span v-if="renamingTabId !== tab.id" class="terminal-tab-label">{{ tab.label }}</span>
                <input
                  v-else
                  v-model="renamingTabLabel"
                  class="etw-tab-rename-input"
                  @keydown.enter.prevent.stop="commitRenameTab()"
                  @keydown.esc.prevent.stop="cancelRenameTab()"
                  @blur="commitRenameTab()"
                />
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
      <div class="etw-modal etw-quick-editor-modal">
        <div class="etw-modal-title">{{ t('embeddedTerminal.editQuickCommands') }}</div>
        <p class="small text-muted mb-3">{{ t('embeddedTerminal.quickEditHint') || '添加命令名称和多行命令内容' }}</p>
        
        <!-- 添加新命令表单 -->
        <div class="etw-quick-add-form">
          <input v-model="quickCmdNewName" class="etw-quick-input-name" placeholder="命令名称（如：构建项目）" @keyup.enter="addQuickCmd" />
          <textarea v-model="quickCmdNewCmd" class="etw-quick-input-cmd" placeholder="命令内容（支持多行）" rows="3" @keyup.ctrl.enter="addQuickCmd" />
          <button type="button" class="btn btn-sm btn-primary" @click="addQuickCmd">{{ t('common.add') || '添加' }}</button>
        </div>
        
        <!-- 命令列表 -->
        <div class="etw-quick-list">
          <div v-if="!quickCmdList.length" class="etw-quick-empty">
            暂无快速命令，点击上方添加
          </div>
          <div v-for="(item, idx) in quickCmdList" :key="idx" class="etw-quick-item">
            <div class="etw-quick-item-header">
              <span class="etw-quick-item-name">{{ item.name }}</span>
              <button type="button" class="btn btn-sm btn-link text-danger" @click="removeQuickCmd(idx)">{{ t('common.delete') || '删除' }}</button>
            </div>
            <pre class="etw-quick-item-cmd">{{ item.command }}</pre>
          </div>
        </div>
        
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

const openTerminalSettingsWorkbenchTab = inject('openTerminalSettingsWorkbenchTab', null)

const rootWorkbenchStyle = computed(() => integratedTerminalWorkbenchDarkVars())
const tabsListMinW = TerminalTabsListSizes.WideViewMinimumWidth
const tabsListMaxW = TerminalTabsListSizes.MaximumWidth

const props = defineProps({
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null }
})

// 卡片上下文：有卡片时终端会话随卡片恢复；无卡片时退化为按项目作用域（仍在项目详情页内）
const terminalCardContext = inject('terminalCardContext', ref({ cardId: null, cardTitle: '', type: '' }))
// 保留注入点以兼容上层 provide，但本组件不再使用 plan 作为 fallback
inject('terminalPlanContext', null)

function toPositiveIntOrNull(v) {
  const raw = Array.isArray(v) ? v[0] : v
  if (raw == null || raw === '') return null
  const x = typeof raw === 'object' && raw !== null && 'value' in raw ? raw.value : raw
  const n = parseInt(String(x), 10)
  return Number.isFinite(n) && n > 0 ? n : null
}

/**
 * 终端会话持久化键：优先绑定卡片，其次绑定当前项目（否则列表视图无 cardId，根本不会创建 tab → WS 无 term_start 帧）
 */
const sessionScopeKey = computed(() => {
  const ctx = terminalCardContext?.value || terminalCardContext || {}
  const cid = toPositiveIntOrNull(ctx.cardId)
  if (cid) return `c:${cid}`
  const pid = toPositiveIntOrNull(props.projectId)
  if (pid) return `p:${pid}`
  return null
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
const openNewBugFromTerminal = inject('openNewBugFromTerminal', null)
const openNewTestcaseFromTerminal = inject('openNewTestcaseFromTerminal', null)

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
  // 当代理从不可用(null/false)变为可用(true)时重连
  if (ok !== true) return
  if (prevOk === true) return  // 已经是连接状态，不需要重连
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

// 终端实例注册表，供菜单操作使用
const termRegistry = {
  _map: new Map(),
  register(csid, term) {
    this._map.set(csid, term)
  },
  unregister(csid) {
    this._map.delete(csid)
  },
  get(csid) {
    return this._map.get(csid) || null
  },
  getActive() {
    const term = this.get(activeTabId.value)
    this._activeTerm = term
    return term
  }
}
provide('termRegistry', termRegistry)

// 终端补全：由子组件（EmbeddedPtyTerminal）发起打开请求，Workspace 负责渲染候选并把命令写回 xterm
const showAutocomplete = ref(false)
const autocompleteOptions = ref([])
const autocompleteSelected = ref(0)
const autocompleteForSessionId = ref('')
const acListRef = ref(null)

function closeAutocomplete() {
  showAutocomplete.value = false
  autocompleteOptions.value = []
  autocompleteSelected.value = 0
  autocompleteForSessionId.value = ''
}

function buildAutocompleteOptions(csid, prefix) {
  const pfx = String(prefix || '').trim()
  const out = []
  const seen = new Set()

  // 1) 本会话历史命令（优先）
  const hist = termCommandRegistry.getCommands(csid) || []
  for (const h of hist) {
    const s = String(h || '')
    if (!s.trim()) continue
    if (pfx && !s.toLowerCase().startsWith(pfx.toLowerCase())) continue
    if (seen.has(s)) continue
    seen.add(s)
    out.push(s)
    if (out.length >= 40) return out
  }

  // 2) 快速命令（作为补充：支持多行，写入时会自动 \r）
  for (const cmd of quickCommands.value || []) {
    const s = String(cmd || '').trim()
    if (!s) continue
    if (pfx && !s.toLowerCase().startsWith(pfx.toLowerCase())) continue
    if (seen.has(s)) continue
    seen.add(s)
    out.push(s)
    if (out.length >= 60) return out
  }

  return out
}

function openAutocomplete(payload) {
  const csid = String(payload?.client_session_id || '').trim() || activeTabId.value
  if (!csid) return
  const prefix = String(payload?.prefix || '')
  autocompleteForSessionId.value = csid
  autocompleteOptions.value = buildAutocompleteOptions(csid, prefix)
  autocompleteSelected.value = 0
  showAutocomplete.value = true
  nextTick(() => {
    try {
      acListRef.value?.scrollTo?.({ top: 0 })
    } catch (_) {
      /* ignore */
    }
  })
}

function applyAutocomplete(idx) {
  const csid = autocompleteForSessionId.value || activeTabId.value
  if (!csid) return
  const term = termRegistry.get(csid)
  const opt = autocompleteOptions.value[idx]
  if (!term || !opt) return
  // 写入命令（不回车，让用户可再编辑；回车可直接按 Enter）
  try {
    // 先尽量清掉当前行输入：用 \x15 (Ctrl+U) 在大多数 shell 中清行；不支持时也不会破坏
    term.write('\x15')
  } catch (_) {
    /* ignore */
  }
  term.write(String(opt))
  closeAutocomplete()
  focusEmbeddedTerminalArea()
}

function onAutocompleteKeydown(e) {
  if (!showAutocomplete.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    closeAutocomplete()
    focusEmbeddedTerminalArea()
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    e.stopPropagation()
    autocompleteSelected.value = Math.max(0, autocompleteSelected.value - 1)
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    e.stopPropagation()
    autocompleteSelected.value = Math.min(autocompleteOptions.value.length - 1, autocompleteSelected.value + 1)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    e.stopPropagation()
    applyAutocomplete(autocompleteSelected.value)
  }
}

provide('onRequestAutocomplete', openAutocomplete)

// 注入父组件的全局命令历史弹框方法（需在 termCommandRegistry 定义之后）
const openGlobalCmdHistory = inject('openGlobalCmdHistory', null)

// 终端命令历史注册表：追踪 cd 命令以实现"转到最近目录"
const termHistoryRegistry = {
  _map: new Map(),
  /** 记录一次 cd 切换：保存即将离开的当前目录（下次可切回） */
  pushDir(csid, prevDir) {
    if (!prevDir) return
    if (!this._map.has(csid)) this._map.set(csid, [])
    const hist = this._map.get(csid)
    // 去重，相同路径不重复入栈
    if (hist.length > 0 && hist[hist.length - 1] === prevDir) return
    this._map.get(csid).push(prevDir)
  },
  /** 弹出最近一次离开的目录 */
  popRecentDir(csid) {
    const hist = this._map.get(csid)
    if (!hist || hist.length === 0) return null
    return hist.pop()
  },
  unregister(csid) {
    this._map.delete(csid)
  }
}

// 终端滚动位置循环队列：102 槽位，索引 0-101，循环浏览
// 索引 0 是最旧命令，索引 101 是最新命令
const termScrollRegistry = {
  // csid -> { positions: number[102], head: number, count: number, currentIdx: number }
  _dataMap: new Map(),
  
  /** 注册当前命令位置（缓冲区行号），在用户按回车执行命令后调用 */
  pushCommandPos(csid, promptLine) {
    if (!this._dataMap.has(csid)) {
      this._dataMap.set(csid, {
        positions: new Array(102).fill(null),
        head: 0,       // 下一个写入位置
        count: 0,      // 当前存储数量
        currentIdx: -1 // 当前浏览位置，-1 表示未浏览过
      })
    }
    const data = this._dataMap.get(csid)
    
    // 去重：检查当前 head 位置的值
    if (data.count > 0 && data.positions[data.head] === promptLine) return
    
    // 写入当前位置
    data.positions[data.head] = promptLine
    data.head = (data.head + 1) % 102  // 循环移动
    if (data.count < 102) data.count++
    // 新命令入队后，重置 currentIdx 为最新位置（索引 101 或 count-1）
    data.currentIdx = Math.min(data.count - 1, 101)
  },
  
  /** 获取有效范围：返回 { minIdx, maxIdx } 表示逻辑索引范围 */
  _getValidRange(data) {
    if (data.count === 0) return { minIdx: -1, maxIdx: -1 }
    // 索引 0 是最旧，索引 count-1 是最新（最多到 101）
    return { minIdx: 0, maxIdx: data.count - 1 }
  },
  
  /** 向上滚动：往更旧的命令方向走（索引递减），循环
   * @param csid 会话ID
   * @param viewportY 当前视口顶部行号
   * @param visiblePrompts 当前屏幕可见的命令提示符行号数组
   */
  getPrevPos(csid, viewportY, visiblePrompts) {
    const data = this._dataMap.get(csid)
    if (!data || data.count === 0) return null
    
    const { minIdx, maxIdx } = this._getValidRange(data)
    
    // 确定当前参考索引
    let refIdx
    if (visiblePrompts && visiblePrompts.length > 0) {
      const topPrompt = Math.min(...visiblePrompts)
      refIdx = this._findIdxBeforePrompt(data, topPrompt)
    } else {
      refIdx = data.currentIdx >= 0 ? data.currentIdx : maxIdx
    }
    
    // 往上走一步（索引递减）
    let newIdx = refIdx - 1
    if (newIdx < minIdx) {
      // 循环回到最新
      newIdx = maxIdx
    }
    
    data.currentIdx = newIdx
    const line = data.positions[newIdx]
    console.log('[scrollUp] currentIdx:', newIdx, 'line:', line, 'count:', data.count)
    
    return { line, idx: newIdx }
  },
  
  /** 向下滚动：往更新的命令方向走（索引递增），循环
   * @param csid 会话ID
   * @param viewportY 当前视口顶部行号
   * @param visiblePrompts 当前屏幕可见的命令提示符行号数组
   */
  getNextPos(csid, viewportY, visiblePrompts) {
    const data = this._dataMap.get(csid)
    if (!data || data.count === 0) return null
    
    const { minIdx, maxIdx } = this._getValidRange(data)
    
    // 确定当前参考索引
    let refIdx
    if (visiblePrompts && visiblePrompts.length > 0) {
      const bottomPrompt = Math.max(...visiblePrompts)
      refIdx = this._findIdxAtOrAfterPrompt(data, bottomPrompt)
    } else {
      refIdx = data.currentIdx >= 0 ? data.currentIdx : maxIdx
    }
    
    // 往下走一步（索引递增）
    let newIdx = refIdx + 1
    if (newIdx > maxIdx) {
      // 循环回到最旧
      newIdx = minIdx
    }
    
    data.currentIdx = newIdx
    const line = data.positions[newIdx]
    console.log('[scrollDown] currentIdx:', newIdx, 'line:', line, 'count:', data.count)
    
    return { line, idx: newIdx }
  },
  
  /** 找到在给定 prompt 之前的最近命令索引（物理存储位置） */
  _findIdxBeforePrompt(data, promptY) {
    // 从最新往最旧找，找到第一个 < promptY 的位置
    const { minIdx, maxIdx } = this._getValidRange(data)
    for (let i = maxIdx; i >= minIdx; i--) {
      if (data.positions[i] < promptY) {
        return i
      }
    }
    return maxIdx  // 没找到，返回最新
  },
  
  /** 找到在给定 prompt 处或之后的最近命令索引 */
  _findIdxAtOrAfterPrompt(data, promptY) {
    const { minIdx, maxIdx } = this._getValidRange(data)
    for (let i = minIdx; i <= maxIdx; i++) {
      if (data.positions[i] >= promptY) {
        return i
      }
    }
    return minIdx  // 没找到，返回最旧
  },
  
  /** 获取最新命令位置 */
  getLatestPos(csid) {
    const data = this._dataMap.get(csid)
    if (!data || data.count === 0) return null
    return data.positions[data.count - 1]
  },
  
  /** 重置浏览索引到最新 */
  resetBrowseIdx(csid) {
    const data = this._dataMap.get(csid)
    if (data && data.count > 0) {
      data.currentIdx = data.count - 1
    }
  },
  
  /** 调试：获取当前位置数组 */
  getDebugInfo(csid) {
    const data = this._dataMap.get(csid)
    if (!data) return null
    return {
      positions: data.positions.slice(0, data.count),
      head: data.head,
      count: data.count,
      currentIdx: data.currentIdx
    }
  },
  
  unregister(csid) {
    this._dataMap.delete(csid)
  }
}
provide('termHistoryRegistry', termHistoryRegistry)

// 终端命令历史注册表：记录用户执行的命令，供"执行最近命令"使用
const STORAGE_KEY = 'etw_cmd_history'
const MAX_CMDS_PER_SESSION = 50
const MAX_TOTAL_SESSIONS = 20

// 从 localStorage 加载历史
function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const data = JSON.parse(raw)
      const map = new Map()
      for (const [k, v] of Object.entries(data)) {
        if (Array.isArray(v)) map.set(k, v)
      }
      return map
    }
  } catch (e) { /* ignore */ }
  return new Map()
}

function cmdHistDebugEnabled() {
  try {
    return String(localStorage.getItem('badcase_cmd_hist_debug') || '').trim() === '1'
  } catch (_) {
    return false
  }
}

function cmdHistLog(...args) {
  if (!cmdHistDebugEnabled()) return
  try {
    // eslint-disable-next-line no-console
    console.log('[cmd-hist]', ...args)
  } catch (_) {
    /* ignore */
  }
}

// 保存历史到 localStorage
function saveHistory(map) {
  try {
    const obj = Object.fromEntries(map)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(obj))
  } catch (e) { /* ignore */ }
}

const termCommandRegistry = {
  _map: loadHistory(),
  pushCommand(csid, cmd) {
    const sid = String(csid ?? '').trim()
    console.log('[termCommandRegistry.pushCommand]', sid, cmd)
    if (!sid) return
    if (!cmd || !cmd.trim()) return
    if (!this._map.has(sid)) this._map.set(sid, [])
    const hist = this._map.get(sid)
    // 去重：将相同命令移到最前面
    const idx = hist.indexOf(cmd.trim())
    if (idx !== -1) hist.splice(idx, 1)
    hist.unshift(cmd.trim())
    if (hist.length > MAX_CMDS_PER_SESSION) hist.length = MAX_CMDS_PER_SESSION
    // 限制总 session 数量
    if (this._map.size > MAX_TOTAL_SESSIONS) {
      const oldest = this._map.keys().next().value
      this._map.delete(oldest)
    }
    saveHistory(this._map)
    cmdHistLog('push', { sid, len: hist.length, cmd: String(cmd).slice(0, 200) })
  },
  getCommands(csid) {
    const sid = String(csid ?? '').trim()
    if (!sid) return []
    const out = this._map.get(sid) || []
    cmdHistLog('get', { sid, len: out.length })
    return out
  },
  unregister(csid) {
    const sid = String(csid ?? '').trim()
    if (!sid) return
    // 不在组件卸载时清空历史：否则“搜索命令/最近命令”会经常变成空。
    // 若需要清空，应由显式的“清空历史”操作来做。
    return
  }
}
provide('termCommandRegistry', termCommandRegistry)
console.log('[EmbeddedTerminalWorkspace] providing termCommandRegistry:', typeof termCommandRegistry === 'object')

// 暴露到全局，供 ProjectDetail 的全局命令历史弹框使用
globalThis.__termCommandRegistry__ = termCommandRegistry
globalThis.__termRegistry__ = termRegistry
globalThis.__termScrollRegistry__ = termScrollRegistry

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
const FONT_SIZE_KEY = 'embeddedTerminalFontSizePx'
const FONT_SIZE_SYNC_EVENT = 'badcase-embedded-terminal-font-size'
const fontSize = ref(14)
function loadFontSize() {
  try {
    const raw = localStorage.getItem(FONT_SIZE_KEY)
    if (raw != null) {
      const n = parseInt(String(raw), 10)
      if (Number.isFinite(n)) fontSize.value = Math.max(10, Math.min(26, n))
    }
  } catch (_) {
    /* ignore */
  }
}
function persistFontSize() {
  try {
    localStorage.setItem(FONT_SIZE_KEY, String(fontSize.value))
  } catch (_) {
    /* ignore */
  }
}
function increaseFontSize() {
  fontSize.value = Math.min(26, (fontSize.value || 14) + 1)
  persistFontSize()
  showMoreMenu.value = false
}
function decreaseFontSize() {
  fontSize.value = Math.max(10, (fontSize.value || 14) - 1)
  persistFontSize()
  showMoreMenu.value = false
}
function resetFontSize() {
  fontSize.value = 14
  persistFontSize()
  showMoreMenu.value = false
}

const tabs = ref([])
const activeTabId = ref(null)
// sessionScopeKey -> { tabs, activeTabId }
const _tabsByScope = new Map()

function saveTerminalStateForScope(key) {
  const k = key != null ? String(key).trim() : ''
  if (!k) return
  _tabsByScope.set(k, { tabs: tabs.value, activeTabId: activeTabId.value })
}

function restoreTerminalStateForScope(key) {
  const k = key != null ? String(key).trim() : ''
  if (!k) {
    tabs.value = []
    activeTabId.value = null
    return
  }
  const st = _tabsByScope.get(k)
  if (st && Array.isArray(st.tabs)) {
    tabs.value = st.tabs
    activeTabId.value = st.activeTabId
    return
  }
  tabs.value = []
  activeTabId.value = null
}
const ptySessionMeta = ref({})
const sessionRailResizeTick = ref(0)

const activeTabLabel = computed(() => {
  const id = activeTabId.value
  if (!id) return ''
  const tab = tabs.value.find((x) => x.id === id)
  return tab?.label ? String(tab.label) : ''
})

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
const terminalCfg = ref(null)
const showQuickEditor = ref(false)
const quickEditText = ref('')
const quickCmdVersion = ref(0)
const quickCmdLoading = ref(false)
const quickCmdData = ref([]) // 云端数据

// Key-Value 编辑相关
const quickCmdList = ref([]) // { name: string, command: string }[]
const quickCmdNewName = ref('')
const quickCmdNewCmd = ref('')

function openQuickEditor() {
  // 云端数据转内部格式
  quickCmdList.value = quickCmdData.value.map(x => ({ name: x.name || '', command: x.command || '' }))
  showQuickEditor.value = true
  loadQuickCommands()
}

function addQuickCmd() {
  const name = quickCmdNewName.value.trim()
  const cmd = quickCmdNewCmd.value.trim()
  if (!name || !cmd) return
  quickCmdList.value.unshift({ name, command: cmd })
  quickCmdNewName.value = ''
  quickCmdNewCmd.value = ''
}

function removeQuickCmd(idx) {
  quickCmdList.value.splice(idx, 1)
}

async function saveQuickCommands() {
  const parsed = quickCmdList.value.slice(0, 50).map(x => ({
    name: x.name.trim(),
    command: x.command.trim()
  }))

  try {
    await api.post('/api/terminal/quick-commands/sync', { commands: parsed, project_id: projectId.value || null })
    await loadQuickCommands()
    quickCmdVersion.value += 1
    showQuickEditor.value = false
  } catch (e) {
    console.error('保存快速命令失败:', e)
  }
}

async function loadQuickCommands() {
  if (quickCmdLoading.value) return
  quickCmdLoading.value = true
  try {
    const res = await api.get('/api/terminal/quick-commands', {
      params: { project_id: projectId.value || undefined },
    })
    if (res.data.success) {
      quickCmdData.value = res.data.items || []
    }
  } catch (_) {
    /* ignore */
  } finally {
    quickCmdLoading.value = false
  }
}

// 辅助函数：从缓冲区行找上一个命令提示符行
function findPrevPromptLine(buffer, fromY) {
  for (let y = fromY - 1; y >= 0; y--) {
    const line = buffer.getLine(y)
    if (!line) continue
    const text = line.translateToString()
    // 匹配各种命令提示符格式（Windows / PowerShell / 常见 *nix）
    if (isPromptLine(text)) {
      return y
    }
  }
  return null
}

// 辅助函数：从缓冲区行找下一个命令提示符行
function findNextPromptLine(buffer, fromY) {
  for (let y = fromY + 1; y < buffer.length; y++) {
    const line = buffer.getLine(y)
    if (!line) continue
    const text = line.translateToString()
    if (isPromptLine(text)) {
      return y
    }
  }
  return null
}

// 辅助函数：检测一行是否是命令提示符
function isPromptLine(text) {
  const s = String(text || '').trimStart()
  // PowerShell 常见：提示符 + 命令在同一行
  // 例：PS C:\Path> dir
  //     (venv) PS C:\Path> python -V
  if (/^(?:\([^)]*\)\s*)*PS\s+[A-Za-z]:[^\r\n>]*>\s*/.test(s)) return true
  // cmd 常见：C:\Path> dir
  if (/^[A-Za-z]:[^\r\n>]*>\s*/.test(s)) return true
  // *nix：极简提示符（仅 $/# 开头）或 [tag]... 这种前缀
  if (/^\$/.test(s) || /^#/.test(s) || /^\[[^\]]+\]/.test(s)) return true
  return false
}

// 辅助函数：扫描当前屏幕可见范围内的所有命令提示符行号
function scanVisiblePrompts(buffer, viewportY, visibleRows) {
  const prompts = []
  const endY = Math.min(viewportY + visibleRows - 1, buffer.length - 1)
  for (let y = viewportY; y <= endY; y++) {
    const line = buffer.getLine(y)
    if (!line) continue
    const text = line.translateToString()
    if (isPromptLine(text)) {
      prompts.push(y)
    }
  }
  return prompts
}

function scrollHistoryUp() {
  const term = termRegistry.getActive()
  if (!term) return
  const buffer = term.buffer.active
  const viewportY = term.buffer.active.viewportY
  const visibleRows = term.rows
  
  // 从当前视口的底部开始查找上一条命令
  // 这样可以确保找到的是当前视口之前的命令
  const viewportBottom = viewportY + visibleRows - 1
  const prevPromptY = findPrevPromptLine(buffer, viewportBottom)
  
  if (prevPromptY !== null && prevPromptY < viewportY) {
    // 计算需要滚动的行数
    const scrollLines = prevPromptY - viewportY
    if (scrollLines !== 0) term.scrollLines(scrollLines)
    return
  }
  
  // 如果在当前视口内找到了命令，尝试找更前面的
  if (prevPromptY !== null && prevPromptY >= viewportY) {
    const earlierPromptY = findPrevPromptLine(buffer, prevPromptY - 1)
    if (earlierPromptY !== null) {
      const scrollLines = earlierPromptY - viewportY
      if (scrollLines !== 0) term.scrollLines(scrollLines)
      return
    }
  }

  // 没有更早的提示符：直接到最顶（旧逻辑会从末尾找，反而把视口拉回去）
  term.scrollToTop()
}

function scrollHistoryDown() {
  const term = termRegistry.getActive()
  if (!term) return
  const buffer = term.buffer.active
  const viewportY = term.buffer.active.viewportY
  
  // 从当前视口往后找下一条命令
  const nextPromptY = findNextPromptLine(buffer, viewportY)
  if (nextPromptY !== null) {
    // 计算需要滚动的行数
    const scrollLines = nextPromptY - viewportY
    if (scrollLines !== 0) term.scrollLines(scrollLines)
    return
  }
  
  // 没有更多历史：回到最新命令
  term.scrollToBottom()
}

function goToRecentDir() {
  const term = termRegistry.getActive()
  if (!term) return
  const csid = activeTabId.value
  if (!csid) return

  // 优先从记录的 cd 历史中取上一个目录
  const prevDir = termHistoryRegistry.popRecentDir(csid)
  if (prevDir) {
    term.write('cd /d "' + prevDir + '"\r')
    return
  }

  // 没有历史：尝试从 scrollback 找上一条命令的路径（跳过当前行）
  const buffer = term.buffer.active
  for (let y = buffer.length - 2; y >= 0; y--) {
    const line = buffer.getLine(y)
    if (!line) continue
    const text = line.translateToString().trim()
    // 跳过包含 > 的行（那是命令提示符本身）
    if (text.includes('>') || text.includes('$')) continue
    const winMatch = text.match(/^([A-Za-z]:[\\\/][^\s:*?"<>|]+)/)
    if (winMatch) {
      term.write('cd /d "' + winMatch[1] + '"\r')
      return
    }
    const unixMatch = text.match(/^(\/[^\s]+)/)
    if (unixMatch) {
      term.write('cd ' + unixMatch[1] + '\r')
      return
    }
  }
}

const quickCommands = computed(() => {
  quickCmdVersion.value
  // 优先返回云端数据
  if (quickCmdData.value.length) {
    return quickCmdData.value.map((x) => x.command)
  }
  // 本地缓存 fallback
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
  if (!sessionScopeKey.value) return ''
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `t-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function selectTerminalTab(id) {
  if (!id) return
  if (!tabs.value.some((x) => x.id === id)) return
  activeTabId.value = id
}

function addTab() {
  if (!sessionScopeKey.value) return
  const id = newTabId()
  if (!id) return
  const mode = 'local'
  const ssh = {}
  const kind = 'local'
  const label = (t('embeddedTerminal.tabLocal') || 'Local').trim()
  tabs.value.push({ id, mode, ssh, label, kind })
  activeTabId.value = id
  persistTabLabels()
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
  persistTabLabels()
  return id
}

const TAB_LABELS_KEY = 'embeddedTerminalTabLabels'
const TAB_LABELS_USER_KEY = 'embeddedTerminalTabLabelsUserRenamed'
function loadTabLabels() {
  try {
    const raw = localStorage.getItem(TAB_LABELS_KEY)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? obj : {}
  } catch (_) {
    return {}
  }
}
function persistTabLabels() {
  try {
    const out = {}
    for (const t0 of tabs.value) {
      if (!t0?.id) continue
      if (t0.label && String(t0.label).trim()) out[String(t0.id)] = String(t0.label).trim()
    }
    localStorage.setItem(TAB_LABELS_KEY, JSON.stringify(out))
  } catch (_) {
    /* ignore */
  }
}

function loadUserRenamedSet() {
  try {
    const raw = localStorage.getItem(TAB_LABELS_USER_KEY)
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return new Set()
    return new Set(arr.map((x) => String(x)))
  } catch (_) {
    return new Set()
  }
}

function persistUserRenamedSet(set) {
  try {
    const arr = Array.from(set || [])
    localStorage.setItem(TAB_LABELS_USER_KEY, JSON.stringify(arr))
  } catch (_) {
    /* ignore */
  }
}

const userRenamedTabIds = ref(loadUserRenamedSet())

function markTabUserRenamed(id) {
  const sid = String(id || '').trim()
  if (!sid) return
  const next = new Set(userRenamedTabIds.value || [])
  next.add(sid)
  userRenamedTabIds.value = next
  persistUserRenamedSet(next)
}

function shortenLabelFromCommand(cmd, maxLen = 22) {
  const s = String(cmd || '').replace(/\s+/g, ' ').trim()
  if (!s) return ''
  if (s.length <= maxLen) return s
  return s.slice(0, Math.max(8, maxLen - 1)) + '…'
}

function autoUpdateTabLabelFromCommand(csid, cmd, source = 'user') {
  const sid = String(csid || '').trim()
  if (!sid) return
  const idx = tabs.value.findIndex((x) => x.id === sid)
  if (idx < 0) return
  const renamed = userRenamedTabIds.value && userRenamedTabIds.value.has && userRenamedTabIds.value.has(sid)
  if (renamed) return
  const base = shortenLabelFromCommand(cmd)
  if (!base) return
  console.log('[EmbeddedTerminalWorkspace] auto title:', sid, source, '=>', base)
  const nextLabel = source === 'ai' ? `AI: ${base}` : base
  const old = tabs.value[idx]
  tabs.value = [
    ...tabs.value.slice(0, idx),
    { ...old, label: nextLabel },
    ...tabs.value.slice(idx + 1)
  ]
  persistTabLabels()
}

const renamingTabId = ref(null)
const renamingTabLabel = ref('')
function startRenameTab(id) {
  const tab = tabs.value.find((x) => x.id === id)
  if (!tab) return
  renamingTabId.value = id
  renamingTabLabel.value = String(tab.label || '').trim()
  nextTick(() => {
    try {
      const root = etwRootRef.value
      const inp = root?.querySelector?.('.etw-tab-rename-input')
      inp?.focus?.()
      inp?.select?.()
    } catch (_) {
      /* ignore */
    }
  })
}
function commitRenameTab() {
  const id = renamingTabId.value
  if (!id) return
  const tab = tabs.value.find((x) => x.id === id)
  if (!tab) {
    renamingTabId.value = null
    return
  }
  const nextLabel = String(renamingTabLabel.value || '').trim()
  tab.label = nextLabel || tab.label
  renamingTabId.value = null
  if (nextLabel) markTabUserRenamed(id)
  persistTabLabels()
}
function cancelRenameTab() {
  renamingTabId.value = null
}

const showMoreMenu = ref(false)
const showPlusMenu = ref(false)

// 命令历史弹窗
const showCmdHistory = ref(false)
const cmdHistoryList = ref([])
const cmdHistorySelected = ref(0)
const cmdSearchText = ref('')
const cmdSearchInput = ref(null)
const cmdHistoryListRef = ref(null)
let cmdHistoryKeyHandler = null
let cmdHistoryCleanupTimer = null

// 带原始索引的命令列表（用于显示序号）
const indexedCmdHistory = computed(() =>
  cmdHistoryList.value.map((text, i) => ({ text, index: i + 1 }))
)

const filteredCmdHistory = computed(() => {
  const q = cmdSearchText.value.trim().toLowerCase()
  if (!q) return indexedCmdHistory.value
  return indexedCmdHistory.value.filter((c) => c.text.toLowerCase().includes(q))
})

function openCmdHistory() {
  const csid = activeTabId.value
  console.log('[openCmdHistory] csid:', csid, 'termCommandRegistry:', typeof termCommandRegistry, termCommandRegistry)
  if (!csid) return
  const cmds = termCommandRegistry.getCommands(csid)
  console.log('[openCmdHistory] commands:', cmds)
  cmdHistoryList.value = cmds
  cmdHistorySelected.value = 0
  cmdSearchText.value = ''
  showCmdHistory.value = true
  showMoreMenu.value = false

  // 自动聚焦搜索框
  nextTick(() => {
    cmdSearchInput.value?.focus()
  })

  // 键盘处理：↑/↓ 选择，Enter 执行，Escape 关闭
  cmdHistoryKeyHandler = (e) => {
    if (!showCmdHistory.value) {
      document.removeEventListener('keydown', cmdHistoryKeyHandler)
      cmdHistoryCleanupTimer = null
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      e.stopPropagation()
      const max = filteredCmdHistory.value.length - 1
      cmdHistorySelected.value = Math.max(0, cmdHistorySelected.value - 1)
      scrollSelectedIntoView()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      e.stopPropagation()
      cmdHistorySelected.value = Math.min(filteredCmdHistory.value.length - 1, cmdHistorySelected.value + 1)
      scrollSelectedIntoView()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      e.stopPropagation()
      pickHistoryCommand(cmdHistorySelected.value)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      showCmdHistory.value = false
    }
  }
  document.addEventListener('keydown', cmdHistoryKeyHandler, true)
}

function scrollSelectedIntoView() {
  nextTick(() => {
    const list = cmdHistoryListRef.value
    if (!list) return
    const selected = list.querySelector('.etw-cmd-history-item--selected')
    if (selected) selected.scrollIntoView({ block: 'nearest' })
  })
}

function onCmdSearchKeydown(e) {
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    cmdHistorySelected.value = Math.max(0, cmdHistorySelected.value - 1)
    scrollSelectedIntoView()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    cmdHistorySelected.value = Math.min(filteredCmdHistory.value.length - 1, cmdHistorySelected.value + 1)
    scrollSelectedIntoView()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    pickHistoryCommand(cmdHistorySelected.value)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showCmdHistory.value = false
  }
}

function pickHistoryCommand(idx) {
  const item = filteredCmdHistory.value[idx]
  if (!item) return
  showCmdHistory.value = false
  document.removeEventListener('keydown', cmdHistoryKeyHandler)
  const term = termRegistry.getActive()
  if (!term) return
  // 写入命令并回车执行
  term.write(item.text + '\r')
}

function goToRecentCmd() {
  const csid = activeTabId.value
  if (!csid) return
  // 优先使用 ProjectDetail 的全局弹框（覆盖界面顶部）
  if (openGlobalCmdHistory) {
    openGlobalCmdHistory(csid)
  } else {
    // fallback: 使用本地弹框
    openCmdHistory()
  }
}

function closeAllMenus() {
  showMoreMenu.value = false
  showPlusMenu.value = false
}

function toggleMoreMenu() {
  showMoreMenu.value = !showMoreMenu.value
}

function togglePlusMenu() {
  showPlusMenu.value = !showPlusMenu.value
  if (showPlusMenu.value) showMoreMenu.value = false
}

function openTerminalSettingsTabFromPlusMenu() {
  showPlusMenu.value = false
  openTerminalSettingsTab()
}

function openQuickEditorFromPlusMenu() {
  showPlusMenu.value = false
  openQuickEditor()
}

function openTerminalSettingsTab() {
  showMoreMenu.value = false
  try {
    openTerminalSettingsWorkbenchTab?.()
  } catch (_) {
    /* ignore */
  }
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
    persistTabLabels()
    return
  }
  if (wasActive) {
    activeTabId.value = tabs.value[tabs.value.length - 1].id
  }
  persistTabLabels()
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
  // 该命令由对话/AI 注入到终端：自动用它更新右侧会话标题（用户手动改过的不会覆盖）
  autoUpdateTabLabelFromCommand(targetId, raw, 'ai')
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

function createBugFromTerminal() {
  if (!openNewBugFromTerminal) return
  const raw = getActiveSelection().trim()
  if (!raw) return
  openNewBugFromTerminal(`【终端选中输出】\n${raw}`)
}

function createTestcaseFromTerminal() {
  if (!openNewTestcaseFromTerminal) return
  const raw = getActiveSelection().trim()
  if (!raw) return
  openNewTestcaseFromTerminal(`【终端选中输出】\n${raw}`)
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

function onExternalFontSizeSync() {
  loadFontSize()
}

onMounted(async () => {
  loadFontSize()
  if (typeof window !== 'undefined') {
    window.addEventListener(FONT_SIZE_SYNC_EVENT, onExternalFontSizeSync)
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
  loadQuickCommands()
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
  // tabs 初始化由 sessionScopeKey watch 控制：无作用域（无项目/卡片）不创建
  
  // 恢复自定义 session 标题
  try {
    const labels = loadTabLabels()
    if (labels && typeof labels === 'object' && tabs.value.length) {
      tabs.value = tabs.value.map((x) => {
        const v = labels[String(x.id)]
        return v ? { ...x, label: String(v) } : x
      })
    }
  } catch (_) {
    /* ignore */
  }

  // 恢复“手动重命名过”的标记集合
  try {
    userRenamedTabIds.value = loadUserRenamedSet()
  } catch (_) {
    /* ignore */
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
    const getActiveCwd = () => {
      try {
        const id = activeTabId.value ? String(activeTabId.value) : ''
        if (id && ptySessionMeta.value?.[id]?.cwd) {
          return String(ptySessionMeta.value[id].cwd).trim()
        }
        const metas = ptySessionMeta.value || {}
        for (const k of Object.keys(metas)) {
          const c = metas[k]?.cwd != null ? String(metas[k].cwd).trim() : ''
          if (c) return c
        }
        return ''
      } catch (_) {
        return ''
      }
    }
    terminalCtl.value = {
      injectCommand,
      focusTerminal: focusEmbeddedTerminalArea,
      getActiveCwd,
      /** 供 ReAct client_shell */
      getClientShell: () => {
        const isWin =
          typeof navigator !== 'undefined' &&
          (/Win/i.test(navigator.userAgent || '') || /Win/i.test(navigator.platform || ''))
        return {
          cwd: getActiveCwd() || '',
          platform: isWin ? 'windows' : 'posix',
          shell: isWin ? 'powershell' : 'bash'
        }
      }
    }
  }
  document.addEventListener('keydown', onAutocompleteKeydown, true)
})

watch(
  sessionScopeKey,
  (next, prev) => {
    if (prev && prev !== next) saveTerminalStateForScope(prev)
    restoreTerminalStateForScope(next)
    // 进入某一作用域时，确保至少有一个 terminal tab（才会向 /pty 发送 term_start）
    if (next && (!tabs.value.length || !activeTabId.value)) {
      addTab()
    }
    // 切换卡片时关闭悬浮菜单/弹框，避免串卡操作
    closeAllMenus()
    showCmdHistory.value = false
    closeAutocomplete()
  },
  { immediate: true }
)

// 子组件通知：用户在某个终端会话里按回车执行了命令
provide('onTermCommandExecuted', ({ client_session_id, command, source }) => {
  autoUpdateTabLabelFromCommand(client_session_id, command, source || 'user')
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
    window.removeEventListener(FONT_SIZE_SYNC_EVENT, onExternalFontSizeSync)
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
  document.removeEventListener('keydown', onAutocompleteKeydown, true)
})

defineExpose({
  openQuickEditor,
  createBadcaseFromTerminal,
  createBugFromTerminal,
  createTestcaseFromTerminal
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

.etw-vscode-menu-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.etw-plus-chevron-anchor :deep(.action-item.codicon-chevron-down) {
  padding-left: 2px;
  padding-right: 2px;
}

/* 下拉菜单定位：确保新加的“⌄”与“⋯”一致可见 */
.etw-vscode-menu {
  position: absolute;
  right: 0;
  z-index: 3000;
}

/* + 右侧的 ⌄：向上弹出 */
.etw-plus-chevron-anchor .etw-vscode-menu {
  top: auto;
  bottom: calc(100% + 6px);
}

/* ⋯ 更多：向下弹出 */
.etw-terminal-menu-anchor .etw-vscode-menu {
  bottom: auto;
  top: calc(100% + 6px);
}

.etw-tab-rename-input {
  width: 100%;
  min-width: 0;
  font-size: 12px;
  padding: 2px 6px;
  color: #d4d4d4;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 4px;
  outline: none;
}

.etw-autocomplete-host {
  position: absolute;
  inset: 60px 12px 12px 12px;
  z-index: 2050;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  pointer-events: auto;
}

.etw-autocomplete-panel {
  width: min(720px, calc(100% - 24px));
  max-height: min(420px, calc(100% - 24px));
  background: #252526;
  border: 1px solid #3e3e42;
  border-radius: 10px;
  box-shadow: 0 10px 34px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

.etw-autocomplete-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 10px 12px 8px;
  color: #d4d4d4;
}

.etw-autocomplete-icon {
  font-size: 14px;
  color: #4ec9b0;
}

.etw-autocomplete-title {
  font-weight: 600;
  font-size: 12px;
}

.etw-autocomplete-hint {
  font-size: 11px;
  color: #9aa0a6;
}

.etw-autocomplete-divider {
  height: 1px;
  background: #3e3e42;
}

.etw-autocomplete-list {
  padding: 8px;
  overflow: auto;
  max-height: 360px;
}

.etw-autocomplete-item {
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: #d4d4d4;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
}

.etw-autocomplete-item:hover,
.etw-autocomplete-item.is-active {
  background: #0e639c;
}

.etw-autocomplete-empty {
  padding: 16px 10px;
  color: #9aa0a6;
  font-size: 12px;
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

.etw-quick-editor-modal {
  width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.etw-modal-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #eee;
}

.etw-quick-add-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #252525;
  border-radius: 6px;
  border: 1px solid #3c3c3c;
}

.etw-quick-input-name {
  padding: 8px 10px;
  background: #1e1e1e;
  border: 1px solid #3c3c3c;
  border-radius: 4px;
  color: #ccc;
  font-size: 13px;
}

.etw-quick-input-name:focus {
  outline: none;
  border-color: #0e639c;
}

.etw-quick-input-cmd {
  padding: 8px 10px;
  background: #1e1e1e;
  border: 1px solid #3c3c3c;
  border-radius: 4px;
  color: #ccc;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
  resize: vertical;
}

.etw-quick-input-cmd:focus {
  outline: none;
  border-color: #0e639c;
}

.etw-quick-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
  margin-bottom: 12px;
}

.etw-quick-empty {
  text-align: center;
  color: #666;
  padding: 30px;
  font-size: 13px;
}

.etw-quick-item {
  background: #252525;
  border: 1px solid #3c3c3c;
  border-radius: 6px;
  margin-bottom: 8px;
  overflow: hidden;
}

.etw-quick-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #1e1e1e;
  border-bottom: 1px solid #3c3c3c;
}

.etw-quick-item-name {
  font-weight: 600;
  color: #e0a030;
  font-size: 13px;
}

.etw-quick-item-cmd {
  margin: 0;
  padding: 10px 12px;
  color: #ccc;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  background: transparent;
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
