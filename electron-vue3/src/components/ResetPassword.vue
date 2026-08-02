<template>
  <div class="reset-password-container">
    <div class="background-animation"></div>
    <div class="reset-password-card">
      <div class="text-center mb-4">
        <h2 class="text-primary">重置密码</h2>
        <p class="text-muted">请输入邮箱验证码与新密码</p>
      </div>
      
      <form @submit.prevent="handleResetPassword">
        <div class="mb-3">
          <label for="email" class="form-label">邮箱</label>
          <input
            type="email"
            class="form-control"
            id="email"
            v-model="form.email"
            required
            placeholder="注册邮箱"
          />
        </div>

        <div class="mb-3">
          <label for="code" class="form-label">验证码</label>
          <input
            type="text"
            class="form-control"
            id="code"
            v-model="form.verification_code"
            required
            placeholder="邮箱收到的验证码"
          />
        </div>

        <div class="mb-3">
          <label for="password" class="form-label">新密码</label>
          <input
            type="password"
            class="form-control"
            id="password"
            v-model="form.password"
            required
            minlength="6"
            placeholder="请输入新密码（至少 6 位）"
          />
        </div>
        
        <div class="mb-3">
          <label for="confirm-password" class="form-label">确认密码</label>
          <input
            type="password"
            class="form-control"
            id="confirm-password"
            v-model="form.confirmPassword"
            required
            placeholder="请再次输入新密码"
          />
        </div>
        
        <div class="d-grid gap-2">
          <button type="submit" class="btn btn-primary" :disabled="loading">
            {{ loading ? '重置中...' : '重置密码' }}
          </button>
        </div>
      </form>
      
      <div class="mt-3 text-center">
        <a href="#" @click.prevent="$router.push('/login')" class="text-decoration-none">
          返回登录
        </a>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { resetPassword } from '../api.js'

export default {
  name: 'ResetPassword',
  setup() {
    const router = useRouter()
    const route = useRoute()
    const loading = ref(false)
    
    const form = ref({
      email: '',
      verification_code: '',
      password: '',
      confirmPassword: ''
    })

    onMounted(() => {
      const qEmail = route.query?.email
      if (qEmail) form.value.email = String(qEmail)
    })
    
    const handleResetPassword = async () => {
      if (form.value.password !== form.value.confirmPassword) {
        alert('两次输入的密码不一致')
        return
      }
      
      loading.value = true
      try {
        const res = await resetPassword({
          email: form.value.email,
          verification_code: form.value.verification_code,
          password: form.value.password
        })
        if (res?.data?.success === false) {
          throw new Error(res?.data?.error || '重置失败')
        }
        alert(res?.data?.message || '密码重置成功')
        router.push('/login')
      } catch (error) {
        console.error('重置密码失败:', error)
        alert(error?.response?.data?.error || error?.message || '重置失败')
      } finally {
        loading.value = false
      }
    }
    
    return {
      form,
      loading,
      handleResetPassword
    }
  }
}
</script>

<style scoped>
.reset-password-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  position: relative;
  overflow: hidden;
}

.background-animation {
  position: absolute;
  inset: 0;
  background: linear-gradient(45deg, #667eea, #764ba2, #f093fb, #f5576c);
  background-size: 400% 400%;
  animation: gradientShift 15s ease infinite;
  opacity: 0.8;
}

@keyframes gradientShift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.reset-password-card {
  background: white;
  padding: 40px;
  border-radius: 15px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 420px;
  position: relative;
  z-index: 1;
}
</style>
