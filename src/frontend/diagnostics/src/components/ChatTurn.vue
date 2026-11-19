<script setup lang="ts">
import { computed } from 'vue'
import FoldSection from '@/components/base/FoldSection.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import ChatServerAnswer from '@/components/ChatServerAnswer.vue'
import type { IconName } from '@/icon_registry'
import { usd } from '@/cost_format'
import { renderMarkdown } from '@/render_markdown'
import type { ChatResult, SecurityCheck } from '@/types/api/chat_types'
import type { components } from '@/types/api/diagnostics_api'
import { counted } from '@/counted'

/**
 * One turn of the chat, by its kind (decision 100.a). A knowledge turn shows its answer, its quotes word for word with
 * the page each comes from, what the sources do not cover, a follow-up question and the disclaimer; a server turn what the
 * search server answered; a calculation the text code wrote from the numbers. Model text is Markdown, rendered through
 * `render_markdown`; a quote is verbatim and shown as text. Beneath every turn: its id, time and cost, and the security
 * checks, folded away. The agent's own words are never shown: the API does not even send them.
 */
const props = defineProps<{
  result: ChatResult
}>()

type PageLink = components['schemas']['PageLink']
type ArticleLink = components['schemas']['ArticleLink']

const turn = computed(() => props.result.turn ?? null)
// how a knowledge turn's behaviour looks: an answer as itself, nothing found as a warning, a decline or a failure as a notice
const LOOKS: Record<string, string> = {
  answer: 'answer', clarify: 'answer', not_found: 'warning',
  decline_off_topic: 'notice', decline_harmful: 'notice', invalid: 'notice', error: 'notice',
}
const look = computed(() => LOOKS[turn.value?.behaviour ?? ''] ?? 'notice')
// each rendered once per turn, not on every render
const answerHtml = computed(() => renderMarkdown(turn.value?.answer))
const gapsHtml = computed(() => renderMarkdown(turn.value?.gaps))
const followUpHtml = computed(() => renderMarkdown(turn.value?.follow_up))
const textHtml = computed(() => renderMarkdown(props.result.text))

const STATUS: Record<string, { icon: IconName, role: string }> = {
  'passed': { icon: 'status-ok', role: 'quiet' },
  'applied': { icon: 'status-ok', role: 'quiet' },
  'not reached': { icon: 'status-unjudged', role: 'quiet' },
  'warning': { icon: 'status-unknown', role: 'warning' },
  'blocked': { icon: 'status-error', role: 'error' },
}

function statusOf(check: SecurityCheck): { icon: IconName, role: string } {
  return STATUS[check.status] ?? { icon: 'status-unknown', role: 'warning' }
}

function pageOf(view: PageLink) {
  return { name: 'page', params: { kb: view.knowledge_base, work: view.source_id, page: view.pdf_page } }
}

// an HTML section's article, scrolled to the section (164.a): beside the source's own page, never instead of it
function articleOf(article: ArticleLink) {
  return { name: 'html-section', params: { kb: article.knowledge_base, work: article.source_id, section: article.label } }
}
</script>

