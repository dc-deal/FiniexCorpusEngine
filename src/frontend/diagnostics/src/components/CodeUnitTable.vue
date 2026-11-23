<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import DataTable from '@/components/base/DataTable.vue'
import type { CodeUnit } from '@/types/api/code_types'

/** One file in the table: where its text opens, its name as its folder lists it, what the catalog says of its unit. */
export interface UnitRow {
  key: string
  name: string
  to: RouteLocationRaw | null
  unit: CodeUnit | null | undefined
}

/**
 * Code files with what the core's catalog says of each (#12), one look wherever units stand (221.a): a code work's folders and
 * the Librarian page's `code_catalog` answer. Each row: the file, opening its numbered text; its unit (function, indicator,
 * strategy), category and the inputs the code declares, each with its default as written; the sentence a model derived from
 * the code, said as derived and never as a quote; and the source its opening comment names, as written. A file the catalog
 * holds nothing of says so in its row.
 */
defineProps<{
  rows: UnitRow[]
}>()
</script>

<template>
  <DataTable
    table-class="code-units ruled"
    :columns="[{ width: '16rem' }, { width: '6.5rem' }, { width: '8.5rem' }, { width: '13rem' }, {}, { width: '13rem' }]"
    min-width="64rem"
    fixed
    data-part="code-units"
  >
    <template #head>
      <tr>
        <th>File</th>
        <th>Unit</th>
        <th>Category</th>
        <th>Inputs</th>
        <th>What it does</th>
        <th>Source named</th>
      </tr>
    </template>
    <tbody>
      <tr v-for="row in rows" :key="row.key" :data-file="row.key">
        <td class="file"><RouterLink v-if="row.to" :to="row.to">{{ row.name }}</RouterLink><span v-else>{{ row.name }}</span></td>
        <template v-if="row.unit">
          <td data-cell="unit">{{ row.unit.unit }}</td>
          <td data-cell="category">{{ row.unit.category }}</td>
          <td data-cell="inputs">
            <span v-for="input in row.unit.inputs" :key="input.name" class="input">{{ input.name }} = {{ input.default }}</span>
          </td>
          <!-- a model's sentence about the code: derived, never quoted, and it says which model made it -->
          <td data-cell="summary">
            <span class="summary">{{ row.unit.summary }}</span>
            <span class="derived" data-part="derived">{{ row.unit.summary_is ?? 'derived' }}, never quoted</span>
          </td>
          <td data-cell="source">{{ row.unit.source_named }}</td>
        </template>
        <td v-else colspan="5" data-cell="none"><span class="none">not in the catalog</span></td>
      </tr>
    </tbody>
  </DataTable>
</template>

<style scoped>
.file {
  overflow-wrap: anywhere;
}

/* each input on a line of its own, as the code declares them */
.input {
  display: block;
}

/* the derived sentence's marking, as a derived block's: its words in the ink of what stands beside, on a line of its own */
.derived {
  display: block;
  color: var(--color-text-secondary);
}

.none {
  color: var(--color-text-secondary);
}
</style>
