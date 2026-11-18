<script setup lang="ts">
import { computed, nextTick, provide, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import AppButton from '@/components/base/AppButton.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import OutlineUnitNode from '@/components/OutlineUnitNode.vue'
import PageJump from '@/components/PageJump.vue'
import PageTable from '@/components/PageTable.vue'
import OwnPages from '@/components/OwnPages.vue'
import RouteTable from '@/components/RouteTable.vue'
import UnitCells from '@/components/UnitCells.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import PersonTally from '@/components/PersonTally.vue'
import StateMark from '@/components/StateMark.vue'
import { queryValues } from '@/address_query'
import { CHAPTER_MARKS, unitKey } from '@/chapter_marks'
import { categoryOf } from '@/page_category'
import { pageCount } from '@/page_count'
import { useOpenUnitsStore } from '@/stores/open_units_store'
import { usePageStore } from '@/stores/page_store'
import { useSettingsStore } from '@/stores/settings_store'
import { useViewName } from '@/view_name'
import type { OutlineUnit, PageRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { Facet, FacetSelection } from '@/types/facet_types'

/**
 * Every read page of one work, narrowed by check state and route. Where the work has an order of its own (a PDF's
 * bookmarks, decision 84.a), its pages stand under its chapters, folded, each chapter with the states of all its pages,
 * and the flat table in PDF order is one click away (the operator: the table, but not as the first view). A work without an order
 * is listed flat and says why. The work's knowledge base stands once, above its pages.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
}>()

const store = usePageStore()
const { pagesError } = storeToRefs(store)
const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)
const selection = ref<FacetSelection>({})
const address = useRoute()
// the pages outside every chapter fold like a chapter, and are remembered like one (the operator, 2026-11-10)
const openUnits = useOpenUnitsStore()

function onOutsideToggle(opened: boolean): void {
  if (!filtering.value) openUnits.setOpen(`${props.kb}/${props.work}`, 'outside', opened)
}

watch(() => [props.kb, props.work] as const, ([kb, work]) => {
  void store.loadWorkPages(kb, work)
}, { immediate: true })

// A link may choose the filter: the shelf's "39 blocked" opens the work with `?route=<that route>`, so exactly the
// pages it counted stand here. Set again whenever the address changes, also for the same work.
watch(() => [props.kb, props.work, address.query.state, address.query.person, address.query.category, address.query.route] as const, () => {
  const chosen: FacetSelection = {}
  for (const key of ['state', 'person', 'category', 'route']) {
    const values = queryValues(address.query, key)
    if (values.length) chosen[key] = values
  }
  selection.value = chosen
}, { immediate: true })

// an answer for another work, still on screen while this one loads, is not shown as this one: matched by the request it
// answers, not by its fields
const shown = computed(() => store.pagesOf(props.kb, props.work))
useViewName(() => shown.value?.title ?? null)

// the states stay a facet; the routes have their table, whose rows narrow the list the same way (the operator, 10 Nov)
const facets = computed<Facet[]>(() => shown.value?.summary ? [
  { key: 'state', label: 'State', values: shown.value.summary.states },
  // a person's standing verdict (166.a), where a person judged any of the work's pages
  ...(shown.value.summary.people?.length ? [{ key: 'person', label: 'A person', values: shown.value.summary.people }] : []),
  // what kind of page (172.a): every category shown, none chosen, so a click narrows; a work of one category has no choice
  ...((shown.value.summary.categories?.length ?? 0) > 1 ? [{ key: 'category', label: 'Category', values: shown.value.summary.categories }] : []),
] : [])

// a state's count of pages a person accepted or rejected, as the API counted it
function stateCount(value: string) {
  return shown.value?.summary?.states.find(count => count.value === value)
}

const chosenRoutes = computed<string[]>({
  get: () => selection.value.route ?? [],
  set: routes => {
    selection.value = { ...selection.value, route: routes }
  },
})

function kept(key: string, value: string): boolean {
  const chosen = selection.value[key] ?? []
  return chosen.length === 0 || chosen.includes(value)
}

const rows = computed<PageRow[]>(() => (shown.value?.pages ?? [])
  .filter(row => kept('state', row.listed_state ?? row.check.state) && kept('person', row.person?.standing ?? '') && kept('category', categoryOf(row))
    && kept('route', row.route)))
const filtering = computed(() => Object.values(selection.value).some(chosen => chosen.length > 0))

const outline = computed<OutlineUnit[]>(() => shown.value?.outline ?? [])

// The chapters table's columns (159.a), one grid for every row at any depth: the short columns as narrow as their
// content needs, one per check state the work has, in the API's order, so no state goes uncounted; the note at least
// 18rem and up to 21rem, so a short note stays on one line while there is room (decision 160) and a chapter's title,
// which matters more, keeps the rest.
// In rem: the table's least width follows from them, and below it the table scrolls in its own box.
const stateColumns = computed(() => shown.value?.summary?.states.map(count => count.value) ?? [])
// A state's column as wide as its word with its glyph, at least 7rem: "decided by a person" (211.a) ran into the note's
// column at 7rem (the operator, 11 Nov). In characters of the one size (`ch`), so the word decides, not a guess; the least width of
// the table takes a character as 0.55rem, a little more than the monospace's own, so it never falls short
function stateColumn(state: string): { css: string, rem: number } {
  const characters = state.length
  return { css: `max(7rem, calc(${characters}ch + 2rem))`, rem: Math.max(7, characters * 0.55 + 2) }
}
const chapterGrid = computed(() => {
  const states = stateColumns.value.map(stateColumn)
  return {
    '--chapter-columns': `minmax(12rem, 1fr) 7rem 4rem ${states.map(state => state.css).join(' ')} minmax(18rem, 21rem)`,
    'minWidth': `${12 + 7 + 4 + states.reduce((sum, state) => sum + state.rem, 0) + 18 + (4 + states.length)}rem`,
  }
})
const asChapters = computed(() => outline.value.length > 0 && settings.value.workPagesView === 'chapters')

// The outline as the API sent it, arranged for drawing: each unit's sub-units in reading order, each unit's own pages
// among the rows the filters keep, and the pages outside every unit. Nothing here is counted: the counts are the API's.
const childrenOf = computed(() => {
  const map = new Map<string | null, OutlineUnit[]>()
  for (const unit of outline.value) map.set(unit.parent, [...map.get(unit.parent) ?? [], unit])
  return map
})
const rowsOf = computed(() => {
  const map = new Map<string, PageRow[]>()
  for (const row of rows.value) for (const id of row.units ?? []) map.set(id, [...map.get(id) ?? [], row])
  return map
})
const outsideRows = computed(() => rows.value.filter(row => row.units?.length === 0))

// units with every unit above them, by the outline's own parents
function withAbove(ids: string[]): Set<string> {
  const parentOf = new Map(outline.value.map(unit => [unit.id, unit.parent]))
  const found = new Set<string>()
  for (const id of ids) {
    for (let at: string | null | undefined = id; at && !found.has(at); at = parentOf.get(at)) found.add(at)
  }
  return found
}

// While a filter is chosen, the units holding a kept page, with every unit above them: only these are drawn, opened
const matching = computed<Set<string> | null>(() => (filtering.value ? withAbove(rows.value.flatMap(row => row.units ?? [])) : null))

// A chapter's count opens its pages (225.a): the units that hold them stand open, as if the reader had opened them, and
// the pages are marked, the first brought into view; the pages behind a count are the API's
const marked = ref<Set<number>>(new Set())
const outlineBox = ref<HTMLElement | null>(null)
async function showPages(pages: number[]): Promise<void> {
  const wanted = new Set(pages)
  const holding = withAbove((shown.value?.pages ?? []).filter(row => wanted.has(row.pdf_page)).flatMap(row => row.units ?? []))
  for (const unit of outline.value) if (holding.has(unit.id)) openUnits.setOpen(`${props.kb}/${props.work}`, unitKey(unit), true)
  marked.value = wanted
  await nextTick()
  // by its first cell, at the table's left edge: the whole row is wider than the chapters' box, and brought into view it
  // would scroll the box sideways and cut the chapters' titles off
  outlineBox.value?.querySelector('tr.marked > td')?.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'auto' })
}
provide(CHAPTER_MARKS, { marked, show: pages => void showPages(pages) })
watch(() => [props.kb, props.work], () => { marked.value = new Set() })
</script>

<template>
  <section class="work-pages">
    <p class="trail"><RouterLink to="/sources">Sources</RouterLink></p>
    <ApiFailure v-if="pagesError" :error="pagesError" @retry="store.loadWorkPages(kb, work)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <h1 class="view-title">{{ shown.title }}</h1>
      <!-- the work's record as a page's is (219.a, the operator: "carry the same line through, as far as possible and sensible"): labelled
           lines, the label column as wide as the page head's, so nothing moves between a work and its pages. Every count
           once (159.a): the work, its pages, the states and the rest as the toggles that also filter, a page to jump to -->
      <div class="summary work-facts" data-part="work-facts">
        <LabelledLines :label-chars="10">
          <LabelledLine label="Work" class="work-id"><KnowledgeBaseMark :kb="shown.knowledge_base" /><span class="source-id">{{ shown.source_id }}</span></LabelledLine>
          <LabelledLine v-if="shown.summary" label="Pages"><span class="page-total">{{ pageCount(shown.summary.pages) }}</span></LabelledLine>
        </LabelledLines>
        <template v-if="shown.summary">
          <FacetBar v-model="selection" :facets="facets" :label-chars="10">
            <template #value="{ facet, value }">
              <StateMark v-if="facet.key === 'state'" :state="value" />
              <PersonStanding v-else-if="facet.key === 'person'" :mark="{ standing: value as 'accepted' | 'rejected' | 'noted' }" />
              <template v-else>{{ value }}</template>
            </template>
            <template #after="{ facet, value }">
              <PersonTally v-if="facet.key === 'state'" :accepted="stateCount(value)?.accepted" :rejected="stateCount(value)?.rejected" :noted="stateCount(value)?.noted" />
            </template>
          </FacetBar>
          <LabelledLines :label-chars="10">
            <LabelledLine label="PDF page"><PageJump :kb="kb" :work="work" bare /></LabelledLine>
          </LabelledLines>
        </template>
      </div>
      <p v-if="!shown.summary" class="empty">This work has no page readings.</p>
      <template v-else>
        <RouteTable v-if="shown.routes.length" v-model="chosenRoutes" :routes="shown.routes" :levels="shown.route_levels" />
        <div v-if="outline.length" class="view-switch">
          <AppButton size="compact" :active="asChapters" @click="settingsStore.setWorkPagesView('chapters')">chapters</AppButton>
          <AppButton size="compact" :active="!asChapters" @click="settingsStore.setWorkPagesView('table')">table</AppButton>
        </div>
        <p v-else-if="shown.outline === null" class="no-outline">
          The export carries no outline for this work yet, so its pages stand in PDF order.
        </p>
        <p v-else class="no-outline">This PDF has no bookmarks, so its pages stand in PDF order.</p>
        <p v-if="rows.length === 0" class="empty">No page matches the chosen filters.</p>
        <!-- the chapters as one table (159.a): a head, then a row per unit at any depth in the same columns; on a narrow
             screen it scrolls in its own box, never the page -->
        <div v-else-if="asChapters" class="outline-scroll">
          <div ref="outlineBox" class="outline ruled" :style="chapterGrid">
            <div class="chapter-head" data-part="chapter-head">
              <span>Chapter</span>
              <span>PDF pages</span>
              <span class="number">Pages</span>
              <span v-for="state in stateColumns" :key="state" class="number"><StateMark :state="state" /></span>
              <span>Note</span>
            </div>
            <FoldSection
              v-if="outsideRows.length && shown.outside_outline"
              class="unit outside"
              :open="filtering || openUnits.isOpen(`${kb}/${work}`, 'outside')"
              data-unit="outside"
              mark-in-title
              flat
              @toggle="onOutsideToggle"
            >
              <template #title>
                <span class="unit-head">
                  <UnitCells
                    title="Outside the outline"
                    :level="1"
                    range=""
                    :pages="shown.outside_outline.pages"
                    :states="shown.outside_outline.states"
                    :state-columns="stateColumns"
                    note="before chapter one, or nothing to quote"
                  />
                </span>
              </template>
              <div class="unit-body">
                <OwnPages
                  :caption="`${pageCount(shown.outside_outline.pages)} outside every chapter`"
                  :rows="outsideRows"
                  :kb="kb"
                  :work="work"
                  :indent="1.25"
                />
              </div>
            </FoldSection>
            <OutlineUnitNode
              v-for="unit in childrenOf.get(null) ?? []"
              :key="unit.id"
              :unit="unit"
              :children-of="childrenOf"
              :rows-of="rowsOf"
              :matching="matching"
              :state-columns="stateColumns"
              :kb="kb"
              :work="work"
            />
          </div>
        </div>
        <PageTable v-else :rows="rows" :kb="kb" :work="work" />
      </template>
    </template>
  </section>
</template>

<style scoped>
.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.empty,
.no-outline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}

.source-id {
  color: var(--color-text-secondary);
}

/* the work's record (219.a): its labelled lines in one column, the facets' among them, spaced as a page's record is */
.summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: var(--space-sm);
}

/* the facets stand among the record's lines, so their bar keeps no space of its own beneath */
.summary .facet-bar {
  margin-bottom: 0;
}

.view-switch {
  display: flex;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}

/* the chapters table scrolls in its own box below its least width; the page never does */
.outline-scroll {
  overflow-x: auto;
}

/* the head and every row of the chapters table in the same columns, set once as `--chapter-columns` */
.chapter-head,
.unit-head {
  display: grid;
  grid-template-columns: var(--chapter-columns);
  column-gap: var(--space-md);
  align-items: baseline;
  padding: 2px 0;
}

.chapter-head {
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.number {
  text-align: right;
}

.unit-body {
  padding-bottom: var(--space-xs);
}
</style>
