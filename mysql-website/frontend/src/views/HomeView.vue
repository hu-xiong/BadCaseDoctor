<script setup lang="ts">
import { ref } from 'vue'
import HeroSection from '@/components/HeroSection.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import FeatureCard from '@/components/FeatureCard.vue'
import NewsCard from '@/components/NewsCard.vue'

const features = [
  {
    title: 'High Performance',
    description: 'MySQL delivers lightning-fast performance with advanced indexing, query optimization, and clustering capabilities.',
    icon: 'el-icon-data-line',
    link: '/products'
  },
  {
    title: 'Scalability & Flexibility',
    description: 'Scale from embedded applications to massive data warehouses with flexible deployment options.',
    icon: 'el-icon-connection',
    link: '/products'
  },
  {
    title: 'High Availability',
    description: 'Built-in replication, automatic failover, and backup solutions ensure your data is always available.',
    icon: 'el-icon-s-check',
    link: '/products'
  },
  {
    title: 'Security & Compliance',
    description: 'Enterprise-grade security features including encryption, authentication, and access control.',
    icon: 'el-icon-lock',
    link: '/products'
  },
  {
    title: 'ACID Compliance',
    description: 'Full transactional support with ACID properties ensures data integrity for critical applications.',
    icon: 'el-icon-document',
    link: '/products'
  },
  {
    title: 'Easy to Use',
    description: 'Intuitive tools like MySQL Workbench and comprehensive documentation make getting started simple.',
    icon: 'el-icon-magic-stick',
    link: '/products'
  }
]

const stats = [
  { value: '8.0+', label: 'Latest Version' },
  { value: '50M+', label: 'Installations Worldwide' },
  { value: '200K+', label: 'Downloads Per Day' },
  { value: '99.99%', label: 'Uptime Guarantee' }
]

const news = ref([
  {
    id: 1,
    title: 'MySQL 8.4 LTS Released',
    summary: 'The new Long Term Support release brings enhanced performance, new features, and extended support.',
    date: '2024-04-15',
    category: 'Release',
    image: 'https://picsum.photos/400/200'
  },
  {
    id: 2,
    title: 'MySQL Tech Talk Series',
    summary: 'Join our monthly webinars covering best practices, new features, and real-world use cases.',
    date: '2024-04-10',
    category: 'Event',
    image: 'https://picsum.photos/400/201'
  },
  {
    id: 3,
    title: 'MySQL Community Awards 2024',
    summary: 'Recognizing outstanding contributions from our global community of developers and contributors.',
    date: '2024-04-05',
    category: 'Community',
    image: 'https://picsum.photos/400/202'
  }
])

const cases = ref([
  {
    company: 'TechCorp',
    description: 'Leading e-commerce platform scales to handle 10M+ daily transactions with MySQL.',
    logo: 'TC'
  },
  {
    company: 'DataFlow Inc',
    description: 'Real-time analytics platform processes 1TB+ data daily using MySQL Cluster.',
    logo: 'DF'
  },
  {
    company: 'CloudFirst',
    description: 'SaaS provider serves 500K+ businesses with highly available MySQL infrastructure.',
    logo: 'CF'
  }
])
</script>

