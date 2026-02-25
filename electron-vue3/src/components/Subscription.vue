<template>
  <div class="subscription-page">
    <div class="header">
      <h1>Choose Your Plan</h1>
      <p class="subtitle">Select the plan that best fits your needs</p>
      <div class="credits-info" v-if="userCredits !== null">
        <span class="credits-label">Current Credits:</span>
        <span class="credits-value">{{ userCredits }}</span>
      </div>
    </div>

    <div class="plans-container">
      <div 
        v-for="plan in plans" 
        :key="plan.id"
        class="plan-card"
        :class="{ 'popular': plan.id === 'professional' }"
      >
        <div class="popular-badge" v-if="plan.id === 'professional'">Most Popular</div>
        <h2 class="plan-name">{{ plan.name }}</h2>
        <div class="plan-price">
          <span class="currency">$</span>
          <span class="amount">{{ plan.price }}</span>
        </div>
        <div class="plan-credits">
          <span class="credits-number">{{ plan.credits }}</span>
          <span class="credits-text">credits</span>
        </div>
        <p class="plan-description">{{ plan.description }}</p>
        <button 
          class="subscribe-btn"
          :class="{ 'loading': loadingPlan === plan.id }"
          @click="handleSubscribe(plan.id)"
          :disabled="loadingPlan !== null"
        >
          <span v-if="loadingPlan === plan.id">Processing...</span>
          <span v-else>Get Started</span>
        </button>
      </div>
    </div>

    <div class="features-section">
      <h3>All plans include:</h3>
      <ul class="features-list">
        <li>AI-powered bug detection</li>
        <li>Browser automation testing</li>
        <li>Detailed analysis reports</li>
        <li>Priority support</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const plans = ref([])
const userCredits = ref(null)
const loadingPlan = ref(null)

// 获取计划列表
const fetchPlans = async () => {
  try {
    const res = await axios.get('/api/payment/plans')
    plans.value = res.data.plans
  } catch (error) {
    console.error('获取计划失败:', error)
  }
}

// 获取用户额度
const fetchCredits = async () => {
  try {
    const res = await axios.get('/api/payment/credits')
    userCredits.value = res.data.credits
  } catch (error) {
    console.error('获取额度失败:', error)
  }
}

// 发起订阅
const handleSubscribe = async (planId) => {
  loadingPlan.value = planId
  try {
    const res = await axios.post('/api/payment/create-checkout', { plan_id: planId })
    // 跳转到 Stripe 支付页面
    window.location.href = res.data.checkout_url
  } catch (error) {
    console.error('创建支付失败:', error)
    alert('Payment failed. Please try again.')
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
  font-size: 18px;
  opacity: 0.9;
}

.credits-info {
  margin-top: 20px;
  background: rgba(255,255,255,0.2);
  display: inline-block;
  padding: 10px 25px;
  border-radius: 30px;
}

.credits-label {
  margin-right: 8px;
}

.credits-value {
  font-weight: bold;
  font-size: 20px;
}

.plans-container {
  display: flex;
  justify-content: center;
  gap: 25px;
  flex-wrap: wrap;
  max-width: 1200px;
  margin: 0 auto;
}

.plan-card {
  background: white;
  border-radius: 20px;
  padding: 40px 30px;
  width: 260px;
  text-align: center;
  position: relative;
  transition: transform 0.3s, box-shadow 0.3s;
  box-shadow: 0 10px 40px rgba(0,0,0,0.1);
}

.plan-card:hover {
  transform: translateY(-10px);
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}

.plan-card.popular {
  border: 3px solid #667eea;
  transform: scale(1.05);
}

.plan-card.popular:hover {
  transform: scale(1.05) translateY(-10px);
}

.popular-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 6px 20px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.plan-name {
  font-size: 22px;
  color: #333;
  margin-bottom: 20px;
}

.plan-price {
  margin-bottom: 10px;
}

.currency {
  font-size: 24px;
  vertical-align: top;
  color: #667eea;
}

.amount {
  font-size: 56px;
  font-weight: 700;
  color: #333;
}

.plan-credits {
  margin-bottom: 20px;
}

.credits-number {
  font-size: 32px;
  font-weight: 600;
  color: #667eea;
}

.credits-text {
  font-size: 16px;
  color: #666;
  margin-left: 5px;
}

.plan-description {
  color: #888;
  font-size: 14px;
  margin-bottom: 30px;
  min-height: 40px;
}

.subscribe-btn {
  width: 100%;
  padding: 15px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.3s, transform 0.2s;
}

.subscribe-btn:hover:not(:disabled) {
  opacity: 0.9;
  transform: scale(1.02);
}

.subscribe-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.subscribe-btn.loading {
  background: #999;
}

.features-section {
  text-align: center;
  color: white;
  margin-top: 60px;
}

.features-section h3 {
  font-size: 24px;
  margin-bottom: 20px;
}

.features-list {
  list-style: none;
  padding: 0;
  display: flex;
  justify-content: center;
  gap: 40px;
  flex-wrap: wrap;
}

.features-list li {
  font-size: 16px;
  opacity: 0.9;
}

.features-list li::before {
  content: '✓';
  margin-right: 8px;
  font-weight: bold;
}
</style>
