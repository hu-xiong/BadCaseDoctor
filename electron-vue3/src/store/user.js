import { ref } from 'vue'
import { getCurrentUser } from '../api.js'
import { clearLastProjectId } from '../utils/lastProject.js'

const user = ref(null)

export async function fetchUser() {
  try {
    const res = await getCurrentUser()
    if (res.data.success) {
      user.value = res.data.user
    } else {
      user.value = null
    }
  } catch {
    user.value = null
  }
}

export function setUser(u) {
  user.value = u
  // 同时保存到localStorage，确保页面刷新后仍能获取到用户信息
  if (u) {
    localStorage.setItem('user', JSON.stringify(u))
  } else {
    localStorage.removeItem('user')
  }
}

export function logout() {
  user.value = null
  localStorage.removeItem('user')
  clearLastProjectId()
}

export default user 