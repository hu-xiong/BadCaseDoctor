<template>
  <div class="left-search-panel">
    <GlobalSearch
      :projectId="projectId"
      :showClose="false"
      @close="emit('close')"
      @select-card="onSelect"
      @select-detail="onSelect"
    />
  </div>
</template>

<script setup>
import GlobalSearch from '../GlobalSearch.vue'

defineProps({
  projectId: { type: [String, Number, null], default: null }
})

const emit = defineEmits(['close', 'select'])

const onSelect = (result) => {
  emit('select', result)
}
</script>

<style scoped>
.left-search-panel {
  height: 100%;
  width: 100%;
  overflow: auto;
}
</style>

