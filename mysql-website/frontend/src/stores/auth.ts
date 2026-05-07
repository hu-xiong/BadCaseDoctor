import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login, register, logout, getCurrentUser } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  interface User {
    id: number
    username: string
    email: string
    avatar?: string
  }

  async function loginAction(credentials: { username: string; password: string }) {
    loading.value = true
    try {
      const response = await login(credentials)
      token.value = response.data.token
      user.value = response.data.user
      localStorage.setItem('token', response.data.token)
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
      const response = await register(userData)
      token.value = response.data.token
      user.value = response.data.user
      localStorage.setItem('token', response.data.token)
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
      const response = await getCurrentUser()
      user.value = response.data
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
