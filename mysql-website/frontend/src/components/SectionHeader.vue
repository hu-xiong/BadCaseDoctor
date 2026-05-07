<script setup lang="ts">
interface Props {
  title: string
  subtitle?: string
  centered?: boolean
}

withDefaults(defineProps<Props>(), {
  centered: true
})
</script>

<template>
  <div class="section-header" :class="{ 'text-center': centered }">
    <h2 class="section-title">{{ title }}</h2>
    <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
  </div>
</template>

<style scoped>
.section-header {
  margin-bottom: 48px;
}

.text-center {
  text-align: center;
}

.section-title {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.section-subtitle {
  font-size: 18px;
  color: var(--text-secondary);
  line-height: 1.6;
}

@media (max-width: 768px) {
  .section-title {
    font-size: 28px;
  }
  
  .section-subtitle {
    font-size: 16px;
  }
}
</style>
