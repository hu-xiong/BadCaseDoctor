<template>
  <BadcaseListPanel v-bind="$attrs" />
</template>

<script>
import BadcaseListPanel from './BadcaseListPanel.vue'

export default {
  name: 'BugListPanel',
  components: { BadcaseListPanel },
  inheritAttrs: false
}
</script>

