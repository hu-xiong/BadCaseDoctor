<template>
  <span
    ref="rootRef"
    class="selectable-title-tip"
    @mouseenter="onTriggerEnter"
    @mouseleave="onTriggerLeave"
    @mousedown="onTriggerMouseDown"
  >
    <!-- 锚点：fit-content 收缩到实际文字宽度，避免 flex:1 整列占位导致悬浮层跑偏 -->
    <span ref="triggerRef" class="selectable-title-tip__trigger"><slot /></span>
    <Teleport v-if="fullText" to="body">
      <div
        v-show="open"
        ref="panelRef"
        class="selectable-title-tip__panel"
        :class="{ 'selectable-title-tip__panel--below': placement === 'below' }"
        :style="panelStyle"
        @mouseenter="onPanelEnter"
        @mouseleave="onPanelLeave"
        @mousedown.stop
      >
        <div class="selectable-title-tip__body">{{ fullText }}</div>
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  /** 悬浮层内完整文案（可选中后右键复制）；为空则不渲染悬浮层 */
  text: { type: String, default: '' }
})

const rootRef = ref(null)
const triggerRef = ref(null)
const panelRef = ref(null)
const open = ref(false)
const panelStyle = ref({})
const placement = ref('above')

const fullText = computed(() => String(props.text ?? '').trim())

let showTimer = null
let hideTimer = null
/** 打开后监听：点 Tab / 进子列表等不会触发锚点 mouseleave，需在 document 上关掉浮层 */
let offDocPointerDown = null

function clearShowHideTimers() {
  if (showTimer) clearTimeout(showTimer)
  if (hideTimer) clearTimeout(hideTimer)
  showTimer = hideTimer = null
}

function detachDocPointerDown() {
  if (offDocPointerDown) {
    document.removeEventListener('pointerdown', offDocPointerDown, true)
    offDocPointerDown = null
  }
}

function detachGlobalListeners() {
  window.removeEventListener('scroll', updatePosition, true)
  window.removeEventListener('resize', updatePosition)
}

/** 用 Range 包住锚点内全部内容，得到紧贴文字的矩形（避免外层 flex:1 占满整列） */
function getAnchorRect(el) {
  if (!el) return null
  try {
    const range = document.createRange()
    range.selectNodeContents(el)
    const rects = range.getClientRects()
    let minL = Infinity
    let maxR = -Infinity
    let minT = Infinity
    let maxB = -Infinity
    for (let i = 0; i < rects.length; i++) {
      const r = rects[i]
      if (r.width === 0 && r.height === 0) continue
      minL = Math.min(minL, r.left)
      maxR = Math.max(maxR, r.right)
      minT = Math.min(minT, r.top)
      maxB = Math.max(maxB, r.bottom)
    }
    if (minL !== Infinity && maxR > minL && maxB > minT) {
      return {
        left: minL,
        top: minT,
        width: maxR - minL,
        height: maxB - minT,
        right: maxR,
        bottom: maxB
      }
    }
  } catch {
    /* ignore */
  }
  return el.getBoundingClientRect()
}

function updatePosition() {
  const trigger = triggerRef.value
  const panel = panelRef.value
  if (!trigger || !panel || !open.value) return
  const rr = getAnchorRect(trigger)
  if (!rr || !(rr.width > 0 || rr.height > 0)) return
  const margin = 10
  const gap = 10
  const maxW = Math.min(520, window.innerWidth - 2 * margin)

  panel.style.maxWidth = `${maxW}px`
  void panel.offsetWidth
  const ph = panel.offsetHeight || 44

  let top = rr.top - ph - gap
  let place = 'above'
  if (top < margin) {
    top = rr.bottom + gap
    place = 'below'
    if (top + ph > window.innerHeight - margin) {
      top = Math.max(margin, window.innerHeight - ph - margin)
    }
  } else {
    top = Math.max(margin, top)
  }
  placement.value = place

  const pw = Math.min(panel.offsetWidth || maxW, maxW)
  let left = rr.left + rr.width / 2 - pw / 2
  left = Math.max(margin, Math.min(left, window.innerWidth - pw - margin))

  const triggerCx = rr.left + rr.width / 2
  const arrowLeft = triggerCx - left

  panelStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${left}px`,
    zIndex: 10050,
    maxWidth: `${maxW}px`,
    '--tip-arrow-left': `${arrowLeft}px`
  }
}

function closePanel() {
  clearShowHideTimers()
  open.value = false
  detachGlobalListeners()
  detachDocPointerDown()
}

function attachDocPointerDown() {
  if (offDocPointerDown) return
  offDocPointerDown = (e) => {
    const node = e.target
    const t = triggerRef.value
    const p = panelRef.value
    if (t && typeof t.contains === 'function' && t.contains(node)) return
    if (p && typeof p.contains === 'function' && p.contains(node)) return
    closePanel()
  }
  document.addEventListener('pointerdown', offDocPointerDown, true)
}

/** 点击进详情/子 Tab 时锚点可能直接卸载，来不及 mouseleave */
function onTriggerMouseDown() {
  closePanel()
}

function onTriggerEnter() {
  if (!fullText.value) return
  clearTimeout(hideTimer)
  hideTimer = null
  showTimer = setTimeout(() => {
    open.value = true
    nextTick(() => {
      updatePosition()
      requestAnimationFrame(() => {
        updatePosition()
      })
      window.addEventListener('scroll', updatePosition, true)
      window.addEventListener('resize', updatePosition)
      attachDocPointerDown()
    })
  }, 260)
}

function onTriggerLeave() {
  clearTimeout(showTimer)
  showTimer = null
  hideTimer = setTimeout(closePanel, 160)
}

function onPanelEnter() {
  clearTimeout(hideTimer)
  hideTimer = null
}

function onPanelLeave() {
  hideTimer = setTimeout(closePanel, 160)
}

watch(fullText, () => {
  closePanel()
})

onBeforeUnmount(() => {
  closePanel()
})
</script>

<style scoped>
.selectable-title-tip {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  align-items: center;
  vertical-align: bottom;
}

.selectable-title-tip__trigger {
  display: inline-block;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

/* 标题差分两行展示：不要被 nowrap 压成一行 */
.selectable-title-tip__trigger :where(.field-diff-inline, .create-pending-diff) {
  white-space: normal;
}

.selectable-title-tip__panel {
  position: relative;
  padding: 12px 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  color: #1e293b;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.06),
    0 18px 38px -12px rgba(15, 23, 42, 0.18),
    0 0 0 1px rgba(255, 255, 255, 0.7) inset;
  user-select: text;
  cursor: text;
  text-align: left;
}

/* 指向标题的小箭头：默认在上方，箭头朝下 */
.selectable-title-tip__panel::after {
  content: '';
  position: absolute;
  left: var(--tip-arrow-left, 50%);
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-top: 8px solid #f1f5f9;
  filter: drop-shadow(0 1px 0 rgba(148, 163, 184, 0.25));
  bottom: -8px;
}

/* 悬浮层在标题下方时，箭头朝上 */
.selectable-title-tip__panel--below::after {
  bottom: auto;
  top: -8px;
  border-top: none;
  border-bottom: 8px solid #ffffff;
  filter: drop-shadow(0 -1px 0 rgba(148, 163, 184, 0.2));
}

.selectable-title-tip__body {
  font-size: 13px;
  line-height: 1.55;
  letter-spacing: 0.01em;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: min(320px, 50vh);
  overflow-y: auto;
  font-weight: 450;
}

.selectable-title-tip__body::-webkit-scrollbar {
  width: 6px;
}

.selectable-title-tip__body::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 4px;
}
</style>
