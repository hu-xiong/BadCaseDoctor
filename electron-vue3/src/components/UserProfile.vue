<template>
  <div v-if="embedded" class="profile-embedded" :class="{ 'profile-embedded--light': tone === 'light' }">
    <div class="modal-body embedded-body">
        <!-- 用户基本信息 -->
        <div class="user-info-section">
          <div class="avatar-large">{{ userInitial }}</div>
          <div class="user-details">
            <h3>{{ user?.name || '用户' }}</h3>
            <p class="email">{{ user?.email || '' }}</p>
          </div>
        </div>

        <!-- 订阅信息 -->
        <div class="subscription-section">
          <h4>订阅信息</h4>
          
          <div v-if="loading" class="loading-state">
            加载中...
          </div>
          
          <div v-else-if="credits > 0" class="subscription-active">
            <div class="credits-display">
              <div class="credits-circle">
                <span class="credits-number">{{ credits }}</span>
                <span class="credits-label">剩余次数</span>
              </div>
            </div>
            <div class="subscription-stats">
              <div class="stat-item">
                <span class="stat-value">{{ totalPurchased }}</span>
                <span class="stat-label">累计购买</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ totalPurchased - credits }}</span>
                <span class="stat-label">已使用</span>
              </div>
            </div>
            <button class="buy-more-btn" @click="goToSubscription">
              购买更多
            </button>
          </div>
          
          <div v-else class="no-subscription">
            <div class="empty-icon">💳</div>
            <p>您还没有订阅</p>
            <p class="hint">订阅后可使用 AI 智能诊断功能</p>
            <button class="subscribe-btn" @click="goToSubscription">
              立即订阅
            </button>
          </div>
        </div>
      </div>
  </div>
  <div v-else class="profile-modal-overlay" @click.self="$emit('close')">
    <div class="profile-modal">
      <div class="modal-header">
        <h2>个人资料</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>
      
      <div class="modal-body">
        <!-- 用户基本信息 -->
        <div class="user-info-section">
          <div class="avatar-large">{{ userInitial }}</div>
          <div class="user-details">
            <h3>{{ user?.name || '用户' }}</h3>
            <p class="email">{{ user?.email || '' }}</p>
          </div>
        </div>

        <!-- 订阅信息 -->
        <div class="subscription-section">
          <h4>订阅信息</h4>
          
          <div v-if="loading" class="loading-state">
            加载中...
          </div>
          
          <div v-else-if="credits > 0" class="subscription-active">
            <div class="credits-display">
              <div class="credits-circle">
                <span class="credits-number">{{ credits }}</span>
                <span class="credits-label">剩余次数</span>
              </div>
            </div>
            <div class="subscription-stats">
              <div class="stat-item">
                <span class="stat-value">{{ totalPurchased }}</span>
                <span class="stat-label">累计购买</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ totalPurchased - credits }}</span>
                <span class="stat-label">已使用</span>
              </div>
            </div>
            <button class="buy-more-btn" @click="goToSubscription">
              购买更多
            </button>
          </div>
          
          <div v-else class="no-subscription">
            <div class="empty-icon">💳</div>
            <p>您还没有订阅</p>
            <p class="hint">订阅后可使用 AI 智能诊断功能</p>
            <button class="subscribe-btn" @click="goToSubscription">
              立即订阅
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const props = defineProps({
  user: Object,
  embedded: { type: Boolean, default: false },
  /** 嵌入到浅色工作台时用 light */
  tone: { type: String, default: 'dark', validator: (v) => ['dark', 'light'].includes(v) }
})

const emit = defineEmits(['close'])
const router = useRouter()

const credits = ref(0)
const totalPurchased = ref(0)
const loading = ref(true)

const userInitial = computed(() => {
  return props.user?.name?.charAt(0)?.toUpperCase() || 'U'
})

const fetchCredits = async () => {
  try {
    const res = await api.get('/api/payment/credits')
    credits.value = res.data.credits || 0
    totalPurchased.value = res.data.total_purchased || 0
  } catch (error) {
    console.error('获取订阅信息失败:', error)
  } finally {
    loading.value = false
  }
}

const goToSubscription = () => {
  emit('close')
  router.push('/subscription')
}

onMounted(() => {
  fetchCredits()
})
</script>

<style scoped>
.profile-embedded {
  width: 100%;
}

.embedded-body {
  padding: 0;
  background: transparent;
}

.profile-embedded--light .modal-body {
  padding: 20px 22px 22px;
  background: #fff;
}

.profile-embedded--light .user-info-section {
  border-bottom-color: #e9ecef;
}

.profile-embedded--light .user-details h3 {
  color: #212529;
}

.profile-embedded--light .user-details .email {
  color: #6c757d;
}

.profile-embedded--light .subscription-section h4 {
  color: #868e96;
}

.profile-embedded--light .loading-state {
  color: #868e96;
}

.profile-embedded--light .stat-value {
  color: #212529;
}

.profile-embedded--light .stat-label {
  color: #868e96;
}

.profile-embedded--light .no-subscription p {
  color: #212529;
}

.profile-embedded--light .no-subscription .hint {
  color: #6c757d;
}

.profile-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.profile-modal {
  background: #1e1e1e;
  border-radius: 16px;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #333;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  color: #fff;
}

.close-btn {
  background: none;
  border: none;
  color: #888;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #fff;
}

.modal-body {
  padding: 24px;
}

.user-info-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #333;
}

.avatar-large {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 600;
  color: white;
}

.user-details h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
  color: #fff;
}

.user-details .email {
  margin: 0;
  color: #888;
  font-size: 14px;
}

.subscription-section h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.loading-state {
  text-align: center;
  color: #888;
  padding: 20px;
}

.subscription-active {
  text-align: center;
}

.credits-display {
  margin-bottom: 20px;
}

.credits-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: 0 auto;
  box-shadow: 0 8px 30px rgba(34, 197, 94, 0.3);
}

.credits-number {
  font-size: 36px;
  font-weight: 700;
  color: white;
}

.credits-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
}

.subscription-stats {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}

.stat-label {
  font-size: 12px;
  color: #888;
}

.buy-more-btn {
  background: transparent;
  border: 1px solid #4ade80;
  color: #4ade80;
  padding: 10px 30px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}

.buy-more-btn:hover {
  background: #4ade80;
  color: #000;
}

.no-subscription {
  text-align: center;
  padding: 20px 0;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.no-subscription p {
  margin: 0 0 8px 0;
  color: #fff;
  font-size: 16px;
}

.no-subscription .hint {
  color: #888;
  font-size: 14px;
  margin-bottom: 20px;
}

.subscribe-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
  padding: 12px 40px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}

.subscribe-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
}
</style>
