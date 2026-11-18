<script setup lang="ts">
import type { Count } from '@/types/api/page_types'

/** Why a page is in its state, in the check's own words; a reason given more than once says how often. */
defineProps<{
  reasons: Count[]
}>()
</script>

<template>
  <span class="reasons">
    <span v-for="reason in reasons" :key="reason.value" class="reason">
      {{ reason.value }}<span v-if="reason.count > 1" class="times"> ×{{ reason.count }}</span>
    </span>
  </span>
</template>

<style scoped>
.reasons {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
}

.times {
  color: var(--color-text-secondary);
}
</style>
