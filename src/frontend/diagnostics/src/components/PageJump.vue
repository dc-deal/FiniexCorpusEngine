<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * Straight to a PDF page of the work by its number, instead of scrolling a list of hundreds. A page the work has no
 * reading of opens all the same, and the page view says so.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
  // in a head of labelled lines the line's label names it, so the field says it only to a reader that cannot see (219.a)
  bare?: boolean
}>()

const router = useRouter()
const wanted = ref('')

// digits only: Number() alone would also take '1e2' as page 100 and '0x10' as page 16
function jump(): void {
  const typed = wanted.value.trim()
  if (!/^\d+$/.test(typed) || Number(typed) < 1) return
  void router.push({ name: 'page', params: { kb: props.kb, work: props.work, page: Number(typed) } })
  wanted.value = ''
}
</script>

<template>
  <label class="page-jump">
    <span v-if="!bare" class="page-jump-label">PDF page</span>
    <input v-model="wanted" :aria-label="bare ? 'PDF page' : undefined" type="text" inputmode="numeric" size="5" placeholder="go to" @keydown.enter="jump">
  </label>
</template>

<style scoped>
.page-jump {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.page-jump-label {
  color: var(--color-text-secondary);
}

.page-jump input {
  font: inherit;
  width: 8ch;
  padding: 2px var(--space-xs);
  color: var(--color-text-primary);
  background-color: var(--color-bg-elevated);
  /* the border a control's surface has, so the field reads as one to type in, never as disabled (the viewer's tip 7) */
  border: 1px solid var(--color-border-overlay);
  border-radius: 4px;
}

.page-jump input:hover {
  border-color: var(--color-accent);
}

.page-jump input:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}
</style>
