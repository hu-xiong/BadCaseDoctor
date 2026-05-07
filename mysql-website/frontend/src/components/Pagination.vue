<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  current: number
  total: number
  pageSize?: number
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10
})

const emit = defineEmits<{
  (e: 'update:current', value: number): void
  (e: 'change', value: number): void
}>()

const totalPages = computed(() => Math.ceil(props.total / props.pageSize))

const handlePageChange = (page: number) => {
  if (page >= 1 && page <= totalPages.value) {
    emit('update:current', page)
    emit('change', page)
  }
}
</script>

<template>
  <div class="pagination">
    <el-pagination
      :current-page="current"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      @current-change="handlePageChange"
    />
  </div>
</template>

<style scoped>
.pagination {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.pagination :deep(.el-pager li) {
  background: transparent;
}

.pagination :deep(.el-pager li.is-active) {
  background: var(--mysql-blue);
  color: #ffffff;
}

.pagination :deep(.el-pagination button) {
  background: transparent;
}
</style>
