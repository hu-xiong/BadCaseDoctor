<template>
  <div class="sidebar-content" v-show="!planCollapsed">
    <div class="sidebar-header">
      <div class="header-top">
        <button class="action-icon-btn" @click="onShowCreatePlanModal" :title="t('project.addPlan')">
          <span class="icon">➕</span>
          <span class="btn-text">新建迭代</span>
        </button>
      </div>
    </div>

    <div class="plan-tree">
      <!-- 扁平展示所有活跃迭代（排除已归档） -->
      <div class="active-iterations">
        <div v-if="loading" class="loading-state">
          <span class="loading-text">{{ t('common.loading') }}</span>
        </div>

        <div v-else-if="!activePlans || activePlans.length === 0" class="empty-state">
          <span class="empty-text">{{ t('project.noActivePlans') }}</span>
        </div>

        <div v-else class="plan-list">
          <template v-for="plan in activePlans" :key="plan.id">
            <div
              class="plan-item"
              :class="{ 'active': selectedPlan === plan.id }"
              @click="onSelectPlan(plan.id)"
              @mouseenter="onShowPlanActions(plan.id)"
              @mouseleave="onHidePlanActions(plan.id)"
            >
              <span
                v-if="plan.children && plan.children.length > 0"
                class="expand-arrow"
                :class="{ 'expanded': expandedPlans && expandedPlans.includes(plan.id) }"
                @click.stop="onTogglePlanExpansion(plan.id)"
              >▶</span>
              <span v-else class="expand-placeholder"></span>
              <span class="plan-icon">{{ getPlanIcon('badcase') }}</span>
              <span class="plan-name">{{ plan.name }}</span>
              <span class="plan-date">{{ formatDate(plan.created_at) }}</span>

              <div v-show="hoveredPlan === plan.id" class="plan-actions">
                <button class="action-btn" @click.stop="onShowContextMenu(plan, $event)">
                  ⚙️
                </button>
              </div>

              <div
                v-if="contextMenu?.visible && contextMenu?.planId === plan.id"
                class="context-menu"
                :class="{ 'is-dragging': contextMenuDragActive }"
                :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                @mousedown.stop
              >
                <div
                  class="context-menu-drag-handle"
                  :title="t('project.contextMenuDragHint')"
                  @mousedown.stop="onContextMenuDragStart"
                >
                  <span class="drag-grip">⋮⋮</span>
                  <span class="drag-label">{{ t('project.contextMenuDrag') }}</span>
                </div>
                <div class="context-menu-body">
                  <div class="menu-item" @click="onCreateSubPlan(plan)">
                    <span class="menu-icon">➕</span>
                    <span>{{ t('project.menuSubPlan') }}</span>
                  </div>
                  <div class="menu-item" @click="onCreateSiblingPlan(plan)">
                    <span class="menu-icon">📝</span>
                    <span>{{ t('project.menuSiblingPlan') }}</span>
                  </div>
                  <div class="menu-item" @click="onEditPlan(plan)">
                    <span class="menu-icon">✏️</span>
                    <span>{{ t('project.menuEdit') }}</span>
                  </div>
                  <div class="menu-item" @click="onArchivePlan(plan)">
                    <span class="menu-icon">📦</span>
                    <span>{{ t('project.menuArchive') }}</span>
                  </div>
                  <div class="menu-item" @click="onDeletePlan(plan)">
                    <span class="menu-icon">🗑️</span>
                    <span>{{ t('project.menuDelete') }}</span>
                  </div>
                  <div class="menu-item" @click="onPinPlan(plan)">
                    <span class="menu-icon">📌</span>
                    <span>{{ plan.is_pinned ? t('project.unpin') : t('project.pin') }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div
              v-if="plan.children && plan.children.length > 0 && expandedPlans && expandedPlans.includes(plan.id)"
              class="sub-plan-list"
            >
              <div
                v-for="childPlan in plan.children"
                :key="childPlan.id"
                class="plan-item sub-plan"
                :class="{ 'active': selectedPlan === childPlan.id }"
                @click="onSelectPlan(childPlan.id)"
                @mouseenter="onShowPlanActions(childPlan.id)"
                @mouseleave="onHidePlanActions(childPlan.id)"
              >
                <span class="expand-placeholder"></span>
                <span class="plan-icon">{{ getPlanIcon('badcase') }}</span>
                <span class="plan-name">{{ childPlan.name }}</span>
                <span class="plan-date">{{ formatDate(childPlan.created_at) }}</span>

                <div v-show="hoveredPlan === childPlan.id" class="plan-actions">
                  <button class="action-btn" @click.stop="onShowContextMenu(childPlan, $event)">
                    ⚙️
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  planCollapsed: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  activePlans: { type: Array, default: () => [] },
  selectedPlan: { type: [String, Number, null], default: null },
  expandedPlans: { type: Array, default: () => [] },
  hoveredPlan: { type: [String, Number, null], default: null },
  contextMenu: { type: Object, default: () => ({}) },
  contextMenuDragActive: { type: Boolean, default: false },
  getPlanIcon: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  onShowCreatePlanModal: { type: Function, required: true },
  onSelectPlan: { type: Function, required: true },
  onShowPlanActions: { type: Function, required: true },
  onHidePlanActions: { type: Function, required: true },
  onTogglePlanExpansion: { type: Function, required: true },
  onShowContextMenu: { type: Function, required: true },
  onContextMenuDragStart: { type: Function, required: true },
  onCreateSubPlan: { type: Function, required: true },
  onCreateSiblingPlan: { type: Function, required: true },
  onEditPlan: { type: Function, required: true },
  onArchivePlan: { type: Function, required: true },
  onDeletePlan: { type: Function, required: true },
  onPinPlan: { type: Function, required: true }
})
</script>

