<script setup lang="ts">
import PageTable from '@/components/PageTable.vue'
import type { PageRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * A unit's own pages in the chapters table (decision 161.a, the operator: "indentation is missing"): a tinted block with a rule on its
 * left, standing one step deeper than its unit's title at any depth, so it reads as the unit's and not as a second table. A
 * caption says whose pages they are and how many, the count the API's; then the pages, their head once, in the work's one
 * column grid: the block's first column gives up the indent, so Printed, State, Class, Retry and Cost stand at one x in
 * every block.
 */
defineProps<{
  caption: string
  rows: PageRow[]
  kb: KnowledgeBase
  work: string
  // in rem, one step deeper than the unit's title
  indent: number
}>()
</script>

<template>
  <div class="own-pages" :style="{ marginLeft: `${indent}rem` }" data-part="own-pages">
    <p class="own-caption">{{ caption }}</p>
    <PageTable :rows="rows" :kb="kb" :work="work" :indent="indent" />
  </div>
</template>

<style scoped>
.own-pages {
  margin-top: 2px;
  margin-bottom: var(--space-xs);
  background-color: var(--color-bg-surface);
  box-shadow: inset 2px 0 0 var(--color-border);
}

.own-caption {
  padding: 2px var(--space-sm);
  color: var(--color-text-secondary);
}

.own-pages :deep(.pages th) {
  background-color: var(--color-bg-surface);
}

.own-pages :deep(.pages th:first-child),
.own-pages :deep(.pages td:first-child) {
  padding-left: var(--space-sm);
}
</style>
