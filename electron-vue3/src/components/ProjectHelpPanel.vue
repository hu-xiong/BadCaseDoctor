<template>
  <div class="php-root">
    <header class="php-header">
      <h1 class="php-title">{{ t('helpDoc.pageTitle') }}</h1>
      <p class="php-intro">{{ t('helpDoc.intro') }}</p>
      <div class="php-search-wrap">
        <span class="php-search-icon" aria-hidden="true">⌕</span>
        <input
          v-model="query"
          type="search"
          class="php-search"
          :placeholder="t('helpDoc.searchPlaceholder')"
          autocomplete="off"
        />
      </div>
    </header>
    <div class="php-body">
      <p v-if="filtered.length === 0" class="php-empty">{{ t('helpDoc.noResults') }}</p>
      <article v-for="(sec, idx) in filtered" :key="sec.id || idx" class="php-card">
        <h2 class="php-card-title">{{ sec.title }}</h2>
        <p v-if="sec.keywords" class="php-keywords">
          <span class="php-kw-label">{{ t('helpDoc.keywordsLabel') }}</span>
          {{ sec.keywords }}
        </p>
        <div class="php-paras">
          <p v-for="(para, pi) in sec.paragraphs" :key="pi" class="php-para">{{ para }}</p>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

defineProps({
  visible: { type: Boolean, default: true }
})

const { t, tm } = useI18n()
const query = ref('')

const sections = computed(() => {
  const raw = tm('helpDoc.sections')
  if (!Array.isArray(raw)) return []
  return raw
    .filter((s) => s && typeof s.title === 'string')
    .map((s, i) => ({
      id: s.id || `h-${i}`,
      title: s.title,
      keywords: typeof s.keywords === 'string' ? s.keywords : '',
      paragraphs: Array.isArray(s.paragraphs) ? s.paragraphs.filter((p) => typeof p === 'string') : []
    }))
})

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return sections.value
  return sections.value.filter((s) => {
    const blob = [s.title, s.keywords, ...s.paragraphs].join('\n').toLowerCase()
    return blob.includes(needle)
  })
})
</script>

<style scoped>
.php-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
  border-top: 1px solid #e9ecef;
}

.php-header {
  flex-shrink: 0;
  padding: 20px 24px 16px;
  border-bottom: 1px solid #e9ecef;
  background: #fafbfc;
}

.php-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #212529;
}

.php-intro {
  margin: 0 0 14px;
  font-size: 13px;
  color: #495057;
  line-height: 1.5;
  max-width: 920px;
}

.php-search-wrap {
  position: relative;
  max-width: 420px;
}

.php-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  color: #868e96;
  pointer-events: none;
}

.php-search {
  width: 100%;
  box-sizing: border-box;
  height: 36px;
  padding: 0 12px 0 32px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
  color: #212529;
  outline: none;
}

.php-search:focus {
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.12);
}

.php-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 24px 28px;
  max-width: 960px;
}

.php-empty {
  margin: 24px 0;
  color: #868e96;
  font-size: 14px;
}

.php-card {
  margin-bottom: 20px;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.php-card-title {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 600;
  color: #212529;
}

.php-keywords {
  margin: 0 0 12px;
  font-size: 12px;
  color: #6c757d;
  line-height: 1.45;
}

.php-kw-label {
  font-weight: 600;
  color: #495057;
  margin-right: 6px;
}

.php-paras {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.php-para {
  margin: 0;
  font-size: 13px;
  color: #343a40;
  line-height: 1.65;
}
</style>
