<template>
  <div class="asp-root">
    <aside class="asp-sidebar">
      <div class="asp-profile">
        <div class="asp-avatar">{{ userInitials }}</div>
        <div class="asp-profile-meta">
          <div class="asp-email">{{ user?.email || t('shell.emailFallback') }}</div>
          <div class="asp-plan">{{ planLine }}</div>
        </div>
      </div>
      <div class="asp-search-wrap">
        <span class="asp-search-icon" aria-hidden="true">⌕</span>
        <input
          v-model="navQuery"
          type="search"
          class="asp-search"
          :placeholder="t('appSettings.searchPlaceholder')"
          autocomplete="off"
        />
      </div>
      <nav class="asp-nav" aria-label="settings">
        <template v-for="(group, gi) in navGroups" :key="gi">
          <div v-if="gi > 0" class="asp-nav-divider" />
          <button
            v-for="item in filterItems(group)"
            :key="item.id"
            type="button"
            class="asp-nav-item"
            :class="{ active: activePane === item.id }"
            @click="activePane = item.id"
          >
            <span class="asp-nav-icon" aria-hidden="true">{{ item.icon }}</span>
            <span class="asp-nav-text">{{ t(item.labelKey) }}</span>
          </button>
        </template>
      </nav>
    </aside>
    <main class="asp-main">
      <h1 class="asp-pane-title">{{ t(paneTitleKey) }}</h1>
      <div v-show="activePane === 'account'" class="asp-pane asp-pane-account">
        <div class="asp-account-card">
          <UserProfile embedded tone="light" :user="user" @close="$emit('close')" />
        </div>
      </div>
      <div v-show="activePane === 'team'" class="asp-pane asp-pane-team">
        <div class="asp-team-surface">
          <TeamManagement v-if="projectId != null" :project-id="projectId" hide-top-heading />
          <p v-else class="asp-muted">{{ t('appSettings.teamNeedProject') }}</p>
        </div>
      </div>
      <div v-show="activePane === 'preferences'" class="asp-pane">
        <div class="asp-card">
          <div class="asp-card-h">{{ t('prefs.title') }}</div>
          <p class="asp-card-desc">{{ t('appSettings.prefsDesc') }}</p>
          <label class="asp-field-label">{{ t('prefs.language') }}</label>
          <select v-model="localeDraft" class="asp-select">
            <option value="zh-CN">{{ t('prefs.zh') }}</option>
            <option value="en">{{ t('prefs.en') }}</option>
          </select>
          <div class="asp-card-actions">
            <button type="button" class="asp-btn asp-btn-primary" @click="savePrefs">{{ t('prefs.save') }}</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import { persistLocale } from '../i18n/index.js'
import UserProfile from './UserProfile.vue'
import TeamManagement from './TeamManagement.vue'

const props = defineProps({
  user: { type: Object, default: null },
  projectId: { type: [String, Number], default: null },
  initialPane: { type: String, default: 'account' },
  visible: { type: Boolean, default: false }
})

defineEmits(['close'])

const { t, locale } = useI18n()

const activePane = ref('account')
const navQuery = ref('')
const credits = ref(null)
const creditsLoading = ref(false)
const localeDraft = ref('zh-CN')

const navGroups = [
  [{ id: 'account', labelKey: 'appSettings.navAccount', icon: '◉' }],
  [{ id: 'team', labelKey: 'appSettings.navTeam', icon: '👥' }],
  [{ id: 'preferences', labelKey: 'appSettings.navPreferences', icon: '⚙' }]
]

const userInitials = computed(() => {
  const u = props.user
  if (!u) return 'U'
  const name = String(u.name || '').trim()
  const local = String(u.email || '').split('@')[0] || ''
  let s = 'U'
  if (name.length >= 2) s = name.slice(0, 2)
  else if (name.length === 1) s = (name + (local[0] || '')).slice(0, 2)
  else if (local.length >= 2) s = local.slice(0, 2)
  return s.toUpperCase()
})

const planLine = computed(() => {
  if (creditsLoading.value) return t('appSettings.planLoading')
  const n = credits.value
  if (n == null) return t('appSettings.planUnknown')
  if (n > 0) return t('appSettings.planActive', { n })
  return t('appSettings.planNone')
})

const paneTitleKey = computed(() => {
  if (activePane.value === 'account') return 'appSettings.paneAccount'
  if (activePane.value === 'team') return 'appSettings.paneTeam'
  return 'appSettings.panePreferences'
})

