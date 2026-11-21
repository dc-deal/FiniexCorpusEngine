<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '@/components/base/AppIcon.vue'
import HintPanel from '@/components/base/HintPanel.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import { chunkHint } from '@/overlap_hint'
import type { PageChunks } from '@/types/api/page_types'

/**
 * A PDF page "as served", chunk first (the operator, 21 Nov, in place of the dashed start lines): the page as the chunks
 * semantic search holds of it. A chunk is the semantic index's cut of the served text and usually holds several blocks, so
 * each is a group: its one-line head, the API's words (its letter in page order, its characters, its pages, what it shares
 * with the one before, where it runs in from or on to, a kept edition's "held back"), then the quoted blocks it holds in the
 * form the search and the chat quote, a block it holds in part marked "(part)", the text two chunks share dashed in both.
 * A block never quoted is in no chunk and stands nowhere here; quoted text no chunk placed here holds is listed apart, and
 * a chunk that cannot be placed is said in words. Nothing here is placed or counted by the view: every cut is the API's.
 */
defineProps<{
  chunks: PageChunks
}>()

const emit = defineEmits<{ hover: [block: string | null] }>()
const hintOpen = ref(false)
</script>

<template>
  <div class="chunk-groups" data-part="chunk-groups">
    <p class="chunks-said" data-part="chunks-said">
      <span>{{ chunks.head_said ?? chunks.said }}</span>
      <span v-if="chunks.held_back && !chunks.groups.length" class="held-back" data-part="held-back">kept: {{ chunks.held_back }}</span>
      <HintToggle id="chunks" v-model:open="hintOpen" />
    </p>
    <HintPanel v-if="hintOpen" id="chunks" @close="hintOpen = false">
      <p class="legend" data-part="chunks-legend">{{ chunkHint(chunks.splitter) }}</p>
    </HintPanel>
    <p v-if="chunks.not_placed" class="not-placed" role="alert" data-part="not-placed"><AppIcon name="status-error" /> {{ chunks.not_placed }}</p>
    <section v-for="group in chunks.groups" :key="group.id" class="chunk-group" :data-chunk="group.letter">
      <p class="chunk-head" data-part="chunk-head"><strong class="chunk-letter">chunk {{ group.letter }}</strong>{{ ` · ${group.head.join(' · ')}` }}</p>
      <ol class="chunk-blocks">
        <li v-for="(block, at) in group.blocks" :key="at" class="chunk-block" :data-block="block.block" :data-part-of="block.part ? 'part' : undefined"
            @mouseenter="emit('hover', block.block)" @mouseleave="emit('hover', null)">
          <p class="chunk-block-head">
            <span class="block-id">{{ block.block }}</span>
            <span class="block-class">{{ block.block_class }}</span>
            <span v-if="block.part" class="block-part" data-part="block-part">(part)</span>
          </p>
          <p class="served-form" data-part="served-form"><span v-for="(run, r) in block.runs" :key="r" :class="{ overlap: run.shared }">{{ run.text }}</span></p>
        </li>
      </ol>
    </section>
    <!-- quoted text no chunk placed here holds; every quoted block where the page has no chunk -->
    <section v-if="chunks.outside.length" class="chunk-group outside" data-part="outside">
      <p v-if="chunks.groups.length" class="chunk-head"><strong class="chunk-letter">in no chunk placed here</strong></p>
      <ol class="chunk-blocks">
        <li v-for="(block, at) in chunks.outside" :key="at" class="chunk-block" :data-block="block.block"
            @mouseenter="emit('hover', block.block)" @mouseleave="emit('hover', null)">
          <p class="chunk-block-head">
            <span class="block-id">{{ block.block }}</span>
            <span class="block-class">{{ block.block_class }}</span>
            <span v-if="block.part" class="block-part" data-part="block-part">(part)</span>
          </p>
          <p class="served-form" data-part="served-form"><span v-for="(run, r) in block.runs" :key="r">{{ run.text }}</span></p>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.chunks-said {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 var(--space-sm);
  margin-bottom: var(--space-xs);
}

.held-back,
.chunk-block-head,
.legend {
  color: var(--color-text-secondary);
}

.not-placed {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-error);
}

/* a chunk a group in the annotation's role: a dashed edge, as an HTML section's chunks are marked, the blocks it holds inside */
.chunk-group {
  margin-top: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  border: 1px dashed var(--color-annotation);
}

.chunk-group.outside {
  border-color: var(--color-row-rule);
}

.chunk-head {
  margin-bottom: var(--space-xs);
}

.chunk-blocks {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

/* a block in the reading's own look: a fine box, its id and class at its top */
.chunk-block {
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--color-row-rule);
}

.chunk-block-head {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
}

.served-form {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.overlap {
  text-decoration: underline dashed var(--color-annotation);
  text-underline-offset: 3px;
}
</style>
