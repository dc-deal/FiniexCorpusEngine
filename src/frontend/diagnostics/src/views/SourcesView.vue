<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import DataTable from '@/components/base/DataTable.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import ServedTally from '@/components/ServedTally.vue'
import StateMark from '@/components/StateMark.vue'
import { applyFacets, sortRows } from '@/components/base/facet_filter'
import { groupRows, keepOpenGroups, openGroups } from '@/row_groups'
import { useSourceStore } from '@/stores/source_store'
import type { KnowledgeBase, Work } from '@/types/api/source_types'
import type { FacetDefinition, SortDefinition } from '@/types/facet_types'
import { useFacetState } from '@/use_facet_state'
import { useScrollRestore } from '@/use_scroll_restore'
import { counted } from '@/counted'

/**
 * Every work of every knowledge base served, one row each, each marked with its knowledge base: the free catalog in its
 * order, then the licensed works, which have no catalog entry and so only an id and a title. Its structure says how the
 * work is cut, by its format's model (the operator's 4.a): a work read page by page shows its pages' check states and opens its page
 * list; an HTML work its sections by heading and their chunks, and opens its outline (the operator's 6.a).
 *
 * The facet bar narrows it (the operator's Y1.a, 19 Nov): by knowledge base, format, topic, structure and series, a search
 * over title, authors and id, sorted by title, author or year. The parts of one series stand together under a heading,
 * closed, where the first of them would stand in the sort, in their parts' order. A reload (F5) brings back the bar and
 * where the reader stood.
 */
const store = useSourceStore()
// Work and Authors share what the fixed columns leave, each on one line, the whole text in the row's card. A fixed column is
// as wide as its longest word and its gap to the next (`--space-md`, the cells' right padding): "licensed" with its glyph,
// "12th edition", "trading_finance"; so none of their words is ever split, and nothing runs into the next cell (the
// operator, 18 Nov: "trading_financ|e", "5th editio|n"). Publisher and licence stand in the card only: long, and 63 of 78
// works carried one licence (measured 19 Nov). Each work's pages and the five states a reader acts on or weighs are figure
// columns, so the figures line up and the list sorts by them (the operator's B3.a, 19 Nov); the rarer states, an automated
// review's, a stopped work's and the pages not checked yet, stand in the card. Ranked so every width keeps the work's
// column at 8 rem at least (B2, its ladder taken again with the figures, 19 Nov): the work and its pages stay; then issue
// and blocked; then the knowledge base, ok and the authors; then ok unjudged and decided by a person; the year, the format
// and the topic last. Measured: with the knowledge base a rung earlier, the work's column kept 121 px at 34 rem
const fixed = (width: string, rank?: 2 | 3 | 4 | 5) => ({ width: `calc(${width} + var(--space-md))`, rank })
// the states with a figure column of their own, in the core's order
const FIGURE_STATES = [
  { state: 'ok', column: fixed('6ch', 3) },
  { state: 'ok_unjudged', column: fixed('10ch', 4) },
  { state: 'issue', column: fixed('12ch', 2) },
  { state: 'blocked', column: fixed('9ch', 2) },
  { state: 'decided_by_a_person', column: fixed('9ch', 4) },
]
const COLUMNS = [{}, fixed('11ch', 3), fixed('14ch'), ...FIGURE_STATES.map(one => one.column), { rank: 3 as const },
  fixed('12ch', 5), fixed('5ch', 5), fixed('16ch', 5)]
// a series' heading stands in the work's column and leaves an empty cell in each other, each with its column's rank: a
// cell spanning all seven made a narrow table, which keeps two, add five columns of its own and squeeze the work's to a
// letter (measured at 390 px, 19 Nov)
const AFTER_WORK = COLUMNS.slice(1).map(column => column.rank)

/** A work's whole record under the pointer, what its row shortens or leaves out: the rows the API gave, an empty one left out. */
function cardRows(work: Work): { label: string, value: string | null | undefined }[] {
  const series = work.series
    ? `${work.series.title}, part ${work.series.part} of ${work.series.of}${work.series.version ? ` (${work.series.version})` : ''}`
    : null
  return [
    { label: 'id', value: work.id },
    { label: 'authors', value: work.authors },
    { label: 'publisher', value: work.publisher },
    { label: 'year', value: work.year ? String(work.year) : null },
    { label: 'edition', value: work.edition ? `${work.edition} edition` : null },
    { label: 'licence', value: work.licence },
    { label: 'format', value: work.format },
    { label: 'topic', value: work.shelf },
    { label: 'series', value: series },
    { label: 'notes', value: work.notes },
    { label: 'structure', value: work.structure_why_not },
    // the rarer states, which have no column of their own (B3.a), with their counts as the API gave them
    ...(work.readings?.states ?? []).filter(count => !FIGURE_STATES.some(one => one.state === count.value))
      .map(count => ({ label: count.value.replace(/_/g, ' '), value: count.count.toLocaleString('en') })),
  ]
}

