<script setup lang="ts">
interface Props {
  fullscreen?: boolean
  text?: string
}

withDefaults(defineProps<Props>(), {
  fullscreen: false,
  text: 'Loading...'
})
</script>

<template>
  <div v-if="!fullscreen" class="loading-container">
    <div class="loading-spinner">
      <div class="spinner"></div>
      <p class="loading-text">{{ text }}</p>
    </div>
  </div>
</template>

<style scoped>
.loading-container {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.loading-spinner {
  text-align: center;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--bg-light);
  border-top-color: var(--mysql-blue);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-text {
  font-size: 14px;
  color: var(--text-secondary);
}
</style>
