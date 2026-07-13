<script setup lang="ts">
import { onMounted } from 'vue'
import NavBar from './components/NavBar.vue'
import Footer from './components/Footer.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

onMounted(() => {
  if (authStore.token && !authStore.user) {
    authStore.fetchCurrentUser()
  }
})
</script>

<template>
  <div class="app-container">
    <NavBar />
    <main class="main-content">
      <router-view />
    </main>
    <Footer />
  </div>
</template>

<style scoped>
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
}
</style>
