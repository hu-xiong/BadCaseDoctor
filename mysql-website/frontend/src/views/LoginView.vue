<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref()
const loading = computed(() => authStore.loading)

const form = ref({
  email: '',
  password: '',
  remember: false
})

const rules = {
  email: [
    { required: true, message: 'Please enter email', trigger: 'blur' },
    { type: 'email', message: 'Please enter a valid email', trigger: 'blur' }
  ],
  password: [
    { required: true, message: 'Please enter password', trigger: 'blur' },
    { min: 6, message: 'Password must be at least 6 characters', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const result = await authStore.loginAction({
    email: form.value.email,
    password: form.value.password
  })

  if (result.success) {
    ElMessage.success('Login successful!')
    const redirect = route.query.redirect as string || '/'
    router.push(redirect)
  } else {
    ElMessage.error(result.message || 'Login failed')
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-container">
      <div class="auth-card card">
        <div class="auth-header">
          <router-link to="/" class="logo">
            <img src="/mysql-logo.svg" alt="MySQL" />
          </router-link>
          <h1>Welcome Back</h1>
          <p>Sign in to your MySQL account</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="auth-form"
          @submit.prevent="handleLogin"
        >
          <el-form-item prop="email">
            <el-input
              v-model="form.email"
              placeholder="Email address"
              size="large"
              prefix-icon="User"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="Password"
              size="large"
              prefix-icon="Lock"
              show-password
            />
          </el-form-item>

          <div class="form-options">
            <el-checkbox v-model="form.remember">Remember me</el-checkbox>
            <router-link to="/forgot-password" class="forgot-link">
              Forgot password?
            </router-link>
          </div>

          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="submit-btn"
            @click="handleLogin"
          >
            Sign In
          </el-button>
        </el-form>

        <div class="auth-footer">
          <p>
            Don't have an account?
            <router-link to="/register">Create one</router-link>
          </p>
        </div>

        <div class="divider">
          <span>or continue with</span>
        </div>

        <div class="social-login">
          <el-button size="large" plain>
            <i class="el-icon-ship"></i>
            Oracle Account
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { User, Lock } from '@element-plus/icons-vue'
export default {
  components: { User, Lock }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 40px 20px;
}

.auth-container {
  width: 100%;
  max-width: 440px;
}

.auth-card {
  padding: 48px 40px;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo img {
  height: 40px;
  margin-bottom: 24px;
}

.auth-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.auth-header p {
  font-size: 14px;
  color: var(--text-secondary);
}

.auth-form {
  margin-bottom: 24px;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.forgot-link {
  font-size: 14px;
  color: var(--mysql-blue);
}

.submit-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
}

.auth-footer {
  text-align: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.auth-footer a {
  color: var(--mysql-blue);
  font-weight: 500;
}

.divider {
  text-align: center;
  margin: 24px 0;
  position: relative;
}

.divider::before,
.divider::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 40%;
  height: 1px;
  background: var(--border-color);
}

.divider::before {
  left: 0;
}

.divider::after {
  right: 0;
}

.divider span {
  background: #ffffff;
  padding: 0 12px;
  color: var(--text-secondary);
  font-size: 13px;
  position: relative;
}

.social-login {
  display: flex;
  gap: 12px;
}

.social-login .el-button {
  flex: 1;
}
</style>
