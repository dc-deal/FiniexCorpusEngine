<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { epubImageUrl } from '@/api/api_client'
import ApiFailure from '@/components/ApiFailure.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import PagerLinks from '@/components/base/PagerLinks.vue'
import SectionRecord from '@/components/SectionRecord.vue'
import { useEpubStore } from '@/stores/epub_store'
import { useViewName } from '@/view_name'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One section of a licensed EPUB work (decision 123.a, the operator's P1.a) as the librarian serves it, `s12` as a search hit
 * names it: its heading path, where it stands in the EPUB, and its text with each image where its mark stood. An image inside
 * a line of text (an inline formula, most often) stays in its line; one on its own is a block. Its alt text is the image's
 * alt attribute. The images come from the EPUB's own zip through the API, never extracted; reading a formula image as
 * LaTeX comes later. The text is the book's, so it never leaves this machine: no screenshot, test or file holds it.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
  section: string
}>()

const store = useEpubStore()
const { sectionError } = storeToRefs(store)

watch(() => [props.kb, props.work, props.section] as const, ([kb, work, section]) => {
  void store.loadSection(kb, work, section)
}, { immediate: true })

const shown = computed(() => store.sectionOf(props.kb, props.work, props.section))
useViewName(() => (shown.value ? `${shown.value.work_title} ${shown.value.label}` : null))

function neighbour(label: string | null | undefined) {
  return label ? { to: { name: 'epub-section', params: { kb: props.kb, work: props.work, section: label } }, label } : null
}
</script>

<template>
  <section class="epub-section">
    <p class="trail">
      <RouterLink to="/sources">Sources</RouterLink>
      <span aria-hidden="true">›</span>
      <RouterLink :to="{ name: 'epub-work', params: { kb, work } }">{{ shown?.work_title ?? work }}</RouterLink>
      <KnowledgeBaseMark :kb="kb" />
    </p>
    <ApiFailure v-if="sectionError" :error="sectionError" @retry="store.loadSection(kb, work, section)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <PagerLinks :previous="neighbour(shown.previous)" :next="neighbour(shown.next)" label="Previous and next section" />
      <h1 class="view-title" data-part="heading-path">{{ shown.heading_path || shown.work_title }}</h1>
      <p class="place" data-part="place">{{ shown.label }}<template v-if="shown.place"> · {{ shown.place }}</template></p>
      <!-- the record's rows, as every page has them (H1.a): a section has nothing but its own ladder (V2.a), born digital, its
           text served, keyword search, its chunks in the private index (#8), and every other row says so -->
      <SectionRecord :ladder="shown.ladder" />
      <!-- the text in its runs, its line breaks kept; an image where its mark stood, inline in its line or a block of its own -->
      <div class="section-text" data-part="section-text">
        <template v-for="(part, at) in shown.parts" :key="at">
          <span v-if="part.kind === 'text'" class="text-run">{{ part.text }}</span>
          <img
            v-else-if="part.image && part.image.inline"
            class="inline-image"
            data-part="inline-image"
            :src="epubImageUrl(kb, work, part.image.href)"
            :alt="part.image.alt"
            loading="lazy"
          >
          <figure v-else-if="part.image" class="block-image" data-part="block-image">
            <img :src="epubImageUrl(kb, work, part.image.href)" :alt="part.image.alt" loading="lazy">
          </figure>
        </template>
      </div>
    </template>
  </section>
</template>

<style scoped>
.trail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
}

.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover {
  text-decoration: underline;
}

.place {
  margin-bottom: var(--space-md);
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

/* the book's text as the librarian holds it: its line breaks are its paragraphs */
.section-text {
  max-width: 80ch;
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

/* an inline image sits on the line, as tall as a line may grow for a formula, never wider than the column; on a light
   ground, since a formula image is most often black on a transparent one and would vanish on the dark theme */
.inline-image {
  max-width: 100%;
  vertical-align: middle;
  background-color: #ffffff;
}

/* an image on its own: a block, on a light ground as the book prints it, never wider than the column */
.block-image {
  margin: var(--space-sm) 0;
}

.block-image img {
  display: block;
  max-width: 100%;
  height: auto;
  background-color: #ffffff;
}
</style>
