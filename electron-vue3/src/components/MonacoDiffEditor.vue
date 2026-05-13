<template>
  <div
    class="monaco-diff-editor"
    :class="{ 'monaco-diff-editor--light': isLightTheme }"
    :style="{ height }"
  >
    <div ref="containerRef" class="editor"></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'

const props = defineProps({
  original: { type: String, default: '' },
  modified: { type: String, default: '' },
  language: { type: String, default: 'markdown' },
  theme: { type: String, default: 'vs-dark' },
  height: { type: String, default: '180px' },
  readOnly: { type: Boolean, default: true },
  renderSideBySide: { type: Boolean, default: false }
})

const containerRef = ref(null)
let diffEditor = null
let originalModel = null
let modifiedModel = null

const isLightTheme = computed(() => {
  const t = (props.theme || '').toLowerCase()
  return t === 'vs' || t === 'vs-light' || t === 'hc-light'
})

const buildModels = () => {
  if (originalModel) originalModel.dispose()
  if (modifiedModel) modifiedModel.dispose()

  originalModel = monaco.editor.createModel(props.original ?? '', props.language)
  modifiedModel = monaco.editor.createModel(props.modified ?? '', props.language)

  diffEditor?.setModel({ original: originalModel, modified: modifiedModel })
}

onMounted(() => {
  if (!containerRef.value) return

  diffEditor = monaco.editor.createDiffEditor(containerRef.value, {
    theme: props.theme,
    readOnly: props.readOnly,
    renderSideBySide: props.renderSideBySide,
    automaticLayout: true,
    minimap: { enabled: false },
    wordWrap: 'on',
    scrollBeyondLastLine: false,
    renderIndicators: true,
    renderMarginRevertIcon: false,
    originalEditable: false
  })

  buildModels()

  // 尽量贴近“输入框内 diff”的观感：减少装饰，弱化分隔
  const modifiedEditor = diffEditor.getModifiedEditor()
  modifiedEditor.updateOptions({
    lineNumbers: 'off',
    glyphMargin: false,
    folding: false,
    scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
    overviewRulerBorder: false,
    hideCursorInOverviewRuler: true,
    renderLineHighlight: 'none',
    contextmenu: false
  })

  const originalEditor = diffEditor.getOriginalEditor()
  originalEditor.updateOptions({
    lineNumbers: 'off',
    glyphMargin: false,
    folding: false,
    scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
    overviewRulerBorder: false,
    hideCursorInOverviewRuler: true,
    renderLineHighlight: 'none',
    contextmenu: false
  })
})

watch(
  () => [props.original, props.modified, props.language],
  () => {
    if (!diffEditor) return
    buildModels()
  }
)

watch(
  () => props.theme,
  (t) => {
    try {
      monaco.editor.setTheme(t || 'vs-dark')
    } catch {
      /* ignore */
    }
  }
)

onBeforeUnmount(() => {
  try {
    originalModel?.dispose()
    modifiedModel?.dispose()
    diffEditor?.dispose()
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.monaco-diff-editor {
  width: 100%;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  overflow: hidden;
  background: #1e1e1e;
}

.monaco-diff-editor--light {
  border: 1px solid #e5e7eb;
  background: #ffffff;
}

.editor {
  width: 100%;
  height: 100%;
}

/* 暗色主题：删除/新增条带 */
.monaco-diff-editor:not(.monaco-diff-editor--light) :deep(.monaco-diff-editor .line-delete),
.monaco-diff-editor:not(.monaco-diff-editor--light) :deep(.monaco-diff-editor .delete) {
  background: rgba(244, 63, 94, 0.18) !important;
}

.monaco-diff-editor:not(.monaco-diff-editor--light) :deep(.monaco-diff-editor .line-insert),
.monaco-diff-editor:not(.monaco-diff-editor--light) :deep(.monaco-diff-editor .insert) {
  background: rgba(34, 197, 94, 0.14) !important;
}

/* 浅色主题 */
.monaco-diff-editor--light :deep(.monaco-diff-editor .line-delete),
.monaco-diff-editor--light :deep(.monaco-diff-editor .delete) {
  background: rgba(239, 68, 68, 0.12) !important;
}

.monaco-diff-editor--light :deep(.monaco-diff-editor .line-insert),
.monaco-diff-editor--light :deep(.monaco-diff-editor .insert) {
  background: rgba(16, 185, 129, 0.12) !important;
}
</style>

