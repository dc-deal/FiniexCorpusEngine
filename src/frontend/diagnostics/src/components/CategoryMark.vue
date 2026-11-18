<script setup lang="ts">
import HoverCard from '@/components/base/HoverCard.vue'

/**
 * What kind of page it is, where it is not content (decision 172.a): an exercise, an index, contents, front or back
 * matter, a cover, a blank page, an advertisement, said quietly beside the state. Under the pointer a card says what the
 * category means, the API's line (177.a), and what the reader called the page. A content page, and one no reading named,
 * say nothing. The category is the core's.
 */
defineProps<{
  category: string | null | undefined
  said?: string | null
  kind?: string | null
}>()
</script>

<template>
  <HoverCard
    v-if="category && category !== 'content'"
    title="Page category"
    :rows="[{ label: 'category', value: category }, { label: 'means', value: said }, { label: 'the reader called it', value: kind?.replace(/_/g, ' ') }]"
  >
    <span class="category-mark" :data-category="category">{{ category }}</span>
  </HoverCard>
</template>

<style scoped>
/* set like the state and the person's mark beside it, so the three stand on one line; dotted, since its card says more */
.category-mark {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-secondary);
  font-style: italic;
  white-space: nowrap;
  text-decoration: underline dotted;
  cursor: help;
}
</style>