/** A work's count of pages in a state, as the API counted it; null where it has no pages in it, or no pages at all. */
function stateCount(work: Work, state: string) {
  return work.readings?.states.find(count => count.value === state) ?? null
}
const { works, error, loaded } = storeToRefs(store)

/** A facet's values, the field's own words; a work without the field states none and is matched only by an empty facet. */
const said = (value: string | null | undefined): string[] => (value ? [value] : [])

const FACETS: FacetDefinition<Work>[] = [
  { id: 'kb', label: 'Knowledge base', valuesOf: work => [work.knowledge_base] },
  { id: 'format', label: 'Format', valuesOf: work => said(work.format) },
  // the catalog's topic shelf, named as its column is (23.a): never taken for the Shelf view's counts
  { id: 'shelf', label: 'Topic', valuesOf: work => said(work.shelf) },
  { id: 'structure', label: 'Structure', valuesOf: work => said(work.structure) },
  { id: 'series', label: 'Series', valuesOf: work => said(work.series?.title) },
]

const byTitle = (a: Work, b: Work): number => a.title.localeCompare(b.title, 'en', { sensitivity: 'base' })
/** A work that names no author, or no year, stands after those that do, whichever way the rest are sorted. */
const lastWithout = (a: unknown, b: unknown): number => Number(a == null || a === '') - Number(b == null || b === '')

const SORTS: SortDefinition<Work>[] = [
  { id: 'title', label: 'title', compare: byTitle },
  {
    id: 'author',
    label: 'author',
    compare: (a, b) => lastWithout(a.authors, b.authors)
      || (a.authors ?? '').localeCompare(b.authors ?? '', 'en', { sensitivity: 'base' }) || byTitle(a, b),
  },
  {
    id: 'year',
    label: 'year, newest first',
    compare: (a, b) => lastWithout(a.year, b.year) || (b.year ?? 0) - (a.year ?? 0) || byTitle(a, b),
  },
  // a state's figure column sorted, most first, a work without pages read last (B3.a)
  ...['blocked', 'issue'].map(state => ({
    id: state,
    label: `${state}, most first`,
    compare: (a: Work, b: Work) => Number(!a.readings) - Number(!b.readings)
      || (stateCount(b, state)?.count ?? 0) - (stateCount(a, state)?.count ?? 0) || byTitle(a, b),
  })),
]

const searchOf = (work: Work): string => `${work.title} ${work.authors ?? ''} ${work.id}`
const { selection, search, sort } = useFacetState('sources', 'title')

const shown = computed(() => sortRows(
  applyFacets({ rows: works.value, definitions: FACETS, selection: selection.value, search: search.value, searchOf }),
  SORTS, sort.value))

/** A series' parts by their number, a current part before an earlier version of it. */
const byPart = (a: Work, b: Work): number => (a.series?.part ?? 0) - (b.series?.part ?? 0)
  || Number(Boolean(a.series?.version)) - Number(Boolean(b.series?.version)) || byTitle(a, b)

const groupOf = (work: Work): string => (work.series ? `series:${work.series.id}` : `work:${work.knowledge_base}/${work.id}`)

/** One line of the table: a series' heading, or a work, stepped in where it stands under one. */
type Line = { kind: 'head', key: string, title: string, works: number, open: boolean } | { kind: 'work', work: Work, under: boolean }

const opened = ref(new Set(openGroups('sources')))

/** The table's lines: a group of one stands as its work alone, as a heading would only hide what is already there. */
const lines = computed<Line[]>(() => groupRows(shown.value, groupOf, byPart).flatMap((group): Line[] => {
  const first = group.rows[0]!
  if (group.rows.length === 1 || !first.series) return group.rows.map(work => ({ kind: 'work', work, under: false }))
  const open = opened.value.has(group.key)
  const head: Line = { kind: 'head', key: group.key, title: first.series.title, works: group.rows.length, open }
  return [head, ...(open ? group.rows.map((work): Line => ({ kind: 'work', work, under: true })) : [])]
}))

