<script setup lang="ts">
import AppButton from '@/components/base/AppButton.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import MathTex from '@/components/reading/MathTex.vue'
import type { Segment } from '@/types/api/page_types'

/**
 * Prose as the core parsed it: text as text, math typeset, code as code, and its inline marks (decision 206.a): a
 * superscript raised, a subscript lowered, and a note's marker raised; and a table cell's line break as a break. A marker
 * whose note the page holds (the API's `note`) is a link to it: under the pointer a card holds the note's text, and a
 * click brings the note into view. A marker without a note stands alone. None of it is ever markup.
 */
defineProps<{
  segments: Segment[]
}>()

const emit = defineEmits<{
  jump: [id: string]
}>()
</script>

<template>
  <span class="segments">
    <template v-for="(segment, at) in segments" :key="at">
      <MathTex v-if="segment.kind === 'math'" :latex="segment.content" />
      <code v-else-if="segment.kind === 'code'">{{ segment.content }}</code>
      <sub v-else-if="segment.kind === 'sub'" data-segment="sub">{{ segment.content }}</sub>
      <HoverCard v-else-if="segment.kind === 'fn' && segment.note" :title="`Note ${segment.content}`" :rows="[{ label: 'note', value: segment.note_text }]">
        <sup class="note-marker" data-segment="fn"><AppButton variant="link" :data-note="segment.note" @click="emit('jump', segment.note)">{{ segment.content }}</AppButton></sup>
      </HoverCard>
      <sup v-else-if="segment.kind === 'fn' || segment.kind === 'sup'" :data-segment="segment.kind">{{ segment.content }}</sup>
      <br v-else-if="segment.kind === 'br'" data-segment="br">

      <template v-else>{{ segment.content }}</template>
    </template>
  </span>
</template>
