<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { applyFacets } from '@/components/base/facet_filter'
import { localDay, sayDate } from '@/human_time'
import { useCallsStore } from '@/stores/calls_store'
import type { AnsweredPage, Call } from '@/types/api/calls_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { FacetDefinition, SortDefinition } from '@/types/facet_types'
import { useFacetState } from '@/use_facet_state'
import { counted, noun } from '@/counted'

/**
 * The search server's call log (19.a, decision 98.c): who asked what, which pages answered, how long it took. On top, each
 * tool's figures; then the calls newest first, by day, filtered by tool, state, caller and knowledge base. The caller is the
 * client's own name: "view" for the Librarian page, "evaluation" for a measurement run, an IDE session's name for an IDE. Every figure
 * is the API's; an answered page opens its page view where the export holds it.
 */
const store = useCallsStore()
const { list, error } = storeToRefs(store)
// the bar's picks are kept across a reload (F5, Y1.a stage C), as the sources list keeps its own
const { selection, search, sort } = useFacetState('calls', 'newest')
// a call answered by many pages lists them on request, not on its line
const INLINE_PAGES = 3

onMounted(() => {
  void store.loadCalls()
})

// The facet bar of the sources list, here too (Y1.a, stage C): each value with how many of the calls listed carry it, among
// those the other facets leave (the operator's Q4.a); the tools' figures above count every logged call, the API's. A
// call's words are the API's (`filtered_by`), in the order the API lists them
const facetOf = (id: string, label: string, order: string[]): FacetDefinition<Call> =>
  ({ id, label, valuesOf: call => call.filtered_by[id] ?? [], order })
const facets = computed<FacetDefinition<Call>[]>(() => list.value ? [
  facetOf('tool', 'Tool', list.value.tools.map(tool => tool.tool)),
  facetOf('state', 'State', list.value.states.map(count => count.value)),
  facetOf('client', 'Caller', list.value.clients.map(count => count.value)),
  facetOf('kb', 'Knowledge base', list.value.knowledge_bases.map(count => count.value)),
] : [])
// newest first, as the API serves them: one order, so the bar draws no sort control
const NEWEST: SortDefinition<Call>[] = [{ id: 'newest', label: 'newest first', compare: () => 0 }]

// the calls by the reader's own calendar day, newest first, as the API ordered them
const days = computed(() => {
  const grouped: { day: string, calls: Call[] }[] = []
  for (const call of applyFacets({ rows: list.value?.calls ?? [], definitions: facets.value, selection: selection.value })) {
    const day = localDay(call.at)
    if (grouped.at(-1)?.day !== day) grouped.push({ day, calls: [] })
    grouped.at(-1)!.calls.push(call)
  }
  return grouped
})

function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return ''
  return ms < 1000 ? `${ms.toFixed(ms < 10 ? 1 : 0)} ms` : `${(ms / 1000).toFixed(1)} s`
}

function asked(call: Call): string {
  if (call.query) return `"${call.query}"`
  return [call.work && `work ${call.work}`, call.page && `page ${call.page}`, call.corpus && `corpus ${call.corpus}`]
    .filter(Boolean).join(' · ')
}

function pageName(page: AnsweredPage): string {
  return `${page.title ?? page.work ?? ''} p. ${page.label}`
}

function viewOf(page: AnsweredPage) {
  return { name: 'page', params: { kb: page.view!.knowledge_base, work: page.view!.source_id, page: page.view!.pdf_page } }
}
</script>

