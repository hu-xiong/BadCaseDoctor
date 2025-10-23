<template>
  <div class="reset-password-container">
    <div class="background-animation"></div>
    <div class="reset-password-card">
      <div class="text-center mb-4">
        <h2 class="text-primary">重置密码</h2>
        <p class="text-muted">请输入新密码</p>
      </div>
      
      <form @submit.prevent="handleResetPassword">
        <div class="mb-3">
          <label for="password" class="form-label">新密码</label>
          <input
            type="password"
            class="form-control"
            id="password"
            v-model="form.password"
            required
            placeholder="请输入新密码"
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'

export default {
  name: 'ResetPassword',
  setup() {
    const router = useRouter()
    const loading = ref(false)
    
    const form = ref({
      password: '',
      confirmPassword: ''
    })
    
    const handleResetPassword = async () => {
      if (form.value.password !== form.value.confirmPassword) {
        alert('两次输入的密码不一致')
        return
      }
      
      loading.value = true
      try {
        // 模拟重置密码
        await new Promise(resolve => setTimeout(resolve, 1000))
        alert('密码重置成功')
        router.push('/login')
      } catch (error) {
        console.error('重置密码失败:', error)
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
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
}

.reset-password-card {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
  position: relative;
  z-index: 1;
  border: 1px solid rgba(255, 255, 255, 0.2);
  animation: slideIn 0.6s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.reset-password-card h2 {
  color: #333;
  font-weight: 600;
  margin-bottom: 10px;
}

.reset-password-card p {
  color: #666;
  margin-bottom: 30px;
}

.form-label {
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}

.form-control {
  border: 2px solid #e1e5e9;
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 14px;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.9);
}

.form-control:focus {
  border-color: #667eea;
  box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
  outline: none;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 10px;
  padding: 12px 24px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
}

.btn-primary:disabled {
  transform: none;
  box-shadow: none;
}

.text-decoration-none {
  color: #667eea;
  transition: color 0.3s ease;
}

.text-decoration-none:hover {
  color: #764ba2;
}

.text-center {
  text-align: center;
}

.mb-4 {
  margin-bottom: 1.5rem;
}

.mb-3 {
  margin-bottom: 1rem;
}

.mt-3 {
  margin-top: 1rem;
}

.d-grid {
  display: grid;
}

.gap-2 {
  gap: 0.5rem;
}

.text-muted {
  color: #6c757d;
}

.text-primary {
  color: #667eea;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  text-decoration: none;
  display: inline-block;
}

.btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.form-label {
  display: inline-block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.form-control {
  display: block;
  width: 100%;
  padding: 0.375rem 0.75rem;
  font-size: 1rem;
  font-weight: 400;
  line-height: 1.5;
  color: #495057;
  background-color: #fff;
  background-clip: padding-box;
  border: 1px solid #ced4da;
  border-radius: 0.25rem;
  transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

.form-control:focus {
  color: #495057;
  background-color: #fff;
  border-color: #667eea;
  outline: 0;
  box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
}
</style> 