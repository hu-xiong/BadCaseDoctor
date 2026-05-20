<template>
  <div class="rich-text-html-editor" :class="{ compact: variant === 'compact' }">
    <VueEditor
      ref="editorRef"
      :html="editorHtml"
      :options="editorOptions"
      :placeholder="placeholder"
      :toolsbar="toolbarItems"
      @update:html="onHtml"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed, onBeforeUnmount, onMounted } from 'vue'
import { VueEditor } from 'vue3-tiptap-editor'
import { BACKEND_BASE_URL, uploadRichTextImageFile } from '../api.js'
import {
  prepareRichTextHtmlForEditor,
  normalizeRichTextHtmlForStorage,
  uploadResponseToImageUrl,
  preloadUploadImage,
  convertUploaderNodesToImages
} from '../utils/uploadImageUrl.js'

const TOOLBAR_ITEMS = [
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
  ? `${String(BACKEND_BASE_URL).replace(/\/+$/, '')}/api/upload`
  : '/api/upload'

/** 富文本插图（上传 / 粘贴）单张上限 */
const MAX_RICH_TEXT_IMAGE_BYTES = 1024 * 1024

function alertImageTooLarge() {
  window.alert?.('图片不能超过 1MB')
}

function validateRichTextImageFile(file) {
  if (!file?.type?.startsWith('image/')) return false
  if (file.size > MAX_RICH_TEXT_IMAGE_BYTES) {
    alertImageTooLarge()
    return false
  }
  return true
}

function collectClipboardImageFiles(event) {
  const dt = event.clipboardData
  if (!dt) return []
  const files = []
  if (dt.files?.length) {
    for (let i = 0; i < dt.files.length; i++) {
      const f = dt.files[i]
      if (f?.type?.startsWith('image/')) files.push(f)
    }
  }
  if (!files.length && dt.items?.length) {
    for (const item of dt.items) {
      if (item.kind === 'file' && item.type?.startsWith('image/')) {
        const f = item.getAsFile()
        if (f) files.push(f)
      }
    }
  }
  return files
}

async function uploadAndInsertImage(editor, file) {
  if (!validateRichTextImageFile(file)) return
  const url = await uploadRichTextImageFile(file)
  await preloadUploadImage(url)
  editor
    .chain()
    .focus()
    .setImage({ src: url, class: 'rte-inline-img', alt: file.name || 'image' })
    .run()
  onUploadUrlReady(url)
}

async function uploadAndInsertClipboardImages(editor, files) {
  for (const file of files) {
    try {
      await uploadAndInsertImage(editor, file)
    } catch (e) {
      console.error('粘贴图片上传失败:', e)
      window.alert?.(e?.message || '图片上传失败')
    }
  }
}

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  variant: { type: String, default: 'default' },
  /** 评论框等：Enter 提交，Shift+Enter 换行 */
  submitOnEnter: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'submit'])

const editorRef = ref(null)
const converting = ref(false)
let detachEditorUpdate = null
let detachPasteHandler = null
let detachEnterSubmitHandler = null
let isUnmounted = false
let syncGeneration = 0
let syncingFromModel = false
let syncScheduleTimer = null

const editorHtml = computed(() => prepareRichTextHtmlForEditor(props.modelValue ?? ''))

function stripHtmlText(html) {
  return String(html || '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .trim()
}

function getTiptapEditor() {
  const wrap = editorRef.value
  const ed = wrap?.editor
  return ed?.value ?? ed ?? null
}

/** 接口返回 URL 后：预加载完成再转 img，避免 100% 后空白等待 */
function onUploadUrlReady(url) {
  if (!url) return
  preloadUploadImage(url).then(() => {
    const editor = getTiptapEditor()
    if (!editor || converting.value) return
    converting.value = true
    convertUploaderNodesToImages(editor)
    nextTick(() => {
      converting.value = false
    })
  })
}

function tryEmitSubmitOnEnter(event) {
  if (!props.submitOnEnter) return false
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return false
  event.preventDefault()
  event.stopPropagation()
  emit('submit')
  return true
}

/** vue3-tiptap-editor 已内置 image 扩展，勿再重复注册 */
const editorOptions = computed(() => ({
  uploaderHooks: {
    action: uploadAction,
    exceedSize(file) {
      if (!file?.type?.startsWith('image/')) return false
      if (file.size > MAX_RICH_TEXT_IMAGE_BYTES) {
        alertImageTooLarge()
        return true
      }
      return false
    },
    filelink(rs) {
      const url = uploadResponseToImageUrl(rs)
      if (url) onUploadUrlReady(url)
      return url
    },
  },
}))

const toolbarItems = computed(() => [...TOOLBAR_ITEMS])

function onHtml(v) {
  if (syncingFromModel) return
  if (converting.value) {
    emit('update:modelValue', normalizeRichTextHtmlForStorage(v ?? ''))
    return
  }
  emit('update:modelValue', normalizeRichTextHtmlForStorage(v ?? ''))
}

/** 库内 XHR 上传默认不带 Cookie，补上以便 /api/upload 鉴权 */
function patchUploadXhrCredentials() {
  if (typeof XMLHttpRequest === 'undefined' || window.__rteUploadXhrCred) return
  window.__rteUploadXhrCred = true
  const nativeOpen = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    const ret = nativeOpen.call(this, method, url, ...rest)
    const u = String(url || '')
    if (u.includes('/api/upload') || u.endsWith('/upload')) {
      this.withCredentials = true
    }
    return ret
  }
}

