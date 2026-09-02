<template>
  <div class="payment-result success">
    <div class="result-card">
      <div class="icon">✓</div>
      <h1>{{ t('subscription.successTitle') }}</h1>
      <p>{{ t('subscription.successDesc') }}</p>
      <p v-if="creditsLoaded" class="credits-line">
        {{ t('subscription.successCredits', { n: credits }) }}
      </p>
      <p v-if="loadError" class="error-line">{{ loadError }}</p>
      <button class="back-btn" @click="$router.push('/subscription')">
        {{ t('subscription.successBack') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api.js'

const { t } = useI18n()
const route = useRoute()
const credits = ref(0)
const creditsLoaded = ref(false)
const loadError = ref('')

onMounted(async () => {
  try {
    const res = await api.get('/api/payment/credits')
    credits.value = Number(res.data?.credits ?? 0)
    creditsLoaded.value = true
  } catch (e) {
    loadError.value = t('subscription.successCreditsLoadFailed')
  }
  // session_id 仅用于排查；入账由 mock 同步或 Stripe webhook 完成
  if (route.query.session_id) {
    console.info('[payment] session_id=', route.query.session_id)
  }
})
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
  margin-bottom: 16px;
}

.credits-line {
  font-weight: 600;
  color: #2e7d32;
}

.error-line {
  color: #c62828;
  font-size: 14px;
}

.back-btn {
  margin-top: 12px;
  padding: 15px 40px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  cursor: pointer;
}
</style>