<template>
  <section class="calls-view">
    <h1 class="view-title">Calls</h1>
    <ApiFailure v-if="error" :error="error" @retry="store.loadCalls()" />
    <LoadingLine v-else-if="!list" />
    <p v-else-if="list.why_not" class="note">{{ list.why_not }}</p>
    <template v-else>
      <p v-if="list.hidden" class="note" data-note="hidden">
        {{ list.hidden }} calls not shown: they asked about or answered with the licensed knowledge base, or come from before
        5 Nov and cannot be told (--public-only).
      </p>
      <div class="tools">
        <article v-for="tool in list.tools" :key="tool.tool" class="tool" :data-tool="tool.tool">
          <h2 class="tool-name">{{ tool.tool }}</h2>
          <p class="tool-figure"><span class="value">{{ tool.calls.toLocaleString('en') }}</span> {{ noun(tool.calls, 'call') }}</p>
          <p v-if="tool.median_ms !== null" class="tool-figure"><span class="value">{{ duration(tool.median_ms) }}</span> median</p>
          <p class="tool-states">
            <span v-for="state in tool.states" :key="state.value" :data-state="state.value">{{ state.value }} {{ state.count }}</span>
          </p>
        </article>
      </div>

      <FacetBar
        v-model:selection="selection"
        v-model:search="search"
        v-model:sort="sort"
        :rows="list.calls"
        :facets="facets"
        :sorts="NEWEST"
      >
        <!-- a knowledge base keeps its glyph and its word in the panel, as everywhere (Q3.a); "none" is a word -->
        <template #value="{ facet, value }">
          <KnowledgeBaseMark v-if="facet === 'kb' && (value === 'free' || value === 'licensed')" :kb="value as KnowledgeBase" />
          <template v-else>{{ value }}</template>
        </template>
      </FacetBar>
      <p v-if="list.older" class="note">{{ list.older }} older calls are counted above but not listed.</p>

      <section v-for="group in days" :key="group.day" class="day" :data-day="group.day">
        <h2 class="day-title" :title="sayDate(group.day).title">{{ sayDate(group.day).text }}</h2>
        <DataTable table-class="call-rows ruled" wide>
          <tbody>
            <tr v-for="(call, at) in group.calls" :key="`${call.at}/${at}`" :data-tool="call.tool" :data-client="call.filtered_by.client[0]">
              <td class="when"><HumanTime :at="call.at" clock /></td>
              <td class="tool-cell">{{ call.tool }}</td>
              <td class="state">{{ call.state ?? '' }}</td>
              <td class="ms">{{ duration(call.ms) }}</td>
              <td class="client">{{ call.filtered_by.client[0] }}</td>
              <td class="asked">
                <span class="question">{{ asked(call) }}</span>
                <span v-if="call.answered.length && call.answered.length <= INLINE_PAGES" class="answered">
                  <template v-for="(page, number) in call.answered" :key="number">
                    <RouterLink v-if="page.view" :to="viewOf(page)">{{ pageName(page) }}</RouterLink>
                    <span v-else>{{ pageName(page) }}</span>
                  </template>
                </span>
                <!-- opened, one page a line: a work's title can be longer than a line (the EU regulation's), and pages set
                     side by side ran into each other -->
                <FoldSection v-else-if="call.answered.length" class="answered" :title="`${call.answered.length} pages answered`">
                  <ol class="answered-pages ruled">
                    <li v-for="(page, number) in call.answered" :key="number">
                      <RouterLink v-if="page.view" :to="viewOf(page)">{{ pageName(page) }}</RouterLink>
                      <span v-else>{{ pageName(page) }}</span>
                    </li>
                  </ol>
                </FoldSection>
                <!-- a search over works answers with works, each opening its pages where this app holds them -->
                <span v-if="call.answered_works.length" class="answered" data-answered="works">
                  {{ counted(call.answered_works.length, 'work') }} answered:
                  <template v-for="(work, number) in call.answered_works" :key="number">
                    <RouterLink v-if="work.source_id && work.knowledge_base" :to="{ name: 'work', params: { kb: work.knowledge_base, work: work.source_id } }">
                      {{ work.title ?? work.work }}
                    </RouterLink>
                    <span v-else>{{ work.title ?? work.work }}</span>
                  </template>
                </span>
              </td>
            </tr>
          </tbody>
        </DataTable>
      </section>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.note {
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}

/* each tool's figures: the number large, its word small beside it */
.tools {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.tool {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: var(--color-bg-surface);
  padding: var(--space-sm) var(--space-md);
}

.tool-name {
  font-weight: normal;
  margin-bottom: var(--space-xs);
}

.tool-figure,
.tool-states {
  color: var(--color-text-secondary);
}

.value {
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.tool-states {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
}

.day {
  margin-top: var(--space-md);
}

.day-title {
  font-weight: normal;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-xs);
  margin-bottom: var(--space-xs);
}

.call-rows td {
  padding: 2px var(--space-sm) 2px 0;
  vertical-align: top;
}

.when,
.tool-cell,
.state,
.ms,
.client {
  white-space: nowrap;
}

.when,
.state,
.ms,
.client {
  color: var(--color-text-secondary);
}

.ms {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.answered {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
  color: var(--color-text-secondary);
}

.answered a {
  color: var(--color-accent);
  text-decoration: none;
}

.answered a:hover {
  text-decoration: underline;
}

details.answered {
  display: block;
}

.answered-pages {
  list-style: none;
  margin: 2px 0 0;
  padding-left: calc(1ch + var(--space-sm));
}
</style>
