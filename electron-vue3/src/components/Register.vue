<template>
  <div class="register-container">
    <div class="container">
      <div class="row justify-content-center">
        <div class="col-md-6 col-lg-4">
          <div class="card mt-5">
            <div class="card-header text-center">
              <h4>用户注册</h4>
            </div>
            <div class="card-body">
              <form @submit.prevent="handleRegister">
                <div class="mb-3">
                  <label for="username" class="form-label">用户名</label>
                  <BFormInput
                    id="username"
                    v-model="form.username"
                    type="text"
                    placeholder="请输入用户名"
                    required
                  />
                </div>
                
                <div class="mb-3">
                  <label for="email" class="form-label">邮箱</label>
                  <BFormInput
                    id="email"
                    v-model="form.email"
                    type="email"
                    placeholder="请输入邮箱"
                    required
                  />
                </div>
                
                <div class="mb-3">
                  <label for="password" class="form-label">密码</label>
                  <BFormInput
                    id="password"
                    v-model="form.password"
                    type="password"
                    placeholder="请输入密码"
                    required
                  />
                </div>
                
                <div class="mb-3">
                  <label for="confirmPassword" class="form-label">确认密码</label>
                  <BFormInput
                    id="confirmPassword"
                    v-model="form.confirmPassword"
                    type="password"
                    placeholder="请再次输入密码"
                    required
                  />
                </div>
                
                <div class="d-grid gap-2">
                  <BButton variant="primary" type="submit" :disabled="loading">
                    {{ loading ? '注册中...' : '注册' }}
                  </BButton>
                </div>
                
                <div class="text-center mt-3">
                  <small>
                    已有账号？
                    <a href="#" @click.prevent="goLogin">立即登录</a>
                  </small>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { BButton, BFormInput } from 'bootstrap-vue-next'

export default {
  name: 'Register',
  components: {
    BButton,
    BFormInput
  },
  setup() {
    const router = useRouter()
    const loading = ref(false)
    
    const form = ref({
      username: '',
      email: '',
      password: '',
      confirmPassword: ''
    })
    
    const handleRegister = async () => {
      if (form.value.password !== form.value.confirmPassword) {
        alert('两次输入的密码不一致')
        return
      }
      
      loading.value = true
      try {
        const response = await fetch('/api/register', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            username: form.value.username,
            email: form.value.email,
            password: form.value.password
          })
        })
        
        if (response.ok) {
          alert('注册成功！请登录')
          router.push('/login')
        } else {
          const error = await response.json()
          alert(error.message || '注册失败')
        }
      } catch (error) {
        console.error('注册失败:', error)
        alert('注册失败，请重试')
      } finally {
        loading.value = false
      }
    }
    
    const goLogin = () => {
      router.push('/login')
    }
    
    return {
      form,
      loading,
      handleRegister,
      goLogin
    }
  }
}
</script>

<style scoped>
.register-container {
  min-height: 100vh;
  background-color: #f8f9fa;
  padding: 20px 0;
}

.card {
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: none;
}

.card-header {
  background-color: #fff;
  border-bottom: 1px solid #dee2e6;
}
</style> 