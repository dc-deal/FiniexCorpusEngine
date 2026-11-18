<script setup lang="ts">
import StateMark from '@/components/StateMark.vue'
import type { Count } from '@/types/api/page_types'

/** How many pages are in each check state, as the API counted them. */
defineProps<{
  counts: Count[]
}>()
</script>

<template>
  <span class="state-counts">
    <span v-for="item in counts" :key="item.value" class="state-count" :data-state="item.value">
      <StateMark :state="item.value" />
      <span class="count">{{ item.count.toLocaleString('en') }}</span>
    </span>
  </span>
</template>

<style scoped>
.state-counts {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
}

.state-count {
  display: inline-flex;
  gap: var(--space-xs);
}
</style>
