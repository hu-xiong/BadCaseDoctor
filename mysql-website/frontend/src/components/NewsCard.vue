<script setup lang="ts">
interface Props {
  title: string
  summary: string
  date: string
  category?: string
  image?: string
  link?: string
}

defineProps<Props>()
</script>

<template>
  <router-link :to="link || '/news'" class="news-card card">
    <div v-if="image" class="news-image">
      <img :src="image" :alt="title" />
    </div>
    <div class="news-content">
      <div class="news-meta">
        <span v-if="category" class="news-category">{{ category }}</span>
        <span class="news-date">{{ date }}</span>
      </div>
      <h3 class="news-title">{{ title }}</h3>
      <p class="news-summary">{{ summary }}</p>
    </div>
  </router-link>
</template>

<style scoped>
.news-card {
  display: block;
  padding: 0;
  overflow: hidden;
}

.news-image {
  height: 200px;
  overflow: hidden;
}

.news-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.news-card:hover .news-image img {
  transform: scale(1.05);
}

.news-content {
  padding: 20px;
}

.news-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 13px;
}

.news-category {
  background: var(--mysql-blue);
  color: #ffffff;
  padding: 4px 10px;
  border-radius: 4px;
}

.news-date {
  color: var(--text-secondary);
}

.news-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
  line-height: 1.4;
}

.news-summary {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
