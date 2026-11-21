<script setup lang="ts">
import FoldSection from '@/components/base/FoldSection.vue'
import RecordRows from '@/components/base/RecordRows.vue'
import PageLadderLines from '@/components/PageLadderLines.vue'
import type { PageLadder } from '@/types/api/ladder_types'

/**
 * An EPUB's or an HTML work's section in the rows every page's record has (the operator's H1.a, 21 Nov: "the layout never
 * jumps between pages"): Check, Route, Reading, Findings, Coverage, Reading History, Lab, Details, in that order. A section is
 * born digital: no reader read it and no judge checked it, so every row but its coverage says it has nothing, in one word.
 */
defineProps<{
  ladder: PageLadder | null | undefined
}>()

const NONE_BEFORE = ['Check', 'Route', 'Reading', 'Findings']
const NONE_AFTER = ['Reading History', 'Lab', 'Details']
</script>

<template>
  <RecordRows class="summary section-record" data-part="section-record">
    <FoldSection v-for="label in NONE_BEFORE" :key="label" :label="label" plain><template #title><span class="none">none</span></template></FoldSection>
    <PageLadderLines v-if="ladder" :ladder="ladder" label="Coverage" />
    <FoldSection v-else label="Coverage" plain><template #title><span class="none">none</span></template></FoldSection>
    <FoldSection v-for="label in NONE_AFTER" :key="label" :label="label" plain><template #title><span class="none">none</span></template></FoldSection>
  </RecordRows>
</template>

<style scoped>
.none {
  color: var(--color-text-secondary);
}
</style>
