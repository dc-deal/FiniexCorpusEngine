<script setup lang="ts">
import ServedTally from '@/components/ServedTally.vue'
import StateMark from '@/components/StateMark.vue'
import type { StateCount } from '@/types/api/page_types'

/** How many pages are in each check state, as the API counted them, and how many of a state to look at are served. */
defineProps<{
  counts: StateCount[]
}>()
</script>

<template>
  <span class="state-counts">
    <span v-for="item in counts" :key="item.value" class="state-count" :data-state="item.value">
      <StateMark :state="item.value" />
      <span class="count">{{ item.count.toLocaleString('en') }}</span>
      <ServedTally :served="item.served" />
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
  flex-wrap: wrap;
  gap: var(--space-xs);
}

/* a state's own words wrap where the cell is narrower than them ("decided by an automated review"), as in a facet toggle:
   the mark keeps them on one line everywhere else (the operator, 18 Nov: they ran into the next column) */
.state-count :deep(.state-mark) {
  white-space: normal;
}
</style>