function filterItems(items) {
  const q = navQuery.value.trim().toLowerCase()
  if (!q) return items
  return items.filter((it) => t(it.labelKey).toLowerCase().includes(q))
}

async function fetchCreditsSummary() {
  creditsLoading.value = true
  credits.value = null
  try {
    const res = await api.get('/api/payment/credits')
    credits.value = typeof res.data?.credits === 'number' ? res.data.credits : 0
  } catch {
    credits.value = null
  } finally {
    creditsLoading.value = false
  }
}

function savePrefs() {
  persistLocale(localeDraft.value)
}

function syncFromProps() {
  activePane.value = ['account', 'team', 'preferences'].includes(props.initialPane) ? props.initialPane : 'account'
  localeDraft.value = locale.value
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      syncFromProps()
      fetchCreditsSummary()
    } else {
      navQuery.value = ''
    }
  },
  { immediate: true }
)

watch(
  () => props.initialPane,
  (p) => {
    if (props.visible && ['account', 'team', 'preferences'].includes(p)) {
      activePane.value = p
    }
  }
)
</script>

<style scoped>
.asp-root {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: #fff;
  border-top: 1px solid #e9ecef;
}

.asp-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #f4f6f8;
  border-right: 1px solid #dee2e6;
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
  gap: 12px;
  overflow: auto;
}

.asp-profile {
  display: flex;
  gap: 10px;
  align-items: center;
}

.asp-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e8ecf0;
  color: #495057;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid #dee2e6;
}

.asp-profile-meta {
  min-width: 0;
}

.asp-email {
  font-size: 12px;
  color: #212529;
  word-break: break-all;
  line-height: 1.35;
}

.asp-plan {
  margin-top: 2px;
  font-size: 11px;
  color: #6c757d;
  line-height: 1.3;
}

.asp-search-wrap {
  position: relative;
}

.asp-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  color: #868e96;
  pointer-events: none;
}

.asp-search {
  width: 100%;
  box-sizing: border-box;
  height: 32px;
  padding: 0 10px 0 30px;
  border-radius: 6px;
  border: 1px solid #ced4da;
  background: #fff;
  color: #212529;
  font-size: 12px;
  outline: none;
}

.asp-search:focus {
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.12);
}

.asp-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.asp-nav-divider {
  height: 1px;
  background: #dee2e6;
  margin: 8px 0;
}

.asp-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #495057;
  font-size: 13px;
  cursor: pointer;
}

.asp-nav-item:hover {
  background: rgba(0, 123, 255, 0.08);
}

.asp-nav-item.active {
  background: #fff;
  color: #007bff;
  font-weight: 600;
  box-shadow: inset 0 0 0 1px #dee2e6;
}

.asp-nav-icon {
  width: 18px;
  text-align: center;
  opacity: 0.9;
  font-size: 14px;
}

.asp-main {
  flex: 1;
  min-width: 0;
  padding: 20px 28px 28px;
  overflow: auto;
  background: #fff;
}

.asp-pane-title {
  margin: 0 0 18px;
  font-size: 20px;
  font-weight: 600;
  color: #212529;
  letter-spacing: -0.02em;
}

.asp-pane {
  max-width: 720px;
}

.asp-pane-account :deep(.profile-embedded) {
  max-width: 100%;
}

.asp-account-card {
  background: #fff;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.asp-team-surface {
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  padding: 12px;
  max-height: min(620px, 70vh);
  overflow: auto;
}

.asp-pane-team :deep(.team-management) {
  background: transparent;
  padding: 0;
}

.asp-muted {
  color: #6c757d;
  font-size: 13px;
}

.asp-card {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 18px 20px;
}

.asp-card-h {
  font-size: 14px;
  font-weight: 600;
  color: #212529;
  margin-bottom: 6px;
}

.asp-card-desc {
  margin: 0 0 14px;
  font-size: 12px;
  color: #6c757d;
  line-height: 1.45;
}

.asp-field-label {
  display: block;
  font-size: 12px;
  color: #495057;
  margin-bottom: 6px;
}

.asp-select {
  width: 100%;
  max-width: 320px;
  height: 34px;
  border-radius: 6px;
  border: 1px solid #ced4da;
  background: #fff;
  color: #212529;
  padding: 0 10px;
  font-size: 13px;
}

.asp-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.asp-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
}

.asp-btn-primary {
  background: #007bff;
  border-color: #007bff;
  color: #fff;
}

.asp-btn-primary:hover {
  background: #0069d9;
  border-color: #0062cc;
}
</style>
