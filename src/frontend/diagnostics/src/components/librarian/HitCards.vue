<script setup lang="ts">
import FoldSection from '@/components/base/FoldSection.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { knowledgeBaseOf } from '@/knowledge_base'
import type { HitCard } from '@/types/api/librarian_types'

/**
 * A search's hits as cards, as `search` and `semantic_search` answer them (L1.a): each its rank, knowledge base, work with
 * its edition and year, its page as a link to the page in this view where the server links one, its section and score,
 * the snippet, and for a semantic hit the whole chunk folded beneath; where the answer keeps one hit per page, its other
 * passages there, and which of the plan's keywords its text holds (#15). Every figure and word is the API's.
 */
defineProps<{
  hits: HitCard[]
}>()
</script>

<template>
  <ol class="hit-cards ruled" data-part="hit-cards">
    <li v-for="hit in hits" :key="hit.rank" class="hit-card" :data-hit="hit.rank">
      <p class="hit-head">
        <span class="rank">#{{ hit.rank }}</span>
        <KnowledgeBaseMark v-if="knowledgeBaseOf(hit.knowledge_base)" :kb="knowledgeBaseOf(hit.knowledge_base)!" />
        <strong class="hit-title">{{ hit.title ?? hit.work }}</strong>
        <span v-if="hit.edition_said" class="secondary" data-part="hit-edition">{{ hit.edition_said }}</span>
        <RouterLink v-if="hit.view" class="hit-page" :to="hit.view" data-part="hit-page">{{ hit.page_said }}</RouterLink>
        <span v-else-if="hit.page_said" class="hit-page" data-part="hit-page">{{ hit.page_said }}</span>
        <span v-if="hit.section" class="secondary">{{ hit.section }}</span>
        <span v-if="hit.score !== null && hit.score !== undefined" class="secondary score">score {{ hit.score }}</span>
        <span v-if="hit.more_on_page_said" class="secondary" data-part="more-on-page">{{ hit.more_on_page_said }}</span>
      </p>
      <p v-if="hit.snippet" class="snippet">{{ hit.snippet }}</p>
      <p class="hit-foot secondary">
        <span v-if="hit.work">{{ hit.work }}</span>
        <span v-if="hit.route">{{ hit.route }}</span>
        <span v-if="hit.licence">{{ hit.licence }}</span>
        <span v-if="hit.terms_missing.length" class="missing" data-part="terms-missing">missing: {{ hit.terms_missing.join(', ') }}</span>
        <span v-if="hit.keywords_found?.length" data-part="keywords-found">keywords: {{ hit.keywords_found.join(', ') }}</span>
      </p>
      <FoldSection v-if="hit.text" class="chunk" title="the whole chunk" data-part="whole-chunk">
        <p class="chunk-text">{{ hit.text }}</p>
      </FoldSection>
    </li>
  </ol>
</template>

<style scoped>
.hit-cards {
  list-style: none;
  display: flex;
  flex-direction: column;
}

.hit-card {
  padding: var(--space-sm) 0;
}

.hit-head,
.hit-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-xs) var(--space-md);
}

.secondary,
.rank {
  color: var(--color-text-secondary);
}

.missing {
  color: var(--color-warning);
}

/* the page's own words around the match, as text and with its line breaks */
.snippet,
.chunk-text {
  white-space: pre-line;
  margin: var(--space-xs) 0;
  padding-left: var(--space-sm);
  border-left: 2px solid var(--color-border);
}
</style>
