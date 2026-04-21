<template>
  <div class="plugin-management">
    <div class="plugin-header">
      <h3>{{ t('pluginManagement.title') }}</h3>
      <button class="close-btn" @click="$emit('close')">×</button>
    </div>
    
    <div class="plugin-content">
      <!-- 内置插件 -->
      <div class="plugin-section">
        <h4>{{ t('pluginManagement.builtInPlugins') }}</h4>
        <div class="plugin-list">
          <div class="plugin-item" v-for="plugin in builtInPlugins" :key="plugin.id">
            <div class="plugin-icon">{{ plugin.icon }}</div>
            <div class="plugin-info">
              <div class="plugin-name">{{ plugin.name }}</div>
              <div class="plugin-version">v{{ plugin.version }}</div>
              <div class="plugin-desc">{{ plugin.description }}</div>
            </div>
            <div class="plugin-status">
              <span class="status-badge built-in">{{ t('pluginManagement.builtIn') }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 已安装插件 -->
      <div class="plugin-section">
        <h4>{{ t('pluginManagement.installedPlugins') }}</h4>
        <div class="plugin-list" v-if="installedPlugins.length > 0">
          <div class="plugin-item" v-for="plugin in installedPlugins" :key="plugin.id">
            <div class="plugin-icon">{{ plugin.icon || '🧩' }}</div>
            <div class="plugin-info">
              <div class="plugin-name">{{ plugin.name }}</div>
              <div class="plugin-version">v{{ plugin.version }}</div>
              <div class="plugin-desc">{{ plugin.description }}</div>
            </div>
            <div class="plugin-actions">
              <label class="switch">
                <input type="checkbox" v-model="plugin.enabled" @change="togglePlugin(plugin)">
                <span class="slider"></span>
              </label>
              <button class="btn-uninstall" @click="uninstallPlugin(plugin)">
                {{ t('pluginManagement.uninstall') }}
              </button>
            </div>
          </div>
        </div>
        <div class="empty-state" v-else>
          {{ t('pluginManagement.noInstalledPlugins') }}
        </div>
      </div>
      
      <!-- 插件市场 -->
      <div class="plugin-section">
        <h4>{{ t('pluginManagement.marketplace') }}</h4>
        <div class="plugin-marketplace">
          <div class="marketplace-hint">
            {{ t('pluginManagement.marketplaceHint') }}
          </div>
          <div class="coming-soon">
            {{ t('pluginManagement.comingSoon') }}
          </div>
        </div>
      </div>
      
      <!-- 插件开发文档 -->
      <div class="plugin-section">
        <h4>{{ t('pluginManagement.developer') }}</h4>
        <div class="developer-docs">
          <div class="doc-item">
            <span class="doc-icon">📖</span>
            <span>{{ t('pluginManagement.pluginGuide') }}</span>
          </div>
          <div class="doc-item">
            <span class="doc-icon">🔌</span>
            <span>{{ t('pluginManagement.apiReference') }}</span>
          </div>
          <div class="doc-item">
            <span class="doc-icon">📝</span>
            <span>{{ t('pluginManagement.examples') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAllPlugins, enablePlugin, disablePlugin } from '../plugins/PluginSystem.js'

const { t } = useI18n()

defineEmits(['close'])

// 示例内置插件
const builtInPlugins = ref([
  {
    id: 'card-types',
    name: '卡片类型管理',
    version: '1.0.0',
    description: '支持Bug、BadCase、测试用例三种卡片类型',
    icon: '📋',
    enabled: true,
    isBuiltIn: true
  },
  {
    id: 'global-search',
    name: '全局搜索',
    version: '1.0.0',
    description: '支持跨类型搜索所有卡片内容',
    icon: '🔍',
    enabled: true,
    isBuiltIn: true
  },
  {
    id: 'plan-management',
    name: '迭代计划管理',
    version: '1.0.0',
    description: '支持创建和管理迭代计划',
    icon: '📅',
    enabled: true,
    isBuiltIn: true
  }
])

// 已安装插件列表
const installedPlugins = ref([])

const togglePlugin = (plugin) => {
  if (plugin.enabled) {
    enablePlugin(plugin.id)
  } else {
    disablePlugin(plugin.id)
  }
}

const uninstallPlugin = (plugin) => {
  if (confirm(t('pluginManagement.confirmUninstall'))) {
    const index = installedPlugins.value.findIndex(p => p.id === plugin.id)
    if (index > -1) {
      installedPlugins.value.splice(index, 1)
    }
  }
}
</script>

<style scoped>
.plugin-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fafafa;
}

.plugin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
}

.plugin-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #666;
}

.plugin-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.plugin-section {
  margin-bottom: 24px;
}

.plugin-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #666;
  font-weight: 500;
}

.plugin-list {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.plugin-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.plugin-item:last-child {
  border-bottom: none;
}

.plugin-icon {
  font-size: 28px;
  width: 40px;
  text-align: center;
}

.plugin-info {
  flex: 1;
}

.plugin-name {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.plugin-version {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

.plugin-desc {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.plugin-status {
  display: flex;
  align-items: center;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.status-badge.built-in {
  background: #e3f2fd;
  color: #1976d2;
}

.plugin-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 开关样式 */
.switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.3s;
  border-radius: 22px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: #4caf50;
}

input:checked + .slider:before {
  transform: translateX(18px);
}

.btn-uninstall {
  padding: 6px 12px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  color: #666;
  transition: all 0.2s;
}

.btn-uninstall:hover {
  background: #ffebee;
  border-color: #ef5350;
  color: #c62828;
}

.empty-state {
  padding: 32px;
  text-align: center;
  color: #999;
  background: white;
  border-radius: 8px;
}

.plugin-marketplace {
  background: white;
  border-radius: 8px;
  padding: 24px;
  text-align: center;
}

.marketplace-hint {
  font-size: 13px;
  color: #666;
  margin-bottom: 16px;
}

.coming-soon {
  padding: 16px;
  background: #f5f5f5;
  border-radius: 6px;
  color: #999;
  font-size: 14px;
}

.developer-docs {
  background: white;
  border-radius: 8px;
  padding: 8px 0;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
}

.doc-item:hover {
  background: #f5f5f5;
}

.doc-icon {
  font-size: 18px;
}

.doc-item span:last-child {
  color: #1976d2;
  font-size: 13px;
}
</style>
