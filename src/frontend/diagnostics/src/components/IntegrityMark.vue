<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/base/AppIcon.vue'
import type { IconName } from '@/icon_registry'

/**
 * Whether a page's reading file is still what was checked, as a glyph and the core's own word (69.a), never as colour
 * alone. A whole file and a page without a reading stay quiet; a file that differs from the checked text, or is gone, is
 * an error: what the search and the chat would quote is no longer what the checks saw.
 */
const props = defineProps<{
  state: string
}>()

interface Look {
  icon: IconName
  role: 'quiet' | 'warning' | 'error'
}

// The core's words: whole, tampered, missing, `no reading` for a row without one. A word added later shows unfamiliar.
const LOOKS: Record<string, Look> = {
  'whole': { icon: 'status-ok', role: 'quiet' },
  'no reading': { icon: 'status-unjudged', role: 'quiet' },
  'tampered': { icon: 'status-error', role: 'error' },
  'missing': { icon: 'status-error', role: 'error' },
}

const look = computed<Look>(() => LOOKS[props.state] ?? { icon: 'status-unknown', role: 'warning' })
</script>

<template>
  <span class="integrity-mark" :class="look.role" :data-integrity="state">
    <AppIcon :name="look.icon" />
    <span class="integrity-word">{{ state }}</span>
  </span>
</template>

<style scoped>
.integrity-mark {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  white-space: nowrap;
}

.quiet {
  color: var(--color-text-secondary);
}

.warning {
  color: var(--color-warning);
}

.error {
  color: var(--color-error);
}
</style>
