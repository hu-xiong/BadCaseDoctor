<template>
  <div class="inline-field-diff">
    <div class="inline-field-diff__toolbar">
      <span class="inline-field-diff__label">{{ label }}</span>
      <div class="inline-field-diff__actions">
        <button type="button" class="inline-field-diff__btn inline-field-diff__btn--ok" title="采纳（立即落库）" @click="$emit('apply')">
          ✓
        </button>
        <button type="button" class="inline-field-diff__btn inline-field-diff__btn--no" title="取消" @click="$emit('cancel')">
          ✗
        </button>
      </div>
    </div>
    <MonacoDiffEditor
      :original="displayOriginal"
      :modified="displayModified"
      :language="language"
      theme="vs"
      :height="height"
      :render-side-by-side="false"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MonacoDiffEditor from './MonacoDiffEditor.vue'

const props = defineProps({
  original: { type: String, default: '' },
  modified: { type: String, default: '' },
  label: { type: String, default: '修改预览' },
  emptyOriginalLabel: { type: String, default: '' },
  height: { type: String, default: '120px' },
  language: { type: String, default: 'plaintext' }
})

defineEmits(['apply', 'cancel'])

const displayOriginal = computed(() => {
  const s = String(props.original ?? '')
  if (s.trim()) return s
  return props.emptyOriginalLabel ? `(${props.emptyOriginalLabel})` : ''
})

const displayModified = computed(() => String(props.modified ?? ''))
</script>

<style scoped>
.inline-field-diff {
  width: 100%;
  background: #fff;
}

.inline-field-diff__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.inline-field-diff__label {
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
}

.inline-field-diff__actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.inline-field-diff__btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, transform 0.15s;
}

.inline-field-diff__btn--ok {
  background: #10b981;
  color: #fff;
}

.inline-field-diff__btn--ok:hover {
  background: #059669;
}

.inline-field-diff__btn--no {
  background: #ef4444;
  color: #fff;
}

.inline-field-diff__btn--no:hover {
  background: #dc2626;
}

.inline-field-diff :deep(.monaco-diff-editor) {
  border: none;
  border-radius: 0;
}
</style>
