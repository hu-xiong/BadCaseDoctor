<template>
  <div class="subscription-page">
    <div class="header">
      <h1>{{ t('subscription.title') }}</h1>
      <p class="subtitle">{{ t('subscription.subtitle') }}</p>
      <div class="credits-info" v-if="userCredits !== null">
        <span class="credits-label">{{ t('subscription.currentCredits') }}:</span>
        <span class="credits-value">{{ userCredits }}</span>
      </div>
      <p v-if="activeProvider === 'mock'" class="mock-hint">{{ t('subscription.mockHint') }}</p>
    </div>

    <div class="plans-container">
      <div 
        v-for="plan in plans" 
        :key="plan.id"
        class="plan-card"
        :class="{ 'popular': plan.id === 'professional' }"
      >
        <div class="popular-badge" v-if="plan.id === 'professional'">{{ t('subscription.mostPopular') }}</div>
        <h2 class="plan-name">{{ plan.name }}</h2>
        <div class="plan-price">
          <span class="currency">{{ plan.currency === 'CNY' ? '¥' : '$' }}</span>
          <span class="amount">{{ plan.price }}</span>
        </div>
        <div class="plan-credits">
          <span class="credits-number">{{ plan.credits }}</span>
          <span class="credits-text">{{ creditsUnit }}</span>
        </div>
        <p class="plan-description">{{ plan.description }}</p>
        <button 
          class="subscribe-btn"
          :class="{ 'loading': loadingPlan === plan.id }"
          @click="handleSubscribe(plan.id)"
          :disabled="loadingPlan !== null"
        >
          <span v-if="loadingPlan === plan.id">{{ t('subscription.processing') }}</span>
          <span v-else>{{ t('subscription.getStarted') }}</span>
        </button>
      </div>
    </div>

    <div class="features-section">
      <h3>{{ t('subscription.featuresTitle') }}</h3>
      <ul class="features-list">
        <li>{{ t('subscription.feature1') }}</li>
        <li>{{ t('subscription.feature2') }}</li>
        <li>{{ t('subscription.feature3') }}</li>
        <li>{{ t('subscription.feature4') }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const router = useRouter()

const plans = ref([])
const userCredits = ref(null)
const loadingPlan = ref(null)
const activeProvider = ref('stripe')

const creditsUnit = computed(() => {
  const cny = plans.value.some((p) => p.currency === 'CNY') || ['mock', 'wechat', 'alipay'].includes(activeProvider.value)
  return cny ? t('subscription.creditsUnit') : t('subscription.creditsUnitEn')
})

const fetchPlans = async () => {
  try {
    const res = await api.get('/api/payment/plans')
    plans.value = res.data.plans || []
    if (res.data.provider) activeProvider.value = res.data.provider
  } catch (error) {
    console.error('获取计划失败:', error)
  }
}

const fetchCredits = async () => {
  try {
    const res = await api.get('/api/payment/credits')
    userCredits.value = res.data.credits
  } catch (error) {
    console.error('获取额度失败:', error)
  }
}

const handleSubscribe = async (planId) => {
  loadingPlan.value = planId
  try {
    const res = await api.post('/api/payment/create-checkout', {
      plan_id: planId,
      provider: activeProvider.value
    })
    const data = res.data || {}
    if (data.provider === 'mock' && data.status === 'completed') {
      await fetchCredits()
      router.push({ path: '/payment/success', query: { session_id: data.session_id } })
      return
    }
    if (data.checkout_url) {
      window.location.href = data.checkout_url
      return
    }
    alert(data.error || data.hint || t('subscription.providerNotReady'))
  } catch (error) {
    console.error('创建支付失败:', error)
    const msg =
      error?.response?.data?.error ||
      error?.response?.data?.hint ||
      t('subscription.payFailed')
    alert(msg)
  } finally {
    loadingPlan.value = null
  }
}

onMounted(() => {
  fetchPlans()
  fetchCredits()
})
</script>

<style scoped>
.subscription-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 60px 20px;
}

.header {
  text-align: center;
  color: white;
  margin-bottom: 50px;
}

.header h1 {
  font-size: 42px;
  font-weight: 700;
  margin-bottom: 10px;
}

.subtitle {
  opacity: 0.9;
  margin-bottom: 16px;
}

.mock-hint {
  margin-top: 12px;
  font-size: 14px;
  opacity: 0.85;
}

.credits-info {
  margin-top: 20px;
  font-size: 18px;
}

.credits-label {
  opacity: 0.85;
  margin-right: 8px;
}

.credits-value {
  font-weight: 700;
}

.plans-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 24px;
  max-width: 1100px;
  margin: 0 auto 48px;
}

.plan-card {
  background: white;
  border-radius: 16px;
  padding: 28px 22px;
  position: relative;
  box-shadow: 0 12px 40px rgba(0,0,0,0.15);
}

.plan-card.popular {
  transform: translateY(-6px);
  box-shadow: 0 18px 48px rgba(0,0,0,0.22);
}

.popular-badge {
  position: absolute;
  top: -12px;
  right: 16px;
  background: #ff9800;
  color: white;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
}

.plan-name {
  font-size: 22px;
  margin-bottom: 12px;
}

.plan-price {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 12px;
}

.currency {
  font-size: 22px;
  color: #667eea;
}

.amount {
  font-size: 40px;
  font-weight: 700;
  color: #333;
}

.plan-credits {
  margin-bottom: 12px;
}

.credits-number {
  font-size: 28px;
  font-weight: 700;
  margin-right: 6px;
}

.credits-text {
  color: #666;
}

.plan-description {
  color: #666;
  min-height: 40px;
  margin-bottom: 20px;
}

.subscribe-btn {
  width: 100%;
  border: none;
  border-radius: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  cursor: pointer;
}

.subscribe-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.features-section {
  max-width: 700px;
  margin: 0 auto;
  color: white;
  text-align: center;
}

.features-list {
  list-style: none;
  padding: 0;
  margin: 16px 0 0;
  display: grid;
  gap: 8px;
}

.features-list li::before {
  content: "✓ ";
}
</style>
