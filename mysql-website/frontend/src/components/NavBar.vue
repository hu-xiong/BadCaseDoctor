<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isScrolled = ref(false)

const navItems = [
  { name: 'Products', path: '/products', hasDropdown: true },
  { name: 'Downloads', path: '/downloads' },
  { name: 'Docs', path: '/docs' },
  { name: 'Community', path: '/community' },
  { name: 'Cases', path: '/cases' },
  { name: 'Resources', path: '/resources', hasDropdown: true }
]

const isAuthenticated = computed(() => authStore.isAuthenticated)
const user = computed(() => authStore.user)

const handleScroll = () => {
  isScrolled.value = window.scrollY > 20
}

const handleLogout = async () => {
  await authStore.logoutAction()
  ElMessage.success('Logged out successfully')
  router.push('/')
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<template>
  <header class="navbar" :class="{ 'navbar-scrolled': isScrolled }">
    <div class="navbar-container">
      <router-link to="/" class="logo">
        <img src="/mysql-logo.svg" alt="MySQL" class="logo-img" />
      </router-link>

      <nav class="nav-menu">
        <div
          v-for="item in navItems"
          :key="item.name"
          class="nav-item"
          :class="{ 'nav-item-active': route.path.startsWith(item.path) }"
        >
          <router-link :to="item.path" class="nav-link">
            {{ item.name }}
          </router-link>
          <span v-if="item.hasDropdown" class="dropdown-arrow">▼</span>
        </div>
      </nav>

      <div class="nav-actions">
        <div class="search-box">
          <el-input
            v-model="searchQuery"
            placeholder="Search..."
            :prefix-icon="Search"
            class="search-input"
            @keyup.enter="handleSearch"
          />
        </div>

        <router-link v-if="!isAuthenticated" to="/login" class="btn btn-login">
          Sign In
        </router-link>

        <el-dropdown v-else trigger="click">
          <div class="user-avatar">
            <el-avatar :size="32" :src="user?.avatar">
              {{ user?.username?.charAt(0).toUpperCase() }}
            </el-avatar>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push('/profile')">Profile</el-dropdown-item>
              <el-dropdown-item @click="router.push('/settings')">Settings</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">Logout</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </header>
</template>

<script lang="ts">
const searchQuery = ref('')
const handleSearch = () => {
  console.log('Search:', searchQuery.value)
}
</script>

<style scoped>
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.navbar-scrolled {
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
}

.navbar-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: center;
}

.logo-img {
  height: 32px;
}

.nav-menu {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
}

.nav-link {
  padding: 8px 16px;
  color: #333;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.3s;
}

.nav-link:hover {
  color: var(--mysql-blue);
}

.nav-item-active .nav-link {
  color: var(--mysql-blue);
}

.dropdown-arrow {
  font-size: 10px;
  margin-left: 4px;
  color: #999;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.search-input {
  width: 200px;
}

.btn-login {
  padding: 8px 20px;
  background: var(--mysql-blue);
  color: #fff;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.3s;
}

.btn-login:hover {
  background: var(--mysql-dark-blue);
  color: #fff;
}

.user-avatar {
  cursor: pointer;
}

@media (max-width: 768px) {
  .nav-menu {
    display: none;
  }
  
  .search-box {
    display: none;
  }
}
</style>
