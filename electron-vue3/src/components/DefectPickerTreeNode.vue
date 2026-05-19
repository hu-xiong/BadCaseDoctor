<template>
  <template v-for="plan in plans" :key="plan.value">
    <div class="tree-node" :class="{ 'sub-plan': depth > 0, [`depth-${depth}`]: true }">
      <div class="tree-node-header" @click="$emit('toggle-plan', plan.value)">
        <span
          class="expand-icon"
          :class="{
            expanded: plan.expanded,
            invisible: !(plan.children?.length || isLeafPlan(plan))
          }"
        >▶</span>
        <span class="plan-icon">{{ plan.icon || '📋' }}</span>
        <span class="plan-name">{{ plan.label }}</span>
        <span class="bug-count">({{ plan.bug_count ?? 0 }})</span>
      </div>

      <div v-if="plan.expanded" class="tree-children">
        <!-- 子计划（最多再递归一层，与 NewBug 三级计划一致） -->
        <DefectPickerTreeNode
          v-if="plan.children && plan.children.length > 0"
          :plans="plan.children"
          :depth="depth + 1"
          :is-defect-selected="isDefectSelected"
          @toggle-plan="$emit('toggle-plan', $event)"
          @toggle-card="(planId, cardId) => $emit('toggle-card', planId, cardId)"
          @toggle-bug="(bug, planId) => $emit('toggle-bug', bug, planId)"
        />

        <!-- 叶子计划：仅展示 bug 类型卡片 -->
        <template v-else>
          <div v-if="plan.cards === null" class="tree-children loading">
            <span class="loading-text">加载中...</span>
          </div>
          <div v-else-if="!plan.cards || plan.cards.length === 0" class="no-bugs-tip">
            暂无缺陷卡片
          </div>
          <template v-else>
            <div
              v-for="card in plan.cards"
              :key="card.value"
              class="tree-node card-node"
            >
              <div class="tree-node-header card-header" @click="$emit('toggle-card', plan.value, card.value)">
                <span class="expand-icon" :class="{ expanded: card.expanded }">▶</span>
                <span class="card-type-badge bug">Bug</span>
                <span class="card-name">{{ card.label }}</span>
                <span class="bug-count">({{ card.bug_count ?? (card.bugs?.length || 0) }})</span>
              </div>
              <div v-if="card.expanded" class="tree-children">
                <div v-if="card.bugs === null" class="tree-children loading">
                  <span class="loading-text">加载中...</span>
                </div>
                <div v-else-if="!card.bugs || card.bugs.length === 0" class="no-bugs-tip">
                  暂无缺陷
                </div>
                <div
                  v-else
                  v-for="bug in card.bugs"
                  :key="bug.id"
                  class="bug-item"
                  :class="{ selected: isDefectSelected(bug.id) }"
                  @click="$emit('toggle-bug', bug, plan.value)"
                >
                  <div class="checkbox" :class="{ checked: isDefectSelected(bug.id) }">
                    <span v-if="isDefectSelected(bug.id)" class="checkmark">✓</span>
                  </div>
                  <div class="bug-info">
                    <span class="bug-id">Bug-{{ bug.id }}</span>
                    <span class="bug-title">{{ bug.title }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>
  </template>
</template>

<script>
export default {
  name: 'DefectPickerTreeNode',
  props: {
    plans: {
      type: Array,
      default: () => []
    },
    depth: {
      type: Number,
      default: 0
    },
    isDefectSelected: {
      type: Function,
      required: true
    }
  },
  emits: ['toggle-plan', 'toggle-card', 'toggle-bug'],
  methods: {
    isLeafPlan(plan) {
      return !plan.children || plan.children.length === 0
    }
  }
}
</script>

<style scoped>
.tree-node {
  border-bottom: 1px solid #e9ecef;
}

.tree-node.sub-plan {
  border-left: 2px solid #e9ecef;
}

.tree-node.depth-1 {
  margin-left: 16px;
}

.tree-node.depth-2 {
  margin-left: 32px;
}

.tree-node.card-node {
  margin-left: 16px;
  border-left: 2px solid #fde2e2;
}

.tree-node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f8f9fa;
  cursor: pointer;
  transition: background-color 0.2s;
  user-select: none;
}

.tree-node-header:hover {
  background: #f0f0f0;
}

.tree-node-header.card-header {
  background: #fff8f8;
}

.tree-node-header.card-header:hover {
  background: #fff0f0;
}

.expand-icon {
  font-size: 12px;
  color: #999;
  transition: transform 0.2s;
  width: 12px;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.expand-icon.invisible {
  visibility: hidden;
}

.plan-icon {
  font-size: 16px;
}

.plan-name,
.card-name {
  flex: 1;
  font-weight: 500;
  color: #333;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bug-count {
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
}

.card-type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.card-type-badge.bug {
  background: #ffebee;
  color: #c62828;
}

.tree-children {
  background: #fff;
}

.tree-children.loading {
  padding: 16px;
  text-align: center;
}

.loading-text,
.no-bugs-tip {
  color: #999;
  font-size: 14px;
}

.no-bugs-tip {
  padding: 16px;
  text-align: center;
}

.bug-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px 10px 48px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.bug-item:last-child {
  border-bottom: none;
}

.bug-item:hover {
  background: #f8f9fa;
}

.bug-item.selected {
  background: #e3f2fd;
}

.checkbox {
  width: 16px;
  height: 16px;
  border: 2px solid #ddd;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.checkbox.checked {
  background: #409eff;
  border-color: #409eff;
}

.checkmark {
  color: white;
  font-size: 10px;
  font-weight: bold;
}

.bug-info {
  flex: 1;
  min-width: 0;
}

.bug-id {
  font-weight: 500;
  color: #409eff;
  margin-right: 8px;
}

.bug-title {
  color: #333;
}
</style>
