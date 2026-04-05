<template>
  <div class="etw-root">
    <div class="etw-topbar">
      <div class="etw-topbar-left">
        <button
          type="button"
          class="etw-top-tab"
          :class="{ active: mainTab === 'term' }"
          @click="mainTab = 'term'"
        >
          {{ t('embeddedTerminal.tab') }}
        </button>
        <button
          type="button"
          class="etw-top-tab"
          :class="{ active: mainTab === 'output' }"
          @click="mainTab = 'output'"
        >
          {{ t('embeddedTerminal.outputTab') }}
        </button>
        <span v-if="terminalCfg?.ai_whitelist_enabled" class="etw-top-pill">
          {{ t('embeddedTerminal.whitelistOn') }}
        </span>
      </div>
      <div class="etw-topbar-right">
        <div class="etw-menu-wrap">
          <button type="button" class="etw-icon-btn" :title="t('embeddedTerminal.newTab')" @click="toggleNewMenu">+</button>
          <div v-if="showNewMenu" class="etw-menu" @click="showNewMenu = false">
            <button type="button" class="etw-menu-item" @click.stop="addTab()">{{ t('embeddedTerminal.newTab') }}</button>
          </div>
        </div>

        <div class="etw-menu-wrap">
          <button type="button" class="etw-icon-btn" :title="t('common.more')" @click="toggleMoreMenu">…</button>
          <div v-if="showMoreMenu" class="etw-menu etw-menu-wide" @click="showMoreMenu = false">
            <button type="button" class="etw-menu-item" :disabled="!activeTabId" @click.stop="clearActive()">
              {{ t('embeddedTerminal.clearScreen') }}
            </button>
            <button type="button" class="etw-menu-item" :disabled="!activeTabId" @click.stop="closeActiveTab()">
              {{ t('embeddedTerminal.closeTab') }}
            </button>
            <div class="etw-menu-sep" />
            <button type="button" class="etw-menu-item" @click.stop="openQuickEditor()">
              {{ t('embeddedTerminal.editQuickCommands') }}
            </button>
            <button type="button" class="etw-menu-item" :disabled="auditExporting" @click.stop="exportAuditCsv()">
              {{ t('embeddedTerminal.exportAudit') }}
            </button>
            <button
              v-if="openAiComposerPrefill"
              type="button"
              class="etw-menu-item"
              @click.stop="onOpenChatForCommands"
            >
              {{ t('embeddedTerminal.openChatForCommands') }}
            </button>
            <button
              v-if="openNewBadcaseFromTerminal"
              type="button"
              class="etw-menu-item"
              :disabled="!hasTerminalSelection"
              @click.stop="createBadcaseFromTerminal"
            >
              {{ t('embeddedTerminal.createBadcaseFromTerminal') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-show="mainTab === 'term'" class="etw-term-stack">
      <div class="etw-split">
        <div class="etw-term-wrap">
          <EmbeddedPtyTerminal
            v-for="t in tabs"
            v-show="activeTabId === t.id"
            :key="t.id"
            :client-session-id="t.id"
            :mode="t.mode"
            :ssh-config="t.ssh"
            :working-directory="workingDirectory"
            :project-id="projectId"
          />
        </div>
        <aside class="etw-session-rail" aria-label="terminal-sessions">
          <div class="etw-rail-title">{{ t('embeddedTerminal.sessions') }}</div>
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            class="etw-rail-item"
            :class="{ active: activeTabId === tab.id, [`kind-${tab.kind}`]: true }"
            :title="tab.label"
            @click="activeTabId = tab.id"
          >
            <span class="etw-rail-icon" aria-hidden="true">{{ sessionIcon(tab) }}</span>
            <span class="etw-rail-label">{{ tab.label }}</span>
          </button>
          <p v-if="agentTabActive" class="etw-rail-hint">{{ t('embeddedTerminal.agentReadonlyHint') }}</p>
        </aside>
      </div>
    </div>

    <div v-show="mainTab === 'output'" class="etw-output-panel">
      <div class="etw-output-toolbar">
        <span class="small text-muted">{{ t('embeddedTerminal.outputHint') }}</span>
        <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearActiveOutputLog">
          {{ t('embeddedTerminal.clearOutput') }}
        </button>
      </div>
      <pre class="etw-output-pre">{{ activeOutputLog }}</pre>
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
import { ref, reactive, onMounted, onBeforeUnmount, provide, computed, inject, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { io } from 'socket.io-client'
import { api, BACKEND_BASE_URL } from '../api.js'
import EmbeddedPtyTerminal from './EmbeddedPtyTerminal.vue'

const props = defineProps({
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null }
})

const { t } = useI18n()

const terminalCtl = inject('terminalCtl', null)
const openAiComposerPrefill = inject('openAiComposerPrefill', null)
const openNewBadcaseFromTerminal = inject('openNewBadcaseFromTerminal', null)

const socketRef = ref(null)
const terminalPasteRef = ref({ token: 0, csid: '', text: '' })
provide('ptySocket', socketRef)
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

const tabs = ref([])
const activeTabId = ref(null)

const auditExporting = ref(false)
const mainTab = ref('term')
const terminalCfg = ref(null)
const showQuickEditor = ref(false)
const quickEditText = ref('')
const quickCmdVersion = ref(0)

const outputLogs = reactive({})
const activeOutputLog = computed(() => {
  const id = activeTabId.value
  if (!id) return ''
  return outputLogs[id] || ''
})

const agentTabActive = computed(() => {
  const id = activeTabId.value
  const tab = tabs.value.find((x) => x.id === id)
  return tab && tab.kind === 'agent'
})

function sessionIcon(tab) {
  if (tab.kind === 'agent') return '∞'
  return '>'
}

function appendOutputLog(csid, text) {
  if (!csid || text == null) return
  const chunk = String(text)
  const cur = outputLogs[csid] || ''
  const next = cur + chunk
  const max = 256 * 1024
  outputLogs[csid] = next.length > max ? next.slice(-max) : next
}

function b64ToUtf8(b64) {
  try {
    const bin = atob(b64)
    const u8 = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i += 1) u8[i] = bin.charCodeAt(i)
    return new TextDecoder('utf-8', { fatal: false }).decode(u8)
  } catch (_) {
    return ''
  }
}

function clearActiveOutputLog() {
  const id = activeTabId.value
  if (id) delete outputLogs[id]
}

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

const showNewMenu = ref(false)
const showMoreMenu = ref(false)

function closeAllMenus() {
  showNewMenu.value = false
  showMoreMenu.value = false
}

function toggleNewMenu() {
  showMoreMenu.value = false
  showNewMenu.value = !showNewMenu.value
}

function toggleMoreMenu() {
  showNewMenu.value = false
  showMoreMenu.value = !showMoreMenu.value
}

function onDocPointerDown(e) {
  const el = e?.target
  if (!el) return
  if (el.closest && el.closest('.etw-menu-wrap')) return
  closeAllMenus()
}

function closeActiveTab() {
  const id = activeTabId.value
  if (!id) return
  tabs.value = tabs.value.filter((x) => x.id !== id)
  if (tabs.value.length) {
    activeTabId.value = tabs.value[tabs.value.length - 1].id
  } else {
    activeTabId.value = null
  }
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

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('pointerdown', onDocPointerDown, { capture: true })
  }
  loadTerminalConfig()
  console.log('[EmbeddedTerminalWorkspace] Creating Socket.IO connection...')
  const s = io(BACKEND_BASE_URL || undefined, {
    path: '/socket.io/',
    transports: ['polling'],  // 只用 polling，避免 Vite 代理 WebSocket 升级失败
    withCredentials: true,
    timeout: 60000,
    reconnection: true,
    reconnectionAttempts: 20,
    reconnectionDelay: 800
  })
  socketRef.value = s
  s.on('connect', () => {
    console.log('[EmbeddedTerminalWorkspace] Socket connected, sid:', s.id)
  })
  s.on('connect_error', (err) => {
    console.error('[EmbeddedTerminalWorkspace] Socket connect_error:', err)
  })
  s.on('disconnect', (reason) => {
    console.log('[EmbeddedTerminalWorkspace] Socket disconnected:', reason)
  })
  s.on('term_output', (payload) => {
    if (!payload || !payload.b64 || !payload.client_session_id) return
    appendOutputLog(payload.client_session_id, b64ToUtf8(payload.b64))
  })
  if (!tabs.value.length) {
    addTab()
  }

  if (terminalCtl) {
    terminalCtl.value = {
      injectCommand,
      focusTerminal: () => {
        mainTab.value = 'term'
      }
    }
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointerdown', onDocPointerDown, { capture: true })
  }
  if (socketRef.value) {
    socketRef.value.off('term_output')
    socketRef.value.close()
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
  height: 100%;
  min-height: 280px;
  background: #1e1e1e;
  color: #cccccc;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.etw-topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border-bottom: 1px solid #2d2d2d;
  background: #252526;
}

.etw-topbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.etw-topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.etw-top-tab {
  border: none;
  background: transparent;
  color: #bbb;
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.etw-top-tab:hover {
  background: rgba(255, 255, 255, 0.06);
}

.etw-top-tab.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}

.etw-top-pill {
  font-size: 10px;
  color: #ffe082;
  border: 1px solid rgba(255, 193, 7, 0.35);
  background: rgba(255, 193, 7, 0.08);
  padding: 2px 6px;
  border-radius: 999px;
  white-space: nowrap;
}

.etw-menu-wrap {
  position: relative;
}

.etw-icon-btn {
  border: none;
  background: transparent;
  color: #cfcfcf;
  width: 26px;
  height: 22px;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
}

.etw-icon-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}

