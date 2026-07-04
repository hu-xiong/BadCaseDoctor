<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref()
const loading = computed(() => authStore.loading)
const agreement = ref(false)

const form = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const validateConfirmPassword = (_rule: any, value: any, callback: any) => {
  if (value !== form.value.password) {
    callback(new Error('Passwords do not match'))
  } else {
    callback()
  }
}

const rules = {
  username: [
    { required: true, message: 'Please enter username', trigger: 'blur' },
    { min: 3, max: 20, message: 'Username must be 3-20 characters', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: 'Username can only contain letters, numbers and underscores', trigger: 'blur' }
  ],
  email: [
    { required: true, message: 'Please enter email', trigger: 'blur' },
    { type: 'email', message: 'Please enter a valid email', trigger: 'blur' }
  ],
  password: [
    { required: true, message: 'Please enter password', trigger: 'blur' },
    { min: 8, message: 'Password must be at least 8 characters', trigger: 'blur' },
    {
      pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
      message: 'Password must contain uppercase, lowercase and number',
      trigger: 'blur'
    }
  ],
  confirmPassword: [
    { required: true, message: 'Please confirm password', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const handleRegister = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  if (!agreement.value) {
    ElMessage.warning('Please agree to the terms and conditions')
    return
  }

  const result = await authStore.registerAction({
    username: form.value.username,
    email: form.value.email,
    password: form.value.password
  })

  if (result.success) {
    ElMessage.success('Registration successful!')
    router.push('/')
  } else {
    ElMessage.error(result.message || 'Registration failed')
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
          <h1>Create Account</h1>
          <p>Join the MySQL community</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="auth-form"
          @submit.prevent="handleRegister"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              placeholder="Username"
              size="large"
              prefix-icon="User"
            />
          </el-form-item>

          <el-form-item prop="email">
            <el-input
              v-model="form.email"
              placeholder="Email address"
              size="large"
              prefix-icon="Message"
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

          <el-form-item prop="confirmPassword">
            <el-input
              v-model="form.confirmPassword"
              type="password"
              placeholder="Confirm password"
              size="large"
              prefix-icon="Lock"
              show-password
            />
          </el-form-item>

          <div class="agreement">
            <el-checkbox v-model="agreement">
              I agree to the
              <a href="/terms" target="_blank">Terms of Service</a>
              and
              <a href="/privacy" target="_blank">Privacy Policy</a>
            </el-checkbox>
          </div>

          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="submit-btn"
            @click="handleRegister"
          >
            Create Account
          </el-button>
        </el-form>

        <div class="auth-footer">
          <p>
            Already have an account?
            <router-link to="/login">Sign in</router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { User, Lock, Message } from '@element-plus/icons-vue'
export default {
  components: { User, Lock, Message }
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

.agreement {
  margin-bottom: 24px;
  font-size: 13px;
}

.agreement a {
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
</style>
