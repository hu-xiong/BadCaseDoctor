<template>
  <div class="plugin-example">
    <div class="title">示例插件</div>
    <div class="meta">projectId: {{ projectId }} | selectedPlan: {{ selectedPlan }}</div>
    <button class="btn" @click="emit('action', { type: 'openSearch' })">打开搜索</button>
  </div>
</template>

<script setup>
const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  selectedPlan: { type: [String, Number, null], default: null },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['action'])
</script>

<style scoped>
.plugin-example { padding: 12px; }
.title { font-weight: 600; margin-bottom: 8px; }
.meta { color: #666; margin-bottom: 10px; }
.btn { padding: 6px 10px; border: 1px solid #ddd; background: #fff; border-radius: 6px; cursor: pointer; }
</style>

