<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()
const user = authStore.user

const form = ref({
  username: user?.username || '',
  email: user?.email || ''
})

const handleSave = () => {
  ElMessage.success('Profile updated successfully!')
}
</script>

<template>
  <div class="profile-page">
    <div class="container">
      <div class="profile-layout">
        <aside class="profile-sidebar">
          <div class="user-info card">
            <div class="avatar">
              <el-avatar :size="80">
                {{ user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
            </div>
            <h3>{{ user?.username }}</h3>
            <p>{{ user?.email }}</p>
          </div>
          
          <nav class="profile-nav">
            <router-link to="/profile" class="nav-item active">
              <i class="el-icon-user"></i>
              Profile
            </router-link>
            <router-link to="/settings" class="nav-item">
              <i class="el-icon-setting"></i>
              Settings
            </router-link>
            <router-link to="/notifications" class="nav-item">
              <i class="el-icon-bell"></i>
              Notifications
            </router-link>
          </nav>
        </aside>

        <main class="profile-content">
          <div class="card">
            <h2>Edit Profile</h2>
            <el-form :model="form" label-position="top">
              <el-form-item label="Username">
                <el-input v-model="form.username" />
              </el-form-item>
              <el-form-item label="Email">
                <el-input v-model="form.email" type="email" />
              </el-form-item>
              <el-form-item label="Bio">
                <el-input type="textarea" :rows="4" placeholder="Tell us about yourself" />
              </el-form-item>
              <el-button type="primary" @click="handleSave">
                Save Changes
              </el-button>
            </el-form>
          </div>

          <div class="card">
            <h2>Change Password</h2>
            <el-form label-position="top">
              <el-form-item label="Current Password">
                <el-input type="password" placeholder="Enter current password" />
              </el-form-item>
              <el-form-item label="New Password">
                <el-input type="password" placeholder="Enter new password" />
              </el-form-item>
              <el-form-item label="Confirm New Password">
                <el-input type="password" placeholder="Confirm new password" />
              </el-form-item>
              <el-button type="primary">
                Update Password
              </el-button>
            </el-form>
          </div>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  padding-top: 64px;
  min-height: calc(100vh - 64px);
  background: var(--bg-light);
}

.profile-page .container {
  padding: 48px 24px;
}

.profile-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 32px;
  max-width: 1000px;
  margin: 0 auto;
}

.profile-sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.user-info {
  text-align: center;
  padding: 32px 24px;
}

.avatar {
  margin-bottom: 16px;
}

.user-info h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.user-info p {
  font-size: 14px;
  color: var(--text-secondary);
}

.profile-nav {
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  color: var(--text-secondary);
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover {
  background: var(--bg-light);
  color: var(--mysql-blue);
}

.nav-item.active {
  background: rgba(0, 117, 143, 0.1);
  color: var(--mysql-blue);
  font-weight: 500;
}

.profile-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.profile-content h2 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
}
</style>