function bindEditorPaste() {
  detachPasteHandler?.()
  detachPasteHandler = null
  const editor = getTiptapEditor()
  const dom = editor?.view?.dom
  if (!dom) return

  const onPaste = (event) => {
    const files = collectClipboardImageFiles(event)
    if (!files.length) return
    event.preventDefault()
    event.stopPropagation()
    void uploadAndInsertClipboardImages(editor, files)
  }
  dom.addEventListener('paste', onPaste, true)
  detachPasteHandler = () => dom.removeEventListener('paste', onPaste, true)
}

function bindEnterSubmitKeydown() {
  detachEnterSubmitHandler?.()
  detachEnterSubmitHandler = null
  if (!props.submitOnEnter) return
  const editor = getTiptapEditor()
  const dom = editor?.view?.dom
  if (!dom) return
  const onKeydown = (event) => {
    tryEmitSubmitOnEnter(event)
  }
  dom.addEventListener('keydown', onKeydown, true)
  detachEnterSubmitHandler = () => dom.removeEventListener('keydown', onKeydown, true)
}

function bindEditorUpdate() {
  detachEditorUpdate?.()
  detachEditorUpdate = null
  const editor = getTiptapEditor()
  if (!editor || editor.isDestroyed) return
  bindEditorPaste()
  bindEnterSubmitKeydown()
  const handler = ({ transaction }) => {
    if (!transaction?.docChanged) return
    nextTick(() => {
      editor.state.doc.descendants((node, pos) => {
        if (node.type.name !== 'Uploader') return
        const dom = editor.view.nodeDOM(pos)
        const img = dom?.querySelector?.('.image-wrappe img, img.image, img[src]')
        const src = img?.getAttribute?.('src') || ''
        if (src && !src.startsWith('blob:')) onUploadUrlReady(src)
      })
    })
  }
  editor.on('update', handler)
  detachEditorUpdate = () => editor.off('update', handler)
}

function applyHtmlToEditor(next) {
  const wrap = editorRef.value
  const html = next || '<p></p>'
  if (wrap?.setContent) {
    wrap.setContent(html)
    return
  }
  const tiptap = getTiptapEditor()
  tiptap?.commands?.setContent?.(html)
}

function readEditorHtml() {
  const wrap = editorRef.value
  return wrap?.getHTML?.() || getTiptapEditor()?.getHTML?.() || ''
}

/** 外部 v-model 变更后灌入 TipTap（编辑器未就绪时需重试） */
async function syncFromModel() {
  if (isUnmounted) return
  const gen = ++syncGeneration
  const next = editorHtml.value
  const wantText = stripHtmlText(next)

  syncingFromModel = true
  try {
    for (let attempt = 0; attempt < 16; attempt += 1) {
      if (isUnmounted || gen !== syncGeneration) return
      await nextTick()

      const wrap = editorRef.value
      const tiptap = getTiptapEditor()
      if (!wrap?.setContent && !tiptap?.commands?.setContent) {
        await new Promise((r) => setTimeout(r, 40))
        continue
      }
      if (tiptap?.isDestroyed) {
        await new Promise((r) => setTimeout(r, 40))
        continue
      }

      const curText = stripHtmlText(readEditorHtml())
      if ((!wantText && !curText) || (wantText && curText === wantText)) break

      try {
        applyHtmlToEditor(next)
      } catch (_e) {
        await new Promise((r) => setTimeout(r, 40))
        continue
      }

      if (isUnmounted || gen !== syncGeneration) return
      const afterText = stripHtmlText(readEditorHtml())
      if (!wantText || afterText === wantText) break
      await new Promise((r) => setTimeout(r, 40))
    }
  } finally {
    syncingFromModel = false
    if (!isUnmounted && gen === syncGeneration) {
      try {
        bindEditorUpdate()
      } catch (e) {
        console.warn('[RichTextHtmlEditor] bindEditorUpdate failed:', e)
      }
    }
  }
}

