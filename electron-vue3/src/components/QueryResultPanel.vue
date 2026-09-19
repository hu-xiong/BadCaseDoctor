<template>
  <div v-if="visible" class="qr-panel">
    <!-- 头部：标题 + 状态 + 操作 -->
    <div class="qr-header">
      <div class="qr-header-left">
        <svg class="qr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7"></circle>
          <line x1="16.5" y1="16.5" x2="21" y2="21"></line>
        </svg>
        <span class="qr-title">{{ t('queryResult.title') }}</span>
        <span class="qr-status">
          <span>{{ t('queryResult.generatedAt', { time: generatedAtText }) }}</span>
          <span class="qr-dot">·</span>
          <span>{{ t('queryResult.total', { n: items.length }) }}</span>
          <span v-if="itemsTruncated" class="qr-truncated">
            （{{ t('queryResult.truncated', { n: items.length }) }}）
          </span>
          <span v-if="frozen" class="qr-badge-frozen">{{ t('queryResult.frozenBadge') }}</span>
        </span>
      </div>
      <div class="qr-header-right">
        <button
          type="button"
          class="qr-btn"
          :disabled="loading || !hasCondition"
          :title="!hasCondition ? t('queryResult.noCondition') : ''"
          @click="handleRefresh"
        >
          {{ loading ? t('queryResult.refreshing') : t('queryResult.refresh') }}
        </button>
        <button
          type="button"
          class="qr-btn"
          :disabled="!frozen && !items.length"
          @click="handleToggleFreeze"
        >
          {{ frozen ? t('queryResult.unfreeze') : t('queryResult.freeze') }}
        </button>
        <button type="button" class="qr-btn" @click="editing = !editing">
          {{ editing ? t('queryResult.collapseEdit') : t('queryResult.editCondition') }}
        </button>
        <button type="button" class="qr-btn qr-btn--ghost" @click="$emit('close')">
          {{ t('queryResult.close') }}
        </button>
      </div>
    </div>

    <!-- 条件回显 / 编辑 -->
    <div class="qr-condition">
      <template v-if="!editing">
        <span v-if="payload.keywords" class="qr-chip">
          {{ t('queryResult.keywords') }}：{{ payload.keywords }}
        </span>
        <span v-if="payload.assignee" class="qr-chip">
          {{ t('queryResult.assignee') }}：{{ payload.assignee }}
        </span>
        <span v-if="payload.status" class="qr-chip">
          {{ t('queryResult.status') }}：{{ payload.status }}
        </span>
        <span class="qr-chip">{{ t('queryResult.type') }}：{{ typeLabel }}</span>
        <span v-if="!hasCondition" class="qr-cond-empty">{{ t('queryResult.noCondition') }}</span>
      </template>
      <form v-else class="qr-cond-form" @submit.prevent="handleRerun">
        <label class="qr-field">
          <span>{{ t('queryResult.keywords') }}</span>
          <input
            v-model="form.keywords"
            type="text"
            :placeholder="t('queryResult.keywordsPlaceholder')"
            autocomplete="off"
          />
        </label>
        <label class="qr-field">
          <span>{{ t('queryResult.assignee') }}</span>
          <input
            v-model="form.assignee"
            type="text"
            :placeholder="t('queryResult.assigneePlaceholder')"
            autocomplete="off"
          />
        </label>
        <label class="qr-field">
          <span>{{ t('queryResult.status') }}</span>
          <input
            v-model="form.status"
            type="text"
            :placeholder="t('queryResult.statusPlaceholder')"
            autocomplete="off"
          />
        </label>
        <label class="qr-field">
          <span>{{ t('queryResult.type') }}</span>
          <select v-model="form.target">
            <option v-for="tg in TYPE_TARGETS" :key="tg" :value="tg">{{ targetLabel(tg) }}</option>
          </select>
        </label>
        <button type="submit" class="qr-btn qr-btn--primary" :disabled="loading || !formOk">
          {{ loading ? t('queryResult.refreshing') : t('queryResult.rerun') }}
        </button>
      </form>
    </div>

    <!-- 提示 / 错误 -->
    <div v-if="error" class="qr-banner qr-banner--warn">{{ error }}</div>
    <div v-else-if="frozen" class="qr-banner">{{ t('queryResult.frozenHint') }}</div>

    <!-- 列表 -->
    <div v-if="items.length" class="qr-list">
      <div
        v-for="(item, idx) in items"
        :key="ridOf(item) || 'row-' + idx"
        class="qr-row"
        :class="{ 'qr-row--missing': item._missing }"
        @click="handleRowClick(item)"
      >
        <span class="qr-row-badge">{{ targetLabel(item.target) }}</span>
        <span class="qr-row-title">{{ item.title || item.bug_title || '#' + ridOf(item) }}</span>
        <span v-if="item.plan_name" class="qr-row-plan">{{ item.plan_name }}</span>
        <span v-if="item._missing" class="qr-row-missing-tag">{{ t('queryResult.missingBadge') }}</span>
        <span class="qr-row-arrow" aria-hidden="true">→</span>
      </div>
    </div>
    <div v-else class="qr-empty">
      {{ loading ? t('queryResult.refreshing') : t('queryResult.empty') }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { replayGrepQuery } from '../api.js'
import {
  normalizeQueryPayload,
  hasQueryPayloadCondition,
  buildQueryResultTabTitle
} from '../utils/queryResultTab.js'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  /** 工作台 Tab：{ id, kind, title, meta }；meta 承载 queryPayload/items/frozen 等 */
  tab: { type: Object, default: null },
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['update-meta', 'close'])
const { t } = useI18n()

