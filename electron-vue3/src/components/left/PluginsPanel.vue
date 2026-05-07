<template>
  <div class="plugins-panel">
    <!-- Header：对齐 Cursor / VS Code 扩展视图 -->
    <div class="plugins-header">
      <div class="plugins-search-row">
        <span class="plugins-search-icon codicon codicon-search" aria-hidden="true" />
        <input
          v-model="query"
          class="plugins-search-input"
          type="search"
          :placeholder="tt('plugins.searchPlaceholder', 'Search extensions…')"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <div class="plugins-header-hint">
        {{ tt('plugins.marketHint', "Click to import local VS Code extensions (don't show again)") }}
      </div>
    </div>

    <div class="plugins-body">
      <!-- 左侧：Installed 列表 -->
      <div class="plugins-list-pane">
        <div class="plugins-section-title">{{ tt('plugins.installed', 'Installed') }}</div>
        <div class="plugins-list" role="listbox" :aria-label="tt('plugins.installed', 'Installed')">
          <button
            v-for="p in filteredPlugins"
            :key="p.id"
            type="button"
            class="plugins-list-row monaco-list-row"
            :class="{ 'is-active': selectedPluginId === p.id }"
            @click="selectPlugin(p.id)"
          >
            <span class="plugins-row-icon" aria-hidden="true">{{ p.icon || '🧩' }}</span>
            <span class="plugins-row-main">
              <span class="plugins-row-title">{{ p.title || p.id }}</span>
              <span class="plugins-row-sub">
                {{ (p.author || '').trim() ? p.author : tt('plugins.authorUnknown', 'Unknown') }}
              </span>
            </span>
            <span v-if="!isPluginEnabled(p.id)" class="plugins-row-badge">
              {{ tt('plugins.disabled', 'Disabled') }}
            </span>
          </button>
          <div v-if="!filteredPlugins.length" class="plugins-empty">
            {{ tt('plugins.empty', 'No extensions found.') }}
          </div>
        </div>
      </div>

      <!-- 右侧：详情 + 操作 +（可选）插件面板 -->
      <div class="plugins-detail-pane">
        <div v-if="activePlugin" class="plugins-detail">
          <div class="plugins-detail-head">
            <div class="plugins-detail-title-row">
              <div class="plugins-detail-icon" aria-hidden="true">{{ activePlugin.icon || '🧩' }}</div>
              <div class="plugins-detail-titles">
                <div class="plugins-detail-title">{{ activePlugin.title || activePlugin.id }}</div>
                <div class="plugins-detail-meta">
                  <span class="plugins-detail-author">{{ (activePlugin.author || '').trim() ? activePlugin.author : (t('plugins.authorUnknown') || 'Unknown') }}</span>
                  <span class="plugins-detail-dot">•</span>
                  <span class="plugins-detail-version">{{ activePlugin.version || '0.0.0' }}</span>
                </div>
              </div>
            </div>

            <div class="plugins-detail-actions">
              <button type="button" class="plugins-btn" @click="toggleEnabled(activePlugin.id)">
                {{ isPluginEnabled(activePlugin.id) ? tt('plugins.disable', 'Disable') : tt('plugins.enable', 'Enable') }}
              </button>
              <button
                type="button"
                class="plugins-btn plugins-btn-primary"
                :disabled="!isPluginEnabled(activePlugin.id)"
                @click="openPluginPanel(activePlugin)"
              >
                {{ tt('plugins.open', 'Open') }}
              </button>
            </div>
          </div>

          <div class="plugins-detail-desc">
            {{ activePlugin.description || tt('plugins.noDescription', 'No description.') }}
          </div>

          <div v-if="panelPlugin" class="plugins-panel-host">
            <div class="plugins-panel-host-head">
              <div class="plugins-panel-host-title">{{ panelPlugin.title || panelPlugin.id }}</div>
              <button type="button" class="plugins-btn plugins-btn-ghost" @click="closePluginPanel">
                {{ t('common.close') || 'Close' }}
              </button>
            </div>
            <div class="plugins-panel-host-body">
              <component
                v-if="panelPlugin && panelPlugin.component"
                :is="panelPlugin.component"
                :projectId="projectId"
                :selectedPlan="selectedPlan"
                :currentUser="currentUser"
                @action="emit('action', $event)"
              />
            </div>
          </div>
        </div>

        <div v-else class="plugins-detail-empty">
          {{ tt('plugins.pickOne', 'Select an extension to view details.') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { pluginCards } from '../../plugins/registry.js'

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  selectedPlan: { type: [String, Number, null], default: null },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['action'])

const { t } = useI18n()
function tt(key, fallback) {
  const v = t(key)
  return v === key ? fallback : v
}

const query = ref('')
const selectedPluginId = ref('')
const panelPlugin = ref(null)

const STORAGE_ENABLED = 'pluginsEnabledMapV1'

function loadEnabledMap() {
  try {
    const raw = localStorage.getItem(STORAGE_ENABLED)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? obj : {}
  } catch (_) {
    return {}
  }
}

function saveEnabledMap(map) {
  try {
    localStorage.setItem(STORAGE_ENABLED, JSON.stringify(map || {}))
  } catch (_) {
    /* ignore */
  }
}

const enabledMap = ref(loadEnabledMap())

const sortedPlugins = computed(() => {
  const list = Array.isArray(pluginCards) ? pluginCards.slice() : []
  const ctx = { projectId: props.projectId, currentUser: props.currentUser }
  return list
    .filter((p) => (typeof p.visible === 'function' ? !!p.visible(ctx) : true))
    .sort((a, b) => (Number(a.order ?? 0) - Number(b.order ?? 0)))
})

const filteredPlugins = computed(() => {
  const q = String(query.value || '').trim().toLowerCase()
  if (!q) return sortedPlugins.value
  return sortedPlugins.value.filter((p) => {
    const hay = `${p.title || ''} ${p.id || ''} ${p.description || ''} ${p.author || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const activePlugin = computed(() => {
  const id = String(selectedPluginId.value || '').trim()
  if (!id) return null
  return filteredPlugins.value.find((p) => p.id === id) || sortedPlugins.value.find((p) => p.id === id) || null
})

function ensureSelection() {
  if (selectedPluginId.value && sortedPlugins.value.some((p) => p.id === selectedPluginId.value)) return
  selectedPluginId.value = sortedPlugins.value[0]?.id || ''
}

watch(sortedPlugins, () => ensureSelection(), { immediate: true })

function selectPlugin(id) {
  selectedPluginId.value = String(id || '')
  panelPlugin.value = null
}

function isPluginEnabled(id) {
  const k = String(id || '')
  if (!k) return true
  // 默认启用：没有记录时为 true
  return enabledMap.value?.[k] !== false
}

function toggleEnabled(id) {
  const k = String(id || '')
  if (!k) return
  const next = !isPluginEnabled(k)
  enabledMap.value = { ...(enabledMap.value || {}), [k]: next }
  saveEnabledMap(enabledMap.value)
  if (!next && panelPlugin.value?.id === k) {
    panelPlugin.value = null
  }
}

function openPluginPanel(p) {
  if (!p || !p.id) return
  if (!isPluginEnabled(p.id)) return
  panelPlugin.value = p
}

function closePluginPanel() {
  panelPlugin.value = null
}
</script>

<style scoped>
.plugins-panel {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  color: #444;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.plugins-header {
  padding: 10px 12px 8px;
  border-bottom: 1px solid #e9ecef;
  background: #fff;
}

.plugins-search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  background: #fff;
}

.plugins-search-icon {
  color: #6c757d;
}

.plugins-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: #444;
  font-size: 12px;
}

.plugins-header-hint {
  margin-top: 6px;
  font-size: 11px;
  color: #777;
}

.plugins-body {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.plugins-list-pane {
  width: 320px;
  min-width: 260px;
  max-width: 420px;
  border-right: 1px solid #e9ecef;
  background: #fff;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.plugins-section-title {
  padding: 10px 12px 8px;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: #777;
}

.plugins-list {
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
  padding: 6px;
}

.plugins-list-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.plugins-list-row:hover {
  background: #f8f9fa;
}

.plugins-list-row.is-active {
  background: #e3f2fd;
  outline: 1px solid rgba(25, 118, 210, 0.35);
}

.plugins-row-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex: 0 0 auto;
}

.plugins-row-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.plugins-row-title {
  font-size: 12px;
  font-weight: 600;
  color: #222;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plugins-row-sub {
  margin-top: 2px;
  font-size: 11px;
  color: #777;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plugins-row-badge {
  font-size: 10px;
  color: #a36a00;
  border: 1px solid rgba(163, 106, 0, 0.28);
  padding: 2px 6px;
  border-radius: 999px;
  flex: 0 0 auto;
}

.plugins-empty {
  padding: 10px 12px;
  color: #777;
  font-size: 12px;
}

.plugins-detail-pane {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  background: #fff;
  overflow: auto;
}

.plugins-detail {
  padding: 14px 16px 18px;
}

.plugins-detail-empty {
  padding: 18px 16px;
  color: #777;
  font-size: 12px;
}

.plugins-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.plugins-detail-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.plugins-detail-icon {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  flex: 0 0 auto;
}

.plugins-detail-titles {
  min-width: 0;
}

.plugins-detail-title {
  font-size: 16px;
  font-weight: 700;
  color: #222;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plugins-detail-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #777;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plugins-detail-dot {
  opacity: 0.6;
}

.plugins-detail-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.plugins-btn {
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
  color: #444;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.plugins-btn:hover {
  background: #f8f9fa;
}

.plugins-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.plugins-btn-primary {
  background: #1976d2;
  border-color: #1976d2;
  color: #fff;
}

.plugins-btn-primary:hover {
  background: #1565c0;
}

.plugins-btn-ghost {
  background: transparent;
}

.plugins-detail-desc {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e9ecef;
  font-size: 12px;
  color: #555;
  line-height: 1.55;
}

.plugins-panel-host {
  margin-top: 14px;
  border: 1px solid #e9ecef;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}

.plugins-panel-host-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  background: #fff;
  border-bottom: 1px solid #e9ecef;
}

.plugins-panel-host-title {
  font-size: 12px;
  font-weight: 600;
  color: #222;
}

.plugins-panel-host-body {
  padding: 12px;
}
</style>

