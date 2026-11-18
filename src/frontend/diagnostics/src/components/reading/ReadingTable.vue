<script setup lang="ts">
import InlineSegments from '@/components/reading/InlineSegments.vue'
import type { Cell } from '@/types/api/page_types'

/**
 * A table of a page's text as the core's table parser gave its cells, each cell's prose as segments: a reading's table
 * block, and a person's correction of one (decision 204.a), so both are drawn alike and neither reaches the page as markup.
 * A table wider than its column scrolls inside the column instead of being cut off at the window's edge.
 */
defineProps<{
  rows: Cell[][]
}>()

const emit = defineEmits<{
  jump: [id: string]
}>()
</script>

<template>
  <div class="table-scroll">
    <table class="cells">
      <tbody>
        <tr v-for="(row, r) in rows" :key="r">
          <component
            :is="cell.header ? 'th' : 'td'"
            v-for="(cell, c) in row"
            :key="c"
            :rowspan="cell.rowspan > 1 ? cell.rowspan : undefined"
            :colspan="cell.colspan > 1 ? cell.colspan : undefined"
          >
            <InlineSegments :segments="cell.segments" @jump="emit('jump', $event)" />
          </component>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.table-scroll {
  overflow-x: auto;
}

.cells {
  border-collapse: collapse;
}

.cells th,
.cells td {
  border: 1px solid var(--color-border);
  padding: 2px var(--space-sm);
  text-align: left;
  vertical-align: top;
}
</style>
