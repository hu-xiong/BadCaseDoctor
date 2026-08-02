<template>
  <div class="login-container">
    <div class="background-animation"></div>
    <div class="login-card">
      <div class="text-center mb-4">
        <h2 class="text-primary">BadCase Doctor</h2>
        <p class="text-muted">{{ t('auth.subtitle') }}</p>
      </div>
      
      <form @submit.prevent="handleLogin">
        <div class="mb-3">
          <label for="email" class="form-label">{{ t('auth.email') }}</label>
          <input
            type="email"
            class="form-control"
            id="email"
            v-model="form.email"
            required
            :placeholder="t('auth.emailPlaceholder')"
          />
        </div>
        
        <div class="mb-3">
          <label for="password" class="form-label">{{ t('auth.password') }}</label>
          <input
            type="password"
            class="form-control"
            id="password"
            v-model="form.password"
            required
            :placeholder="t('auth.passwordPlaceholder')"
          />
        </div>
        
        <div class="d-grid gap-2">
          <button type="submit" class="btn btn-primary" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2"></span>
            {{ loading ? t('auth.loggingIn') : t('auth.login') }}
          </button>
        </div>
        

      </form>
      
      <div class="mt-3 text-center">
        <a href="#" @click.prevent="showRegister = true" class="text-decoration-none">
          {{ t('auth.registerLink') }}
        </a>
      </div>
      
      <div class="mt-2 text-center">
        <a href="#" @click.prevent="showForgotPassword = true" class="text-decoration-none">
          {{ t('auth.forgotPassword') }}
        </a>
      </div>
    </div>
    
    <!-- 注册模态框 -->
    <div v-if="showRegister" class="modal fade show d-block" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ t('auth.registerTitle') }}</h5>
            <button type="button" class="btn-close" @click="showRegister = false"></button>
          </div>
          <div class="modal-body">
            <form @submit.prevent="handleRegister">
              <div class="mb-3">
                <label for="reg-email" class="form-label">{{ t('auth.email') }}</label>
                <div class="input-group">
                  <input
                    type="email"
                    class="form-control"
                    id="reg-email"
                    v-model="registerForm.email"
                    required
                    :placeholder="t('auth.emailPlaceholder')"
                  />
                  <button
                    type="button"
                    class="btn btn-outline-secondary"
                    @click="sendVerificationCode"
                    :disabled="codeSending"
                  >
                    {{ codeSending ? t('auth.sendingCode') : t('auth.sendCode') }}
                  </button>
                </div>
              </div>
              
              <div class="mb-3">
                <label for="verification-code" class="form-label">{{ t('auth.verificationCode') }}</label>
                <input
                  type="text"
                  class="form-control"
                  id="verification-code"
                  v-model="registerForm.verification_code"
                  required
                  :placeholder="t('auth.codePlaceholder')"
                />
              </div>
              
              <div class="mb-3">
                <label for="reg-name" class="form-label">{{ t('auth.name') }}</label>
                <input
                  type="text"
                  class="form-control"
                  id="reg-name"
                  v-model="registerForm.name"
                  required
                  :placeholder="t('auth.namePlaceholder')"
                />
              </div>
              
              <div class="mb-3">
                <label for="reg-password" class="form-label">{{ t('auth.password') }}</label>
                <input
                  type="password"
                  class="form-control"
                  id="reg-password"
                  v-model="registerForm.password"
                  required
                  :placeholder="t('auth.passwordPlaceholder')"
                />
              </div>
              
              <div class="d-grid gap-2">
                <button type="submit" class="btn btn-primary" :disabled="registerLoading">
                  {{ registerLoading ? t('auth.registering') : t('auth.register') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 忘记密码模态框 -->
    <div v-if="showForgotPassword" class="modal fade show d-block" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ t('auth.forgotTitle') }}</h5>
            <button type="button" class="btn-close" @click="showForgotPassword = false"></button>
          </div>
          <div class="modal-body">
            <form @submit.prevent="handleForgotPassword">
              <div class="mb-3">
                <label for="forgot-email" class="form-label">{{ t('auth.email') }}</label>
                <input
                  type="email"
                  class="form-control"
                  id="forgot-email"
                  v-model="forgotPasswordForm.email"
                  required
                  :placeholder="t('auth.emailPlaceholder')"
                />
              </div>
              
              <div class="d-grid gap-2">
                <button type="submit" class="btn btn-primary" :disabled="forgotPasswordLoading">
                  {{ forgotPasswordLoading ? t('auth.sendingReset') : t('auth.sendReset') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { login, register, sendVerificationCode, forgotPassword } from '../api.js'
import { setUser } from '../store/user.js'
import { navigateAfterAuth } from '../utils/loginNavigate.js'

export default {
  name: 'Login',
  setup() {
    const router = useRouter()
    const { t } = useI18n()
    
    const form = reactive({
      email: '',
      password: ''
    })
    
    const registerForm = reactive({
      email: '',
      name: '',
      password: '',
      verification_code: ''
    })
    
    const forgotPasswordForm = reactive({
      email: ''
    })
    
    const loading = ref(false)
    const showRegister = ref(false)
    const showForgotPassword = ref(false)
    const codeSending = ref(false)
    const registerLoading = ref(false)
    const forgotPasswordLoading = ref(false)
    
    const handleLogin = async () => {
      loading.value = true
      try {
        const response = await login({
          email: form.email,
          password: form.password
        })
        
        if (response.data.success) {
          setUser(response.data.user)
          await navigateAfterAuth(router, { projectId: response.data.project_id })
        } else {
          alert(response.data.error || t('auth.loginFailed'))
        }
      } catch (error) {
        console.error('登录失败:', error)
        if (error.response) {
          alert(t('auth.loginErrorDetail', { msg: error.response.data?.error || error.response.statusText }))
        } else {
          alert(t('auth.loginErrorDetail', { msg: error.message }))
        }
      } finally {
        loading.value = false
      }
    }
    
    const handleRegister = async () => {
      registerLoading.value = true
      try {
        const response = await register({
          email: registerForm.email,
          name: registerForm.name,
          password: registerForm.password,
          verification_code: registerForm.verification_code
        })
        
        if (response.data.success) {
          showRegister.value = false
          alert(t('auth.registerSuccess'))
          setUser(response.data.user)
          await navigateAfterAuth(router, { projectId: response.data.project_id })
        } else {
          alert(response.data.error || t('auth.registerFailed'))
        }
      } catch (error) {
        console.error('注册失败:', error)
        if (error.response) {
          alert(t('auth.registerErrorDetail', { msg: error.response.data?.error || error.response.statusText }))
        } else {
          alert(t('auth.registerErrorDetail', { msg: error.message }))
        }
      } finally {
        registerLoading.value = false
      }
    }
    
    const handleSendVerificationCode = async () => {
      if (!registerForm.email) {
        alert(t('auth.enterEmailFirst'))
        return
      }
      
      codeSending.value = true
      try {
        const response = await sendVerificationCode({
          email: registerForm.email
        })
        
        if (response.data.success) {
        alert(t('auth.codeSent'))
        } else {
          alert(response.data.error || t('auth.sendCodeFailed'))
        }
      } catch (error) {
        console.error('发送验证码失败:', error)
        if (error.response) {
          alert(t('auth.sendCodeErrorDetail', { msg: error.response.data?.error || error.response.statusText }))
        } else {
          alert(t('auth.sendCodeErrorDetail', { msg: error.message }))
        }
      } finally {
        codeSending.value = false
      }
    }
    
    const handleForgotPassword = async () => {
      forgotPasswordLoading.value = true
      try {
        const res = await forgotPassword({ email: forgotPasswordForm.email })
        if (res?.data?.success === false) {
          throw new Error(res?.data?.error || t('auth.sendResetFailed'))
        }
        showForgotPassword.value = false
        alert(t('auth.resetSent'))
        router.push({
          path: '/reset-password',
          query: { email: forgotPasswordForm.email }
        })
      } catch (error) {
        console.error('发送重置链接失败:', error)
        alert(error?.response?.data?.error || error?.message || t('auth.sendResetFailed'))
      } finally {
        forgotPasswordLoading.value = false
      }
    }

    return {
      t,
      form,
      registerForm,
      forgotPasswordForm,
      loading,
      showRegister,
      showForgotPassword,
      codeSending,
      registerLoading,
      forgotPasswordLoading,
      handleLogin,
      handleRegister,
      sendVerificationCode: handleSendVerificationCode,
      handleForgotPassword
    }
  }
}
</script>

<style scoped>
.login-container {
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

.login-card {
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

.login-card h2 {
  color: #333;
  font-weight: 600;
  margin-bottom: 10px;
}

.login-card p {
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

.modal {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(5px);
}

.modal-content {
  border-radius: 15px;
  border: none;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.modal-header {
  border-bottom: 1px solid #e1e5e9;
  padding: 20px 25px;
}

.modal-body {
  padding: 25px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #666;
}

.btn-close:hover {
  color: #333;
}

.input-group .btn {
  border-radius: 0 10px 10px 0;
  border-left: none;
}

.input-group .form-control {
  border-radius: 10px 0 0 10px;
}

/* 响应式设计 */
@media (max-width: 480px) {
  .login-card {
    margin: 20px;
    padding: 30px 20px;
  }
}
</style> 
