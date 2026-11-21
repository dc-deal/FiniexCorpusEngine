<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/base/AppIcon.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import ContentsTree from '@/components/librarian/ContentsTree.vue'
import HitCards from '@/components/librarian/HitCards.vue'
import LibrarianWorks from '@/components/librarian/LibrarianWorks.vue'
import { knowledgeBaseOf } from '@/knowledge_base'
import type { IconName } from '@/icon_registry'
import type { LibrarianCall } from '@/types/api/librarian_types'

/**
 * One call's answer as the librarian gave it (L1.a): a head line of its state, how many it found, the server's own words,
 * relevance against its floor in the warning role where it lies below, how long the call took and whether a model ran;
 * the plan the router made, where it ran; then the tool's own parts, hits as cards, works as a table, contents as a tree,
 * a page as its text, an image with what it is; and the answer as it came, one click away, always.
 */
const props = defineProps<{
  call: LibrarianCall
}>()

const head = computed(() => props.call.head)
// the state by form, word and colour: found, an answer that is not one (nothing found, declined, no image), an error
const stateIcon = computed<IconName>(() => (head.value.state === 'found' ? 'status-ok' : head.value.state === 'error' ? 'status-error' : 'status-unknown'))
// a duration as a person reads it: milliseconds under a second
const took = computed(() => (head.value.seconds < 1 ? `${Math.round(head.value.seconds * 1000)} ms` : `${head.value.seconds.toFixed(1)} s`))
const raw = computed(() => JSON.stringify(props.call.answer, null, 2))
</script>

<template>
  <div class="librarian-answer" :data-tool="call.tool">
    <p class="call-head" data-part="call-head">
      <span class="state" :class="head.state === 'error' ? 'error' : head.state === 'found' ? '' : 'quiet'" data-part="state">
        <AppIcon :name="stateIcon" /> {{ head.state ?? 'no state' }}
      </span>
      <span v-if="head.count" data-part="count">{{ head.count }}</span>
      <span v-if="head.said" class="said" data-part="said">{{ head.said }}</span>
      <span v-if="head.floor_said" :class="{ warning: head.below_floor }" data-part="floor">{{ head.floor_said }}</span>
      <span class="secondary" data-part="took">{{ took }}</span>
      <span class="secondary" data-part="model">{{ head.model_said }}</span>
    </p>
    <!-- the plan the router made, where it ran: its translation of the question -->
    <LabelledLines v-if="call.plan" class="plan" data-part="plan" :label-chars="14">
      <LabelledLine label="Search query">{{ call.plan.search_query ?? '' }}</LabelledLine>
      <LabelledLine label="Concept query">{{ call.plan.concept_query ?? '' }}</LabelledLine>
      <LabelledLine label="Keywords">{{ call.plan.keywords.join(', ') }}</LabelledLine>
      <LabelledLine v-if="call.plan.behaviour" label="Behaviour">{{ call.plan.behaviour }}{{ call.plan.fell_back ? ' · fell back' : '' }}</LabelledLine>
    </LabelledLines>
    <HitCards v-if="call.hits?.length" :hits="call.hits" />
    <LibrarianWorks v-else-if="call.works || call.found_works?.length" :works="call.works" :found="call.found_works" />
    <ContentsTree v-else-if="call.contents?.entries.length" :contents="call.contents" />
    <div v-else-if="call.page" class="opened-page" data-part="opened-page">
      <p class="page-head">
        <KnowledgeBaseMark v-if="knowledgeBaseOf(call.page.knowledge_base)" :kb="knowledgeBaseOf(call.page.knowledge_base)!" />
        <strong>{{ call.page.title ?? call.page.work }}</strong>
        <span v-if="call.page.edition_said" class="secondary">{{ call.page.edition_said }}</span>
        <span>{{ call.page.page_said }}</span>
        <span v-if="call.page.section" class="secondary">{{ call.page.section }}</span>
        <RouterLink v-if="call.page.view" :to="call.page.view" data-part="page-view">in the page view</RouterLink>
      </p>
      <p class="secondary">{{ [call.page.route, call.page.licence].filter(Boolean).join(' · ') }}</p>
      <!-- the page word for word, as a client receives it: text, never Markdown -->
      <pre class="page-text" data-part="page-text">{{ call.page.text }}</pre>
    </div>
    <figure v-else-if="call.image" class="sent-image" data-part="sent-image">
      <img :src="call.image.src" :alt="`${call.image.page_said ?? 'the page'} as the librarian sent it`">
      <LabelledLines class="described" :label-chars="10">
        <LabelledLine v-for="[label, value] in call.image.described" :key="label" :label="label">{{ value }}</LabelledLine>
      </LabelledLines>
    </figure>
    <!-- the answer as it came, one click away, always; an image's pixels stand above it as the image -->
    <FoldSection class="raw-answer" title="raw JSON" data-part="raw-json">
      <pre class="raw">{{ raw }}</pre>
    </FoldSection>
  </div>
</template>

<style scoped>
.librarian-answer {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.call-head,
.page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
}

.state {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  font-weight: bold;
}

.state.quiet,
.secondary {
  color: var(--color-text-secondary);
}

.state.error {
  color: var(--color-error);
}

.warning {
  color: var(--color-warning);
}

.page-text,
.raw {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 40rem;
  overflow-y: auto;
  margin: 0;
}

.sent-image img {
  display: block;
  max-width: 100%;
  height: auto;
  border: 1px solid var(--color-border);
  margin-bottom: var(--space-xs);
}
</style>
