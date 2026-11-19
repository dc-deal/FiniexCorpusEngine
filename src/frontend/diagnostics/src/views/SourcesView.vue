<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import DataTable from '@/components/base/DataTable.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import StateCounts from '@/components/StateCounts.vue'
import { applyFacets, sortRows } from '@/components/base/facet_filter'
import { pageCount } from '@/page_count'
import { groupRows, keepOpenGroups, openGroups } from '@/row_groups'
import { useSourceStore } from '@/stores/source_store'
import type { KnowledgeBase, Work } from '@/types/api/source_types'
import type { FacetDefinition, SortDefinition } from '@/types/facet_types'
import { useFacetState } from '@/use_facet_state'
import { useScrollRestore } from '@/use_scroll_restore'

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
// Work, Authors and Publisher share what the fixed columns leave. A fixed column is as wide as its longest word and its
// gap to the next (`--space-md`, the cells' right padding): "licensed" with its glyph, "12th edition", "trading_finance",
// "(licensed)"; so none of their words is ever split, and nothing runs into the next cell (the operator, 18 Nov: the
// knowledge base ran into the structure, "trading_financ|e", "5th editio|n")
const fixed = (width: string) => ({ width: `calc(${width} + var(--space-md))` })
const COLUMNS = [{}, fixed('11ch'), fixed('26ch'), {}, {}, fixed('12ch'), fixed('5ch'), fixed('16ch'), fixed('16ch')]
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
    <DataTable v-else-if="loaded && works.length" table-class="works ruled" fixed min-width="64rem" :columns="COLUMNS">
      <template #head>
        <tr>
          <th>Work</th>
          <th>Knowledge base</th>
          <!-- how the work is cut, by its format's model (the operator's 4.a): a PDF by its pages, an HTML work by its headings -->
          <th>Structure</th>
          <th>Authors</th>
          <th>Publisher</th>
          <th>Year</th>
          <th>Format</th>
          <!-- the catalog's topic shelf (trading_finance, architecture), not the Shelf view's counts (the operator's 23.a) -->
          <th>Topic</th>
          <th>Licence</th>
        </tr>
      </template>
      <tbody>
        <template v-for="line in lines" :key="lineKey(line)">
          <!-- a series' heading: its title and how many of its parts the bar leaves, closed until opened -->
          <tr v-if="line.kind === 'head'" class="series-head" :data-series="line.key">
            <td colspan="9">
              <AppButton variant="quiet" class="series-toggle" :aria-expanded="line.open" @click="toggleGroup(line.key)">
                <span class="series-glyph" aria-hidden="true">{{ line.open ? '▾' : '▸' }}</span>
                <span class="series-title">{{ line.title }}</span>
              </AppButton>
              <span class="series-count">{{ line.works }} works</span>
            </td>
          </tr>
          <tr v-else :class="{ 'in-series': line.under }" :data-work="line.work.id" :data-kb="line.work.knowledge_base">
            <td class="shared">
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
              <span class="work-id">{{ line.work.id }}</span>
              <!-- a few words about a licensed copy, from the local licensed catalog (N1.a): "stand-in file", "lecture slides" -->
              <span v-if="line.work.notes" class="work-notes" data-part="work-notes">{{ line.work.notes }}</span>
            </td>
            <td><KnowledgeBaseMark :kb="line.work.knowledge_base" /></td>
            <td data-cell="structure">
              <template v-if="line.work.readings">
                <span class="page-count">{{ pageCount(line.work.readings.pages) }} · read and judged</span>
                <StateCounts :counts="line.work.readings.states" />
              </template>
              <!-- a licensed EPUB by its sections (123.a), or why they are not counted yet, in the API's words -->
              <span v-else-if="line.work.epub_key" class="page-count" data-part="epub-sections">
                {{ typeof line.work.sections === 'number' ? `${line.work.sections.toLocaleString('en')} sections by heading` : line.work.structure_why_not }}
              </span>
              <span v-else-if="typeof line.work.sections === 'number' && typeof line.work.chunks === 'number'" class="page-count">
                {{ line.work.sections.toLocaleString('en') }} sections by heading · {{ line.work.chunks.toLocaleString('en') }} chunks
              </span>
              <span v-else-if="line.work.structure_why_not" class="not-built" :title="line.work.structure_why_not">
                sections by heading · search index not built
              </span>
              <!-- a licensed catalog entry the export holds no pages of (O1.a), in the API's words, until the core reads it -->
              <span v-else-if="line.work.not_read" class="page-count" data-part="not-read">{{ line.work.not_read }}</span>
            </td>
            <td class="shared">{{ line.work.authors }}</td>
            <td class="shared">{{ line.work.publisher }}</td>
            <!-- a licensed copy's edition beside its year, where the catalog names one (N1.a) -->
            <td>{{ line.work.year }}<span v-if="line.work.edition" class="edition" data-part="edition">{{ `${line.work.year ? ' · ' : ''}${line.work.edition} edition` }}</span></td>
            <td>{{ line.work.format }}</td>
            <td>{{ line.work.shelf }}</td>
            <td>{{ line.work.licence }}</td>
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

/* every cell wraps at its words, never past its column; only the three shared columns may split a word too long for any
   line, a fixed column being as wide as its longest word */
.works th,
.works td {
  white-space: normal;
}

.works td.shared {
  overflow-wrap: break-word;
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

/* the id is what a ticket and a reading key name, so it stays on screen beneath the title, broken anywhere where a long
   one has no space to break at */
.work-id {
  overflow-wrap: anywhere;
}

.work-id,
.work-notes,
.page-count,
.not-built {
  display: block;
  color: var(--color-text-secondary);
}

/* a series' heading spans the row: its toggle with the one disclosure glyph, its title in the heading's weight, and how
   many of its parts the bar leaves in the colour of what stands beside */
.series-head td {
  padding-right: 0;
}

.series-toggle {
  gap: var(--space-xs);
}

.series-title {
  font-weight: bold;
}

.series-count {
  margin-left: var(--space-sm);
  color: var(--color-text-secondary);
}

/* a part stands one step in under its series' heading, the one indent step of the app */
.in-series > td:first-child {
  padding-left: var(--indent-step);
}
</style>
