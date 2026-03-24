<template>
  <div class="create-preview">
    <div class="preview-header">
      <span class="preview-icon">➕</span>
      <span class="preview-title">新建{{ getTargetLabel(previewData.target) }}</span>
    </div>
    
    <div class="preview-fields">
      <div
        v-for="([key, value], idx) in displayFieldEntries"
        :key="key + '_' + idx"
        class="field-row"
      >
        <span class="field-label">{{ getFieldLabel(key) }}：</span>
        <span class="field-value">{{ formatValue(value) }}</span>
      </div>

      <div v-if="restFieldCount > 0" class="field-row field-row--more">
        <span class="field-label">…</span>
        <span class="field-value">其余 {{ restFieldCount }} 项为详情字段，请在表单或列表中查看</span>
      </div>
    </div>
    
    <!-- 确认按钮 -->
    <div v-if="showConfirm" class="confirm-actions">
      <button @click="handleConfirm" class="btn-confirm">
        ✓ 确认创建
      </button>
      <button @click="handleCancel" class="btn-cancel">
        ✗ 取消
      </button>
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits, computed } from 'vue'

/** 与列表列一致（与 SimpleChatPanel / ProjectDetail 列表字段对齐） */
const PREVIEW_LIST_KEYS = {
  bug: new Set([
    'title',
    'status',
    'priority',
    'severity',
    'assignee',
    'assignee_id',
    'owner',
    'bug_type',
    'plan_id',
    'environment',
    'browser',
    'os'
  ]),
  badcase: new Set([
    'title',
    'status',
    'priority',
    'assignee',
    'assignee_id',
    'case_category',
    'plan_id',
    'document_type'
  ]),
  testcase: new Set([
    'title',
    'status',
    'priority',
    'assignee',
    'assignee_id',
    'case_type',
    'test_type',
    'plan_id',
    'version'
  ]),
  plan: new Set(['name', 'title', 'plan_type', 'status', 'priority', 'parent_id', 'start_date', 'end_date', 'cycle'])
}

const props = defineProps({
  previewData: {
    type: Object,
    required: true
  },
  showConfirm: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['confirm', 'cancel'])

const filteredFieldEntries = computed(() => {
  const fields = props.previewData.preview || {}
  const target = (props.previewData.target || 'bug').toLowerCase()
  const allow = PREVIEW_LIST_KEYS[target] || PREVIEW_LIST_KEYS.bug
  const filteredEntries = []
  for (const [key, value] of Object.entries(fields)) {
    if (!allow.has(key)) continue
    if (value === null || value === undefined || value === '') continue
    if (key === 'project_id' || key === 'created_at' || key === 'updated_at') continue
    filteredEntries.push([key, value])
  }
  return filteredEntries
})

const displayFieldEntries = computed(() => filteredFieldEntries.value)

const restFieldCount = computed(() => {
  const fields = props.previewData.preview || {}
  const target = (props.previewData.target || 'bug').toLowerCase()
  const allow = PREVIEW_LIST_KEYS[target] || PREVIEW_LIST_KEYS.bug
  let hidden = 0
  for (const key of Object.keys(fields)) {
    if (allow.has(key)) continue
    if (['project_id', 'created_at', 'updated_at'].includes(key)) continue
    const v = fields[key]
    if (v !== null && v !== undefined && v !== '') hidden++
  }
  return hidden
})

const getTargetLabel = (target) => {
  const labels = {
    'bug': 'Bug',
    'badcase': 'BadCase',
    'plan': '迭代计划'
  }
  return labels[target] || target
}

const getFieldLabel = (key) => {
  const labels = {
    'title': '标题',
    'name': '名称',
    'description': '描述',
    'priority': '优先级',
    'severity': '严重程度',
    'status': '状态',
    'plan_type': '计划类型',
    'plan_id': '所属计划',
    'parent_id': '父计划',
    'assignee_id': '负责人',
    'reproduce_steps': '复现步骤',
    'expected_result': '预期结果',
    'actual_result': '实际结果',
    'start_date': '开始日期',
    'end_date': '结束日期',
    'bug_type': '类型',
    'case_category': '问题分类',
    'case_type': '用例类型',
    'test_type': '测试类型',
    'document_type': '文档类型'
  }
  return labels[key] || key
}

const formatValue = (value) => {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim() === '') return '未填写'
  return value
}

const handleConfirm = () => {
  emit('confirm', props.previewData)
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<style scoped>
.create-preview {
  background: #f0f9ff;
  border: 2px solid #3b82f6;
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}

.preview-header {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #bfdbfe;
  gap: 10px;
}

.preview-icon {
  font-size: 20px;
  margin-right: 8px;
}

.preview-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
  flex: 1;
}

.preview-fields {
  background: white;
  border-radius: 6px;
  padding: 12px;
}

.field-row {
  display: flex;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}

.field-row:last-child {
  border-bottom: none;
}

.field-row--more .field-label {
  width: 120px;
}

.field-label {
  flex-shrink: 0;
  width: 120px;
  font-weight: 500;
  color: #64748b;
}

.field-value {
  flex: 1;
  color: #1e293b;
  word-break: break-word;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #bfdbfe;
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
  background: #3b82f6;
  color: white;
}

.btn-confirm:hover {
  background: #2563eb;
}

.btn-cancel {
  background: #6c757d;
  color: white;
}

.btn-cancel:hover {
  background: #5a6268;
}
</style>
