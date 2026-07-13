<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { formatDate } from '@/utils/format'
import BreadCrumb from '@/components/BreadCrumb.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getNewsDetail, getLatestNews, type NewsItem } from '@/api/news'

const route = useRoute()
const loading = ref(true)
const article = ref<NewsItem | null>(null)
const relatedNews = ref<NewsItem[]>([])

const breadcrumbs = computed(() => [
  { title: 'News', path: '/news' },
  { title: article.value?.title || 'Loading...' }
])

onMounted(async () => {
  loading.value = true
  try {
    const id = route.params.id as string
    article.value = await getNewsDetail(id)
    const latest = await getLatestNews(4)
    relatedNews.value = latest.filter(item => String(item.id) !== id).slice(0, 3)
  } catch {
    article.value = null
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="news-detail-page">
    <LoadingSpinner v-if="loading" />
    <template v-else-if="article">
      <div class="page-hero-small">
        <div class="container">
          <BreadCrumb :items="breadcrumbs" />
          <span class="news-category">News</span>
          <h1 class="article-title">{{ article.title }}</h1>
          <div class="article-meta">
            <span class="date">{{ formatDate(article.created_at, 'long') }}</span>
          </div>
        </div>
      </div>

      <div class="article-body">
        <div class="container">
          <div class="article-layout">
            <article class="article-content card">
              <img
                v-if="article.image_url"
                :src="article.image_url"
                :alt="article.title"
                class="hero-image"
              />
              <p v-if="article.summary" class="article-summary">{{ article.summary }}</p>
              <div class="markdown-body">{{ article.content }}</div>
            </article>

            <aside v-if="relatedNews.length" class="related-news">
              <h3>Related News</h3>
              <ul>
                <li v-for="item in relatedNews" :key="item.id">
                  <router-link :to="`/news/${item.id}`">
                    {{ item.title }}
                  </router-link>
                  <span class="related-date">{{ formatDate(item.created_at) }}</span>
                </li>
              </ul>
            </aside>
          </div>
        </div>
      </div>
    </template>
    <el-empty v-else description="News article not found" />
  </div>
</template>

<style scoped>
.news-detail-page {
  padding-top: 64px;
  min-height: calc(100vh - 64px);
}

.page-hero-small {
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 48px 0;
  color: #ffffff;
}

.news-category {
  display: inline-block;
  background: rgba(255, 255, 255, 0.2);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  margin-bottom: 16px;
}

.article-title {
  font-size: 36px;
  font-weight: 700;
  margin-bottom: 16px;
  line-height: 1.3;
}

.article-meta {
  font-size: 14px;
  opacity: 0.9;
}

.article-body {
  padding: 48px 0;
  background: var(--bg-light);
}

.article-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 32px;
}

.article-content {
  padding: 32px;
}

.hero-image {
  width: 100%;
  max-height: 360px;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 24px;
}

.article-summary {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 24px;
  line-height: 1.7;
}

.markdown-body {
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.related-news {
  background: #ffffff;
  padding: 24px;
  border-radius: 8px;
  height: fit-content;
}

.related-news h3 {
  font-size: 16px;
  margin-bottom: 16px;
}

.related-news ul {
  list-style: none;
  padding: 0;
}

.related-news li {
  margin-bottom: 16px;
}

.related-news a {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
}

.related-date {
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 992px) {
  .article-layout {
    grid-template-columns: 1fr;
  }
}
</style>
