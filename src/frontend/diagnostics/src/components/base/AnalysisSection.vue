<script setup lang="ts">
/**
 * The analysis of a view, its original beside its reading or its chunks (decisions 181.a, 183): the one part that takes
 * the wide container, under its own heading, told by its form, a rule through the middle (`── Analysis ──`), never by a
 * size of its own. Where the view shows something other than the standing state (`overlay`, a recalled judgement), the
 * region it acts on is framed, dashed, in the annotation role; the words that say so stand in the heading's hint.
 */
defineProps<{
  overlay?: boolean
}>()
</script>

<template>
  <section class="analysis" :class="{ overlay }" data-zone="analysis" data-part="analysis" :data-overlay="overlay ? 'yes' : null">
    <h2 class="analysis-title">
      <span class="analysis-word">Analysis</span>
      <slot name="hint" />
    </h2>
    <slot />
  </section>
</template>

<style scoped>
.analysis {
  margin-top: var(--space-md);
}

/* a heading by its form: bold, at the one size, a rule through the middle */
.analysis-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  font-weight: bold;
  margin-bottom: var(--space-sm);
}

.analysis-title::before {
  content: '';
  flex: 0 0 var(--space-lg);
  border-top: 1px solid var(--color-border);
}

.analysis-title::after {
  content: '';
  flex: 1 1 var(--space-lg);
  border-top: 1px solid var(--color-border);
}

.analysis.overlay {
  outline: 2px dashed var(--color-annotation);
  outline-offset: var(--space-xs);
}
</style>