.etw-menu {
  position: absolute;
  top: 26px;
  right: 0;
  min-width: 180px;
  background: #1f1f1f;
  border: 1px solid #2d2d2d;
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  z-index: 20;
}

.etw-menu-wide {
  min-width: 240px;
}

.etw-menu-item {
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  color: #ddd;
  font-size: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}

.etw-menu-item:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.06);
}

.etw-menu-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.etw-menu-sep {
  height: 1px;
  margin: 6px 6px;
  background: #2d2d2d;
}

.etw-term-stack {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.etw-label {
  font-size: 12px;
  opacity: 0.85;
}

.etw-split {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
}

.etw-term-wrap {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 200px;
  position: relative;
  background: #0c0c0c;
}

.etw-session-rail {
  flex: 0 0 132px;
  width: 132px;
  border-left: 1px solid #2d2d2d;
  background: #252526;
  display: flex;
  flex-direction: column;
  padding: 6px 4px;
  gap: 4px;
  overflow-y: auto;
}

.etw-rail-title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #888;
  padding: 4px 6px;
}

.etw-rail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 4px;
  background: #2d2d2d;
  color: #ccc;
  font-size: 11px;
  padding: 6px 8px;
  cursor: pointer;
}

.etw-rail-item:hover {
  background: #383838;
}

.etw-rail-item.active {
  border-color: #007fd4;
  background: #094771;
  color: #fff;
}

.etw-rail-icon {
  flex: 0 0 auto;
  opacity: 0.9;
  font-size: 12px;
}

.etw-rail-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.etw-rail-hint {
  font-size: 10px;
  color: #888;
  padding: 6px;
  line-height: 1.35;
  margin: 0;
}

.etw-output-panel {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
}

.etw-output-toolbar {
  flex: 0 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-bottom: 1px solid #2d2d2d;
}

.etw-output-pre {
  flex: 1 1 auto;
  min-height: 0;
  margin: 0;
  padding: 8px;
  overflow: auto;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #ccc;
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
