<template>
  <div class="payment-result success">
    <div class="result-card">
      <div class="icon">✓</div>
      <h1>{{ t('subscription.successTitle') }}</h1>
      <p>{{ t('subscription.successDesc') }}</p>
      <button class="back-btn" @click="$router.push('/subscription')">
        {{ t('subscription.successBack') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<style scoped>
.payment-result {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.result-card {
  background: white;
  padding: 60px 80px;
  border-radius: 20px;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}

.icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: #4CAF50;
  color: white;
  font-size: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 30px;
}

h1 {
  color: #333;
  margin-bottom: 15px;
}

p {
  color: #666;
  margin-bottom: 30px;
}

.back-btn {
  padding: 15px 40px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  cursor: pointer;
}
</style>
