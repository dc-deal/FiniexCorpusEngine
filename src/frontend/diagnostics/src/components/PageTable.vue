<script setup lang="ts">
import { inject } from 'vue'
import { CHAPTER_MARKS } from '@/chapter_marks'
import { NOT_MEASURABLE, usd } from '@/cost_format'
import DataTable from '@/components/base/DataTable.vue'
import ReasonList from '@/components/ReasonList.vue'
import RouteWhy from '@/components/RouteWhy.vue'
import CategoryMark from '@/components/CategoryMark.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import StateMark from '@/components/StateMark.vue'
import { isDecided } from '@/listed_state'
import type { PageRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * Pages of one work, one row each, each opening its page: the flat list, or the pages of one unit of the work's own order.
 * Every such table of a work shares one column grid (decision 159.a): the short columns at fixed widths, Reasons and Why
 * sharing the rest, so PDF page, Printed, State, Class, Retry and Cost stand at the same place in every chapter. A page
 * that is fine prints nothing beyond its state: a printed number, reasons, a changed class and a retry appear only where
 * there is one. The Why column says why a page is served as it is, where that is worth saying: the provider's own sentence
 * where it gave one, else its route's level and why as the API parts them, the fallback with its glyph, the whole route in
 * the hover. The judge needs no column of its own: the state says a judged page is ok, and the reasons name a bad verdict
 * (the operator's 5.a). On a narrow screen the table keeps its columns and scrolls in its own box; the page never does.
 * A PDF page no reader has read (V1.b) stands in its own quiet state, "planned" beside it where a plan holds it, its Why
 * saying what serves it, and it cost nothing; its number opens its own view, its image and ladder (V2.a).
 */
withDefaults(defineProps<{
  rows: PageRow[]
  kb: KnowledgeBase
  work: string
  // how far, in rem, the table's block stands indented under its unit (161.a): its first column gives up that much, so
  // every other column keeps its place at every depth
  indent?: number
}>(), { indent: 0 })

// the first column's width before an indent: enough for "p. 1234" at four steps deep
const PAGE_COLUMN = 10

// the pages a chapter's count opened, marked as the block on show is (225.a); none outside a work's chapters
const marks = inject(CHAPTER_MARKS, null)

function classChange(row: PageRow): string {
  if (row.class_when_collected !== row.class_now) return `${row.class_when_collected} → ${row.class_now}`
  return row.class_now === 'ok' ? '' : row.class_now
}
</script>

<template>
  <!-- the library's table (179): its scroll box, its grid from the columns given here, its head's and cells' look -->
  <DataTable
    table-class="pages ruled"
    :columns="[{ width: `${PAGE_COLUMN - indent}rem` }, { width: '5rem' }, { width: '10rem' }, {}, {}, { width: '8rem' },
               { width: '3.5rem' }, { width: '6.5rem' }]"
    min-width="64rem"
    fixed
    sticky-head
  >
    <template #head>
      <tr>
        <th>PDF page</th>
        <th>Printed</th>
        <th>State</th>
        <th>Reasons</th>
        <th>Why</th>
        <th>Class</th>
        <th>Retry</th>
        <th class="number">Cost (USD)</th>
      </tr>
    </template>
    <tbody>
      <tr v-for="row in rows" :key="row.pdf_page" :class="{ marked: marks?.marked.value.has(row.pdf_page) }" :data-page="row.pdf_page">
        <td>
          <RouterLink :to="{ name: 'page', params: { kb, work, page: row.pdf_page } }">p. {{ row.pdf_page }}</RouterLink>
        </td>
        <td class="printed">{{ row.printed_label ?? '' }}</td>
        <!-- beside the judge's state a person's standing verdict (166.a) and a page's category where it is not content
             (172.a), wrapping beneath it where the column is narrow; one line, since a template drops a space at a break -->
        <td class="state-cell"><StateMark :state="row.check.state" :quiet="isDecided(row.listed_state)" :also="row.planned ? 'planned' : null" /> <PersonStanding :mark="row.person" /> <CategoryMark :category="row.category" :said="row.category_said" :kind="row.page_kind" /></td>
        <td><ReasonList :reasons="row.check.reasons" /></td>
        <td class="why"><RouteWhy :row="row" /></td>
        <td>{{ classChange(row) }}</td>
        <td class="number">{{ row.attempt > 0 ? row.attempt : '' }}</td>
        <td class="number cost">{{ !row.read ? '' : row.cost_usd === null ? NOT_MEASURABLE : usd(row.cost_usd) }}</td>
      </tr>
    </tbody>
  </DataTable>
</template>

<style scoped>
/* a page's own words may run long in a fixed column: they wrap anywhere rather than reach into the next */
td {
  overflow-wrap: anywhere;
}

/* a page a chapter's count opened (225.a), marked as the block on show is: the accent's edge on a raised row */
tr.marked > td {
  background-color: var(--color-bg-elevated);
}

tr.marked > td:first-child {
  box-shadow: inset 2px 0 0 var(--color-accent);
}

.printed,
.why,
.cost {
  color: var(--color-text-secondary);
}
</style>