<template>
  <article class="chat-turn" :data-kind="result.kind" :data-turn="result.turn_id">
    <template v-if="result.kind === 'knowledge' && turn">
      <!-- the search's measure of its best passage, in sight: a near miss must not read like a clear hit -->
      <p v-if="typeof turn.relevance === 'number'" class="relevance" :class="{ below: turn.below_floor }" data-part="relevance">
        <AppIcon v-if="turn.below_floor" name="status-unknown" />
        relevance {{ turn.relevance.toFixed(3) }}<template v-if="typeof turn.relevance_floor === 'number'">, floor {{ turn.relevance_floor.toFixed(3) }}</template>
        <template v-if="turn.below_floor">: the best passage lies below the floor</template>
      </p>
      <!-- whose words are whose: the answer is the model's, the quotes are the sources' own -->
      <p v-if="turn.quotes.length || turn.sources.length" class="part-label" data-part="answer">
        The answer, in the model's words; a number in brackets names the passage a sentence draws on
      </p>
      <!-- eslint-disable-next-line vue/no-v-html -- model output, sanitised in render_markdown: no raw HTML, an allow-list of tags -->
      <div class="markdown answer" :class="look" :data-behaviour="turn.behaviour" v-html="answerHtml" />
      <p v-if="turn.quotes.length" class="part-label" data-part="quotes">Quoted word for word, each checked against its passage</p>
      <section v-if="turn.quotes.length" class="quotes">
        <blockquote v-for="quote in turn.quotes" :key="`${quote.passage}/${quote.text}`" class="quote" :data-passage="quote.passage">
          <!-- verbatim, as checked against its passage: text, never Markdown -->
          <p class="quote-text">{{ quote.text }}</p>
          <p class="quote-source">
            [{{ quote.passage }}] {{ quote.citation.text }}<template v-if="quote.citation.licence"> · {{ quote.citation.licence }}</template>
            <RouterLink v-if="quote.view" class="open" :to="pageOf(quote.view)">open the page</RouterLink>
            <a v-else-if="quote.citation.link" class="open" :href="quote.citation.link" target="_blank" rel="noopener noreferrer">open the source</a>
            <RouterLink v-if="quote.article" class="open" :to="articleOf(quote.article)" data-part="article">open in the article</RouterLink>
          </p>
        </blockquote>
      </section>
      <div v-if="turn.gaps" class="gaps">
        <span class="label">Not covered by the sources:</span>
        <!-- eslint-disable-next-line vue/no-v-html -- model output, sanitised in render_markdown -->
        <div class="markdown" v-html="gapsHtml" />
      </div>
      <div v-if="turn.follow_up" class="follow-up">
        <span class="label">A question back:</span>
        <!-- eslint-disable-next-line vue/no-v-html -- model output, sanitised in render_markdown -->
        <div class="markdown" v-html="followUpHtml" />
      </div>
      <FoldSection v-if="turn.sources.length" class="sources" title="Sources" :count="counted(turn.sources.length, 'passage')">
        <ol class="ruled">
          <li v-for="source in turn.sources" :key="source.number" :data-source="source.number">
            [{{ source.number }}] {{ source.citation.text }}
            <RouterLink v-if="source.view" class="open" :to="pageOf(source.view)">open the page</RouterLink>
            <a v-else-if="source.citation.link" class="open" :href="source.citation.link" target="_blank" rel="noopener noreferrer">open the source</a>
            <RouterLink v-if="source.article" class="open" :to="articleOf(source.article)" data-part="article">open in the article</RouterLink>
          </li>
        </ol>
      </FoldSection>
      <p v-if="turn.disclaimer" class="disclaimer">{{ turn.disclaimer }}</p>
    </template>
    <ChatServerAnswer v-else-if="result.kind === 'server' && result.server" :server="result.server" />
    <template v-else-if="result.kind === 'calculation'">
      <!-- eslint-disable-next-line vue/no-v-html -- written by code from the numbers, sanitised in render_markdown all the same -->
      <div class="markdown" v-html="textHtml" />
      <p v-if="result.disclaimer" class="disclaimer">{{ result.disclaimer }}</p>
    </template>
    <!-- an invalid question, and any kind the core adds later: its text, as text -->
    <p v-else class="notice">{{ result.text }}</p>
    <p v-if="result.call_limit_reached" class="cap"><AppIcon name="status-unknown" /> {{ result.call_limit_reached }}</p>

    <footer class="turn-foot">
      <span class="turn-id">{{ result.turn_id }}</span>
      · {{ (result.seconds ?? 0).toFixed(1) }} s
      · {{ typeof result.usd === 'number' ? `≈ ${usd(result.usd)} USD` : 'cost unknown' }}
      <span class="cost-note">(agent, router and generator; query embeddings not counted)</span>
      <span v-if="!result.logged" class="not-logged">· not in the turn log</span>
      <FoldSection class="security" title="Security checks">
        <ul class="ruled">
          <li v-for="check in result.security" :key="check.check" :class="statusOf(check).role" :data-check="check.check">
            <AppIcon :name="statusOf(check).icon" /> {{ check.status }} · {{ check.name }}<span v-if="check.detail" class="detail">: {{ check.detail }}</span>
          </li>
        </ul>
      </FoldSection>
    </footer>
  </article>
</template>

<style scoped>
.chat-turn {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.answer.warning {
  color: var(--color-warning);
}

.answer.notice,
.notice {
  color: var(--color-text-secondary);
}

.quote {
  border-left: 3px solid var(--color-border);
  padding: var(--space-xs) var(--space-md);
}

.quote-text {
  white-space: pre-wrap;
}

.part-label,
.relevance,
.follow-up .label,
.quote-source,
.gaps .label,
.disclaimer,
.turn-foot,
.cost-note,
.detail,
.sources {
  color: var(--color-text-secondary);
}

.open,
.sources a {
  color: var(--color-accent);
  text-decoration: none;
  margin-left: var(--space-sm);
}

.open:hover {
  text-decoration: underline;
}

.cap,
.warning,
.relevance.below {
  color: var(--color-warning);
}

.relevance {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.error {
  color: var(--color-error);
}

.quiet {
  color: var(--color-text-secondary);
}

.sources ol,
.security ul {
  padding-left: var(--space-lg);
}

.security ul {
  list-style: none;
  padding-left: 0;
}

summary {
  cursor: pointer;
}

/* Markdown the view did not write: spacing and tables, since the base style zeroes every margin */
.markdown :deep(p),
.markdown :deep(ul),
.markdown :deep(ol),
.markdown :deep(pre),
.markdown :deep(blockquote),
.markdown :deep(table) {
  margin-bottom: var(--space-sm);
}

.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: var(--space-lg);
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: var(--space-sm) 0 var(--space-xs);
}

.markdown :deep(code) {
  background-color: var(--color-bg-elevated);
  padding: 0 2px;
}

.markdown :deep(pre) {
  white-space: pre-wrap;
  background-color: var(--color-bg-elevated);
  padding: var(--space-sm);
}

.markdown :deep(table) {
  border-collapse: collapse;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--color-border);
  padding: 2px var(--space-sm);
  font-variant-numeric: tabular-nums;
}

.markdown :deep(a) {
  color: var(--color-accent);
}

.markdown > :deep(:last-child) {
  margin-bottom: 0;
}
</style>
