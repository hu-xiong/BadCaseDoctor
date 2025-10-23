<template>
  <div class="badcase-detail-container">
    <div class="badcase-header">
      <h1>BadCase详情</h1>
      <button class="btn btn-primary" @click="$router.go(-1)">
        返回
      </button>
    </div>
    
    <div class="badcase-content">
      <div class="badcase-info">
        <h2>BadCase信息</h2>
        <p>BadCase详情页面 - 显示BadCase的详细信息</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'BadcaseDetail'
}
</script>

<style scoped>
.badcase-detail-container {
  padding: 24px;
}

.badcase-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.badcase-header h1 {
  margin: 0;
  color: #333;
}

.badcase-content {
  background: white;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.badcase-info h2 {
  color: #333;
  margin-bottom: 16px;
}

.badcase-info p {
  color: #666;
  margin: 0;
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

.btn-primary {
  background: #667eea;
  color: white;
}

.btn-primary:hover {
  background: #5a6fd8;
}
</style> 