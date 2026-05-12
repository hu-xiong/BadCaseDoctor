<template>
  <div class="diff-viewer">
    <!-- 批量修改结果 -->
    <div v-if="batchResults && batchResults.length > 0" class="batch-results">
      <div class="batch-header">
        <span class="batch-icon">📝</span>
        <span class="batch-title">修改预览</span>
        <span class="batch-count">{{ batchResults.length }} 项变更</span>
      </div>
      
      <div v-for="(item, index) in batchResults" :key="index" class="diff-item">
        <div class="diff-item-header">
          <span class="item-title">{{ item.result?.before?.title || `Bug #${item.bug_id}` }}</span>
          <span class="item-id">ID: {{ item.bug_id }}</span>
        </div>
        
        <!-- 字段差异对比 -->
        <div v-for="(fieldDiff, idx) in item.result?.diff" :key="idx" class="field-diff">
          <div class="field-header">
            <span class="field-label">{{ fieldDiff.field_label }}</span>
            <span class="field-name">({{ fieldDiff.field }})</span>
          </div>
          
          <div class="diff-content">
            <!-- 删除的行（旧值） -->
            <div v-for="(line, lineIdx) in fieldDiff.lines.filter(l => l.type === 'delete')" 
                 :key="'del-' + lineIdx" 
                 class="diff-line diff-line-delete">
              <span class="line-gutter">-</span>
              <span class="line-content old-value">{{ line.content }}</span>
            </div>
            <!-- 新增的行（新值） -->
            <div v-for="(line, lineIdx) in fieldDiff.lines.filter(l => l.type === 'add')" 
                 :key="'add-' + lineIdx" 
                 class="diff-line diff-line-add">
              <span class="line-gutter">+</span>
              <span class="line-content new-value">{{ line.content }}</span>
            </div>
          </div>
        </div>
        
        <!-- 单项审核按钮 -->
        <div class="item-actions">
          <button @click="handleItemApprove(item)" class="btn-approve" title="采纳此修改">
            <span class="btn-icon">✓</span>
            <span>采纳</span>
          </button>
          <button @click="handleItemReject(item)" class="btn-reject" title="拒绝此修改">
            <span class="btn-icon">✗</span>
            <span>拒绝</span>
          </button>
        </div>
      </div>
      
      <!-- 批量操作按钮 -->
      <div class="batch-actions">
        <button @click="handleApproveAll" class="btn-approve-all">
          <span class="btn-icon">✓</span>
          <span>全部采纳</span>
        </button>
        <button @click="handleRejectAll" class="btn-reject-all">
          <span class="btn-icon">✗</span>
          <span>全部拒绝</span>
        </button>
      </div>
    </div>
    
    <!-- 单个修改结果 -->
    <div v-else-if="diffData && diffData.length > 0">
      <div v-for="(fieldDiff, index) in diffData" :key="index" class="field-diff">
        <div class="field-header">
          <span class="field-label">{{ fieldDiff.field_label }}</span>
          <span class="field-name">({{ fieldDiff.field }})</span>
        </div>
        
        <div class="diff-content">
          <div v-for="(line, idx) in fieldDiff.lines" 
               :key="idx"
               class="diff-line"
               :class="`diff-line-${line.type}`">
            <span class="line-gutter">
              {{ line.type === 'delete' ? '-' : line.type === 'add' ? '+' : ' ' }}
            </span>
            <span class="line-content">{{ line.content }}</span>
          </div>
        </div>
      </div>
      
      <!-- 确认按钮 -->
      <div v-if="showConfirm" class="confirm-actions">
        <button @click="handleConfirm" class="btn-approve">
          <span class="btn-icon">✓</span>
          <span>确认修改</span>
        </button>
        <button @click="handleCancel" class="btn-reject">
          <span class="btn-icon">✗</span>
          <span>取消</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  diffData: {
    type: Array,
    default: () => []
  },
  showConfirm: {
    type: Boolean,
    default: true
  },
  modifyData: {
    type: Object,
    default: () => ({})
  },
  batchResults: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['confirm', 'cancel', 'approve-item', 'reject-item', 'approve-all', 'reject-all'])

