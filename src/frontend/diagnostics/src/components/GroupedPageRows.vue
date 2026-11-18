<script setup lang="ts">
import { computed } from 'vue'
import DataTable from '@/components/base/DataTable.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import ReasonList from '@/components/ReasonList.vue'
import RouteWhy from '@/components/RouteWhy.vue'
import CategoryMark from '@/components/CategoryMark.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import StateMark from '@/components/StateMark.vue'
import { isDecided } from '@/listed_state'
import type { IssueRow } from '@/types/api/page_types'

/**
 * Pages of many works in one table, a work's title once above its pages, each page one click from its page view. The Why
 * column says why a page is served as it is, as a work's page table says it (159.a): the provider's words where it gave
 * some, else its route's level and why, the whole route in the hover. Used by the Issues and by the pages behind a figure
 * of the overview. On a narrow screen it scrolls in its own box.
 */
const props = defineProps<{
  rows: IssueRow[]
}>()

// the API sends the rows ordered by knowledge base and work, so runs are groups
const groups = computed(() => {
  const runs: { key: string, title: string, rows: IssueRow[] }[] = []
  for (const row of props.rows) {
    const key = `${row.knowledge_base}/${row.source_id}`
    const last = runs.at(-1)
    if (last?.key === key) last.rows.push(row)
    else runs.push({ key, title: row.title, rows: [row] })
  }
  return runs
})
</script>

<template>
  <!-- one grid for every such table, so the Issues' two lists, the pages to repair and those apart from the content,
       stand in the same columns (172.a); Reasons and Why share the rest. The library's table (179) -->
  <DataTable
    table-class="grouped-rows ruled"
    :columns="[{ width: '6rem' }, { width: '15rem' }, { width: '17rem' }, {}]"
    min-width="48rem"
    fixed
  >
    <template #head>
      <tr>
        <th>PDF page</th>
        <th>State</th>
        <th>Reasons</th>
        <th>Why</th>
      </tr>
    </template>
    <tbody v-for="group in groups" :key="group.key" :data-work="group.key">
      <tr class="work-row">
        <th colspan="4">
          {{ group.title }}
          <KnowledgeBaseMark :kb="group.rows[0].knowledge_base" />
          <span class="work-id">{{ group.rows[0].source_id }}</span>
        </th>
      </tr>
      <tr v-for="row in group.rows" :key="row.pdf_page" :data-page="`${group.key}/${row.pdf_page}`">
        <td>
          <!-- the link opens the page on its first finding (186), as the API names it -->
          <RouterLink :to="{ name: 'page', params: { kb: row.knowledge_base, work: row.source_id, page: row.pdf_page }, query: row.focus ? { focus: row.focus } : {} }">
            p. {{ row.pdf_page }}
          </RouterLink>
        </td>
        <!-- beside the judge's state a person's standing verdict (166.a) and a page's category where it is not content
             (172.a), wrapping beneath it where the column is narrow; one line, since a template drops a space at a break -->
        <td class="state-cell"><StateMark :state="row.check.state" :quiet="isDecided(row.listed_state)" /> <PersonStanding :mark="row.person" /> <CategoryMark :category="row.category" :said="row.category_said" :kind="row.page_kind" /></td>
        <td><ReasonList :reasons="row.check.reasons" /></td>
        <td class="why"><RouteWhy :row="row" /></td>
      </tr>
    </tbody>
  </DataTable>
</template>

<style scoped>
/* the work's title heads its pages: ink, not the muted look of a column heading */
.work-row th {
  color: var(--color-text-primary);
  white-space: normal;
  padding-top: var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.work-row .kb-mark,
.work-id {
  margin-left: var(--space-sm);
}

.work-id,
.why {
  color: var(--color-text-secondary);
}
</style>
