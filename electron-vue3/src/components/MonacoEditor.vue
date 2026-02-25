<template>
  <div class="monaco-editor-container">
    <div class="editor-toolbar">
      <div class="toolbar-left">
        <select v-model="currentLanguage" @change="changeLanguage" class="language-select">
          <option value="python">Python</option>
          <option value="javascript">JavaScript</option>
          <option value="typescript">TypeScript</option>
          <option value="java">Java</option>
          <option value="json">JSON</option>
          <option value="markdown">Markdown</option>
          <option value="sql">SQL</option>
          <option value="html">HTML</option>
          <option value="css">CSS</option>
        </select>
        <button @click="toggleTheme" class="theme-btn" :title="isDarkTheme ? '切换到亮色主题' : '切换到暗色主题'">
          {{ isDarkTheme ? '🌙' : '☀️' }}
        </button>
      </div>
      <div class="toolbar-right">
        <button @click="formatCode" class="action-btn" title="格式化代码">
          <span>📐</span> 格式化
        </button>
        <button @click="clearContent" class="action-btn" title="清空内容">
          <span>🗑️</span> 清空
        </button>
        <button @click="copyContent" class="action-btn" title="复制内容">
          <span>📋</span> 复制
        </button>
      </div>
    </div>
    <div ref="editorContainer" class="editor-wrapper"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as monaco from 'monaco-editor'

// Props
const props = defineProps({
  modelValue: {
    type: String,
    default: '# 欢迎使用 Monaco Editor\n\n这是一个强大的代码编辑器，支持：\n- 语法高亮\n- 代码自动补全\n- 多光标编辑\n- 代码格式化\n\n开始编写你的代码吧！'
  },
  language: {
    type: String,
    default: 'python'
  },
  theme: {
    type: String,
    default: 'vs-dark'
  },
  readOnly: {
    type: Boolean,
    default: false
  }
})

// Emits
const emit = defineEmits(['update:modelValue', 'change'])

// 响应式变量
const editorContainer = ref(null)
let editor = null
const currentLanguage = ref(props.language)
const isDarkTheme = ref(props.theme === 'vs-dark')

// 初始化编辑器
onMounted(() => {
  if (!editorContainer.value) return

  // 创建编辑器实例
  editor = monaco.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: currentLanguage.value,
    theme: isDarkTheme.value ? 'vs-dark' : 'vs',
    readOnly: props.readOnly,
    automaticLayout: true,
    fontSize: 14,
    lineNumbers: 'on',
    minimap: {
      enabled: true
    },
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    tabSize: 4,
    insertSpaces: true,
    formatOnPaste: true,
    formatOnType: true,
    suggestOnTriggerCharacters: true,
    acceptSuggestionOnEnter: 'on',
    quickSuggestions: true,
    folding: true,
    foldingStrategy: 'indentation',
    showFoldingControls: 'always',
    renderLineHighlight: 'all',
    selectOnLineNumbers: true,
    roundedSelection: true,
    cursorStyle: 'line',
    cursorBlinking: 'smooth',
    mouseWheelZoom: true
  })

  // 监听内容变化
  editor.onDidChangeModelContent(() => {
    const value = editor.getValue()
    emit('update:modelValue', value)
    emit('change', value)
  })

  // 窗口大小变化时自动调整
  const resizeObserver = new ResizeObserver(() => {
    if (editor) {
      editor.layout()
    }
  })
  
  if (editorContainer.value) {
    resizeObserver.observe(editorContainer.value)
  }

  // 清理函数
  onBeforeUnmount(() => {
    resizeObserver.disconnect()
    if (editor) {
      editor.dispose()
    }
  })
})

// 监听外部 modelValue 变化
watch(() => props.modelValue, (newValue) => {
  if (editor && editor.getValue() !== newValue) {
    editor.setValue(newValue)
  }
})

// 切换语言
const changeLanguage = () => {
  if (editor) {
    const model = editor.getModel()
    if (model) {
      monaco.editor.setModelLanguage(model, currentLanguage.value)
    }
  }
}

// 切换主题
const toggleTheme = () => {
  isDarkTheme.value = !isDarkTheme.value
  monaco.editor.setTheme(isDarkTheme.value ? 'vs-dark' : 'vs')
}

// 格式化代码
const formatCode = () => {
  if (editor) {
    editor.getAction('editor.action.formatDocument').run()
  }
}

// 清空内容
const clearContent = () => {
  if (editor) {
    editor.setValue('')
  }
}

// 复制内容
const copyContent = async () => {
  if (editor) {
    const content = editor.getValue()
    try {
      await navigator.clipboard.writeText(content)
      // 可以添加一个提示
      console.log('内容已复制到剪贴板')
    } catch (err) {
      console.error('复制失败:', err)
    }
  }
}

// 暴露方法给父组件
defineExpose({
  getValue: () => editor?.getValue(),
  setValue: (value) => editor?.setValue(value),
  getEditor: () => editor,
  focus: () => editor?.focus()
})
</script>

<style scoped>
.monaco-editor-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #1e1e1e;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #2d2d2d;
  border-bottom: 1px solid #3e3e3e;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.language-select {
  padding: 4px 8px;
  background: #3e3e3e;
  color: #ccc;
  border: 1px solid #555;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  outline: none;
}

.language-select:hover {
  background: #4e4e4e;
}

.language-select:focus {
  border-color: #007acc;
}

.theme-btn,
.action-btn {
  padding: 4px 12px;
  background: #3e3e3e;
  color: #ccc;
  border: 1px solid #555;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}

.theme-btn {
  font-size: 16px;
  padding: 4px 8px;
}

.action-btn span {
  font-size: 14px;
}

.theme-btn:hover,
.action-btn:hover {
  background: #007acc;
  border-color: #007acc;
  color: #fff;
}

.editor-wrapper {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 确保 Monaco Editor 填充整个容器 */
.editor-wrapper :deep(.monaco-editor) {
  height: 100% !important;
}
</style>

