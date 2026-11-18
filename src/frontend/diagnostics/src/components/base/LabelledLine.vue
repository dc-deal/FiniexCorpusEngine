<script setup lang="ts">
/**
 * One labelled line of the library (decision 179, 184): a bold label and its value at the one size, the label told by its
 * weight, never by a size of its own. The record of a page reads as such lines ("State: ok", "Route: noted · vision
 * reading · ..."), so a reader finds a fact by its name rather than by its place in a run of chips.
 */
defineProps<{
  label: string
}>()
</script>

<template>
  <div class="labelled-line" :data-label="label">
    <span class="line-label">{{ `${label}:` }}</span>
    <span class="line-value"><slot /></span>
  </div>
</template>

<style scoped>
.labelled-line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-sm);
}

/* among labelled lines (`LabelledLines`), a line takes the whole's two columns: its label and value align with the
   others', and a long value wraps in its own column. Label and value stand at the line's top: both are lines of the one
   size, so their words meet; a baseline would be set by a glyph where a value begins with one (a person's mark, a
   state's), and put the label 3px below its value's words */
.labelled-lines > .labelled-line {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
  align-items: start;
}

.line-label {
  font-weight: bold;
  white-space: nowrap;
}

.line-value {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
  min-width: 0;
}
</style>
