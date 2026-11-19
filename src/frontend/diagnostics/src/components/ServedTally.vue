<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'

/**
 * How many of a state's pages to look at the core serves all the same, after the state's count ("issue 9 · 9 served"):
 * an issue whose judge's findings lie on blocks never quoted (133.b) is served, its reading quoted, while a blocked page
 * serves its text layer. The operator, 18 Nov: "issue 9" read as nine pages held back where the core held back none.
 * The state stays the core's word; the count is the API's (`StateCount.served`). Nothing where none is served.
 */
defineProps<{
  served: number | null | undefined
  // on a line of its own, beneath a figure (the sources list's columns, B3.a): without the dot that joins it to a count
  alone?: boolean
}>()
</script>

<template>
  <span v-if="served" class="served-tally" data-part="served"><template v-if="!alone">· </template><AppIcon name="quoted" /> {{ served }} served</span>
</template>

<style scoped>
.served-tally {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-text-secondary);
}
</style>
