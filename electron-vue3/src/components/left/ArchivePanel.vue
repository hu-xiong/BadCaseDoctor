<template>
  <div class="sidebar-content" v-show="!planCollapsed">
    <div class="sidebar-header">
      <div class="header-top">
        <div class="panel-title">{{ t('project.sectionArchived') }}</div>
      </div>
    </div>

    <div class="plan-tree">
      <div class="active-iterations">
        <div v-if="loading" class="loading-state">
          <span class="loading-text">{{ t('common.loading') }}</span>
        </div>

        <div v-else-if="!archivedPlans || archivedPlans.length === 0" class="empty-state">
          <span class="empty-text">{{ t('project.emptyArchived') }}</span>
        </div>

        <div v-else class="plan-list">
          <template v-for="plan in archivedPlans" :key="plan.id">
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
                  <div class="menu-item" @click="onEditPlan(plan)">
                    <span class="menu-icon">✏️</span>
                    <span>{{ t('project.menuEdit') }}</span>
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
  archivedPlans: { type: Array, default: () => [] },
  selectedPlan: { type: [String, Number, null], default: null },
  expandedPlans: { type: Array, default: () => [] },
  hoveredPlan: { type: [String, Number, null], default: null },
  contextMenu: { type: Object, default: () => ({}) },
  contextMenuDragActive: { type: Boolean, default: false },
  getPlanIcon: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  onSelectPlan: { type: Function, required: true },
  onShowPlanActions: { type: Function, required: true },
  onHidePlanActions: { type: Function, required: true },
  onTogglePlanExpansion: { type: Function, required: true },
  onShowContextMenu: { type: Function, required: true },
  onContextMenuDragStart: { type: Function, required: true },
  onEditPlan: { type: Function, required: true },
  onDeletePlan: { type: Function, required: true },
  onPinPlan: { type: Function, required: true }
})
</script>

<style scoped>
/* 直接复用 PlansPanel 的布局与样式，保证展示一致 */
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

.panel-title {
  font-size: 12px;
  color: #666;
  font-weight: 600;
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
}

.plan-item:hover {
  background: #f8f9fa;
}

.plan-item.active {
  background: #eef2ff;
}

.expand-arrow {
  font-size: 10px;
  color: #666;
  width: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: rotate(0deg);
  transition: transform 0.15s ease;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 12px;
}

.plan-icon {
  font-size: 14px;
  width: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.plan-name {
  flex: 1;
  font-size: 13px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-date {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
}

.plan-actions {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
}

.action-btn {
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.8;
}

.sub-plan-list {
  margin-left: 18px;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-plan {
  padding-left: 10px;
}

.loading-state,
.empty-state {
  padding: 8px 10px;
  color: #666;
  font-size: 12px;
}

.context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  width: 190px;
  overflow: hidden;
}

.context-menu-drag-handle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f8f9fa;
  border-bottom: 1px solid #eef1f4;
  cursor: move;
  user-select: none;
}

.drag-grip {
  font-size: 14px;
  color: #888;
  line-height: 1;
}

.drag-label {
  font-size: 12px;
  color: #666;
}

.context-menu-body {
  padding: 6px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  color: #333;
}

.menu-item:hover {
  background: #f3f5f7;
}

.menu-icon {
  width: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>

