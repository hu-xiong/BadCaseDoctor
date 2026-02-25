<template>
  <div class="typewriter-container">
    <span class="typewriter-text">{{ displayText }}<span v-if="isTyping" class="cursor"></span></span>
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  text: {
    type: String,
    default: ''
  },
  speed: {
    type: Number,
    default: 30  // ms per character
  },
  autoPlay: {
    type: Boolean,
    default: true
  },
  instant: {
    type: Boolean,
    default: false  // 是否立即显示全部内容（历史消息用）
  }
})

const displayText = ref('')
const isTyping = ref(false)
let typewriterInterval = null

// 开始打字
const startTyping = () => {
  if (!props.text) return
  
  isTyping.value = true
  displayText.value = ''
  let index = 0
  
  typewriterInterval = setInterval(() => {
    if (index < props.text.length) {
      displayText.value += props.text[index]
      index++
    } else {
      isTyping.value = false
      clearInterval(typewriterInterval)
    }
  }, props.speed)
}

// 立即显示全部文本
const showAll = () => {
  displayText.value = props.text
  isTyping.value = false
  if (typewriterInterval) {
    clearInterval(typewriterInterval)
  }
}

// 监听 text 属性变化
watch(() => props.text, (newText) => {
  if (typewriterInterval) {
    clearInterval(typewriterInterval)
  }
  if (newText) {
    if (props.instant) {
      // 历史消息直接显示全部
      displayText.value = newText
      isTyping.value = false
    } else if (props.autoPlay) {
      startTyping()
    }
  }
}, { immediate: true })

// 在卸载时清理
onBeforeUnmount(() => {
  if (typewriterInterval) {
    clearInterval(typewriterInterval)
  }
})

// 暴露方法给父组件
defineExpose({
  startTyping,
  showAll
})
</script>

<style scoped>
.typewriter-container {
  display: inline-block;
  width: 100%;
}

.typewriter-text {
  font-family: inherit;
  word-wrap: break-word;
  white-space: pre-wrap;
  line-height: 1.6;
}

.cursor {
  display: inline-block;
  width: 1px;
  height: 1em;
  background-color: currentColor;
  margin-left: 2px;
  animation: blink 0.7s infinite;
}

@keyframes blink {
  0%, 49% {
    opacity: 1;
  }
  50%, 100% {
    opacity: 0;
  }
}
</style>
