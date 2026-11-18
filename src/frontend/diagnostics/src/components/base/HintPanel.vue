<script setup lang="ts">
import AppButton from '@/components/base/AppButton.vue'
import { HINTS, type HintId } from '@/hints'

/**
 * A hint, opened (decision 179): its lead sentence from the registry, then what its view adds, such as the API's own
 * figures, and a way to close it. Quiet, in the secondary ink, so it never reads as part of the data it explains.
 */
const props = defineProps<{
  id: HintId
}>()

const emit = defineEmits<{ close: [] }>()
const hint = HINTS[props.id]
</script>

<template>
  <div class="hint-panel" role="note" :data-hint="id">
    <p class="hint-lead">{{ hint.lead }}</p>
    <slot />
    <AppButton variant="link" class="hint-close" :data-part="`${id}-hint-close`" @click="emit('close')">close</AppButton>
  </div>
</template>

<style scoped>
.hint-panel {
  color: var(--color-text-secondary);
  border-left: 2px solid var(--color-border);
  padding: var(--space-xs) var(--space-sm);
  margin: var(--space-xs) 0 var(--space-sm);
}

.hint-lead {
  margin-bottom: var(--space-xs);
}
</style>