const handleConfirm = () => {
  emit('confirm', props.modifyData)
}

const handleCancel = () => {
  emit('cancel')
}

const handleItemApprove = (item) => {
  emit('approve-item', item)
}

const handleItemReject = (item) => {
  emit('reject-item', item)
}

const handleApproveAll = () => {
  emit('approve-all', props.batchResults)
}

const handleRejectAll = () => {
  emit('reject-all', props.batchResults)
}
</script>

<style scoped>
.diff-viewer {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
  color: #d4d4d4;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.batch-results {
  border-radius: 6px;
  overflow: hidden;
}

.batch-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #2d2d2d;
  border-bottom: 1px solid #3d3d3d;
}

.batch-icon {
  font-size: 16px;
}

.batch-title {
  font-weight: 600;
  font-size: 14px;
  color: #e0e0e0;
}

.batch-count {
  margin-left: auto;
  font-size: 12px;
  color: #888;
  background: #3d3d3d;
  padding: 2px 8px;
  border-radius: 10px;
}

.diff-item {
  background: #252526;
  border: 1px solid #3d3d3d;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.diff-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #2d2d2d;
  border-bottom: 1px solid #3d3d3d;
}

.item-title {
  font-weight: 500;
  color: #e0e0e0;
  font-size: 13px;
}

.item-id {
  font-size: 11px;
  color: #888;
  font-family: 'Monaco', 'Menlo', monospace;
}

.field-diff {
  margin-bottom: 8px;
}

.field-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #2d2d2d;
  font-size: 12px;
}

.field-label {
  font-weight: 600;
  color: #4fc3f7;
}

.field-name {
  color: #888;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 11px;
}

.diff-content {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
}

.diff-line {
  display: flex;
  align-items: flex-start;
  padding: 3px 14px;
  line-height: 1.5;
}

.diff-line-delete {
  background: rgba(255, 0, 0, 0.18);
  border-left: 3px solid #f14c4c;
}

.diff-line-add {
  background: rgba(0, 255, 0, 0.1);
  border-left: 3px solid #3fb950;
}

.diff-line-unchanged {
  background: transparent;
  border-left: 3px solid transparent;
}

.line-gutter {
  display: inline-block;
  width: 20px;
  flex-shrink: 0;
  font-weight: bold;
  text-align: center;
  margin-right: 12px;
  font-size: 14px;
}

.diff-line-delete .line-gutter {
  color: #f14c4c;
}

.diff-line-add .line-gutter {
  color: #3fb950;
}

.line-content {
  flex: 1;
  word-break: break-word;
}

.old-value {
  color: #f14c4c;
  text-decoration: line-through;
  opacity: 0.9;
}

.new-value {
  color: #3fb950;
  font-weight: 500;
}

.item-actions {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  background: #2d2d2d;
  border-top: 1px solid #3d3d3d;
}

.btn-approve,
.btn-reject {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-approve {
  background: #238636;
  color: white;
}

.btn-approve:hover {
  background: #2ea043;
}

.btn-reject {
  background: #6e7681;
  color: white;
}

.btn-reject:hover {
  background: #8b949e;
}

.btn-icon {
  font-size: 14px;
  font-weight: bold;
}

.batch-actions {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: #2d2d2d;
  border-top: 1px solid #3d3d3d;
  margin-top: 8px;
  border-radius: 0 0 6px 6px;
}

.btn-approve-all {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: #238636;
  color: white;
  transition: all 0.15s ease;
}

.btn-approve-all:hover {
  background: #2ea043;
}

.btn-reject-all {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: #da3633;
  color: white;
  transition: all 0.15s ease;
}

.btn-reject-all:hover {
  background: #f85149;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #3d3d3d;
}
</style>
