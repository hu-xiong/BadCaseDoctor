<template>
  <div v-if="embedded" class="profile-embedded" :class="{ 'profile-embedded--light': tone === 'light' }">
    <div class="modal-body embedded-body">
        <div class="user-info-section">
          <div class="avatar-large">{{ userInitial }}</div>
          <div class="user-details">
            <h3>{{ user?.name || t('shell.userFallback') }}</h3>
            <p class="email">{{ user?.email || '' }}</p>
          </div>
        </div>

        <div class="subscription-section">
          <h4>{{ t('userProfile.subscriptionInfo') }}</h4>
          
          <div v-if="loading" class="loading-state">
            {{ t('common.loading') }}
          </div>
          
          <div v-else-if="hasActivity" class="subscription-active">
            <div class="credits-display">
              <div class="credits-circle">
                <span class="credits-number">{{ stats.credits }}</span>
                <span class="credits-label">{{ t('userProfile.creditsRemaining') }}</span>
              </div>
            </div>
            <div class="subscription-stats">
              <div class="stat-item">
                <span class="stat-value">{{ stats.total_purchased }}</span>
                <span class="stat-label">{{ t('userProfile.totalPurchased') }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ stats.total_consumed }}</span>
                <span class="stat-label">{{ t('userProfile.totalConsumed') }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ stats.today_consumed }}</span>
                <span class="stat-label">{{ t('userProfile.todayConsumed') }}</span>
              </div>
              <div v-if="stats.total_granted > 0" class="stat-item">
                <span class="stat-value">{{ stats.total_granted }}</span>
                <span class="stat-label">{{ t('userProfile.grantedCredits') }}</span>
              </div>
            </div>
            <div v-if="recentRecords.length" class="usage-records">
              <div class="records-title">{{ t('userProfile.usageRecords') }}</div>
              <div class="records-list">
                <div v-for="rec in recentRecords" :key="rec.id" class="record-item">
                  <span class="record-badge" :class="`record-badge--${rec.type}`">{{ recordTypeLabel(rec.type) }}</span>
                  <span class="record-time">{{ formatTime(rec.created_at) }}</span>
                  <span class="record-credits" :class="{ 'record-credits--plus': rec.credits > 0, 'record-credits--pending': rec.type === 'pending' }">
                    {{ rec.credits > 0 ? '+' + rec.credits : rec.credits }}
                  </span>
                </div>
              </div>
            </div>
            <button class="buy-more-btn" @click="goToSubscription">
              {{ t('userProfile.buyMore') }}
            </button>
          </div>
          
          <div v-else class="no-subscription">
            <div class="empty-icon">💳</div>
            <p>{{ t('userProfile.noSubscription') }}</p>
            <p class="hint">{{ t('userProfile.subscribeHint') }}</p>
            <button class="subscribe-btn" @click="goToSubscription">
              {{ t('subscription.getStarted') }}
            </button>
          </div>
        </div>
      </div>
  </div>
  <div v-else class="profile-modal-overlay" @click.self="$emit('close')">
    <div class="profile-modal">
      <div class="modal-header">
        <h2>{{ t('userProfile.title') }}</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>
      
      <div class="modal-body">
        <div class="user-info-section">
          <div class="avatar-large">{{ userInitial }}</div>
          <div class="user-details">
            <h3>{{ user?.name || t('shell.userFallback') }}</h3>
            <p class="email">{{ user?.email || '' }}</p>
          </div>
        </div>

        <div class="subscription-section">
          <h4>{{ t('userProfile.subscriptionInfo') }}</h4>
          
          <div v-if="loading" class="loading-state">
            {{ t('common.loading') }}
          </div>
          
          <div v-else-if="hasActivity" class="subscription-active">
            <div class="credits-display">
              <div class="credits-circle">
                <span class="credits-number">{{ stats.credits }}</span>
                <span class="credits-label">{{ t('userProfile.creditsRemaining') }}</span>
              </div>
            </div>
            <div class="subscription-stats">
              <div class="stat-item">
                <span class="stat-value">{{ stats.total_purchased }}</span>
                <span class="stat-label">{{ t('userProfile.totalPurchased') }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ stats.total_consumed }}</span>
                <span class="stat-label">{{ t('userProfile.totalConsumed') }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ stats.today_consumed }}</span>
                <span class="stat-label">{{ t('userProfile.todayConsumed') }}</span>
              </div>
              <div v-if="stats.total_granted > 0" class="stat-item">
                <span class="stat-value">{{ stats.total_granted }}</span>
                <span class="stat-label">{{ t('userProfile.grantedCredits') }}</span>
              </div>
            </div>
            <div v-if="recentRecords.length" class="usage-records">
              <div class="records-title">{{ t('userProfile.usageRecords') }}</div>
              <div class="records-list">
                <div v-for="rec in recentRecords" :key="rec.id" class="record-item">
                  <span class="record-badge" :class="`record-badge--${rec.type}`">{{ recordTypeLabel(rec.type) }}</span>
                  <span class="record-time">{{ formatTime(rec.created_at) }}</span>
                  <span class="record-credits" :class="{ 'record-credits--plus': rec.credits > 0, 'record-credits--pending': rec.type === 'pending' }">
                    {{ rec.credits > 0 ? '+' + rec.credits : rec.credits }}
                  </span>
                </div>
              </div>
            </div>
            <button class="buy-more-btn" @click="goToSubscription">
              {{ t('userProfile.buyMore') }}
            </button>
          </div>
          
          <div v-else class="no-subscription">
            <div class="empty-icon">💳</div>
            <p>{{ t('userProfile.noSubscription') }}</p>
            <p class="hint">{{ t('userProfile.subscribeHint') }}</p>
            <button class="subscribe-btn" @click="goToSubscription">
              {{ t('subscription.getStarted') }}
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
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const props = defineProps({
  user: Object,
  embedded: { type: Boolean, default: false },
  /** 嵌入到浅色工作台时用 light */
  tone: { type: String, default: 'dark', validator: (v) => ['dark', 'light'].includes(v) }
})

