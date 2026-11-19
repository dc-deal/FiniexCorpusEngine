<script setup lang="ts">
import { computed } from 'vue'
import FoldSection from '@/components/base/FoldSection.vue'
import OwnPages from '@/components/OwnPages.vue'
import UnitCells from '@/components/UnitCells.vue'
import { useOpenUnitsStore } from '@/stores/open_units_store'
import { unitKey as keyOf } from '@/chapter_marks'
import type { OutlineUnit, PageRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import { counted } from '@/counted'

/**
 * One unit of a work's own order, a row of the chapters table (decision 159.a), folded by default: its title, its PDF
 * pages, its pages and the states of every page in it and beneath it, counted by the API (the operator's 7.a), each in its column.
 * Opened, its own pages in the work's one page grid, then its sub-units, their titles indented, their figures in the same
 * columns. A unit the reader opened stays open on coming back from a page (the operator, 2026-11-10), remembered in this browser.
 * While a filter is chosen, only units holding a matching page are drawn, and they stand open down to the page (the operator's
 * 6.a): that opening is the filter's, not remembered.
 */
const props = defineProps<{
  unit: OutlineUnit
  childrenOf: Map<string | null, OutlineUnit[]>
  // the unit's own pages, already narrowed by the chosen filters
  rowsOf: Map<string, PageRow[]>
  // the units holding a matching page while a filter is chosen; null without one
  matching: Set<string> | null
  // the check states the work has, one column each, in the API's order
  stateColumns: string[]
  kb: KnowledgeBase
  work: string
}>()

function pageRange(unit: OutlineUnit): string {
  return unit.first_page === unit.last_page ? `p. ${unit.first_page}` : `p. ${unit.first_page}–${unit.last_page}`
}

const own = computed<PageRow[]>(() => props.rowsOf.get(props.unit.id) ?? [])

// one step deeper than the unit's title, which stands (level - 1) steps in: a step is the title's own (UnitCells)
const STEP = 1.25
const indent = computed(() => props.unit.level * STEP)
// "1 page of Chapter 3 itself, outside its sections": the count is the API's
const caption = computed(() => {
  const count = props.unit.own_pages
  const outside = (props.childrenOf.get(props.unit.id) ?? []).length ? ', outside its sections' : ''
  return `${counted(count, 'page')} of ${props.unit.title} itself${outside}`
})

// known by its first page and title, which stay when the core renumbers the outline's ids
const openUnits = useOpenUnitsStore()
const workKey = computed(() => `${props.kb}/${props.work}`)
const unitKey = computed(() => keyOf(props.unit))
const open = computed(() => props.matching !== null || openUnits.isOpen(workKey.value, unitKey.value))

// the reader's own opening and folding is remembered; the filter's is not
function onToggle(opened: boolean): void {
  if (props.matching === null) openUnits.setOpen(workKey.value, unitKey.value, opened)
}
</script>

<template>
  <!-- a row of the chapters grid: the fold's mark in its title cell and its rows' own indent, so every column aligns (179) -->
  <FoldSection v-if="matching === null || matching.has(unit.id)" class="unit" :open="open" :data-unit="unit.id" mark-in-title flat @toggle="onToggle">
    <template #title>
      <span class="unit-head">
        <UnitCells
          :title="unit.title"
          :level="unit.level"
          :range="pageRange(unit)"
          :pages="unit.pages"
          :states="unit.states"
          :state-pages="unit.state_pages ?? []"
          :state-columns="stateColumns"
          :note="unit.indexed ? null : 'not in the chat\'s index'"
        />
      </span>
    </template>
    <div class="unit-body ruled">
      <!-- the unit's own pages, a block one step deeper than its title (161.a), so they read as the unit's -->
      <OwnPages v-if="own.length" :caption="caption" :rows="own" :kb="kb" :work="work" :indent="indent" />
      <OutlineUnitNode
        v-for="child in childrenOf.get(unit.id) ?? []"
        :key="child.id"
        :unit="child"
        :children-of="childrenOf"
        :rows-of="rowsOf"
        :matching="matching"
        :state-columns="stateColumns"
        :kb="kb"
        :work="work"
      />
    </div>
  </FoldSection>
</template>

<style scoped>
/* a row of the chapters table: the columns its parent's grid sets, the same at every depth */
.unit-head {
  display: grid;
  grid-template-columns: var(--chapter-columns);
  column-gap: var(--space-md);
  align-items: baseline;
  padding: 2px 0;
}

.unit-body {
  padding-bottom: var(--space-xs);
}
</style>
