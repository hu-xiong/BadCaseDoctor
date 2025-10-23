<script setup>
import { ref, onMounted } from 'vue'

const currentTime = ref('')
const clickCount = ref(0)

const updateTime = () => {
  currentTime.value = new Date().toLocaleString('zh-CN')
}

const testClick = () => {
  clickCount.value++
}

onMounted(() => {
  updateTime()
  setInterval(updateTime, 1000)
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
