<template>
  <div class="payment-result cancel">
    <div class="result-card">
      <div class="icon">✕</div>
      <h1>Payment Cancelled</h1>
      <p>Your payment was cancelled. No charges were made.</p>
      <button class="back-btn" @click="$router.push('/subscription')">
        Back to Plans
      </button>
    </div>
  </div>
</template>

<style scoped>
.payment-result {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.result-card {
  background: white;
  padding: 60px 80px;
  border-radius: 20px;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}

.icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: #f44336;
  color: white;
  font-size: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 30px;
}

h1 {
  color: #333;
  margin-bottom: 15px;
}

p {
  color: #666;
  margin-bottom: 30px;
}

.back-btn {
  padding: 15px 40px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  cursor: pointer;
}
</style>
