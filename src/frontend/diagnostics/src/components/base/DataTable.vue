<script setup lang="ts">
import { computed } from 'vue'

/**
 * The library's data table (decision 179, step 3): one scroll box, so a narrow screen scrolls the table and never the
 * page; one column grid where a view gives one (`columns`, each a width, the rest sharing what is left); one look for its
 * head, its cells, its links and its figures. A view gives its head's rows (`head`) and its bodies (the default slot) and
 * keeps only what is its own, such as a column's colour. `tableClass` names the table for the view's own rules and checks.
 *
 * A column may declare a `rank` (Y1.a's stage B, from the FiniexViewer's ranked list): 1 survives every width, 5 goes first,
 * absent is 1. Measured on the TABLE's own width, not the window's, through a container query, at the viewer's rungs of
 * 34, 48, 62 and 80 rem: below each, the columns of the rank above it give up their `col` and their cells, and their width
 * goes back to the others. The rank stands twice, on the column here and on each of its cells (`data-rank`), since the
 * view owns the cells; a browser check holds the two to agree. Taken from the viewer's list: the ladder, its rungs and the
 * twice-stated rank. Left out: its rows as buttons and the subgrid they need, its bands, its second grouping level, its
 * child records, detail and lead lines (the operator, 19 Nov: "we orient on the viewer, we do not imitate it").
 */
const props = withDefaults(defineProps<{
  columns?: { width?: string, class?: string, rank?: 1 | 2 | 3 | 4 | 5 }[]
  minWidth?: string
  // the columns hold their widths, as a grid every table of one kind shares
  fixed?: boolean
  // the table takes its column's whole width
  wide?: boolean
  // the head stays in view while the rows scroll beneath it
  stickyHead?: boolean
  tableClass?: string
}>(), { columns: () => [], minWidth: undefined, fixed: false, wide: false, stickyHead: false, tableClass: '' })

// a table that ranks a column measures its own width; one that ranks none stays as it was, unmeasured
const ranked = computed(() => props.columns.some(column => (column.rank ?? 1) > 1))
</script>

<template>
  <div class="data-scroll" :class="{ ranked }">
    <table class="data-table" :class="[tableClass, { fixed, wide, 'sticky-head': stickyHead }]" :style="minWidth ? { minWidth } : undefined">
      <colgroup v-if="columns.length">
        <col
          v-for="(column, at) in columns"
          :key="at"
          :class="column.class"
          :style="column.width ? { width: column.width } : undefined"
          :data-rank="column.rank"
        >
      </colgroup>
      <thead v-if="$slots.head">
        <slot name="head" />
      </thead>
      <slot />
    </table>
  </div>
</template>

<!-- not scoped: the cells are the view's own, given through the slots, and take the library's look by the table's class -->
<style>
.data-scroll {
  overflow-x: auto;
}

.data-table {
  border-collapse: collapse;
}

.data-table.fixed {
  table-layout: fixed;
}

.data-table.fixed,
.data-table.wide {
  width: 100%;
}

.data-table th {
  text-align: left;
  font-weight: normal;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.data-table > thead th {
  border-bottom: 1px solid var(--color-border);
}

.data-table.sticky-head > thead th {
  position: sticky;
  top: 0;
  background-color: var(--color-bg-base);
}

.data-table th,
.data-table td {
  padding: 2px var(--space-md) 2px 0;
  vertical-align: top;
}

.data-table a {
  color: var(--color-accent);
  text-decoration: none;
}

.data-table a:hover {
  text-decoration: underline;
}

.data-table .number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* a ranked table is its own measure: the rungs below read its width, never the window's */
.data-scroll.ranked {
  container: data-table / inline-size;
}

/* below each rung the columns of the rank above it go, their `col` with them, so their width returns to the others */
@container data-table (max-width: 80rem) {
  .data-table [data-rank='5'] {
    display: none;
  }
}

@container data-table (max-width: 62rem) {
  .data-table [data-rank='4'] {
    display: none;
  }
}

@container data-table (max-width: 48rem) {
  .data-table [data-rank='3'] {
    display: none;
  }
}

@container data-table (max-width: 34rem) {
  .data-table [data-rank='2'] {
    display: none;
  }
}
</style>
