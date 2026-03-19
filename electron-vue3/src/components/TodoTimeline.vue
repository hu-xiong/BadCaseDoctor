<template>
  <div v-if="todos && todos.length" class="todo-panel" :class="{ expanded: allExpanded }">
    <!-- 顶部汇总栏：弱化卡片感，左侧图标 + 待办步骤标题 -->
    <div class="todo-panel-header" @click="toggleAll">
      <div class="todo-panel-title">
        <img class="todo-panel-icon" :src="todoListIcon" alt="待办步骤" />
        <span class="todo-title-text">待办步骤</span>
        <span class="todo-title-count">
          已完成 {{ completedCount }} / 共 {{ totalCount }}
        </span>
      </div>
      <div class="todo-panel-meta">
        <span v-if="runningCount > 0" class="todo-running-text">
          正在执行 {{ runningCount }} 个步骤…
        </span>
        <img
          class="todo-panel-toggle"
          :src="allExpanded ? chevronDownIcon : chevronRightIcon"
          alt="toggle"
        />
      </div>
    </div>

    <!-- 具体步骤列表 -->
    <div v-show="allExpanded" class="qoder-todo-list">
      <div v-for="(todo, index) in todos" :key="index" class="qoder-todo-item">
        <div class="qoder-todo-check" :class="todo.status" aria-hidden="true"></div>
        <div class="qoder-todo-content-wrapper">
          <div
            class="qoder-todo-row"
            :class="{
              completed: todo.status === 'completed',
              running: todo.status === 'running',
              error: todo.status === 'error'
            }"
          >
            <div class="qoder-todo-text">{{ todo.text }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import todoListIcon from '../assets/todo-list-icon.svg'
import chevronRightIcon from '../assets/chevron-right-qoder.png'
import chevronDownIcon from '../assets/chevron-down-qoder.png'

const props = defineProps({
  todos: {
    type: Array,
    default: () => []
  }
})

const allExpanded = ref(true)

const totalCount = computed(() => props.todos.length)
const completedCount = computed(() =>
  props.todos.filter(t => t.status === 'completed').length
)
const runningCount = computed(() =>
  props.todos.filter(t => t.status === 'running').length
)

const toggleExpand = (index) => {
  expandedItems.value[index] = !expandedItems.value[index]
}

const toggleAll = () => {
  allExpanded.value = !allExpanded.value
}
</script>

<style scoped>
.qoder-todo-item {
  display: flex;
  gap: 10px;
  margin-bottom: 0;
  padding: 8px 10px;
  align-items: center;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.qoder-todo-item:last-child {
  border-bottom: none;
}

/* 圆形复选框：完成=对号，进行中=转圈，待办=空心圆 */
.qoder-todo-check {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  box-sizing: border-box;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qoder-todo-check.completed {
  border-color: rgba(74, 222, 128, 0.55);
}

.qoder-todo-check.completed::after {
  content: '✓';
  font-size: 12px;
  line-height: 1;
  color: #ffffff;
}

.qoder-todo-check.running {
  border-color: rgba(59, 130, 246, 0.65);
}

.qoder-todo-check.running::after {
  content: '';
  width: 10px;
  height: 10px;
  border-radius: 999px;
  border: 2px solid rgba(148, 163, 184, 0.22);
  border-top-color: rgba(59, 130, 246, 0.95);
  animation: todoSpin 0.8s linear infinite;
}

.qoder-todo-check.error {
  border-color: rgba(248, 113, 113, 0.6);
}
.qoder-todo-check.error::after {
  content: '!';
  font-size: 12px;
  line-height: 1;
  color: rgba(248, 113, 113, 0.95);
}

@keyframes todoSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.qoder-todo-content-wrapper {
  flex: 1;
  min-width: 0;
}

.qoder-todo-row {
  display: flex;
  align-items: center;
  color: #ffffff;
  font-size: 13px;
  line-height: 1.5;
}

.qoder-todo-text {
  font-weight: 500;
  word-wrap: break-word;
}

.qoder-todo-row.completed .qoder-todo-text {
  text-decoration: line-through;
  opacity: 0.7;
}

.qoder-todo-row.error .qoder-todo-text {
  color: #fecaca;
}

/* 原始输出样式 */
.qoder-todo-output {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 6px;
  padding: 12px;
  max-height: 400px;
  overflow: auto;
}

.qoder-todo-output pre {
  margin: 0;
  color: #d1d5db;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Courier New', monospace;
}

/* 顶部 Todo 汇总栏：弱化卡片，背景与对话面板一致 */
.todo-panel {
  margin: 8px 0 12px;
  border-radius: 0;
  overflow: visible;
  background: transparent; /* 跟随对话面板底色 */
  border: none;
}

.todo-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: transparent;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
  cursor: pointer;
}

/* 未展开时：不要展示边框线 */
.todo-panel:not(.expanded) .todo-panel-header {
  border-bottom: none;
}

.todo-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #f9fafb;
  font-size: 12px;
}

.todo-panel-icon {
  width: 14px;
  height: 14px;
  display: block;
  filter: invert(1); /* 深色背景下反相成浅色/白色 */
}

.todo-title-text {
  font-weight: 500;
}

.todo-title-count {
  font-size: 11px;
  color: #e5e7eb;
  opacity: 0.9;
}

.todo-panel-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.todo-running-text {
  font-size: 11px;
  color: #93c5fd;
}

.todo-panel-toggle {
  width: 10px;
  height: 10px;
  display: block;
  flex-shrink: 0;
  /* 颜色/观感与深度思考箭头一致 */
  filter: brightness(0) saturate(100%) invert(73%) sepia(11%) saturate(326%) hue-rotate(176deg) brightness(90%) contrast(86%);
  opacity: 0;
  transition: opacity 0.15s ease;
  pointer-events: none;
}

/* 折叠：hover 才显示 */
.todo-panel-header:hover .todo-panel-toggle {
  opacity: 0.95;
}

/* 展开：常显 */
.todo-panel.expanded .todo-panel-toggle {
  opacity: 0.95;
}

.qoder-todo-list {
  position: relative;
  padding: 6px 0 0;
}

/* 列表整体分割线（顶部/底部更自然） */
.qoder-todo-list {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  overflow: hidden;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  max-height: 400px;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