<style scoped>
/* 计划树样式迁移到组件内，避免被 ProjectDetail.vue 的 scoped/:deep 干扰 */
.sidebar-content {
  flex: 1;
  padding: 12px 16px;
  overflow-y: auto;
  min-width: 0;
}

.sidebar-header {
  margin-bottom: 16px;
}

.header-top {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  min-height: 32px;
  gap: 4px;
}

.action-icon-btn {
  height: 24px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  transition: background-color 0.2s;
  padding: 0 6px;
  gap: 4px;
}

.action-icon-btn .btn-text {
  font-size: 12px;
  color: #666;
}

.action-icon-btn:hover {
  background: #f8f9fa;
}

.plan-tree {
  margin-top: 16px;
}

.plan-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  position: relative;
  user-select: none;
}

.plan-item:hover {
  background: #f8f9fa;
}

.plan-item.active {
  background: #e3f2fd;
  color: #1976d2;
}

.expand-arrow {
  width: 14px;
  display: inline-flex;
  justify-content: center;
  transition: transform 0.2s;
  color: #666;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 14px;
  display: inline-block;
}

.plan-icon {
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.plan-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-date {
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
}

.plan-item.active .plan-date {
  color: rgba(25, 118, 210, 0.8);
}

.plan-actions {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
}

.action-btn:hover {
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.context-menu {
  position: fixed;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  max-height: min(60vh, 360px);
  min-width: 150px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.context-menu.is-dragging {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
}

.context-menu-drag-handle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 11px;
  color: #888;
  background: #fafafa;
  border-bottom: 1px solid #eee;
  cursor: grab;
  user-select: none;
}

.context-menu.is-dragging .context-menu-drag-handle {
  cursor: grabbing;
}

.drag-grip {
  letter-spacing: -2px;
  opacity: 0.5;
}

.drag-label {
  font-weight: 400;
}

.context-menu-body {
  flex: 1;
  min-height: 0;
  max-height: min(50vh, 300px);
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 12px;
  color: #444;
  transition: background-color 0.15s;
}

.menu-item:hover {
  background: #f0f5ff;
}

.menu-icon {
  font-size: 12px;
  width: 14px;
  text-align: center;
}

.sub-plan-list {
  margin-left: 18px;
  padding-left: 10px;
  border-left: 1px dashed #e3e6ea;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-plan.plan-item {
  padding-left: 8px;
}

.loading-state,
.empty-state {
  padding: 12px 6px;
  color: #777;
}
</style>