function toggleGroup(key: string): void {
  const next = new Set(opened.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  opened.value = next
  keepOpenGroups('sources', [...next])
}

const lineKey = (line: Line): string => (line.kind === 'head' ? line.key : `${line.work.knowledge_base}/${line.work.id}`)

useScrollRestore(() => loaded.value)

onMounted(() => {
  void store.loadWorks()
})
</script>

<template>
  <section class="sources">
    <h1 class="view-title">Sources</h1>
    <!-- no answer and no failure yet: on its way, from the first frame on -->
    <LoadingLine v-if="!loaded && !error" />
    <ApiFailure v-else-if="error" :error="error" @retry="store.loadWorks()" />
    <p v-else-if="loaded && works.length === 0" class="empty">The catalog lists no works.</p>
    <!-- the table fits the content width (the operator, 18 Nov, on a 2,000 px window: the licence column was cut, the scroll
         bar out of sight at the list's end): the narrow columns hold their widths, the title and the authors share the rest,
         and every cell wraps; below its least width, a phone's, the table scrolls in its own box, never the page -->
    <FacetBar
      v-if="loaded && works.length"
      v-model:selection="selection"
      v-model:search="search"
      v-model:sort="sort"
      :rows="works"
      :facets="FACETS"
      :sorts="SORTS"
      :search-of="searchOf"
      search-placeholder="Search title, author or id"
    >
      <!-- a knowledge base keeps its glyph and its word in the bar, as in its column (Q3.a) -->
      <template #value="{ facet, value }">
        <KnowledgeBaseMark v-if="facet === 'kb'" :kb="value as KnowledgeBase" />
        <template v-else>{{ value }}</template>
      </template>
    </FacetBar>
    <p v-if="loaded && works.length && !shown.length" class="empty" data-part="none-match">
      No work matches the search and the filters.
    </p>
    <!-- the table fits the content width at every width: below each rung of its own width it gives up a rank of columns
         (B2), so it never scrolls sideways; each cell states its column's rank, as the column does -->
    <DataTable v-else-if="loaded && works.length" table-class="works ruled" fixed :columns="COLUMNS">
      <template #head>
        <tr>
          <th>Work</th>
          <th data-rank="3">Knowledge base</th>
          <!-- how the work is cut, by its format's model (the operator's 4.a): a PDF by its pages, an HTML work by its headings -->
          <th class="number">Pages</th>
          <!-- a state's figures under its glyph and the core's word (B3.a) -->
          <th v-for="one in FIGURE_STATES" :key="one.state" class="number state-head" :data-rank="one.column.rank">
            <StateMark :state="one.state" />
          </th>
          <th data-rank="3">Authors</th>
          <th data-rank="5">Year</th>
          <th data-rank="5">Format</th>
          <!-- the catalog's topic shelf (trading_finance, architecture), not the Shelf view's counts (the operator's 23.a) -->
          <th data-rank="5">Topic</th>
        </tr>
      </template>
      <tbody>
        <template v-for="line in lines" :key="lineKey(line)">
          <!-- a series' heading: its title and how many of its parts the bar leaves, closed until opened -->
          <tr v-if="line.kind === 'head'" class="series-head" :data-series="line.key">
            <td>
              <div class="series-line">
                <AppButton variant="quiet" class="series-toggle" :aria-expanded="line.open" @click="toggleGroup(line.key)">
                  <span class="series-glyph" aria-hidden="true">{{ line.open ? '▾' : '▸' }}</span>
                  <span class="series-title">{{ line.title }}</span>
                </AppButton>
                <span class="series-count">{{ line.works }} works</span>
              </div>
            </td>
            <td v-for="(rank, at) in AFTER_WORK" :key="at" :data-rank="rank" />
          </tr>
          <tr v-else :class="{ 'in-series': line.under }" :data-work="line.work.id" :data-kb="line.work.knowledge_base">
            <td class="work-cell">
              <!-- the whole record under the pointer and on the keyboard's focus: the title, id and notes shortened to a line
                   each here, the publisher and licence that stand nowhere else (B2, tip 3) -->
              <HoverCard class="work-card" :title="line.work.title" :rows="cardRows(line.work)">
                <RouterLink
                  v-if="line.work.readings"
                  class="work-title"
                  :to="{ name: 'work', params: { kb: line.work.knowledge_base, work: line.work.id } }"
                >
                  {{ line.work.title }}
                </RouterLink>
                <RouterLink
                  v-else-if="line.work.epub_key"
                  class="work-title"
                  :to="{ name: 'epub-work', params: { kb: line.work.knowledge_base, work: line.work.epub_key } }"
                >
                  {{ line.work.title }}
                </RouterLink>
                <RouterLink
                  v-else-if="line.work.format === 'html'"
                  class="work-title"
                  :to="{ name: 'html-work', params: { kb: line.work.knowledge_base, work: line.work.id } }"
                >
                  {{ line.work.title }}
                </RouterLink>
                <span v-else class="work-title">{{ line.work.title }}</span>
                <!-- the title and the id a line each (the operator's B4.a): the id is what a ticket and a reading key name; a licensed
                     copy's notes (N1.a) stand in the card -->
                <span class="work-id">{{ line.work.id }}</span>
              </HoverCard>
            </td>
            <td data-rank="3"><KnowledgeBaseMark :kb="line.work.knowledge_base" /></td>
            <!-- a work read page by page: its pages, a figure; any other: how it is cut, in the API's words (B3.a) -->
            <td data-cell="structure" class="number">
              <template v-if="line.work.readings">
                <span class="page-total" data-part="pages">{{ line.work.readings.pages.toLocaleString('en') }}</span>
              </template>
              <!-- a licensed EPUB by its sections (123.a), or why they are not counted yet, in the API's words -->
              <span v-else-if="line.work.epub_key" class="page-count" data-part="epub-sections">
                {{ typeof line.work.sections === 'number' ? `${counted(line.work.sections, 'section')} by heading` : line.work.structure_why_not }}
              </span>
              <span v-else-if="typeof line.work.sections === 'number' && typeof line.work.chunks === 'number'" class="page-count">
                {{ counted(line.work.sections, 'section') }} by heading · {{ counted(line.work.chunks, 'chunk') }}
              </span>
              <!-- why, in the API's words, stands in the row's card, where a browser tooltip stood (decision 179) -->
              <span v-else-if="line.work.structure_why_not" class="not-built">
                sections by heading · search index not built
              </span>
              <!-- a licensed catalog entry the export holds no pages of (O1.a), in the API's words, until the core reads it -->
              <span v-else-if="line.work.not_read" class="page-count" data-part="not-read">{{ line.work.not_read }}</span>
            </td>
            <!-- a state's figure, the API's; how many of an issue's pages are served all the same beneath it (18 Nov) -->
            <td v-for="one in FIGURE_STATES" :key="one.state" class="number" :data-rank="one.column.rank" :data-state="one.state">
              <template v-if="stateCount(line.work, one.state)">
                <span class="count">{{ stateCount(line.work, one.state)!.count.toLocaleString('en') }}</span>
                <ServedTally class="served-line" :served="stateCount(line.work, one.state)!.served" alone />
              </template>
            </td>
            <td class="authors" data-rank="3">{{ line.work.authors }}</td>
            <!-- a licensed copy's edition beside its year, where the catalog names one (N1.a) -->
            <td data-rank="5">{{ line.work.year }}<span v-if="line.work.edition" class="edition" data-part="edition">{{ `${line.work.year ? ' · ' : ''}${line.work.edition} edition` }}</span></td>
            <td data-rank="5">{{ line.work.format }}</td>
            <td data-rank="5">{{ line.work.shelf }}</td>
          </tr>
        </template>
      </tbody>
    </DataTable>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.empty {
  color: var(--color-text-secondary);
}

.works th {
  text-align: left;
  color: var(--color-text-secondary);
  font-weight: normal;
  border-bottom: 1px solid var(--color-border);
}

/* a fixed column's cell wraps at its words, never past its column, as wide as its longest word; the work's lines and the
   authors stand on one line each and end in an ellipsis where the column is narrower, their whole text in the row's card
   (Y1.a's tip 3: no word split mid-way, "openstax_principles_of_fina / nce_2e") */
.works th,
.works td {
  white-space: normal;
}

.works td.authors,
.work-title,
.work-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* the card's host fills the work's cell, so the lines inside it know the column's width and shorten to it */
.work-card.hover-card-host {
  display: block;
}

.works th,
.works td {
  padding: var(--space-xs) var(--space-md) var(--space-xs) 0;
  vertical-align: top;
}

.work-title {
  display: block;
}

a.work-title {
  color: var(--color-accent);
  text-decoration: none;
}

a.work-title:hover {
  text-decoration: underline;
}

/* the id is what a ticket and a reading key name, so it stays on screen beneath the title, shortened to its line there and
   whole in the card */
.work-id,
.page-count,
.not-built {
  display: block;
  color: var(--color-text-secondary);
}

/* a state's figures under its glyph and word, right-aligned with them; its words wrap at their spaces in the heading */
.works th.state-head :deep(.state-mark) {
  white-space: normal;
  justify-content: flex-end;
  text-align: right;
}

.works th.number,
.works td.number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* how many of a state's pages are served all the same, on a line of its own beneath the figure */
.served-line {
  justify-content: flex-end;
}

.works td.number .count,
.works td.number .page-total {
  display: block;
}

/* a series' heading in the work's column: its toggle with the one disclosure glyph, its title in the heading's weight,
   shortened to the column, and how many of its parts the bar leaves in the colour of what stands beside, always whole */
.series-line {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  min-width: 0;
}

.series-line .series-toggle {
  gap: var(--space-xs);
  min-width: 0;
  overflow: hidden;
}

.series-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: bold;
}

.series-count {
  flex: none;
  white-space: nowrap;
  color: var(--color-text-secondary);
}

/* a part stands one step in under its series' heading, the one indent step of the app */
.in-series > td:first-child {
  padding-left: var(--indent-step);
}
</style>
