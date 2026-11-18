<script setup lang="ts">
/**
 * The library's data table (decision 179, step 3): one scroll box, so a narrow screen scrolls the table and never the
 * page; one column grid where a view gives one (`columns`, each a width, the rest sharing what is left); one look for its
 * head, its cells, its links and its figures. A view gives its head's rows (`head`) and its bodies (the default slot) and
 * keeps only what is its own, such as a column's colour. `tableClass` names the table for the view's own rules and checks.
 */
withDefaults(defineProps<{
  columns?: { width?: string, class?: string }[]
  minWidth?: string
  // the columns hold their widths, as a grid every table of one kind shares
  fixed?: boolean
  // the table takes its column's whole width
  wide?: boolean
  // the head stays in view while the rows scroll beneath it
  stickyHead?: boolean
  tableClass?: string
}>(), { columns: () => [], minWidth: undefined, fixed: false, wide: false, stickyHead: false, tableClass: '' })
</script>

<template>
  <div class="data-scroll">
    <table class="data-table" :class="[tableClass, { fixed, wide, 'sticky-head': stickyHead }]" :style="minWidth ? { minWidth } : undefined">
      <colgroup v-if="columns.length">
        <col v-for="(column, at) in columns" :key="at" :class="column.class" :style="column.width ? { width: column.width } : undefined">
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
</style>
