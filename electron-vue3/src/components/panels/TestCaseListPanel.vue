<template>
  <BadcaseListPanel v-bind="$attrs" />
</template>

<script>
import BadcaseListPanel from './BadcaseListPanel.vue'

export default {
  name: 'TestCaseListPanel',
  components: { BadcaseListPanel },
  inheritAttrs: false
}
</script>

