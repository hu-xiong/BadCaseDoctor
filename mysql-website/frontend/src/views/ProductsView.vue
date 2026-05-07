<script setup lang="ts">
import { ref } from 'vue'
import SectionHeader from '@/components/SectionHeader.vue'
import FeatureCard from '@/components/FeatureCard.vue'

const products = [
  {
    name: 'MySQL Community Edition',
    description: 'Free, open source database for developers and small teams',
    features: [
      'ACID transactions',
      'MVCC architecture',
      'InnoDB storage engine',
      'Full-text search',
      'Replication support'
    ],
    price: 'Free',
    highlight: false
  },
  {
    name: 'MySQL Enterprise Edition',
    description: 'Commercial edition with advanced features and support',
    features: [
      'Everything in Community',
      'Advanced security features',
      'Automated backup & recovery',
      'Enterprise monitoring',
      '24/7 premium support'
    ],
    price: 'Contact Sales',
    highlight: true
  },
  {
    name: 'MySQL Cluster',
    description: 'Distributed database for high availability and scalability',
    features: [
      'Real-time performance',
      'Auto-sharding',
      'Geographic replication',
      '99.999% availability',
      'In-memory computing'
    ],
    price: 'Contact Sales',
    highlight: false
  }
]

const activeProduct = ref(0)
</script>

<template>
  <div class="products-page">
    <!-- Hero -->
    <section class="page-hero">
      <div class="container">
        <h1 class="page-title">MySQL Products</h1>
        <p class="page-subtitle">
          Choose the right MySQL edition for your needs
        </p>
      </div>
    </section>

    <!-- Product Comparison -->
    <section class="products-section">
      <div class="container">
        <SectionHeader
          title="Compare Editions"
          subtitle="Find the perfect MySQL solution for your project"
        />
        
        <div class="products-grid">
          <div
            v-for="(product, index) in products"
            :key="product.name"
            class="product-card card"
            :class="{ 'product-highlight': product.highlight }"
          >
            <div v-if="product.highlight" class="popular-badge">Most Popular</div>
            <h3 class="product-name">{{ product.name }}</h3>
            <p class="product-description">{{ product.description }}</p>
            <div class="product-price">{{ product.price }}</div>
            
            <ul class="feature-list">
              <li v-for="feature in product.features" :key="feature">
                <i class="el-icon-check"></i>
                {{ feature }}
              </li>
            </ul>
            
            <router-link
              :to="product.highlight ? '/downloads' : '/downloads'"
              class="btn"
              :class="product.highlight ? 'btn-primary' : 'btn-outline'"
            >
              {{ product.price === 'Free' ? 'Download Free' : 'Get Started' }}
            </router-link>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="features-section">
      <div class="container">
        <SectionHeader
          title="Why MySQL?"
          subtitle="Industry-leading features trusted by millions"
        />
        
        <div class="grid grid-3">
          <FeatureCard
            title="High Performance"
            description="Optimized query processing with advanced indexing and caching mechanisms."
            icon="el-icon-lightning"
            link="/docs"
          />
          <FeatureCard
            title="Scalability"
            description="From single-server to distributed cloud deployments, MySQL scales seamlessly."
            icon="el-icon-connection"
            link="/docs"
          />
          <FeatureCard
            title="Reliability"
            description="ACID-compliant transactions ensure data integrity for critical applications."
            icon="el-icon-s-finance"
            link="/docs"
          />
          <FeatureCard
            title="Security"
            description="Enterprise-grade security with encryption, authentication, and access control."
            icon="el-icon-lock"
            link="/docs"
          />
          <FeatureCard
            title="Ease of Use"
            description="Intuitive tools and comprehensive documentation for quick onboarding."
            icon="el-icon-magic-stick"
            link="/docs"
          />
          <FeatureCard
            title="Open Source"
            description="100% open source with no vendor lock-in and active community support."
            icon="el-icon-open"
            link="/docs"
          />
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2>Ready to Get Started?</h2>
          <p>Download MySQL Community Edition for free or contact our sales team for enterprise solutions.</p>
          <div class="cta-buttons">
            <router-link to="/downloads" class="btn btn-secondary btn-large">
              Download Free
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
.products-page {
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

.products-section {
  padding: 80px 0;
  background: #ffffff;
}

.products-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
  margin-top: 48px;
}

.product-card {
  padding: 32px;
  text-align: center;
  position: relative;
}

.product-highlight {
  border: 2px solid var(--mysql-blue);
  transform: scale(1.05);
}

.popular-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--mysql-orange);
  color: #ffffff;
  padding: 4px 16px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.product-name {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.product-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
  min-height: 42px;
}

.product-price {
  font-size: 28px;
  font-weight: 700;
  color: var(--mysql-blue);
  margin-bottom: 24px;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0 0 24px;
  text-align: left;
}

.feature-list li {
  padding: 8px 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.feature-list li i {
  color: var(--mysql-blue);
  margin-right: 8px;
}

.feature-list .btn {
  width: 100%;
  text-align: center;
  margin-top: 16px;
}

.features-section {
  padding: 80px 0;
  background: var(--bg-light);
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

.cta-content h2 {
  font-size: 32px;
  color: #ffffff;
  margin-bottom: 16px;
}

.cta-content p {
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
  .products-grid {
    grid-template-columns: 1fr;
  }
  
  .product-highlight {
    transform: none;
  }
  
  .cta-buttons {
    flex-direction: column;
  }
}
</style>
