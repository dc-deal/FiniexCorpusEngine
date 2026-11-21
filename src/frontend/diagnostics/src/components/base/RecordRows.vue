<script setup lang="ts">
/**
 * A record's rows (the operator's H1.a, 21 Nov): every row a labelled fold (`FoldSection` with a `label`), their labels in one
 * column as wide as the longest label a record can show ("Reading History:", in bold, one character more), so a page and a
 * section, with fewer words in a row, never move the others' lines when a person steps to the next one.
 */
const props = withDefaults(defineProps<{
  labelChars?: number
}>(), { labelChars: 17 })
</script>

<template>
  <div class="record-rows" :style="{ '--label-width': `${props.labelChars}ch` }">
    <slot />
  </div>
</template>

<style scoped>
/* a container of its own width, so a narrow record sets each label above its line (`FoldSection`) */
.record-rows {
  container: record-rows / inline-size;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
