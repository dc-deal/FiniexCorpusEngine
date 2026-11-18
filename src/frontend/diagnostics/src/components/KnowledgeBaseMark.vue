<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * The knowledge base a row belongs to, in the name the row carries (decision 80.a): free, or licensed, which stays on this
 * machine. A glyph beside the word and no colour, since it is not a state.
 */
defineProps<{
  kb: KnowledgeBase
}>()
</script>

<template>
  <span class="kb-mark" :data-kb="kb">
    <AppIcon :name="kb === 'licensed' ? 'kb-licensed' : 'kb-free'" />
    <span class="kb-word">{{ kb }}</span>
  </span>
</template>

<style scoped>
/* centred on the line it stands in, whatever that line aligns by (179: every inline badge alike) */
.kb-mark {
  display: inline-flex;
  align-items: center;
  align-self: center;
  vertical-align: middle;
  gap: var(--space-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
