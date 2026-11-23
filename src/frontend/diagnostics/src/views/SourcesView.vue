<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import type { CardRow } from '@/components/base/card_row'
import DataTable from '@/components/base/DataTable.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import CoverageLadder from '@/components/CoverageLadder.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import LadderLegend from '@/components/LadderLegend.vue'
import { applyFacets, sortRows } from '@/components/base/facet_filter'
import { groupRows, keepOpenGroups, openGroups } from '@/row_groups'
import { useSourceStore } from '@/stores/source_store'
import type { KnowledgeBase, Work } from '@/types/api/source_types'
import type { FacetDefinition, SortDefinition } from '@/types/facet_types'
import { useFacetState } from '@/use_facet_state'
import { useScrollRestore } from '@/use_scroll_restore'
import { counted } from '@/counted'
import { editionRoute } from '@/edition_route'
import { sayDate } from '@/human_time'

/**
 * Every work of every knowledge base served, one row each, each marked with its knowledge base: the free catalog in its
 * order, then the licensed works, which have no catalog entry and so only an id and a title. How far each is refined stands
 * in one Coverage column (the operator's U1.a, 20 Nov), five meters a work, the figures in their card. Every work opens: one
 * read page by page, or a PDF not read yet, its page list, which holds every PDF page (V1.b); an HTML work its outline (the
 * operator's 6.a); a licensed EPUB its sections.
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
// works carried one licence (measured 19 Nov). How far a work is refined is one Coverage column (U1.a), in place of its
// pages and the five state columns of B3.a: five meters, the levels' figures and every state of its read pages in the
// meters' card, the sorts by blocked and by issue kept. Ranked so every width keeps the work's column at 8 rem at least
// (B2): the work and its coverage stay; then the knowledge base and the authors; the year, the format and the topic last
const fixed = (width: string, rank?: 2 | 3 | 4 | 5) => ({ width: `calc(${width} + var(--space-md))`, rank })
const COLUMNS = [{}, fixed('11ch', 3), fixed('7rem'), { rank: 3 as const }, fixed('12ch', 5), fixed('5ch', 5), fixed('16ch', 5)]
// a series' heading stands in the work's column and leaves an empty cell in each other, each with its column's rank: a
// cell spanning all seven made a narrow table, which keeps two, add five columns of its own and squeeze the work's to a
// letter (measured at 390 px, 19 Nov)
const AFTER_WORK = COLUMNS.slice(1).map(column => column.rank)

/** A work's whole record under the pointer, what its row shortens or leaves out: the rows the API gave, an empty one left out;
 * a work in more than one edition (E1.a) its editions apart beneath, each its mark and word (● served, ○ kept, one look with
 * the edition bar of its records), its label and format, and when and why the served one was chosen. */
function cardRows(work: Work): CardRow[] {
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
    // a stand-in file beside it, folded into its row (line 1, 20 Nov: one row per work), in the API's words
    { label: 'stand-in', value: work.stand_in?.said },
    { label: 'held', value: work.stand_in?.held },
    ...(work.editions
      ? [...work.editions.editions.map(edition => ({ label: edition.served ? '● served' : '○ kept', group: 'editions',
          caption: 'Editions', value: `${edition.label}${edition.format ? ` · ${edition.format}` : ''}` })),
        { label: 'chosen', group: 'editions', value: `${sayDate(work.editions.chosen).text}: ${work.editions.why}` }]
      : []),
  ]
}

/** A work's kept editions, which its row names after the one it serves. */
const keptOf = (work: Work) => work.editions?.editions.filter(edition => !edition.served) ?? []

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
  // by a state's pages, most first, a work without pages read last (B3.a, kept with U1.a's Coverage column)
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

