import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login, register, logout, getCurrentUser, type AuthUser } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<AuthUser | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  async function loginAction(credentials: { email: string; password: string }) {
    loading.value = true
    try {
      const payload = await login(credentials)
      token.value = payload.token
      user.value = payload.user
      localStorage.setItem('token', payload.token)
      return { success: true }
    } catch (error: any) {
      return { success: false, message: error.response?.data?.message || 'Login failed' }
    } finally {
      loading.value = false
    }
  }

  async function registerAction(userData: { username: string; email: string; password: string }) {
    loading.value = true
    try {
      const payload = await register(userData)
      token.value = payload.token
      user.value = payload.user
      localStorage.setItem('token', payload.token)
      return { success: true }
    } catch (error: any) {
      return { success: false, message: error.response?.data?.message || 'Registration failed' }
    } finally {
      loading.value = false
    }
  }

  async function logoutAction() {
    try {
      await logout()
    } finally {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
    }
  }

  async function fetchCurrentUser() {
    if (!token.value) return
    try {
      user.value = await getCurrentUser()
    } catch {
      logoutAction()
    }
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    loginAction,
    registerAction,
    logoutAction,
    fetchCurrentUser
  }
})
