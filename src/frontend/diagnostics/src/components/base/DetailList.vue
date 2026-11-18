<script setup lang="ts">
/**
 * The library's key-value list (decision 179): each `dt` a name, each `dd` its value, in two aligned columns, the rows
 * parted by the fine rule every list shares. A view gives the pairs; the look is the list's.
 */
</script>

<template>
  <dl class="detail-list ruled">
    <slot />
  </dl>
</template>

<style scoped>
/* no gap in the grid: the shared row line runs through a pair, and the space it took stands inside the cells */
.detail-list {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  margin: var(--space-xs) 0 var(--space-sm);
}

.detail-list :slotted(dt),
.detail-list :slotted(dd) {
  padding: 2px var(--space-md) 2px 0;
}

.detail-list :slotted(dt) {
  color: var(--color-text-secondary);
}
</style>
