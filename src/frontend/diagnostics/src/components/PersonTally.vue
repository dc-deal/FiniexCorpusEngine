<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'

/**
 * How many of a state's pages a person accepted, rejected or noted, after the state's count (166.a: "ok 399 · 1
 * accepted"; 211.a: "decided by a person 8 · 7 accepted · 1 noted"), each with a person's glyph. Nothing where a
 * person decided none of them. The counts are the API's.
 */
defineProps<{
  accepted: number | null | undefined
  rejected: number | null | undefined
  noted?: number | null | undefined
}>()
</script>

<template>
  <span v-if="accepted || rejected || noted" class="person-tally">
    <span v-if="accepted" class="tally accepted" data-person="accepted">· <AppIcon name="person-accepted" /> {{ accepted }} accepted</span>
    <span v-if="rejected" class="tally rejected" data-person="rejected">· <AppIcon name="person-rejected" /> {{ rejected }} rejected</span>
    <span v-if="noted" class="tally noted" data-person="noted">· <AppIcon name="person-noted" /> {{ noted }} noted</span>
  </span>
</template>

<style scoped>
.person-tally {
  display: inline-flex;
  gap: var(--space-xs);
}

.tally {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.accepted {
  color: var(--color-positive);
}

.rejected {
  color: var(--color-error);
}

.noted {
  color: var(--color-text-secondary);
}
</style>
