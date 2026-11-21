<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import AnalysisSection from '@/components/base/AnalysisSection.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HintPanel from '@/components/base/HintPanel.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import HtmlSectionBody from '@/components/HtmlSectionBody.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import PagerLinks from '@/components/base/PagerLinks.vue'
import RecordZone from '@/components/base/RecordZone.vue'
import SectionRecord from '@/components/SectionRecord.vue'
import { overlapHint as hintOf } from '@/overlap_hint'
import { useHtmlStore } from '@/stores/html_store'
import { useViewName } from '@/view_name'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * An HTML work's article whole, on one scroll (the operator, 10 Nov: a click on "Sharpe ratio" should show the whole article): the
 * top unit of the work's outline that holds the section in the address, a Wikipedia article, an SRE chapter, a chapter of
 * Lefèvre. Every section stands in the work's order, its original beside its chunks; a heading the loader dropped as
 * noise stands greyed at its place; a heading with no text of its own stands as a heading. The section in the address is
 * marked and scrolled to; the contents jump within the scroll, and the neighbouring articles are a click away. The work's
 * licence and attribution stand once above it all.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
  section: string
}>()

const store = useHtmlStore()
const { articleError } = storeToRefs(store)

watch(() => [props.kb, props.work, props.section] as const, ([kb, work, section]) => {
  void store.loadArticle(kb, work, section)
}, { immediate: true })

const shown = computed(() => store.articleOf(props.kb, props.work, props.section))

// The section in the address comes into view once its article stands, and again whenever the address names another. An
// article's first section, where previous and next lead, scrolls nothing while the view's head is in sight, so the boxes
// just clicked stay under the pointer; only from further down does the head come back into view.
const head = ref<HTMLElement | null>(null)
watch([shown, () => props.section], async ([article, label]) => {
  if (!article) return
  await nextTick()
  const first = article.entries.find(entry => entry.label)?.label
  if (label === first) head.value?.scrollIntoView?.({ block: 'nearest' })
  else document.querySelector(`[data-entry="${CSS.escape(label)}"]`)?.scrollIntoView?.({ block: 'start' })
}, { immediate: true })

// What the dashed line means, a hint on demand and only where a chunk shares text with the one before (the operator, 10 Nov: "rather show it as a hint"); the same sentence in the hover of the dashed text and of "N shared". The figures are the API's.
const shares = computed(() => shown.value?.entries.some(entry => entry.section?.chunks.some(chunk => chunk.overlap > 0)) ?? false)
const overlapHint = computed(() => hintOf(shown.value?.splitter))
const hintOpen = ref(false)

useViewName(() => (shown.value ? `${shown.value.title} ${props.section}` : null))
// the section in the address, whose record stands above the article (H1.a)
const chosen = computed(() => shown.value?.entries.find(entry => entry.label === props.section)?.section ?? null)
</script>