const TYPE_TARGETS = ['all', 'bug', 'badcase', 'testcase', 'card', 'plan']
const AUTO_REPLAY_STALE_MS = 60000

const meta = computed(() => props.tab?.meta || {})
const payload = computed(() => normalizeQueryPayload(meta.value.queryPayload || null))
const frozen = computed(() => !!meta.value.frozen)
const frozenIds = computed(() => (Array.isArray(meta.value.frozenIds) ? meta.value.frozenIds : []))
const hasCondition = computed(() => hasQueryPayloadCondition(payload.value))

const items = ref([])
const loading = ref(false)
const error = ref('')
const editing = ref(false)
const form = ref({ keywords: '', assignee: '', status: '', target: 'all', plan_id: '', card_id: '' })

const ridOf = (item) => item?.record_id ?? item?.bug_id ?? item?.id ?? ''

const itemsTruncated = computed(
  () => Number(meta.value.itemsTotal || 0) > items.value.length
)

const generatedAtText = computed(() => {
  const ts = Number(meta.value.generatedAt || 0)
  if (!ts) return '--:--'
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
})

const TYPE_LABEL_KEYS = {
  bug: 'chat.navLabelBug',
  badcase: 'chat.navLabelBadcase',
  testcase: 'chat.navLabelTestcase',
  test_case: 'chat.navLabelTestcase',
  card: 'chat.navLabelCard',
  plan: 'chat.navLabelPlan',
  all: 'queryResult.typeAll'
}
const targetLabel = (tg) => {
  const k = String(tg || 'all').toLowerCase()
  return t(TYPE_LABEL_KEYS[k] || TYPE_LABEL_KEYS.all)
}
const typeLabel = computed(() => targetLabel(payload.value.target))
const formOk = computed(() =>
  hasQueryPayloadCondition(
    normalizeQueryPayload({
      ...form.value,
      plan_id: payload.value.plan_id,
      card_id: payload.value.card_id
    })
  )
)

watch(
  () => meta.value.items,
  (v) => {
    items.value = Array.isArray(v) ? v.slice() : []
  },
  { immediate: true }
)

watch(editing, (v) => {
  if (!v) return
  form.value = {
    keywords: payload.value.keywords,
    assignee: payload.value.assignee,
    status: payload.value.status,
    target: payload.value.target || 'all',
    plan_id: payload.value.plan_id,
    card_id: payload.value.card_id
  }
})

/** 冻结态刷新：重放结果 ∩ 冻结成员；缺失成员沿用旧快照并标 _missing（成员固定） */
const applyFrozenIntersection = (newItems) => {
  const byId = new Map()
  for (const it of newItems) {
    const rid = String(ridOf(it))
    if (rid) byId.set(rid, it)
  }
  const oldById = new Map()
  for (const it of items.value) {
    const rid = String(ridOf(it))
    if (rid) oldById.set(rid, it)
  }
  return frozenIds.value
    .map((id) => {
      const sid = String(id)
      const hit = byId.get(sid)
      if (hit) return hit
      const old = oldById.get(sid)
      return old ? { ...old, _missing: true } : null
    })
    .filter(Boolean)
}

const runReplay = async (payloadArg, { auto = false, updateCondition = false } = {}) => {
  if (loading.value) return
  const norm = normalizeQueryPayload(payloadArg)
  if (!hasQueryPayloadCondition(norm)) {
    error.value = t('queryResult.noCondition')
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await replayGrepQuery(props.projectId, norm)
    const data = res?.data || {}
    if (!data.success) throw new Error(String(data.error || 'replay failed'))
    let newItems = Array.isArray(data?.navigation?.items) ? data.navigation.items : []
    if (frozen.value && frozenIds.value.length) {
      newItems = applyFrozenIntersection(newItems)
    }
    if (auto && !newItems.length && items.value.length) {
      // 自动重放未命中：保留原快照（可能只是索引/权限瞬时波动），仅提示
      error.value = t('queryResult.autoMissKept')
      return
    }
    const patch = {
      items: newItems,
      itemsTotal: newItems.length,
      generatedAt: Date.now()
    }
    if (updateCondition) {
      patch.queryPayload = norm
      patch.title = buildQueryResultTabTitle(norm, t)
    }
    emit('update-meta', patch)
    items.value = newItems
  } catch (e) {
    error.value = t('queryResult.rerunFail', { msg: e?.message || String(e) })
  } finally {
    loading.value = false
  }
}

