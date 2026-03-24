import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import en from './locales/en.json'

export const LOCALE_STORAGE_KEY = 'badcase_app_locale'

function detectInitialLocale() {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (saved === 'en' || saved === 'zh-CN') return saved
  } catch {
    /* ignore */
  }
  if (typeof navigator !== 'undefined' && navigator.language) {
    return String(navigator.language).toLowerCase().startsWith('en') ? 'en' : 'zh-CN'
  }
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    en
  }
})

export function persistLocale(locale) {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    /* ignore */
  }
  i18n.global.locale.value = locale
}

/** 与后端 agents.locale_prompts.normalize_locale 对齐：'en' | 'zh' */
export function apiLocaleParam() {
  const v = i18n.global.locale.value
  return v === 'en' ? 'en' : 'zh-CN'
}
