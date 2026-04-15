<template>
  <div class="project-detail-wrapper">
    <!-- 顶部导航栏：与 ProjectDetail 保持一致 -->
    <div class="top-bar">
      <div class="top-left">
        <div class="logo" style="cursor: pointer;" @click="$emit('goToDashboard')">
          <span class="logo-text">BadCase Doctor</span>
          <span class="star-icon">⭐</span>
        </div>
        <div class="breadcrumb">
          <span class="breadcrumb-item">{{ projectName }}</span>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-item">{{ breadcrumb || t('project.breadcrumbIteration') }}</span>
          <span class="dropdown-arrow">▼</span>
        </div>
        <span class="edit-permission">{{ t('project.editPermission') }}</span>
      </div>

      <div class="top-right">
        <div class="layout-buttons">
          <button
            class="layout-btn"
            :class="{ active: !leftSidebarHidden }"
            :title="t('shell.toggleSidebar')"
            @click="$emit('setLayout', 'left')"
          >
            <div class="layout-icon left-aligned"></div>
          </button>
          <button
            class="layout-btn"
            :class="{ active: showTerminal }"
            :title="t('shell.toggleTerminal')"
            @click="$emit('setLayout', 'bottom')"
          >
            <div class="layout-icon bottom-aligned"></div>
          </button>
          <button
            class="layout-btn"
            :class="{ active: showAIAssistant }"
            :title="t('shell.toggleAI')"
            @click="$emit('setLayout', 'right')"
          >
            <div class="layout-icon right-aligned"></div>
          </button>
        </div>

        <div class="user-dropdown" @click="$emit('toggleUserDropdown')">
          <div class="user-avatar" :title="currentUser?.name || t('shell.userFallback')">
            <span class="user-avatar-initials">{{ userInitials }}</span>
          </div>

          <div v-if="showUserDropdown" class="user-menu" @click.stop>
            <div class="user-info">
              <div class="user-info-row">
                <div class="user-avatar user-avatar-sm">
                  <span class="user-avatar-initials">{{ userInitials }}</span>
                </div>
                <div class="user-info-text">
                  <div class="user-name">{{ currentUser?.name || t('shell.userFallback') }}</div>
                  <div class="user-email">{{ currentUser?.email || t('shell.emailFallback') }}</div>
                </div>
              </div>
              <button type="button" class="user-settings-entry" @click.stop="$emit('openSettings', 'account')">
                {{ t('shell.settings') }}
              </button>
            </div>
            <div class="menu-divider"></div>
            <div class="menu-item" @click="$emit('showNotifications')">
              <span class="menu-icon">🔔</span>
              <span class="menu-text">{{ t('shell.notifications') }}</span>
            </div>
            <div class="menu-item" @click="$emit('showHelp')">
              <span class="menu-icon">❓</span>
              <span class="menu-text">{{ t('shell.help') }}</span>
            </div>
            <div class="menu-item" @click="$emit('showProjectManagement')">
              <span class="menu-icon">📋</span>
              <span class="menu-text">{{ t('shell.projectManagement') }}</span>
            </div>
            <div class="menu-divider"></div>
            <div class="menu-item logout-item" @click="$emit('logout')">
              <span class="menu-icon">🚪</span>
              <span class="menu-text">{{ t('shell.logout') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 壳下方内容由外部挂载 -->
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  projectName: { type: String, default: '' },
  breadcrumb: { type: String, default: '' },
  currentUser: { type: Object, default: null },
  leftSidebarHidden: { type: Boolean, default: false },
  showTerminal: { type: Boolean, default: false },
  showAIAssistant: { type: Boolean, default: false },
  showUserDropdown: { type: Boolean, default: false }
})

const userInitials = computed(() => {
  const u = props.currentUser
  if (!u) return 'U'
  const name = String(u.name || '').trim()
  const local = String(u.email || '').split('@')[0] || ''
  let s = 'U'
  if (name.length >= 2) s = name.slice(0, 2)
  else if (name.length === 1) s = (name + (local[0] || '')).slice(0, 2)
  else if (local.length >= 2) s = local.slice(0, 2)
  return s.toUpperCase()
})

defineEmits([
  'goToDashboard',
  'setLayout',
  'toggleUserDropdown',
  'showNotifications',
  'showHelp',
  'openSettings',
  'logout',
  'showProjectManagement'
])
</script>

<style scoped>
.project-detail-wrapper {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8f9fa;
}

/* 叠在右侧 fixed 对话层之上，避免全高侧栏挡住顶栏点击；对话层仍从视口顶铺满（类似 Cursor 覆盖） */
.top-bar {
  position: relative;
  z-index: 2100;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e9ecef;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.top-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.logo:hover {
  opacity: 0.8;
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.star-icon {
  font-size: 12px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #333;
}

.breadcrumb-separator {
  color: #999;
}

.dropdown-arrow {
  font-size: 10px;
  color: #999;
  margin-left: 4px;
}

.edit-permission {
  font-size: 12px;
  color: #666;
  padding: 4px 8px;
  background: #f8f9fa;
  border-radius: 4px;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 布局按钮组样式（与 ProjectDetail 一致） */
.layout-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 16px;
}

.layout-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  position: relative;
}

.layout-btn:hover {
  background: transparent;
  transform: translateY(-1px);
}

.layout-btn.active {
  background: transparent;
  box-shadow: 0 0 0 1px #e2e8f0;
}

.layout-icon {
  width: 16px;
  height: 16px;
  background: #a0aec0;
  border-radius: 2px;
  position: relative;
}

.layout-icon.left-aligned::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 8px;
  height: 16px;
  background: #000000;
  border-radius: 1px;
}

.layout-icon.bottom-aligned::before {
  content: '';
  position: absolute;
  left: 0;
  bottom: 0;
  width: 16px;
  height: 8px;
  background: #000000;
  border-radius: 1px;
}

.layout-icon.right-aligned::before {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  width: 8px;
  height: 16px;
  background: #000000;
  border-radius: 1px;
}

/* 用户下拉菜单样式（与 ProjectDetail 一致） */
.user-dropdown {
  position: relative;
  cursor: pointer;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e8eaed;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #444;
  transition: all 0.2s ease;
  border: 2px solid transparent;
}

.user-avatar-initials {
  line-height: 1;
  letter-spacing: -0.02em;
}

.user-avatar-sm {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  font-size: 13px;
}

.user-avatar:hover {
  background: #dde1e6;
  border-color: #007bff;
}

.user-menu {
  position: absolute;
  top: 100%;
  right: 0;
  width: 240px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid #e0e0e0;
  z-index: 1000;
  margin-top: 8px;
  overflow: hidden;
}

.user-info {
  padding: 14px 16px 12px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.user-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info-text {
  min-width: 0;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.user-email {
  font-size: 12px;
  color: #666;
  word-break: break-all;
}

.user-settings-entry {
  width: 100%;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #dee2e6;
  background: #fff;
  color: #333;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.user-settings-entry:hover {
  background: #f1f3f5;
  border-color: #ced4da;
}

.menu-divider {
  height: 1px;
  background: #e0e0e0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.15s ease;
  border-bottom: 1px solid #f0f0f0;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-item:hover {
  background: #f8f9fa;
}

.menu-icon {
  font-size: 16px;
  opacity: 0.8;
}

.menu-text {
  font-size: 14px;
  color: #333;
  font-weight: 400;
}

.logout-item {
  color: #dc3545;
}

.logout-item:hover {
  background: #fff5f5;
}

.logout-item .menu-icon {
  color: #dc3545;
}

.logout-item .menu-text {
  color: #dc3545;
  font-weight: 500;
}
</style>

