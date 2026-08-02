<template>
  <div class="forgot-password-container">
    <div class="background-animation"></div>
    <div class="forgot-password-card">
      <div class="text-center mb-4">
        <h2 class="text-primary">忘记密码</h2>
        <p class="text-muted">请输入您的邮箱地址，我们将发送重置验证码</p>
      </div>
      
      <form @submit.prevent="handleForgotPassword">
        <div class="mb-3">
          <label for="email" class="form-label">邮箱地址</label>
          <input
            type="email"
            class="form-control"
            id="email"
            v-model="form.email"
            required
            placeholder="请输入邮箱地址"
          />
        </div>
        
        <div class="d-grid gap-2">
          <button type="submit" class="btn btn-primary" :disabled="loading">
            {{ loading ? '发送中...' : '发送验证码' }}
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { forgotPassword } from '../api.js'

export default {
  name: 'ForgotPassword',
  setup() {
    const router = useRouter()
    const loading = ref(false)
    
    const form = ref({
      email: ''
    })
    
    const handleForgotPassword = async () => {
      loading.value = true
      try {
        const res = await forgotPassword({ email: form.value.email })
        if (res?.data?.success === false) {
          throw new Error(res?.data?.error || '发送失败')
        }
        alert(res?.data?.message || '验证码已发送到您的邮箱')
        router.push({ path: '/reset-password', query: { email: form.value.email } })
      } catch (error) {
        console.error('发送重置链接失败:', error)
        alert(error?.response?.data?.error || error?.message || '发送失败')
      } finally {
        loading.value = false
      }
    }
    
    return {
      form,
      loading,
      handleForgotPassword
    }
  }
}
</script>

<style scoped>
.forgot-password-container {
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
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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

.forgot-password-card {
  background: white;
  padding: 40px;
  border-radius: 15px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
  position: relative;
  z-index: 1;
}
</style>
