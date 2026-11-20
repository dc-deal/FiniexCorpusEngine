<script setup lang="ts">
import { computed } from 'vue'
import { editionRoute } from '@/edition_route'
import type { Editions, KnowledgeBase } from '@/types/api/source_types'

/**
 * The way back above a work's record: Sources, and on an edition's record the work and the edition (the operator's E1.a,
 * 20 Nov: "Sources › <work> › <edition>"), the work a link to its served edition's record where this is another one.
 */
const props = defineProps<{
  editions?: Editions | null
  kb: KnowledgeBase
}>()

const current = computed(() => props.editions?.editions.find(edition => edition.key === props.editions?.current))
const served = computed(() => props.editions?.editions.find(edition => edition.served))
const servedRoute = computed(() => (served.value && served.value.key !== props.editions?.current ? editionRoute(served.value, props.kb) : null))
</script>

<template>
  <p class="trail" data-part="trail">
    <RouterLink to="/sources">Sources</RouterLink>
    <template v-if="editions && current">
      <span class="trail-step" aria-hidden="true"> › </span>
      <RouterLink v-if="servedRoute" :to="servedRoute" data-part="trail-work">{{ editions.title }}</RouterLink>
      <span v-else data-part="trail-work">{{ editions.title }}</span>
      <span class="trail-step" aria-hidden="true"> › </span>
      <span data-part="trail-edition">{{ current.label }}</span>
    </template>
  </p>
</template>

<style scoped>
.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover {
  text-decoration: underline;
}

.trail-step {
  color: var(--color-text-secondary);
}
</style>
