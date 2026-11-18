<script setup lang="ts">
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import { HINTS, type HintId } from '@/hints'

/**
 * The one way to ask what something means (decision 179): an info mark that opens its hint's panel (`HintPanel`), the
 * words from the registry (`hints.ts`). The view holds whether it is open, so the panel can stand where the view wants it.
 */
const props = defineProps<{
  id: HintId
}>()

const open = defineModel<boolean>('open', { default: false })
const hint = HINTS[props.id]
</script>

<template>
  <AppButton
    variant="quiet"
    glyph
    :aria-label="hint.label"
    :aria-expanded="open ? 'true' : 'false'"
    :marked="open"
    :data-part="`${id}-hint-button`"
    @click="open = !open"
  >
    <AppIcon name="hint" />
  </AppButton>
</template>
