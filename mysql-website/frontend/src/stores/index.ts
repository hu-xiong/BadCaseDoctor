import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const searchQuery = ref('')
  const isMobileMenuOpen = ref(false)
  const breadcrumbs = ref<Array<{ title: string; path?: string }>>([])

  function setSearchQuery(query: string) {
    searchQuery.value = query
  }

  function toggleMobileMenu() {
    isMobileMenuOpen.value = !isMobileMenuOpen.value
  }

  function closeMobileMenu() {
    isMobileMenuOpen.value = false
  }

  function setBreadcrumbs(items: Array<{ title: string; path?: string }>) {
    breadcrumbs.value = items
  }

  return {
    searchQuery,
    isMobileMenuOpen,
    breadcrumbs,
    setSearchQuery,
    toggleMobileMenu,
    closeMobileMenu,
    setBreadcrumbs
  }
})
