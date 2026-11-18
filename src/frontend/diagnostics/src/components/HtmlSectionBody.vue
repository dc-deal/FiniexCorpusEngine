<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/base/AppIcon.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import { renderStripped } from '@/render_html'
import type { HtmlSection } from '@/types/api/html_types'

/**
 * One section of an HTML work beside its chunks (the operator's 6.a). On the left, the section's original as line 1's function
 * strips it from the raw file, sanitised again here (`render_html`), formulas typeset, images as their alt text. On the
 * right, its text as the index holds it, chunk by chunk, each in a fine box with its id, its characters in the section's
 * text and the characters it shares with the chunk before it, marked as such; a chunk the API did not find in the
 * section's text says so. A heading the loader drops as noise shows its original and says it has no chunks. What the
 * dashed text means stands in the view's hint; "N shared" says in its card how much and with which chunk (203.a).
 */
const props = defineProps<{
  section: HtmlSection
}>()

const original = computed(() => renderStripped(props.section.original))

// A chunk's text in its paragraphs: the index joins a section's blocks with one '\n', drawn here as a paragraph break (the operator,
// 10 Nov: it read as one run). The characters it shares with the chunk before stay marked within them. Display only: the
// text and its offsets are the API's, unchanged.
function paragraphsOf(text: string, overlap: number): { shared: string, rest: string }[] {
  let at = 0
  return text.split('\n').map(line => {
    const cut = Math.max(0, Math.min(overlap, at + line.length) - at)
    at += line.length + 1
    return { shared: line.slice(0, cut), rest: line.slice(cut) }
  })
}
</script>

<template>
  <div class="side-by-side">
    <div class="original">
      <p v-if="!section.original" class="pending">{{ section.original_why_not ?? 'No original of this section.' }}</p>
      <!-- eslint-disable-next-line vue/no-v-html -- line 1's allow-listed HTML, sanitised again in render_html -->
      <div v-else class="stripped" data-part="original" v-html="original" />
    </div>

    <div class="chunks" data-part="chunks">
      <p v-if="section.dropped" class="dropped-note" data-part="dropped">
        Dropped as noise: not indexed, so no chunks. Its text never stands in a search answer.
      </p>
      <p v-else class="chunks-head">
        {{ section.chunks.length }} {{ section.chunks.length === 1 ? 'chunk' : 'chunks' }} · {{ section.text.length.toLocaleString('en') }}
        characters, as indexed
      </p>
      <p v-if="section.not_found" class="not-found" role="alert">
        <AppIcon name="status-error" /> {{ section.not_found }} of these chunks were not found in the section's text
      </p>
      <ol class="chunk-list">
        <li v-for="chunk in section.chunks" :key="chunk.id" class="chunk" :data-chunk="chunk.number">
          <p class="chunk-head">
            <span>chunk {{ chunk.number }} of {{ section.chunks.length }}</span>
            <span class="chunk-id">{{ chunk.id }}</span>
            <span v-if="chunk.start !== null && chunk.end !== null">characters {{ chunk.start.toLocaleString('en') }}–{{ chunk.end.toLocaleString('en') }}</span>
            <span v-else class="missing">not found in the section's text</span>
            <HoverCard v-if="chunk.overlap" title="Shared with the chunk before" :rows="[{ label: 'characters', value: chunk.overlap.toLocaleString('en') }, { label: 'with', value: `chunk ${chunk.number - 1}` }]"><span class="shared-count">{{ chunk.overlap }} shared</span></HoverCard>
            <span v-if="chunk.tokens">{{ chunk.tokens }} tokens</span>
          </p>
          <div class="chunk-text">
            <p v-for="(paragraph, at) in paragraphsOf(chunk.text, chunk.overlap)" :key="at" class="paragraph"><span v-if="paragraph.shared" class="overlap">{{ paragraph.shared }}</span>{{ paragraph.rest }}</p>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
/* the original and its chunks side by side, each section's pair at the same height of the one scroll; on a narrow screen
   one above the other */
.side-by-side {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-md);
  align-items: start;
}

@media (max-width: 900px) {
  .side-by-side {
    grid-template-columns: minmax(0, 1fr);
  }
}

.pending,
.chunks-head,
.chunk-head,
.dropped-note {
  color: var(--color-text-secondary);
}

.chunks-head,
.chunk-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
}

.chunks-head {
  margin-bottom: var(--space-xs);
}

.not-found,
.missing {
  color: var(--color-error);
}

.not-found {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}

/* every chunk in a fine box of its own, as the reading's blocks are */
.chunk-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.chunk {
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--color-row-rule);
}

.chunk-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* each '\n' of the indexed text a paragraph break, so the blocks the index joined read apart again */
.chunk-text .paragraph + .paragraph {
  margin-top: var(--space-sm);
}

/* the stripped original: plain prose, its headings and tables quiet, an image as its alt text */
.stripped {
  line-height: 1.6;
}

.stripped :deep(h1),
.stripped :deep(h2),
.stripped :deep(h3),
.stripped :deep(h4),
.stripped :deep(h5),
.stripped :deep(h6) {
  margin: 0 0 var(--space-xs);
}

.stripped :deep(p),
.stripped :deep(ul),
.stripped :deep(ol),
.stripped :deep(dl),
.stripped :deep(pre),
.stripped :deep(blockquote),
.stripped :deep(table) {
  margin-bottom: var(--space-sm);
}

.stripped :deep(ul),
.stripped :deep(ol) {
  padding-left: var(--space-lg);
}

.stripped :deep(table) {
  border-collapse: collapse;
}

.stripped :deep(th),
.stripped :deep(td) {
  border: 1px solid var(--color-border);
  padding: 2px var(--space-sm);
  vertical-align: top;
}

.stripped :deep(pre) {
  white-space: pre-wrap;
}

.stripped :deep(a) {
  color: var(--color-accent);
}

.stripped :deep(span[data-image])::before {
  content: '[image: ' attr(data-image) ']';
  color: var(--color-text-secondary);
}

/* a formula of the original, typeset: a block one stands on a line of its own and scrolls sideways when wide */
.stripped :deep(span[data-display='block']) {
  display: block;
  overflow-x: auto;
  margin: var(--space-xs) 0;
}

/* a chunk boundary is structure, not a fault: the annotation role, dashed */
.overlap {
  text-decoration: underline dashed var(--color-annotation);
  text-underline-offset: 3px;
}
</style>
