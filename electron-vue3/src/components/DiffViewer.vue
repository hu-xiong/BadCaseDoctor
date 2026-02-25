<template>
  <div class="diff-viewer">
    <div v-for="(fieldDiff, index) in diffData" :key="index" class="field-diff">
      <div class="field-header">
        <span class="field-label">{{ fieldDiff.field_label }}</span>
      </div>
      <div class="diff-lines">
        <div 
          v-for="(line, idx) in fieldDiff.lines" 
          :key="idx"
          class="diff-line"
          :class="`diff-line-${line.type}`"
        >
          <span class="line-prefix" v-if="line.type !== 'unchanged'">
            {{ line.type === 'delete' ? '-' : '+' }}
          </span>
          <span class="line-content">{{ line.content }}</span>
        </div>
      </div>
    </div>
    
    <!-- 确认按钮 -->
    <div v-if="showConfirm" class="confirm-actions">
      <button @click="handleConfirm" class="btn-confirm">
        ✓ 确认修改
      </button>
      <button @click="handleCancel" class="btn-cancel">
        ✗ 取消
      </button>
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  diffData: {
    type: Array,
    required: true
  },
  showConfirm: {
    type: Boolean,
    default: true
  },
  modifyData: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['confirm', 'cancel'])

const handleConfirm = () => {
  emit('confirm', props.modifyData)
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<style scoped>
.diff-viewer {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}

.field-diff {
  margin-bottom: 16px;
}

.field-header {
  background: #e9ecef;
  padding: 8px 12px;
  border-radius: 4px 4px 0 0;
  font-weight: 600;
  font-size: 14px;
  color: #495057;
}

.field-label {
  display: inline-block;
}

.diff-lines {
  background: #fff;
  border: 1px solid #dee2e6;
  border-top: none;
  border-radius: 0 0 4px 4px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
}

.diff-line {
  padding: 4px 12px;
  line-height: 1.6;
  display: flex;
  align-items: flex-start;
}

.diff-line-delete {
  background: #ffebe9;
  color: #d73a49;
}

.diff-line-add {
  background: #e6ffed;
  color: #28a745;
}

.diff-line-unchanged {
  background: #fff;
  color: #586069;
}

.line-prefix {
  display: inline-block;
  width: 20px;
  flex-shrink: 0;
  font-weight: bold;
  margin-right: 8px;
}

.line-content {
  flex: 1;
  word-break: break-word;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #dee2e6;
}

.btn-confirm,
.btn-cancel {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-confirm {
  background: #28a745;
  color: white;
}

.btn-confirm:hover {
  background: #218838;
}

.btn-cancel {
  background: #6c757d;
  color: white;
}

.btn-cancel:hover {
  background: #5a6268;
}
</style>
