<template>
  <div class="card-type-selector">
    <div class="card-type-selector-header">
      <span class="card-type-selector-title">{{ t('cardTypeSelector.title') }}</span>
    </div>
    <div class="card-type-selector-body">
      <div
        v-for="type in cardTypes"
        :key="type.value"
        class="card-type-item"
        @click="selectType(type)"
      >
        <span class="card-type-icon" :class="type.icon"></span>
        <span class="card-type-name">{{ type.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const emit = defineEmits(['select-type', 'close'])

const cardTypes = [
  {
    value: 'bug',
    label: t('cardTypeSelector.bug'),
    icon: 'bug-icon'
  },
  {
    value: 'badcase',
    label: t('cardTypeSelector.badcase'),
    icon: 'badcase-icon'
  },
  {
    value: 'testcase',
    label: t('cardTypeSelector.testcase'),
    icon: 'testcase-icon'
  }
]

const selectType = (type) => {
  emit('select-type', type)
}

const close = () => {
  emit('close')
}
</script>

<style scoped>
.card-type-selector {
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 8px 0;
  width: 180px;
}

.card-type-selector-header {
  margin-bottom: 6px;
  padding: 0 12px 6px;
  border-bottom: 1px solid #e8e8e8;
}

.card-type-selector-title {
  font-size: 13px;
  font-weight: 500;
  color: #666;
}

.card-type-selector-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-type-item {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.card-type-item:hover {
  background-color: #f0f5ff;
}

.card-type-icon {
  width: 18px;
  height: 18px;
  margin-right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  font-size: 11px;
}

.bug-icon {
  background-color: #ff4d4f;
  color: #fff;
}

.badcase-icon {
  background-color: #faad14;
  color: #fff;
}

.testcase-icon {
  background-color: #1890ff;
  color: #fff;
}

.card-type-name {
  font-size: 13px;
  color: #333;
}
</style>