const emit = defineEmits(['close'])
const router = useRouter()
const { t } = useI18n()

const stats = ref({
  credits: 0,
  total_purchased: 0,
  total_consumed: 0,
  total_granted: 0,
  today_consumed: 0,
})
const recentRecords = ref([])
const loading = ref(true)

// 有过任何额度活动（购买/赠送/消耗/余额）即展示统计，余额耗尽也能看到使用记录
const hasActivity = computed(() =>
  stats.value.credits > 0 ||
  stats.value.total_purchased > 0 ||
  stats.value.total_consumed > 0 ||
  stats.value.total_granted > 0
)

const userInitial = computed(() => {
  return props.user?.name?.charAt(0)?.toUpperCase() || 'U'
})

const recordTypeLabel = (type) =>
  ({
    purchase: t('userProfile.recordPurchase'),
    consume: t('userProfile.recordConsume'),
    pending: t('userProfile.recordPending'),
  })[type] || type

const formatTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

const fetchCredits = async () => {
  try {
    const res = await api.get('/api/payment/credit-stats')
    const data = res.data || {}
    stats.value = {
      credits: data.credits || 0,
      total_purchased: data.total_purchased || 0,
      total_consumed: data.total_consumed || 0,
      total_granted: data.total_granted || 0,
      today_consumed: data.today_consumed || 0,
    }
    recentRecords.value = Array.isArray(data.recent) ? data.recent : []
  } catch (error) {
    console.error('[UserProfile] fetch credit stats failed:', error)
    // 旧后端兜底：至少展示余额与累计购买
    try {
      const res = await api.get('/api/payment/credits')
      stats.value.credits = res.data?.credits || 0
      stats.value.total_purchased = res.data?.total_purchased || 0
    } catch (fallbackError) {
      console.error('[UserProfile] fetch credits fallback failed:', fallbackError)
    }
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

.profile-embedded--light .records-title {
  color: #868e96;
}

.profile-embedded--light .records-list {
  border-color: #e9ecef;
}

.profile-embedded--light .record-item {
  border-bottom-color: #f1f3f5;
}

.profile-embedded--light .record-time {
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
  flex-wrap: wrap;
  gap: 28px;
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

.usage-records {
  text-align: left;
  margin-bottom: 20px;
}

.records-title {
  font-size: 12px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
}

.records-list {
  max-height: 180px;
  overflow-y: auto;
  border: 1px solid #333;
  border-radius: 10px;
}

.record-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  font-size: 13px;
  border-bottom: 1px solid #2a2a2a;
}

.record-item:last-child {
  border-bottom: none;
}

.record-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.record-badge--purchase {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.record-badge--consume {
  background: rgba(96, 165, 250, 0.15);
  color: #60a5fa;
}

.record-badge--pending {
  background: rgba(250, 204, 21, 0.15);
  color: #facc15;
}

.record-time {
  flex: 1;
  color: #888;
}

.record-credits {
  font-weight: 600;
  color: #60a5fa;
}

.record-credits--plus {
  color: #4ade80;
}

.record-credits--pending {
  color: #facc15;
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
