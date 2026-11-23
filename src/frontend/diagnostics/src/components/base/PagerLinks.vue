<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

/** A neighbour to go to: where, and the word its box shows. */
interface Neighbour {
  to: RouteLocationRaw
  label: string
}

/**
 * Previous and next, in a row of their own and in boxes of one fixed width, so a control clicked again and again stays under
 * the pointer (the operator, 10 Nov: the HTML view's "← s146 s148 →" sat after the heading path and moved with its length, "a no-go in design"). A box's word may be long or short, s9 or s147, a short title or a long one: it is cut to the box, whole
 * in its hover, and the box does not move. Where there is no neighbour, its box stays as an empty place, so the other does
 * not slide into it. Whatever follows in the slot, such as a page number to jump to, stands after the two boxes.
 */
withDefaults(defineProps<{
  previous: Neighbour | null
  next: Neighbour | null
  // the width of each box; one width for both, so the row's places never depend on a word
  width?: string
  label?: string
}>(), {
  width: '9rem',
  label: 'Previous and next',
})
</script>

<template>
  <nav class="pager" :aria-label="label" :style="{ '--pager-width': width }">
    <RouterLink v-if="previous" :to="previous.to" class="pager-link previous" data-part="previous" :title="previous.label">
      <span class="arrow" aria-hidden="true">←</span>
      <span class="pager-label">{{ previous.label }}</span>
    </RouterLink>
    <span v-else class="pager-link empty" aria-hidden="true" />
    <RouterLink v-if="next" :to="next.to" class="pager-link next" data-part="next" :title="next.label">
      <span class="pager-label">{{ next.label }}</span>
      <span class="arrow" aria-hidden="true">→</span>
    </RouterLink>
    <span v-else class="pager-link empty" aria-hidden="true" />
    <slot />
  </nav>
</template>

<style scoped>
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs);
}

/* a box of one width whatever its word: the place a pointer clicks again stays the place */
.pager-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  width: var(--pager-width);
  flex: none;
  box-sizing: border-box;
  padding: 1px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-accent);
  text-decoration: none;
}

.pager-link.next {
  justify-content: flex-end;
}

.pager-link:hover {
  background-color: var(--color-bg-hover);
  border-color: var(--color-accent);
}

.pager-link:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

/* where there is no neighbour, its place stays, quiet, and as tall as a box with a word: an empty box had no line and stood
   10px lower, centred in the row (found by #12's check on a code work's last file) */
.pager-link.empty {
  border-style: dashed;
  border-color: var(--color-row-rule);
}

.pager-link.empty::before {
  content: '\200b';
}

.pager-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arrow {
  flex: none;
}
</style>
