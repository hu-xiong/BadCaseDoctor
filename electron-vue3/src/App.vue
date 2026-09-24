<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'

const currentTime = ref('')
const clickCount = ref(0)
const router = useRouter()
let offMenuAction = null

const updateTime = () => {
  currentTime.value = new Date().toLocaleString('zh-CN')
}

const testClick = () => {
  clickCount.value++
}

onMounted(() => {
  updateTime()
  setInterval(updateTime, 1000)

  // 原生菜单动作 → 页面跳转
  offMenuAction = window.electronMenu?.onAction?.((action) => {
    if (action === 'new-project') {
      router.push('/new-project')
    } else if (action === 'import-excel') {
      router.push('/import-excel')
    }
  })
})

onBeforeUnmount(() => {
  offMenuAction?.()
})
</script>

<template>
  <div id="app">
    <router-view />
  </div>
</template>

<style>
#app {
  font-family: Arial, sans-serif;
  min-height: 100vh;
  background: #f5f5f5;
}
</style>
