<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { useSearchStore } from '@/stores/search_store'
import type { Corpus, SearchHit } from '@/types/api/search_types'

/**
 * The search the MCP server answers with, shown: a question in, the pages that hold its words out, best first, each with
 * its quote, both its page numbers, its source, knowledge base and licence, and the route that made its text, so a quote
 * from an unchecked text layer is never taken for a checked reading. A hit on a page the diagnostics shows opens that page,
 * its original beside its reading. "Nothing found" is an answer, said as one. The question lives in the address, so a
 * search can be linked.
 */
const route = useRoute()
const router = useRouter()
const store = useSearchStore()
const { error } = storeToRefs(store)

const CORPORA: Corpus[] = ['all', 'free', 'licensed']
const query = computed(() => String(route.query.q ?? '').trim())
const corpus = computed<Corpus>(() => {
  const asked = String(route.query.corpus ?? 'all')
  return (CORPORA as string[]).includes(asked) ? asked as Corpus : 'all'
})
const typed = ref(query.value)
const chosen = ref<Corpus>(corpus.value)

watch(() => [query.value, corpus.value] as const, ([question, base]) => {
  typed.value = question
  chosen.value = base
  if (question) void store.search(question, base)
}, { immediate: true })

const answer = computed(() => query.value ? store.answerOf(query.value, corpus.value) : null)
// a choice of corpus only where the search holds more than one knowledge base
const offersCorpus = computed(() => (answer.value?.knowledge_bases.length ?? 0) > 1 || corpus.value !== 'all')

function submit(): void {
  const question = typed.value.trim()
  if (!question) return
  void router.push({ name: 'search', query: { q: question, ...chosen.value === 'all' ? {} : { corpus: chosen.value } } })
}

// both page numbers where both are known, as a citation gives them: "p. 456 (PDF p. 470)"
function pageLabel(hit: SearchHit): string {
  const { pdf, printed, label } = hit.page
  if (pdf && printed) return `p. ${printed} (PDF p. ${pdf})`
  if (pdf) return `PDF p. ${pdf}`
  return label
}
</script>

<template>
  <section class="search">
    <h1 class="view-title">Search · BM25, no model</h1>
    <form class="search-form" role="search" @submit.prevent="submit">
      <input v-model="typed" type="search" class="question" aria-label="Search the knowledge base" placeholder="e.g. kelly fraction">
      <div v-if="offersCorpus" class="corpus">
        <AppButton v-for="base in CORPORA" :key="base" size="compact" type="button" :active="chosen === base" @click="chosen = base">
          {{ base }}
        </AppButton>
      </div>
      <AppButton type="submit">Search</AppButton>
    </form>
    <!-- what this search is and is not (the operator, 16 Nov): the keyword tool, for a term; a question in words goes to the chat -->
    <p class="search-note" data-part="search-kind">
      The MCP server's <code>search</code> tool: BM25 over the words of every page, with no model at all, neither embeddings
      nor a language model, for a caller who knows the term. Each hit comes with its pages and the route that made its text.
      A question in words belongs in the <RouterLink :to="{ name: 'chat' }" data-part="to-chat">Chat</RouterLink>, which runs
      the semantic (hybrid) search.
    </p>

    <template v-if="query">
      <ApiFailure v-if="error" :error="error" @retry="store.search(query, corpus)" />
      <div v-else-if="!answer" class="waiting">
        <LoadingLine />
        <p class="search-note">The first search after a start waits until its index is built, up to about a minute.</p>
      </div>
      <p v-else-if="answer.state === 'error'" class="search-error" role="alert">{{ answer.error }}</p>
      <p v-else-if="answer.state === 'nothing found'" class="nothing">
        Nothing found for “{{ answer.query }}”. That is an answer: no page holds these words.
      </p>
      <ol v-else class="hits ruled">
        <li v-for="(hit, at) in answer.hits" :key="`${hit.knowledge_base}/${hit.work}/${hit.page.label}`" class="hit" :data-hit="at">
          <div class="hit-head">
            <RouterLink
              v-if="hit.view"
              class="hit-title"
              :to="{ name: 'page', params: { kb: hit.view.knowledge_base, work: hit.view.source_id, page: hit.view.pdf_page } }"
            >
              {{ hit.title }}
            </RouterLink>
            <span v-else class="hit-title">{{ hit.title }}</span>
            <!-- the edition its citation names beside the title (E1.a): "2nd edition, 2003", or the year alone -->
            <span v-if="hit.edition_said" class="hit-edition" data-part="hit-edition">{{ hit.edition_said }}</span>
            <KnowledgeBaseMark :kb="hit.knowledge_base" />
            <span class="licence">{{ hit.licence }}</span>
          </div>
          <div class="hit-place">
            <span class="page-label">{{ pageLabel(hit) }}</span>
            <span v-if="hit.section" class="section">{{ hit.section }}</span>
            <span class="route">{{ hit.route }}</span>
            <span class="score">score {{ hit.score }}</span>
          </div>
          <p class="snippet">{{ hit.snippet }}</p>
          <p v-if="hit.terms_missing.length || !hit.view" class="hit-foot">
            <span v-if="hit.terms_missing.length" class="missing">missing: {{ hit.terms_missing.join(', ') }}</span>
            <span v-if="!hit.view" class="where">{{ hit.where }}</span>
          </p>
        </li>
      </ol>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.search-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
}

.question {
  font: inherit;
  flex: 1 1 24rem;
  max-width: 48rem;
  padding: var(--space-xs) var(--space-sm);
  color: var(--color-text-primary);
  background-color: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.question:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

.corpus {
  display: flex;
  gap: var(--space-xs);
}

.search-note,
.nothing {
  color: var(--color-text-secondary);
  margin: var(--space-xs) 0 var(--space-md);
}

.search-error {
  color: var(--color-error);
}

/* the space between two hits is as before, the shared row rule standing in its middle */
.hits {
  list-style: none;
  display: flex;
  flex-direction: column;
  max-width: 72rem;
}

.hits > .hit + .hit {
  padding-top: var(--space-sm);
}

.hits > .hit:not(:last-child) {
  padding-bottom: var(--space-sm);
}

.hit-head,
.hit-place,
.hit-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-xs) var(--space-md);
}

.hit-title {
  color: var(--color-text-primary);
}

a.hit-title {
  color: var(--color-accent);
  text-decoration: none;
}

a.hit-title:hover {
  text-decoration: underline;
}

.licence,
.section,
.route,
.score,
.where {
  color: var(--color-text-secondary);
}

.missing {
  color: var(--color-warning);
}

/* the page's own words around the match, as text and with its line breaks */
.snippet {
  white-space: pre-line;
  margin: var(--space-xs) 0;
  padding-left: var(--space-sm);
  border-left: 2px solid var(--color-border);
}

.where {
  word-break: break-all;
}
</style>
