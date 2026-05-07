<template>
  <div v-show="visible" class="tsw-root">
    <div class="tsw-shell">
      <aside class="tsw-sidebar">
        <div class="tsw-search-wrap">
          <span class="tsw-search-icon" aria-hidden="true">⌕</span>
          <input
            v-model="query"
            type="search"
            class="tsw-search"
            :placeholder="t('embeddedTerminal.terminalSettingsSearch')"
            autocomplete="off"
          />
        </div>

        <div class="tsw-nav-title">{{ t('embeddedTerminal.terminalSettingsNavTitle') }}</div>
        <button
          type="button"
          class="tsw-nav-item"
          :class="{ active: activeSection === 'terminal' }"
          @click="activeSection = 'terminal'"
        >
          <span class="tsw-nav-icon" aria-hidden="true">⌘</span>
          <span class="tsw-nav-text">{{ t('embeddedTerminal.terminalSettingsNavTerminal') }}</span>
        </button>
      </aside>

      <main class="tsw-main">
        <h1 class="tsw-title">{{ t('embeddedTerminal.terminalSettingsTitle') }}</h1>

        <div class="tsw-setting" v-show="matches('terminalSettingsFontSize terminalSettingsFontHint fontSize')">
          <div class="tsw-setting-head">
            <div class="tsw-setting-title2">{{ t('embeddedTerminal.terminalSettingsFontSize') }}</div>
            <div class="tsw-setting-desc2">{{ t('embeddedTerminal.terminalSettingsFontHint') }}</div>
          </div>
          <div class="tsw-setting-body">
            <select v-model.number="fontSizeDraft" class="tsw-select">
              <option v-for="n in fontSizeOptions" :key="n" :value="n">{{ n }}px</option>
            </select>
            <button type="button" class="tsw-btn" @click="decrease">{{ t('embeddedTerminal.fontSizeDecrease') }}</button>
            <button type="button" class="tsw-btn" @click="increase">{{ t('embeddedTerminal.fontSizeIncrease') }}</button>
            <button type="button" class="tsw-btn tsw-btn-primary" @click="reset">{{ t('embeddedTerminal.fontSizeReset') }}</button>
          </div>
          <div class="tsw-setting-foot">{{ t('embeddedTerminal.terminalSettingsLayoutHint') }}</div>
        </div>

        <div class="tsw-setting" v-show="matches('terminalSettingsQuickCmdsTitle terminalSettingsQuickCmdsDesc quick commands')">
          <div class="tsw-setting-head">
            <div class="tsw-setting-title2">{{ t('embeddedTerminal.terminalSettingsQuickCmdsTitle') }}</div>
            <div class="tsw-setting-desc2">{{ t('embeddedTerminal.terminalSettingsQuickCmdsDesc') }}</div>
          </div>
          <div class="tsw-setting-body">
            <button type="button" class="tsw-btn tsw-btn-primary" @click="onOpenQuick">
              {{ t('embeddedTerminal.terminalSettingsOpenQuickCmds') }}
            </button>
          </div>
        </div>

        <div class="tsw-setting" v-show="matches('terminalSettingsSelectionActions terminalSettingsSelectionHint selection')">
          <div class="tsw-setting-head">
            <div class="tsw-setting-title2">{{ t('embeddedTerminal.terminalSettingsSelectionActions') }}</div>
            <div class="tsw-setting-desc2">{{ t('embeddedTerminal.terminalSettingsSelectionHint') }}</div>
          </div>
          <div class="tsw-setting-body tsw-setting-body--wrap">
            <button type="button" class="tsw-btn" @click="createBadcase">{{ t('embeddedTerminal.createBadcaseFromSelection') }}</button>
            <button type="button" class="tsw-btn" @click="createBug">{{ t('embeddedTerminal.createBugFromSelection') }}</button>
            <button type="button" class="tsw-btn" @click="createTestcase">{{ t('embeddedTerminal.createTestcaseFromSelection') }}</button>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  visible: { type: Boolean, default: true }
})

const { t } = useI18n()
const FONT_SIZE_KEY = 'embeddedTerminalFontSizePx'
/** 与 EmbeddedTerminalWorkspace 同步字号（同页 localStorage 无 storage 事件） */
const FONT_SIZE_SYNC_EVENT = 'badcase-embedded-terminal-font-size'
const fontSize = ref(14)
const fontSizeDraft = ref(14)
const fontSizeOptions = computed(() => Array.from({ length: 17 }, (_, i) => i + 10)) // 10..26
const openTerminalQuickEditor = inject('openTerminalQuickEditor', null)
const terminalCreateBadcaseFromSelection = inject('terminalCreateBadcaseFromSelection', null)
const terminalCreateBugFromSelection = inject('terminalCreateBugFromSelection', null)
const terminalCreateTestcaseFromSelection = inject('terminalCreateTestcaseFromSelection', null)

const query = ref('')
const activeSection = ref('terminal')