function scheduleSyncFromModel() {
  if (isUnmounted) return
  if (syncScheduleTimer) clearTimeout(syncScheduleTimer)
  syncScheduleTimer = setTimeout(() => {
    syncScheduleTimer = null
    void syncFromModel().catch((e) => {
      if (!isUnmounted) console.warn('[RichTextHtmlEditor] syncFromModel failed:', e)
    })
  }, 48)
}

defineExpose({ syncFromModel: scheduleSyncFromModel })

onMounted(() => {
  patchUploadXhrCredentials()
  scheduleSyncFromModel()
})

watch(
  () => [props.modelValue, editorRef.value],
  () => {
    scheduleSyncFromModel()
  },
  { flush: 'post', immediate: true }
)

onBeforeUnmount(() => {
  isUnmounted = true
  syncGeneration += 1
  if (syncScheduleTimer) clearTimeout(syncScheduleTimer)
  syncScheduleTimer = null
  detachEditorUpdate?.()
  detachPasteHandler?.()
  detachEnterSubmitHandler?.()
})

watch(
  () => props.submitOnEnter,
  () => {
    scheduleSyncFromModel()
  }
)
</script>

<style scoped>
.rich-text-html-editor {
  width: 100%;
  --t-editor-content-width: 100%;
  --t-v-editor-wrapper-pb: 0;
}

.rich-text-html-editor :deep(.-t-v-editor-wrapper) {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  overflow: visible;
  background: #fff;
  padding-bottom: 0;
}

.rich-text-html-editor :deep(.-t-v-tiptap-editor) {
  max-width: 100%;
  margin-inline: 0;
  min-height: 220px;
  max-height: 480px;
  overflow-y: auto;
}

.rich-text-html-editor :deep(.ProseMirror) {
  color: #303133;
  min-height: 1.5em;
  outline: none;
}

.rich-text-html-editor :deep(.ProseMirror p) {
  margin: 0.35em 0;
  min-height: 1.2em;
}

.rich-text-html-editor.compact :deep(.-t-v-tiptap-editor) {
  min-height: 140px;
  max-height: 280px;
}

/* 侧栏等窄容器：工具栏单行横向滚动；滚动条仅悬停时显示 */
.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container) {
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  scrollbar-color: transparent transparent;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container::-webkit-scrollbar) {
  height: 0;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container:hover) {
  scrollbar-width: thin;
  scrollbar-color: #c1c1c1 transparent;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container:hover::-webkit-scrollbar) {
  height: 6px;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container:hover::-webkit-scrollbar-thumb) {
  background: #c1c1c1;
  border-radius: 3px;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-container:hover::-webkit-scrollbar-track) {
  background: transparent;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-h) {
  flex-wrap: nowrap !important;
  width: max-content;
  min-width: 100%;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar) {
  flex-wrap: nowrap !important;
}

.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar-h > *),
.rich-text-html-editor.compact :deep(.-t-v-editor-toolbar button) {
  flex-shrink: 0;
}

.rich-text-html-editor :deep(.uploader-wrap) {
  max-width: 100%;
  margin: 12px 0;
}

.rich-text-html-editor :deep(.uploader-card.image-video-card) {
  max-width: 520px;
}

.rich-text-html-editor :deep(.uploader-card.image-video-card .image-wrappe) {
  display: block;
}

.rich-text-html-editor :deep(.uploader-card .progress-block) {
  background: rgba(255, 255, 255, 0.82);
}

.rich-text-html-editor :deep(.-t-v-tiptap-editor img),
.rich-text-html-editor :deep(.ProseMirror img),
.rich-text-html-editor :deep(.rte-inline-img) {
  display: inline-block !important;
  vertical-align: middle;
  max-width: min(320px, 100%);
  height: auto;
  max-height: 240px;
  margin: 4px 6px 4px 0;
  border: none !important;
  box-shadow: none !important;
  border-radius: 4px;
  object-fit: contain;
}

.rich-text-html-editor :deep(.ProseMirror img.ProseMirror-selectednode) {
  outline: 2px solid #667eea;
  outline-offset: 2px;
}
</style>
