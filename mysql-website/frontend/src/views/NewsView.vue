<script setup lang="ts">
import { ref, computed } from 'vue'
import SectionHeader from '@/components/SectionHeader.vue'
import NewsCard from '@/components/NewsCard.vue'

const selectedCategory = ref('')

const categories = [
  { value: '', label: 'All News' },
  { value: 'release', label: 'Releases' },
  { value: 'event', label: 'Events' },
  { value: 'community', label: 'Community' },
  { value: 'blog', label: 'Blog Posts' }
]

const news = ref([
  {
    id: 1,
    title: 'MySQL 8.4 LTS Released',
    summary: 'The new Long Term Support release brings enhanced performance, new features, and 8 years of support for enterprise deployments.',
    date: '2024-04-15',
    category: 'Release',
    image: 'https://picsum.photos/seed/mysql1/400/200'
  },
  {
    id: 2,
    title: 'MySQL Tech Talk Series - April',
    summary: 'Join our monthly webinars covering best practices, new features, and real-world use cases from MySQL experts.',
    date: '2024-04-10',
    category: 'Event',
    image: 'https://picsum.photos/seed/mysql2/400/201'
  },
  {
    id: 3,
    title: 'MySQL Community Awards 2024',
    summary: 'Recognizing outstanding contributions from our global community of developers, DBAs, and contributors.',
    date: '2024-04-05',
    category: 'Community',
    image: 'https://picsum.photos/seed/mysql3/400/202'
  },
  {
    id: 4,
    title: 'Performance Tuning Best Practices',
    summary: 'Learn the top 10 tips for optimizing MySQL performance in production environments from our engineering team.',
    date: '2024-03-28',
    category: 'Blog',
    image: 'https://picsum.photos/seed/mysql4/400/203'
  },
  {
    id: 5,
    title: 'MySQL Security Advisory',
    summary: 'Important security updates and best practices for maintaining a secure MySQL deployment.',
    date: '2024-03-20',
    category: 'Release',
    image: 'https://picsum.photos/seed/mysql5/400/204'
  },
  {
    id: 6,
    title: 'MySQL User Conference 2024',
    summary: 'Save the date for the annual MySQL User Conference featuring hands-on workshops and expert sessions.',
    date: '2024-03-15',
    category: 'Event',
    image: 'https://picsum.photos/seed/mysql6/400/205'
  }
])

const filteredNews = computed(() => {
  if (!selectedCategory.value) return news.value
  return news.value.filter(n => n.category.toLowerCase() === selectedCategory.value)
})
</script>

<template>
  <div class="news-page">
    <!-- Hero -->
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
        <!-- Category Filter -->
        <div class="category-filter">
          <el-radio-group v-model="selectedCategory" size="large">
            <el-radio-button
              v-for="cat in categories"
              :key="cat.value"
              :value="cat.value"
            >
              {{ cat.label }}
            </el-radio-button>
          </el-radio-group>
        </div>

        <!-- Featured News -->
        <div v-if="!selectedCategory" class="featured-section">
          <div class="featured-card card">
            <div class="featured-image">
              <img :src="news[0].image" :alt="news[0].title" />
              <span class="featured-badge">Featured</span>
            </div>
            <div class="featured-content">
              <span class="news-category">{{ news[0].category }}</span>
              <h2 class="featured-title">{{ news[0].title }}</h2>
              <p class="featured-summary">{{ news[0].summary }}</p>
              <div class="featured-meta">
                <span class="news-date">{{ news[0].date }}</span>
                <router-link :to="`/news/${news[0].id}`" class="read-more">
                  Read More →
                </router-link>
              </div>
            </div>
          </div>
        </div>

        <!-- News Grid -->
        <div class="news-grid">
          <NewsCard
            v-for="item in filteredNews"
            :key="item.id"
            :title="item.title"
            :summary="item.summary"
            :date="item.date"
            :category="item.category"
            :image="item.image"
            :link="`/news/${item.id}`"
          />
        </div>

        <!-- Load More -->
        <div class="load-more">
          <el-button size="large" plain>Load More</el-button>
        </div>
      </div>
    </section>

    <!-- Newsletter Section -->
    <section class="newsletter-section">
      <div class="container">
        <div class="newsletter-content">
          <h2>Stay Updated</h2>
          <p>Subscribe to our newsletter for the latest MySQL news and updates.</p>
          <el-input
            placeholder="Enter your email"
            size="large"
            class="newsletter-input"
          >
            <template #append>
              <el-button>Subscribe</el-button>
            </template>
          </el-input>
        </div>
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
  padding: 48px 0;
  background: var(--bg-light);
}

.category-filter {
  display: flex;
  justify-content: center;
  margin-bottom: 48px;
}

.featured-section {
  margin-bottom: 48px;
}

.featured-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 0;
  overflow: hidden;
}

.featured-image {
  position: relative;
  height: 400px;
}

.featured-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.featured-badge {
  position: absolute;
  top: 20px;
  left: 20px;
  background: var(--mysql-orange);
  color: #ffffff;
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.featured-content {
  padding: 48px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.news-category {
  display: inline-block;
  background: var(--mysql-blue);
  color: #ffffff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
  width: fit-content;
}

.featured-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 16px;
  color: var(--text-primary);
  line-height: 1.3;
}

.featured-summary {
  font-size: 16px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: 24px;
}

.featured-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.news-date {
  font-size: 14px;
  color: var(--text-secondary);
}

.read-more {
  font-size: 14px;
  font-weight: 600;
  color: var(--mysql-blue);
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.load-more {
  text-align: center;
  margin-top: 48px;
}

.newsletter-section {
  background: #2c2c2c;
  padding: 64px 0;
}

.newsletter-content {
  text-align: center;
  max-width: 500px;
  margin: 0 auto;
}

.newsletter-content h2 {
  font-size: 28px;
  color: #ffffff;
  margin-bottom: 12px;
}

.newsletter-content p {
  color: #a0a0a0;
  margin-bottom: 24px;
}

.newsletter-input {
  width: 100%;
}

@media (max-width: 992px) {
  .featured-card {
    grid-template-columns: 1fr;
  }
  
  .featured-image {
    height: 250px;
  }
  
  .featured-content {
    padding: 24px;
  }
  
  .news-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .news-grid {
    grid-template-columns: 1fr;
  }
}
</style>