const handleRefresh = () => {
  void runReplay(payload.value)
}

const handleRerun = () => {
  void runReplay(
    { ...form.value, plan_id: payload.value.plan_id, card_id: payload.value.card_id },
    { updateCondition: true }
  )
}

const handleToggleFreeze = () => {
  if (frozen.value) {
    const cleaned = items.value.map((it) => {
      const { _missing, ...rest } = it
      return rest
    })
    emit('update-meta', { frozen: false, frozenIds: [], items: cleaned })
    items.value = cleaned
    return
  }
  if (!items.value.length) return
  const ids = items.value.map((it) => String(ridOf(it))).filter(Boolean)
  emit('update-meta', { frozen: true, frozenIds: ids })
}

const handleRowClick = (item) => {
  const rid = ridOf(item)
  if (!rid && item?.plan_id == null) return
  const navTarget = String(item?.target || 'bug').toLowerCase()
  window.dispatchEvent(
    new CustomEvent('grep-navigate', {
      detail: {
        planId: item?.plan_id,
        bugId: rid,
        recordId: rid,
        target: navTarget === 'test_case' ? 'testcase' : navTarget
      }
    })
  )
}

onMounted(() => {
  if (!props.visible || !hasCondition.value) return
  const age = Date.now() - Number(meta.value.generatedAt || 0)
  if (age > AUTO_REPLAY_STALE_MS) {
    void runReplay(payload.value, { auto: true })
  }
})
</script>

<style scoped>
.qr-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
  border-top: 1px solid #e9ecef;
}

.qr-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid #e9ecef;
  background: #fafbfc;
}

.qr-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.qr-icon {
  width: 16px;
  height: 16px;
  color: #4f46e5;
  flex-shrink: 0;
}

.qr-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
}

.qr-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

.qr-dot {
  color: #cbd5e1;
}

.qr-truncated {
  color: #94a3b8;
}

.qr-badge-frozen {
  margin-left: 4px;
  padding: 1px 8px;
  font-size: 11px;
  color: #b45309;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 999px;
}

.qr-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.qr-btn {
  padding: 5px 12px;
  font-size: 12px;
  color: #334155;
  background: #fff;
  border: 1px solid #d7dce3;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.qr-btn:hover:not(:disabled) {
  border-color: #4f46e5;
  color: #4f46e5;
}

.qr-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qr-btn--primary {
  color: #fff;
  background: #4f46e5;
  border-color: #4f46e5;
}

.qr-btn--primary:hover:not(:disabled) {
  color: #fff;
  background: #4338ca;
  border-color: #4338ca;
}

.qr-btn--ghost {
  color: #64748b;
}

.qr-condition {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 20px;
  border-bottom: 1px solid #f1f5f9;
}

.qr-chip {
  padding: 3px 10px;
  font-size: 12px;
  color: #334155;
  background: #f1f5f9;
  border-radius: 999px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qr-cond-empty {
  font-size: 12px;
  color: #94a3b8;
}

.qr-cond-form {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
}

.qr-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}

.qr-field input,
.qr-field select {
  padding: 5px 10px;
  font-size: 12px;
  color: #1e293b;
  background: #fff;
  border: 1px solid #d7dce3;
  border-radius: 6px;
  outline: none;
  min-width: 140px;
}

.qr-field input:focus,
.qr-field select:focus {
  border-color: #4f46e5;
}

.qr-banner {
  flex-shrink: 0;
  margin: 8px 20px 0;
  padding: 8px 12px;
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
}

.qr-banner--warn {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #fecaca;
}

.qr-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 20px 20px;
}

.qr-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  margin: 4px 0;
  background: #f8fafc;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.qr-row:hover {
  background: #eef2ff;
  border-color: #c7d2fe;
}

.qr-row--missing {
  opacity: 0.55;
}

.qr-row-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  font-size: 11px;
  color: #4f46e5;
  background: #e0e7ff;
  border-radius: 4px;
}

.qr-row-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qr-row-plan {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 12px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 4px;
}

.qr-row-missing-tag {
  flex-shrink: 0;
  padding: 1px 8px;
  font-size: 11px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 4px;
}

.qr-row-arrow {
  flex-shrink: 0;
  font-size: 13px;
  color: #94a3b8;
}

.qr-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  font-size: 13px;
  color: #94a3b8;
}
</style>
