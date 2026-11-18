<script setup lang="ts">
/**
 * Labelled lines that align (the operator, 11 Nov: "what would you say is best practice to ensure the best overview"):
 * the labels in one column as wide as the widest of them, the values in a second, so the eye runs down both; a long value
 * wraps in its own column, never back under the labels, and running text is held to 100 characters a line. `labelChars`
 * holds the label column to the longest label a view can show, so a page with fewer labels does not move its values when
 * a person steps to the next one.
 */
const props = defineProps<{
  labelChars?: number
}>()
</script>

<template>
  <div class="labelled-lines" :style="props.labelChars ? { '--label-width': `${props.labelChars}ch` } : undefined">
    <slot />
  </div>
</template>

<style scoped>
.labelled-lines {
  display: grid;
  grid-template-columns: minmax(var(--label-width, 0), max-content) minmax(0, 100ch);
  gap: 2px var(--space-sm);
}
</style>