// what the coverage levels mean, the API's words, from the first work that has a ladder: a hint on demand above the table
const legendOpen = ref(false)
const legendRungs = computed(() => works.value.find(work => work.ladder)?.ladder?.rungs ?? [])

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
    <LadderLegend v-if="legendOpen && legendRungs.length" :rungs="legendRungs" @close="legendOpen = false" />
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
          <!-- how far the work is refined (U1.a): five meters, what they mean a hint on demand -->
          <th class="coverage-head">Coverage <HintToggle id="ladder" v-model:open="legendOpen" /></th>
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
                  v-if="line.work.page_list"
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
                <!-- its stand-in file, which its card names with why it is not served; its pages open where it has a list -->
                <RouterLink
                  v-if="line.work.stand_in?.page_list"
                  class="stand-in"
                  data-part="stand-in"
                  :to="{ name: 'work', params: { kb: line.work.knowledge_base, work: line.work.stand_in.id } }"
                >
                  stand-in file
                </RouterLink>
                <span v-else-if="line.work.stand_in" class="stand-in" data-part="stand-in">stand-in file</span>
                <!-- its editions (E1.a): the served one's row, each kept one named after it and a link to its own record -->
                <span v-if="line.work.editions" class="editions" data-part="editions">{{ line.work.editions.said }}<template
                  v-for="edition in keptOf(line.work)" :key="edition.key"
                > · <RouterLink
                  v-if="editionRoute(edition, line.work.knowledge_base)"
                  class="kept-edition"
                  :data-edition="edition.key"
                  :to="editionRoute(edition, line.work.knowledge_base)!"
                >{{ edition.named }} kept</RouterLink><span v-else>{{ edition.named }} kept</span></template></span>
                <!-- its companion code (#12), folded into its row as an edition is: a link to its folders and files -->
                <RouterLink
                  v-if="line.work.code"
                  class="code-part"
                  data-part="code"
                  :data-code="line.work.code.key"
                  :to="{ name: 'code-work', params: { kb: line.work.knowledge_base, work: line.work.code.key } }"
                >{{ line.work.code.said }}</RouterLink>
                <!-- a file that looks like another edition and is linked with none: a call to look, in the warning role -->
                <span v-if="line.work.possible_edition" class="possible-edition" data-part="possible-edition">
                  <AppIcon name="status-unknown" /> {{ line.work.possible_edition }}
                </span>
              </HoverCard>
            </td>
            <td data-rank="3"><KnowledgeBaseMark :kb="line.work.knowledge_base" /></td>
            <!-- how far the work is refined (U1.a), its levels' figures in the meters' card; where no shelf is built here, how
                 the work is cut, in the API's words (B3.a) -->
            <td data-cell="coverage">
              <CoverageLadder v-if="line.work.ladder" :ladder="line.work.ladder" compact />
              <template v-else-if="line.work.readings">
                <span class="page-total" data-part="pages">{{ counted(line.work.readings.pages, 'page') }}</span>
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

/* a stand-in file beside the work, a line of its own: a link where its pages open, else words */
.stand-in {
  display: block;
  color: var(--color-text-secondary);
  text-decoration: none;
}

a.stand-in {
  color: var(--color-accent);
}

/* a work's editions beneath its id, a kept one a link to its own record; a possible edition a call to look */
.editions,
.possible-edition {
  display: block;
  color: var(--color-text-secondary);
}

/* its companion code beneath its id, a link to its files (#12) */
a.code-part {
  display: block;
  color: var(--color-accent);
  text-decoration: none;
}

a.code-part:hover {
  text-decoration: underline;
}

a.kept-edition {
  color: var(--color-accent);
  text-decoration: none;
}

a.kept-edition:hover {
  text-decoration: underline;
}

.possible-edition {
  color: var(--color-warning);
}

/* the id is what a ticket and a reading key name, so it stays on screen beneath the title, shortened to its line there and
   whole in the card */
.work-id,
.page-count,
.not-built {
  display: block;
  color: var(--color-text-secondary);
}

/* the coverage's heading keeps its hint's mark beside its word */
.coverage-head {
  white-space: nowrap;
}

.works td .page-total {
  display: block;
  color: var(--color-text-secondary);
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
