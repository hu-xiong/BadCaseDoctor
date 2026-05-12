<template>
  <div class="rich-text-html-editor" :class="{ compact: variant === 'compact' }">
    <VueEditor
      ref="editorRef"
      :html="modelValue ?? ''"
      :options="editorOptions"
      :placeholder="placeholder"
      :toolsbar="toolsbarList"
      @update:html="onHtml"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { VueEditor } from 'vue3-tiptap-editor'
import { BACKEND_BASE_URL } from '../api.js'

/** 与后端 `POST /upload`（MinIO）对齐；filelink 解析 axios 风格响应 */
const TOOLBAR_DEFAULT = [
  'undo',
  'redo',
  'solid',
  'Heading',
  'List',
  'blockquote',
  'codeBlock',
  'solid',
  'bold',
  'italic',
  'strike',
  'code',
  'underline',
  'fontBgColor',
  'fontColor',
  'Link',
  'UploaderFiles',
  'alignLeft',
  'alignCenter',
  'alignRight',
  'alignJustify',
  'subscript',
  'superscript'
]

const uploadAction = BACKEND_BASE_URL
  ? `${String(BACKEND_BASE_URL).replace(/\/+$/, '')}/upload`
  : '/upload'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  /** default | compact：侧栏评论等较矮区域 */
  variant: { type: String, default: 'default' }
})

const emit = defineEmits(['update:modelValue'])

const editorOptions = ref({
  extensions: [],
  uploaderHooks: {
    action: uploadAction,
    exceedSize(file) {
      const max = 50 * 1024 * 1024
      if (file.size > max) {
        window.alert?.('文件不能超过 50MB')
        return false
      }
      return true
    },
    filelink(rs) {
      if (!rs) return ''
      const d = rs.data !== undefined ? rs.data : rs
      return d.url || d.filelink || d.fileurl || (typeof d === 'string' ? d : '')
    }
  }
})
const toolsbarList = TOOLBAR_DEFAULT
const editorRef = ref(null)

function onHtml(v) {
  emit('update:modelValue', v ?? '')
}

watch(
  () => props.modelValue,
  async (v) => {
    await nextTick()
    const ed = editorRef.value
    if (!ed?.getHTML || !ed.setContent) return
    const next = v ?? ''
    if (ed.getHTML() === next) return
    ed.setContent(next)
  }
)
</script>

<style scoped>
/* 嵌入表单：覆盖库默认 max-width:750px + 居中，消除左侧大块留白 */
.rich-text-html-editor {
  width: 100%;
  --t-editor-content-width: 100%;
}
.rich-text-html-editor :deep(.-t-v-editor-wrapper) {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}
.rich-text-html-editor :deep(.-t-v-tiptap-editor) {
  max-width: 100%;
  margin-inline: 0;
  min-height: 220px;
  max-height: 480px;
  overflow-y: auto;
}
.rich-text-html-editor.compact :deep(.-t-v-tiptap-editor) {
  min-height: 140px;
  max-height: 280px;
}
</style>
