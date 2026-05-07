<script setup lang="ts">
interface Props {
  title: string
  description: string
  icon?: string
  link?: string
}

defineProps<Props>()
</script>

<template>
  <div class="feature-card card">
    <div v-if="icon" class="feature-icon">
      <i :class="icon"></i>
    </div>
    <h3 class="feature-title">{{ title }}</h3>
    <p class="feature-description">{{ description }}</p>
    <router-link v-if="link" :to="link" class="feature-link">
      Learn more →
    </router-link>
  </div>
</template>

<style scoped>
.feature-card {
  text-align: center;
  padding: 32px 24px;
}

.feature-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-light-blue));
  border-radius: 16px;
  font-size: 28px;
  color: #ffffff;
}

.feature-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.feature-description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

.feature-link {
  font-size: 14px;
  font-weight: 500;
  color: var(--mysql-blue);
}

.feature-link:hover {
  color: var(--mysql-dark-blue);
}
</style>
