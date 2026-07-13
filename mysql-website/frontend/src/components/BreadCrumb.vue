<script setup lang="ts">
interface BreadcrumbItem {
  title: string
  path?: string
}

defineProps<{
  items: BreadcrumbItem[]
}>()

</script>

<template>
  <el-breadcrumb separator="/" class="breadcrumb">
    <el-breadcrumb-item :to="{ path: '/' }">Home</el-breadcrumb-item>
    <el-breadcrumb-item v-for="(item, index) in items" :key="index">
      <router-link v-if="item.path && index < items.length - 1" :to="item.path">
        {{ item.title }}
      </router-link>
      <span v-else>{{ item.title }}</span>
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<style scoped>
.breadcrumb {
  font-size: 13px;
  margin-bottom: 16px;
}

.breadcrumb :deep(.el-breadcrumb__inner) {
  color: var(--text-secondary);
}

.breadcrumb :deep(.el-breadcrumb__inner a) {
  color: var(--mysql-blue);
  font-weight: normal;
}

.breadcrumb :deep(.el-breadcrumb__inner a:hover) {
  color: var(--mysql-dark-blue);
}
</style>
