<script setup lang="ts">
import AppButton from '@/components/base/AppButton.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import type { Facet, FacetSelection } from '@/types/facet_types'

/**
 * Filters over a flat list, rather than a cascade of dropdowns: each value of a facet is a toggle with how often it
 * occurs. No value chosen means no filter. The view owns the selection; the bar only changes it. Each facet is a labelled
 * line of the library (the operator, 12 Nov, 219.a: "carry the same line through"; earlier "buttons with labels before them in one line looks messy"): its name in the label column, its toggles beside it, one facet a line, as a page's record
 * reads. `labelChars` holds the label column to the width of the head it stands in, so it aligns with that head's lines.
 */
defineProps<{
  facets: Facet[]
  labelChars?: number
}>()

const selection = defineModel<FacetSelection>({ required: true })

function chosen(key: string, value: string): boolean {
  return (selection.value[key] ?? []).includes(value)
}

function toggle(key: string, value: string): void {
  const current = selection.value[key] ?? []
  const next = current.includes(value) ? current.filter(item => item !== value) : [...current, value]
  selection.value = { ...selection.value, [key]: next }
}
</script>

<template>
  <LabelledLines class="facet-bar" :label-chars="labelChars">
    <LabelledLine v-for="facet in facets" :key="facet.key" :label="facet.label" class="facet" :data-facet="facet.key">
      <AppButton
        v-for="item in facet.values"
        :key="item.value"
        size="compact"
        :active="chosen(facet.key, item.value)"
        :data-value="item.value"
        @click="toggle(facet.key, item.value)"
      >
        <slot name="value" :facet="facet" :value="item.value">{{ item.value }}</slot>
        <span class="facet-count">{{ item.count.toLocaleString('en') }}</span>
        <!-- what a view says of a value after its count, such as how many of a state's pages a person accepted (166.a) -->
        <slot name="after" :facet="facet" :value="item.value" />
      </AppButton>
    </LabelledLine>
  </LabelledLines>
</template>

<style scoped>
.facet-bar {
  margin-bottom: var(--space-md);
}

.facet-count {
  color: var(--color-text-secondary);
}

/* a line of toggles: its label level with the first row's words, also where the toggles wrap to a second row. The
   toggles stand at the line's top, and the label is set down by what sets their words down: a compact toggle's 2px of
   padding and its 1px border */
.facet-bar.labelled-lines > .facet {
  align-items: start;
}

.facet-bar.labelled-lines > .facet :deep(.line-label) {
  padding-top: 3px;
}

/* a toggle's parts wrap inside it where its column is narrow (a phone: "decided by a person 8 · 7 accepted · 1 noted" is
   wider than the value column beside the labels), so the page never scrolls sideways */
.facet .app-button {
  flex-wrap: wrap;
  max-width: 100%;
}

/* and a state's own words wrap too, where one alone is wider than the column ("decided by an automated review", 18 Nov):
   a state's mark keeps its words on one line everywhere else */
.facet .app-button :deep(.state-mark) {
  white-space: normal;
}
</style>
