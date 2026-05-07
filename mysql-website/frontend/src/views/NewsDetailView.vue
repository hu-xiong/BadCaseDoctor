<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { formatDate } from '@/utils/format'
import BreadCrumb from '@/components/BreadCrumb.vue'

const route = useRoute()
const newsId = route.params.id as string

const article = ref({
  id: newsId,
  title: 'MySQL 8.4 LTS Released',
  content: `
# MySQL 8.4 LTS Released

We are excited to announce the release of MySQL 8.4.0, our new Long Term Support (LTS) version!

## What's New

### Performance Improvements
- Enhanced query optimizer for better execution plans
- Improved InnoDB storage engine performance
- Better memory management and caching

### New Features
- JSON table functions
- Window functions improvements
- Enhanced CTEs (Common Table Expressions)

### Security Updates
- Stronger password validation
- Improved authentication plugins
- Enhanced encryption capabilities

## Upgrade Notes

Please review the upgrade notes before upgrading from previous versions. Full documentation is available in our documentation portal.

## Download Now

You can download MySQL 8.4.0 from our [downloads page](/downloads).

---

*MySQL Team*
  `,
  author: 'MySQL Team',
  publishDate: '2024-04-15',
  category: 'Release',
  imageUrl: 'https://picsum.photos/seed/mysql84/1200/400',
  relatedNews: [
    { id: '2', title: 'MySQL Tech Talk Series', date: '2024-04-10' },
    { id: '3', title: 'Community Awards 2024', date: '2024-04-05' }
  ]
})

const breadcrumbs = [
  { title: 'News', path: '/news' },
  { title: article.value.category },
  { title: article.value.title }
]

onMounted(() => {
  // Fetch news detail from API
})
</script>

<template>
  <div class="news-detail-page">
    <div class="page-hero-small">
      <div class="container">
        <BreadCrumb :items="breadcrumbs" />
        <span class="news-category">{{ article.category }}</span>
        <h1 class="article-title">{{ article.title }}</h1>
        <div class="article-meta">
          <span class="author">By {{ article.author }}</span>
          <span class="date">{{ formatDate(article.publishDate, 'long') }}</span>
        </div>
      </div>
    </div>

    <div class="article-content">
      <div class="container">
        <div class="content-layout">
          <article class="main-content">
            <img v-if="article.imageUrl" :src="article.imageUrl" :alt="article.title" class="featured-image" />
            <div class="markdown-body" v-html="article.content"></div>
            
            <div class="share-section">
              <h4>Share this article</h4>
              <div class="share-buttons">
                <el-button size="small">Twitter</el-button>
                <el-button size="small">LinkedIn</el-button>
                <el-button size="small">Facebook</el-button>
              </div>
            </div>
          </article>

          <aside class="sidebar">
            <div class="sidebar-card card">
              <h3>Related Articles</h3>
              <ul class="related-list">
                <li v-for="item in article.relatedNews" :key="item.id">
                  <router-link :to="`/news/${item.id}`">
                    <span class="related-title">{{ item.title }}</span>
                    <span class="related-date">{{ formatDate(item.date) }}</span>
                  </router-link>
                </li>
              </ul>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.news-detail-page {
  padding-top: 64px;
}

.page-hero-small {
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 48px 0;
  color: #ffffff;
}

.page-hero-small :deep(.breadcrumb) {
  margin-bottom: 16px;
}

.page-hero-small :deep(.el-breadcrumb__inner) {
  color: rgba(255, 255, 255, 0.7);
}

.page-hero-small :deep(.el-breadcrumb__inner a) {
  color: rgba(255, 255, 255, 0.7);
}

.news-category {
  display: inline-block;
  background: var(--mysql-orange);
  color: #ffffff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
}

.article-title {
  font-size: 36px;
  font-weight: 700;
  margin-bottom: 16px;
  line-height: 1.3;
}

.article-meta {
  display: flex;
  gap: 16px;
  font-size: 14px;
  opacity: 0.9;
}

.article-content {
  padding: 48px 0;
  background: var(--bg-light);
}

.content-layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 32px;
}

.main-content {
  background: #ffffff;
  padding: 32px;
  border-radius: 8px;
}

.featured-image {
  width: 100%;
  border-radius: 8px;
  margin-bottom: 24px;
}

.markdown-body {
  line-height: 1.8;
}

.markdown-body :deep(h1) {
  font-size: 28px;
  font-weight: 700;
  margin: 32px 0 16px;
}

.markdown-body :deep(h2) {
  font-size: 22px;
  font-weight: 600;
  margin: 28px 0 12px;
}

.markdown-body :deep(p) {
  margin-bottom: 16px;
  color: var(--text-secondary);
}

.share-section {
  margin-top: 48px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.share-section h4 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.share-buttons {
  display: flex;
  gap: 8px;
}

.sidebar-card {
  padding: 20px;
}

.sidebar-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.related-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.related-list li {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);
}

.related-list li:last-child {
  border-bottom: none;
}

.related-list a {
  display: block;
}

.related-title {
  display: block;
  color: var(--mysql-blue);
  font-size: 14px;
  margin-bottom: 4px;
}

.related-date {
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 992px) {
  .content-layout {
    grid-template-columns: 1fr;
  }
  
  .article-title {
    font-size: 28px;
  }
}
</style>
