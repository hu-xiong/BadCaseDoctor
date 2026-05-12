<template>
  <div class="narrow-nav-bar">
    <!-- 文件夹图标：返回迭代计划 -->
    <div class="nav-item" :title="t('narrowNav.returnToPlans')" @click="handleReturnToPlans">
      <span class="nav-icon">📁</span>
    </div>

    <!-- 搜索按钮：打开全局搜索 -->
    <div class="nav-item" :title="t('narrowNav.search')" @click="handleOpenSearch">
      <span class="nav-icon">🔍</span>
    </div>

    <!-- 分隔线 -->
    <div class="nav-divider"></div>

    <!-- 归档按钮 -->
    <div class="nav-item" :title="t('narrowNav.archive')" @click="handleOpenArchive">
      <span class="nav-icon">📦</span>
    </div>

    <!-- 分隔线 + 插件入口（暂时隐藏，需要时把 SHOW_PLUGINS_NAV 设为 true） -->
    <template v-if="SHOW_PLUGINS_NAV">
      <div class="nav-divider"></div>
      <div class="nav-item" :title="t('narrowNav.pluginPlaceholder')" @click="handleOpenPlugins">
        <span class="nav-icon">🧩</span>
      </div>
    </template>

    <!-- 底部：设置按钮 -->
    <div class="nav-item nav-item-bottom" :title="t('narrowNav.settings')" @click="handleOpenSettings">
      <span class="nav-icon">⚙️</span>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

/** 侧栏插件入口：关闭则隐藏 🧩（恢复时改为 true） */
const SHOW_PLUGINS_NAV = false

console.log('[NarrowNavBar] 组件已加载')

const emit = defineEmits([
  'return-to-plans',
  'open-search',
  'open-settings',
  'open-archive',
  'open-plugins'
])

const handleReturnToPlans = () => {
  emit('return-to-plans')
}

const handleOpenSearch = () => {
  emit('open-search')
}

const handleOpenSettings = () => {
  emit('open-settings')
}

const handleOpenArchive = () => {
  emit('open-archive')
}

const handleOpenPlugins = () => {
  emit('open-plugins')
}
</script>

<style scoped>
.narrow-nav-bar {
  width: 48px;
  min-width: 48px;
  height: 100%;
  background: #f8f9fa;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  gap: 4px;
  flex-shrink: 0;
}

.nav-item {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.nav-item:hover {
  background: #e9ecef;
}

.nav-item:active {
  background: #dee2e6;
}


.nav-icon {
  font-size: 18px;
}

.nav-divider {
  width: 24px;
  height: 1px;
  background: #dee2e6;
  margin: 8px 0;
}

.nav-item-bottom {
  margin-top: auto;
}
</style>
