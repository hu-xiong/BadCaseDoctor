<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const goHome = () => {
  router.push('/')
}
</script>

<template>
  <div class="not-found-page">
    <div class="not-found-content">
      <div class="error-code">404</div>
      <h1>Page Not Found</h1>
      <p>Sorry, the page you are looking for does not exist.</p>
      <div class="actions">
        <button class="btn btn-primary" @click="goHome">
          Go to Homepage
        </button>
        <button class="btn btn-outline" @click="router.back()">
          Go Back
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-found-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  text-align: center;
  padding: 40px 20px;
}

.not-found-content {
  max-width: 500px;
}

.error-code {
  font-size: 120px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.2);
  line-height: 1;
  margin-bottom: 24px;
}

h1 {
  font-size: 36px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 16px;
}

p {
  font-size: 18px;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 32px;
}

.actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.btn {
  padding: 12px 32px;
  border-radius: 4px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: #ffffff;
  color: var(--mysql-blue);
  border: none;
}

.btn-primary:hover {
  background: #f0f0f0;
}

.btn-outline {
  background: transparent;
  color: #ffffff;
  border: 2px solid #ffffff;
}

.btn-outline:hover {
  background: #ffffff;
  color: var(--mysql-blue);
}

@media (max-width: 480px) {
  .error-code {
    font-size: 80px;
  }
  
  h1 {
    font-size: 28px;
  }
  
  .actions {
    flex-direction: column;
  }
}
</style>
