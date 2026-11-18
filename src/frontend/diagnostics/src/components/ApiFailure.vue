<script setup lang="ts">
import { computed } from 'vue'
import { ApiError } from '@/api/api_error'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'

/** A request that failed, said in a sentence, with a glyph beside the words and a way to ask again. */
const props = defineProps<{
  error: Error
}>()

const emit = defineEmits<{
  retry: []
}>()

const sentence = computed(() => {
  if (props.error instanceof ApiError && props.error.status === null) {
    return 'No answer from the diagnostics API. Is python -m backend.diagnostics running?'
  }
  return `The diagnostics API refused the request: ${props.error.message}`
})
</script>

<template>
  <p class="failure" role="alert">
    <AppIcon name="status-error" />
    <span>{{ sentence }}</span>
    <AppButton variant="quiet" @click="emit('retry')">Try again</AppButton>
  </p>
</template>

<style scoped>
.failure {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-error);
}
</style>