<template>
  <div class="home">
    <!-- Hero Section -->
    <HeroSection
      title="The World's Most Popular Open Source Database"
      subtitle="MySQL Enterprise Edition"
      description="Trusted by Fortune 100 companies worldwide. MySQL delivers unmatched performance, scalability, and reliability for your most critical applications."
      :primary-button="{ text: 'Download MySQL', link: '/downloads' }"
      :secondary-button="{ text: 'View Documentation', link: '/docs' }"
    />

    <!-- Stats Section -->
    <section class="stats-section">
      <div class="container">
        <div class="stats-grid">
          <div v-for="stat in stats" :key="stat.label" class="stat-item">
            <span class="stat-value">{{ stat.value }}</span>
            <span class="stat-label">{{ stat.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="section features-section">
      <div class="container">
        <SectionHeader
          title="Why Choose MySQL?"
          subtitle="Discover the features that make MySQL the preferred choice for developers and enterprises worldwide"
        />
        <div class="grid grid-3">
          <FeatureCard
            v-for="feature in features"
            :key="feature.title"
            :title="feature.title"
            :description="feature.description"
            :icon="feature.icon"
            :link="feature.link"
          />
        </div>
      </div>
    </section>

    <!-- Performance Section -->
    <section class="section performance-section">
      <div class="container">
        <div class="performance-content">
          <div class="performance-text">
            <SectionHeader
              title="Industry-Leading Performance"
              subtitle="Optimized for speed and efficiency"
              :centered="false"
            />
            <p class="performance-description">
              MySQL's advanced query optimizer, indexing mechanisms, and storage engine architecture deliver 
              exceptional performance for OLTP workloads. Our benchmarks show MySQL outperforming competitors 
              by up to 3x in standard transaction processing tests.
            </p>
            <ul class="performance-features">
              <li>Query optimization with cost-based optimizer</li>
              <li>Multi-threaded, parallel query execution</li>
              <li>Adaptive hash indexing for faster lookups</li>
              <li>Buffer pool caching for reduced I/O</li>
            </ul>
            <router-link to="/docs" class="btn btn-primary">
              Explore Performance Features
            </router-link>
          </div>
          <div class="performance-chart">
            <div class="chart-placeholder">
              <div class="chart-bar" style="height: 85%">
                <span>MySQL</span>
              </div>
              <div class="chart-bar" style="height: 72%">
                <span>Competitor A</span>
              </div>
              <div class="chart-bar" style="height: 68%">
                <span>Competitor B</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Customer Cases Section -->
    <section class="section cases-section">
      <div class="container">
        <SectionHeader
          title="Trusted by Industry Leaders"
          subtitle="See how companies around the world rely on MySQL for their critical infrastructure"
        />
        <div class="cases-grid">
          <div v-for="c in cases" :key="c.company" class="case-card card">
            <div class="case-logo">{{ c.logo }}</div>
            <h4 class="case-company">{{ c.company }}</h4>
            <p class="case-description">{{ c.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- News Section -->
    <section class="section news-section">
      <div class="container">
        <SectionHeader
          title="Latest News"
          subtitle="Stay up to date with MySQL releases, events, and community updates"
        />
        <div class="grid grid-3">
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
        <div class="news-footer">
          <router-link to="/news" class="btn btn-outline">
            View All News
          </router-link>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2 class="cta-title">Ready to Get Started?</h2>
          <p class="cta-description">
            Download MySQL Community Edition for free or explore our enterprise solutions for advanced features and support.
          </p>
          <div class="cta-buttons">
            <router-link to="/downloads" class="btn btn-secondary btn-large">
              Download Now
            </router-link>
            <router-link to="/contact" class="btn btn-outline-white btn-large">
              Contact Sales
            </router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.stats-section {
  background: var(--mysql-dark-blue);
  padding: 48px 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 32px;
  text-align: center;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-value {
  font-size: 36px;
  font-weight: 700;
  color: #ffffff;
}

.stat-label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.features-section {
  background: #ffffff;
}

.performance-section {
  background: var(--bg-light);
}

.performance-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 64px;
  align-items: center;
}

.performance-description {
  font-size: 16px;
  line-height: 1.8;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.performance-features {
  list-style: none;
  padding: 0;
  margin-bottom: 32px;
}

.performance-features li {
  padding: 8px 0;
  padding-left: 24px;
  position: relative;
  font-size: 15px;
  color: var(--text-secondary);
}

.performance-features li::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: var(--mysql-blue);
  font-weight: bold;
}

.performance-chart {
  background: #ffffff;
  padding: 32px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.chart-placeholder {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 300px;
  padding-top: 20px;
}

.chart-bar {
  width: 80px;
  background: linear-gradient(180deg, var(--mysql-blue), var(--mysql-dark-blue));
  border-radius: 8px 8px 0 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 500;
}

.cases-section {
  background: #ffffff;
}

.cases-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.case-card {
  text-align: center;
  padding: 32px;
}

.case-logo {
  width: 64px;
  height: 64px;
  background: var(--mysql-blue);
  color: #ffffff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  margin: 0 auto 16px;
}

.case-company {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.case-description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.news-section {
  background: var(--bg-light);
}

.news-footer {
  text-align: center;
  margin-top: 32px;
}

.cta-section {
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 80px 0;
  text-align: center;
}

.cta-content {
  max-width: 600px;
  margin: 0 auto;
}

.cta-title {
  font-size: 36px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 16px;
}

.cta-description {
  font-size: 18px;
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 32px;
}

.cta-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.btn-outline-white {
  border: 2px solid #ffffff;
  background: transparent;
  color: #ffffff;
}

.btn-outline-white:hover {
  background: #ffffff;
  color: var(--mysql-blue);
}

@media (max-width: 992px) {
  .performance-content {
    grid-template-columns: 1fr;
  }
  
  .cases-grid {
    grid-template-columns: 1fr;
  }
  
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .cta-buttons {
    flex-direction: column;
  }
}
</style>
