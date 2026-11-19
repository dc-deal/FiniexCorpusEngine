<script setup lang="ts">
import { inject } from 'vue'
import AppButton from '@/components/base/AppButton.vue'
import { CHAPTER_MARKS } from '@/chapter_marks'
import type { Count, StatePages } from '@/types/api/page_types'

/**
 * The cells of one row of a work's chapters table (decision 159.a): the unit's title, indented by its depth, its PDF
 * pages, its pages, one column per check state the work has, each count right-aligned under its state, and a note. The
 * cells are the row's grid items, so every row of the work, at any depth, lines up in the columns its parent sets. Every
 * figure is the API's; a state with no page in the unit leaves its cell empty.
 *
 * A count the API gives pages for (225.a: what a person should look at, or what a person decided) is a way to them: a
 * click opens the units that hold them and marks them, without folding the row it sits in. A fine count stays a figure.
 */
const props = withDefaults(defineProps<{
  title: string
  level: number
  range: string
  pages: number
  states: Count[]
  stateColumns: string[]
  note: string | null
  statePages?: StatePages[]
}>(), { statePages: () => [] })

const marks = inject(CHAPTER_MARKS, null)

function countOf(state: string): string {
  const found = props.states.find(count => count.value === state)?.count
  return found ? found.toLocaleString('en') : ''
}

function pagesOf(state: string): number[] {
  return marks ? props.statePages.find(one => one.value === state)?.pages ?? [] : []
}

function pagesSaid(state: string): string {
  const pages = pagesOf(state)
  return `show the ${pages.length === 1 ? 'page' : `${pages.length} pages`} of ${props.title} in ${state.replaceAll('_', ' ')}`
}
</script>

<template>
  <!-- the fold's mark in the title cell (179), so the columns after it stand alike at every depth -->
  <span class="unit-title" :style="{ paddingLeft: `calc(${level - 1} * var(--indent-step))` }"><span class="fold-inline-mark" />{{ title }}</span>
  <span class="unit-range">{{ range }}</span>
  <span class="number unit-pages">{{ pages.toLocaleString('en') }}</span>
  <span v-for="state in stateColumns" :key="state" class="number state-cell" :data-state="state">
    <!-- the click opens the pages, never the fold it sits in: the row's own fold stays as the reader left it -->
    <AppButton
      v-if="pagesOf(state).length"
      variant="link"
      class="state-jump"
      :aria-label="pagesSaid(state)"
      :data-show-state="state"
      @click.prevent.stop="marks?.show(pagesOf(state))"
    >{{ countOf(state) }}</AppButton>
    <template v-else>{{ countOf(state) }}</template>
  </span>
  <span class="note">{{ note ?? '' }}</span>
</template>

<style scoped>
.unit-title {
  color: var(--color-text-primary);
  min-width: 0;
  overflow-wrap: anywhere;
}

.unit-range,
.unit-pages,
.note {
  color: var(--color-text-secondary);
}

.number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* a count that opens its pages is a way, so it wears a link's look, the accent's ink and an underline under the pointer
   (line 1's D9.a, 19 Nov: an underlined figure in a state's colour read as a link) */
.state-cell .state-jump {
  color: var(--color-accent);
  text-decoration: none;
}

.state-cell .state-jump:hover {
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* a state's count where pages need looking at keeps the state's own colour, as its chip does */
.state-cell[data-state='issue'],
.state-cell[data-state='stopped'] {
  color: var(--color-error);
}

.state-cell[data-state='blocked'] {
  color: var(--color-warning);
}
</style>
