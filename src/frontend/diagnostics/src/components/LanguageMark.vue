<script setup lang="ts">
import HoverCard from '@/components/base/HoverCard.vue'

/**
 * A work's language (#11), the ISO 639-1 code its catalog names, beside its knowledge base wherever a work stands (its row in
 * Sources, its head): the language its text is in, and so the language a quote from it is in. The code as the catalog writes
 * it, not a name the view would have to look up; under the pointer a card says what it is. Nothing where the catalog names
 * none.
 */
defineProps<{
  language: string | null | undefined
}>()
</script>

<template>
  <HoverCard
    v-if="language"
    title="Language"
    :rows="[{ label: 'language', value: language }, { label: 'means', value: 'the language of the work\'s text, as its catalog names it (ISO 639-1)' }]"
  >
    <span class="language-mark" :data-language="language">{{ language }}</span>
  </HoverCard>
</template>

<style scoped>
/* quiet beside the knowledge base's mark, dotted, since its card says more */
.language-mark {
  color: var(--color-text-secondary);
  white-space: nowrap;
  text-decoration: underline dotted;
  cursor: help;
}
</style>
