<script setup lang="ts">
interface Props {
  title: string
  subtitle?: string
  description?: string
  primaryButton?: { text: string; link: string }
  secondaryButton?: { text: string; link: string }
}

defineProps<Props>()
</script>

<template>
  <section class="hero">
    <div class="hero-content">
      <h1 class="hero-title">{{ title }}</h1>
      <p v-if="subtitle" class="hero-subtitle">{{ subtitle }}</p>
      <p v-if="description" class="hero-description">{{ description }}</p>
      <div class="hero-actions">
        <router-link
          v-if="primaryButton"
          :to="primaryButton.link"
          class="btn btn-primary btn-large"
        >
          {{ primaryButton.text }}
        </router-link>
        <router-link
          v-if="secondaryButton"
          :to="secondaryButton.link"
          class="btn btn-outline btn-large"
        >
          {{ secondaryButton.text }}
        </router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  background: linear-gradient(135deg, var(--mysql-blue) 0%, var(--mysql-dark-blue) 100%);
  color: #ffffff;
  padding: 160px 24px 100px;
  text-align: center;
}

.hero-content {
  max-width: 800px;
  margin: 0 auto;
}

.hero-title {
  font-size: 48px;
  font-weight: 700;
  margin-bottom: 16px;
  line-height: 1.2;
}

.hero-subtitle {
  font-size: 24px;
  font-weight: 400;
  margin-bottom: 24px;
  opacity: 0.9;
}

.hero-description {
  font-size: 18px;
  line-height: 1.6;
  margin-bottom: 32px;
  opacity: 0.8;
}

.hero-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}

.btn-large {
  padding: 14px 32px;
  font-size: 16px;
}

.btn-outline {
  border: 2px solid #ffffff;
  background: transparent;
  color: #ffffff;
}

.btn-outline:hover {
  background: #ffffff;
  color: var(--mysql-blue);
}

@media (max-width: 768px) {
  .hero {
    padding: 120px 24px 64px;
  }
  
  .hero-title {
    font-size: 32px;
  }
  
  .hero-subtitle {
    font-size: 18px;
  }
  
  .hero-description {
    font-size: 16px;
  }
}
</style>