<template>
  <section class="html-article">
    <!-- the record in the standard width, the analysis below it alone wide (decision 183) -->
    <RecordZone>
      <p class="trail">
        <RouterLink to="/sources">Sources</RouterLink>
        ›
        <RouterLink :to="{ name: 'html-work', params: { kb, work } }">{{ shown?.work_title ?? work }}</RouterLink>
        <KnowledgeBaseMark v-if="shown" :kb="shown.knowledge_base" />
      </p>
      <ApiFailure v-if="articleError" :error="articleError" @retry="store.loadArticle(kb, work, section)" />
      <LoadingLine v-else-if="!shown" />
      <template v-else>
        <!-- the neighbouring articles first, in boxes of one width, so they stay under the pointer article after article; the
             title, of any length, follows them (the operator, 10 Nov: "page forward and back jumps when clicked") -->
        <header ref="head" class="article-head">
          <PagerLinks
            :previous="shown.previous ? { to: { name: 'html-section', params: { kb, work, section: shown.previous } }, label: shown.previous_title ?? shown.previous } : null"
            :next="shown.next ? { to: { name: 'html-section', params: { kb, work, section: shown.next } }, label: shown.next_title ?? shown.next } : null"
            width="14rem"
            label="Previous and next article"
          />
          <h1 class="view-title">{{ shown.title }}</h1>
        </header>
        <!-- the section's record in the rows every page has (H1.a): its own ladder (V2.a), born digital, its text served,
             keyword search, its chunks; every other row says it has nothing -->
        <SectionRecord :ladder="chosen?.ladder" />
        <!-- the work's licence and attribution stand above every original it shows -->
        <p class="attribution" data-part="attribution">
          <span v-if="shown.authors">{{ shown.authors }}</span>
          <a v-if="shown.licence && shown.licence_url" :href="shown.licence_url" target="_blank" rel="noopener noreferrer">{{ shown.licence }}</a>
          <span v-else-if="shown.licence">{{ shown.licence }}</span>
          <HintToggle v-if="shares" v-model:open="hintOpen" id="overlap" />
        </p>
        <!-- what the dashed line means and why it is there, on demand: the splitter's own figures, from the API -->
        <HintPanel v-if="shares && hintOpen" id="overlap" @close="hintOpen = false">
          <p class="legend" data-part="overlap-legend">{{ overlapHint }}</p>
        </HintPanel>

        <FoldSection class="contents" title="Contents">
          <ol class="contents-list">
            <li v-for="(entry, at) in shown.entries" :key="entry.label ?? `heading-${at}`" :style="{ paddingLeft: `${(entry.level - 1) * 1.25}rem` }">
              <RouterLink
                v-if="entry.label"
                :to="{ name: 'html-section', params: { kb, work, section: entry.label } }"
                :class="{ dropped: entry.section?.dropped, chosen: entry.label === section }"
              >
                {{ entry.title }}
              </RouterLink>
              <span v-else class="secondary">{{ entry.title }}</span>
            </li>
          </ol>
        </FoldSection>
      </template>
    </RecordZone>

    <!-- each section's original beside its chunks: the analysis, the one part that takes the wide container (183) -->
    <AnalysisSection v-if="shown && !articleError">
      <template #hint>
        <span class="analysis-hint">each section's original beside the chunks the search holds of it</span>
      </template>
      <article
        v-for="(entry, at) in shown.entries"
        :key="entry.label ?? `heading-${at}`"
        class="entry"
        :class="{ chosen: entry.label === section, dropped: entry.section?.dropped }"
        :data-entry="entry.label ?? undefined"
      >
        <!-- a section's own heading stands in its original; above it, a quiet line of its label, title and source -->
        <p v-if="entry.label" class="entry-head">
          <span class="entry-label">{{ entry.label }}</span>
          <span class="entry-title">{{ entry.title }}</span>
          <span v-if="entry.section?.dropped" class="dropped-word">dropped as noise: not indexed</span>
          <a v-if="entry.section?.url" :href="entry.section.url" target="_blank" rel="noopener noreferrer" class="source-link" data-part="source">open at source</a>
        </p>
        <!-- a heading with no text of its own has no original: its title stands as the heading it is -->
        <h2 v-else class="entry-heading">{{ entry.title }}</h2>
        <HtmlSectionBody v-if="entry.section" :section="entry.section" />
      </article>
    </AnalysisSection>
  </section>
</template>

<style scoped>
.analysis-hint {
  font-weight: normal;
  color: var(--color-text-secondary);
}

.trail {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

.trail a,
.attribution a,
.contents a,
.entry-head .source-link {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover,
.attribution a:hover,
.contents a:hover,
.source-link:hover {
  text-decoration: underline;
}

.article-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm) var(--space-lg);
  margin-bottom: var(--space-xs);
}

.attribution,
.legend,
.secondary {
  color: var(--color-text-secondary);
}

.attribution {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-xs);
}

.legend {
  margin-bottom: var(--space-sm);
  max-width: 72rem;
}

.contents {
  margin-bottom: var(--space-md);
}

.contents-list {
  list-style: none;
  margin-top: var(--space-xs);
}

.contents a.dropped {
  color: var(--color-text-secondary);
}

.contents a.chosen {
  color: var(--color-text-primary);
}

/* each section a band of the one scroll: its heading above its original and its chunks */
.entry {
  padding: var(--space-sm) 0 var(--space-md);
  border-top: 1px solid var(--color-row-rule);
  scroll-margin-top: var(--space-sm);
}

/* the section the address names */
.entry.chosen {
  box-shadow: inset 2px 0 0 var(--color-accent);
  padding-left: var(--space-sm);
}

/* a heading dropped as noise stands greyed at its place */
.entry.dropped {
  opacity: 0.7;
}

.entry-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-xs) var(--space-md);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-xs);
}
</style>
