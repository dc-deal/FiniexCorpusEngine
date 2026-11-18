<script setup lang="ts">
import { computed } from 'vue'
import FoldSection from '@/components/base/FoldSection.vue'
import { useOpenUnitsStore } from '@/stores/open_units_store'
import type { HtmlNode } from '@/types/api/html_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One heading of an HTML work's outline (the operator's 6.a), folded where it has sub-headings: its title, the range of its section
 * labels, and the sections and chunks in it and beneath it, as the API counted them. A heading with a section of its own
 * opens that section; a heading without text of its own names only its range. Opened, its sub-headings in the work's order.
 */
const props = defineProps<{
  node: HtmlNode
  childrenOf: Map<string | null, HtmlNode[]>
  kb: KnowledgeBase
  work: string
}>()

const children = computed(() => props.childrenOf.get(props.node.id) ?? [])

// an opened heading stays open on coming back from a section (the operator, 2026-11-10), known by its first label and title
const openUnits = useOpenUnitsStore()
const workKey = computed(() => `html:${props.kb}/${props.work}`)
const nodeKey = computed(() => `${props.node.first ?? ''}:${props.node.title}`)

function onToggle(opened: boolean): void {
  openUnits.setOpen(workKey.value, nodeKey.value, opened)
}
const range = computed(() => props.node.first === props.node.last ? props.node.first : `${props.node.first}–${props.node.last}`)

function counted(count: number, word: string): string {
  return `${count.toLocaleString('en')} ${word}${count === 1 ? '' : 's'}`
}
</script>

<template>
  <!-- a heading with sub-headings is the one fold (179); its sub-headings stand one step right of its title -->
  <FoldSection v-if="children.length" class="unit" :open="openUnits.isOpen(workKey, nodeKey)" :data-node="node.id" @toggle="onToggle">
    <template #title>
      <span class="unit-line">
        <RouterLink v-if="node.label" class="unit-title" :to="{ name: 'html-section', params: { kb, work, section: node.label } }">
          {{ node.title }}
        </RouterLink>
        <span v-else class="unit-title no-text" title="a heading without text of its own">{{ node.title }}</span>
        <span class="unit-range">{{ range }}</span>
        <span class="unit-count">{{ counted(node.sections, 'section') }} · {{ counted(node.chunks, 'chunk') }}</span>
      </span>
    </template>
    <div class="unit-body ruled">
      <HtmlOutlineNode v-for="child in children" :key="child.id" :node="child" :children-of="childrenOf" :kb="kb" :work="work" />
    </div>
  </FoldSection>
  <!-- a heading the loader drops as noise, greyed at its place: it opens its original, and has no chunks (the operator's 2.a) -->
  <div v-else-if="node.dropped" class="unit-head leaf ruled-row dropped" :data-node="node.id" data-part="dropped">
    <span class="mark-space" />
    <span class="unit-line">
      <RouterLink class="unit-title" :to="{ name: 'html-section', params: { kb, work, section: node.dropped } }">{{ node.title }}</RouterLink>
      <span class="unit-count">dropped as noise: not indexed</span>
    </span>
  </div>
  <!-- a heading with nothing beneath it has nothing to unfold: a row, its marker's place kept so titles align -->
  <div v-else class="unit-head leaf ruled-row" :data-node="node.id">
    <span class="mark-space" />
    <span class="unit-line">
      <RouterLink v-if="node.label" class="unit-title" :to="{ name: 'html-section', params: { kb, work, section: node.label } }">
        {{ node.title }}
      </RouterLink>
      <span v-else class="unit-title no-text">{{ node.title }}</span>
      <span class="unit-range">{{ range }}</span>
      <span class="unit-count">{{ counted(node.chunks, 'chunk') }}</span>
    </span>
  </div>
</template>

<style scoped>
/* a heading with nothing beneath it: a row whose title stands where a fold's would, after a mark's one step */
.unit-head {
  display: flex;
  align-items: baseline;
  padding: 2px 0;
}

.mark-space {
  flex: 0 0 var(--indent-step);
}

.unit-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
  min-width: 0;
}

.unit-title {
  color: var(--color-text-primary);
}

a.unit-title {
  color: var(--color-accent);
  text-decoration: none;
}

a.unit-title:hover {
  text-decoration: underline;
}

/* greyed: it is shown, opened and counted as nothing (the operator's 2.a) */
.dropped a.unit-title {
  color: var(--color-text-secondary);
}

.unit-range,
.unit-count {
  color: var(--color-text-secondary);
}

.unit-body {
  padding-bottom: var(--space-xs);
}
</style>
