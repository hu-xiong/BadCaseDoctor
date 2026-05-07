<script setup lang="ts">
const currentYear = new Date().getFullYear()

const footerLinks = {
  products: [
    { title: 'MySQL Enterprise', link: '/products/enterprise' },
    { title: 'MySQL Community', link: '/products/community' },
    { title: 'MySQL Cluster', link: '/products/cluster' },
    { title: 'MySQL Shell', link: '/products/shell' }
  ],
  downloads: [
    { title: 'MySQL Community Server', link: '/downloads' },
    { title: 'MySQL Cluster', link: '/downloads/cluster' },
    { title: 'MySQL Workbench', link: '/downloads/workbench' },
    { title: 'MySQL Router', link: '/downloads/router' }
  ],
  documentation: [
    { title: 'MySQL Manual', link: '/docs' },
    { title: 'MySQL Reference', link: '/docs/reference' },
    { title: 'API Documentation', link: '/docs/api' },
    { title: 'FAQs', link: '/docs/faq' }
  ],
  community: [
    { title: 'Forums', link: '/community' },
    { title: 'Blogs', link: '/news' },
    { title: 'Events', link: '/events' },
    { title: 'Contribute', link: '/contribute' }
  ],
  about: [
    { title: 'About MySQL', link: '/about' },
    { title: 'Contact Us', link: '/contact' },
    { title: 'Privacy Policy', link: '/privacy' },
    { title: 'Terms of Use', link: '/terms' }
  ]
}
</script>

<template>
  <footer class="footer">
    <div class="footer-container">
      <div class="footer-grid">
        <div class="footer-section">
          <h4 class="footer-title">Products</h4>
          <ul class="footer-links">
            <li v-for="link in footerLinks.products" :key="link.link">
              <router-link :to="link.link">{{ link.title }}</router-link>
            </li>
          </ul>
        </div>

        <div class="footer-section">
          <h4 class="footer-title">Downloads</h4>
          <ul class="footer-links">
            <li v-for="link in footerLinks.downloads" :key="link.link">
              <router-link :to="link.link">{{ link.title }}</router-link>
            </li>
          </ul>
        </div>

        <div class="footer-section">
          <h4 class="footer-title">Documentation</h4>
          <ul class="footer-links">
            <li v-for="link in footerLinks.documentation" :key="link.link">
              <router-link :to="link.link">{{ link.title }}</router-link>
            </li>
          </ul>
        </div>

        <div class="footer-section">
          <h4 class="footer-title">Community</h4>
          <ul class="footer-links">
            <li v-for="link in footerLinks.community" :key="link.link">
              <router-link :to="link.link">{{ link.title }}</router-link>
            </li>
          </ul>
        </div>

        <div class="footer-section">
          <h4 class="footer-title">About</h4>
          <ul class="footer-links">
            <li v-for="link in footerLinks.about" :key="link.link">
              <router-link :to="link.link">{{ link.title }}</router-link>
            </li>
          </ul>
        </div>
      </div>

      <div class="footer-bottom">
        <div class="footer-logo">
          <img src="/mysql-logo.svg" alt="MySQL" />
        </div>
        <p class="copyright">
          Copyright © {{ currentYear }} Oracle, MySQL AB. All rights reserved.
        </p>
        <div class="social-links">
          <a href="https://twitter.com/mysql" target="_blank" rel="noopener" class="social-link">
            Twitter
          </a>
          <a href="https://github.com/mysql" target="_blank" rel="noopener" class="social-link">
            GitHub
          </a>
          <a href="https://www.facebook.com/MySQL" target="_blank" rel="noopener" class="social-link">
            Facebook
          </a>
        </div>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.footer {
  background: #2c2c2c;
  color: #ffffff;
  padding: 64px 0 24px;
}

.footer-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

.footer-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 32px;
  margin-bottom: 48px;
}

.footer-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 20px;
  color: #ffffff;
}

.footer-links {
  list-style: none;
  padding: 0;
  margin: 0;
}

.footer-links li {
  margin-bottom: 12px;
}

.footer-links a {
  color: #a0a0a0;
  font-size: 14px;
  transition: color 0.3s;
}

.footer-links a:hover {
  color: #ffffff;
}

.footer-bottom {
  border-top: 1px solid #404040;
  padding-top: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.footer-logo img {
  height: 28px;
  filter: brightness(0) invert(1);
}

.copyright {
  font-size: 13px;
  color: #808080;
}

.social-links {
  display: flex;
  gap: 24px;
}

.social-link {
  color: #a0a0a0;
  font-size: 14px;
  transition: color 0.3s;
}

.social-link:hover {
  color: #ffffff;
}

@media (max-width: 992px) {
  .footer-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .footer-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .footer-bottom {
    flex-direction: column;
    text-align: center;
  }
}
</style>
