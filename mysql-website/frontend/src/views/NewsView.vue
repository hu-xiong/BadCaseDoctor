<script setup lang="ts">
import { ref, onMounted } from 'vue'
import SectionHeader from '@/components/SectionHeader.vue'
import NewsCard from '@/components/NewsCard.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getNews, type NewsItem } from '@/api/news'
import { formatDate } from '@/utils/format'

const loading = ref(true)
const news = ref<Array<{
  id: number
  title: string
  summary: string
  date: string
  category: string
  image: string
}>>([])

onMounted(async () => {
  loading.value = true
  try {
    const data = await getNews({ page: 1, page_size: 20 })
    news.value = data.list.map((item: NewsItem) => ({
      id: item.id,
      title: item.title,
      summary: item.summary,
      date: formatDate(item.created_at),
      category: 'News',
      image: item.image_url || `https://picsum.photos/seed/mysql${item.id}/400/200`
    }))
  } catch {
    news.value = []
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="news-page">
    <section class="page-hero">
      <div class="container">
        <h1 class="page-title">MySQL News & Updates</h1>
        <p class="page-subtitle">
          Stay up to date with the latest MySQL releases, events, and community news
        </p>
      </div>
    </section>

    <section class="news-content">
      <div class="container">
        <SectionHeader
          title="Latest News"
          subtitle="Official announcements and updates from the MySQL team"
        />
        <LoadingSpinner v-if="loading" />
        <div v-else-if="news.length" class="news-grid">
          <NewsCard
            v-for="item in news"
            :key="item.id"
            :title="item.title"
            :summary="item.summary"
            :date="item.date"
            :category="item.category"
            :image="item.image"
            :link="`/news/${item.id}`"
          />
        </div>
        <el-empty v-else description="No news available" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.news-page {
  padding-top: 64px;
}

.page-hero {
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 80px 0;
  text-align: center;
  color: #ffffff;
}

.page-title {
  font-size: 42px;
  font-weight: 700;
  margin-bottom: 16px;
}

.page-subtitle {
  font-size: 18px;
  opacity: 0.9;
}

.news-content {
  padding: 64px 0;
  background: var(--bg-light);
  min-height: 400px;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

@media (max-width: 992px) {
  .news-grid {
    grid-template-columns: 1fr;
  }
}
</style>