function notifyFontSizeChanged() {
  if (typeof window === 'undefined') return
  try {
    window.dispatchEvent(new CustomEvent(FONT_SIZE_SYNC_EVENT))
  } catch (_) {
    /* ignore */
  }
}

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
  fontSizeDraft.value = fontSize.value
}

function persistFontSize() {
  try {
    localStorage.setItem(FONT_SIZE_KEY, String(fontSize.value))
  } catch (_) {
    /* ignore */
  }
  notifyFontSizeChanged()
}

function decrease() {
  fontSize.value = Math.max(10, (fontSize.value || 14) - 1)
  fontSizeDraft.value = fontSize.value
  persistFontSize()
}

function increase() {
  fontSize.value = Math.min(26, (fontSize.value || 14) + 1)
  fontSizeDraft.value = fontSize.value
  persistFontSize()
}

function reset() {
  fontSize.value = 14
  fontSizeDraft.value = fontSize.value
  persistFontSize()
}

function onOpenQuick() {
  try {
    openTerminalQuickEditor?.()
  } catch (_) {
    /* ignore */
  }
}

function createBadcase() {
  try {
    terminalCreateBadcaseFromSelection?.()
  } catch (_) {
    /* ignore */
  }
}
function createBug() {
  try {
    terminalCreateBugFromSelection?.()
  } catch (_) {
    /* ignore */
  }
}
function createTestcase() {
  try {
    terminalCreateTestcaseFromSelection?.()
  } catch (_) {
    /* ignore */
  }
}

onMounted(() => loadFontSize())

watch(fontSizeDraft, (n) => {
  const v = Number(n)
  if (!Number.isFinite(v)) return
  const clamped = Math.max(10, Math.min(26, v))
  if (clamped === fontSize.value) return
  fontSize.value = clamped
  persistFontSize()
})

function matches(haystack) {
  const q = query.value.trim().toLowerCase()
  if (!q) return true
  const s = String(haystack || '').toLowerCase()
  return s.includes(q)
}
</script>

<style scoped>
.tsw-root {
  flex: 1;
  height: 100%;
  min-height: 0;
  overflow: auto;
  background: #1e1e1e;
  color: #cccccc;
  border-top: 1px solid #2a2a2a;
}

.tsw-shell {
  display: flex;
  min-height: 0;
  height: 100%;
}

.tsw-title {
  font-size: 16px;
  font-weight: 650;
  margin: 0 0 14px;
  color: #e6e6e6;
}

.tsw-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #252526;
  border-right: 1px solid #2f2f2f;
  padding: 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.tsw-main {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  padding: 14px 18px 22px;
  overflow: auto;
}

.tsw-search-wrap {
  position: relative;
}

.tsw-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: #9aa0a6;
  font-size: 12px;
  pointer-events: none;
}

.tsw-search {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 28px;
  border-radius: 6px;
  border: 1px solid #3e3e42;
  background: #1f1f1f;
  color: #d4d4d4;
  outline: none;
  font-size: 12px;
}

.tsw-search:focus {
  border-color: #007fd4;
  box-shadow: 0 0 0 1px rgba(0, 127, 212, 0.35);
}

.tsw-nav-title {
  margin-top: 2px;
  font-size: 12px;
  color: #9aa0a6;
}

.tsw-nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: #d4d4d4;
  cursor: pointer;
  text-align: left;
}

.tsw-nav-item:hover {
  background: rgba(90, 93, 94, 0.31);
}

.tsw-nav-item.active {
  background: #37373d;
  border-color: #3e3e42;
}

.tsw-nav-icon {
  width: 16px;
  color: #c8c8c8;
  flex-shrink: 0;
}

.tsw-nav-text {
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tsw-setting {
  background: #252526;
  border: 1px solid #3e3e42;
  border-radius: 10px;
  padding: 12px 12px 10px;
  margin-bottom: 10px;
}

.tsw-setting-head {
  margin-bottom: 10px;
}

.tsw-setting-title2 {
  font-size: 13px;
  font-weight: 650;
  color: #e6e6e6;
  margin: 0 0 6px;
}

.tsw-setting-desc2 {
  font-size: 12px;
  line-height: 1.55;
  color: #9aa0a6;
}

.tsw-setting-body {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.tsw-setting-body--wrap {
  flex-wrap: wrap;
  align-items: flex-start;
}

.tsw-setting-foot {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.55;
  color: #9aa0a6;
}

.tsw-select {
  height: 30px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid #3e3e42;
  background: #1f1f1f;
  color: #d4d4d4;
  outline: none;
  font-size: 12px;
}

.tsw-btn {
  height: 30px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid #3e3e42;
  background: transparent;
  color: #d4d4d4;
  cursor: pointer;
  font-size: 12px;
}

.tsw-btn:hover {
  background: rgba(90, 93, 94, 0.31);
}

.tsw-btn-primary {
  background: #0e639c;
  border-color: #0e639c;
}

.tsw-btn-primary:hover {
  background: #1177bb;
  border-color: #1177bb;
}
</style>
