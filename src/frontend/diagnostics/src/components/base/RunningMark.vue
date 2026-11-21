<script setup lang="ts">
/**
 * Something a person waits on while it runs (the operator, 21 Nov: "when I ask AI I need an hourglass while it runs"): a mark
 * that turns and its words counting up, "asking the model … 12 s". Form, then word: the words say it without the mark, and
 * for a reader who asked the system for less motion the mark stands still while the words count on. The library had a
 * moving line for a view that loads (`LoadingLine`), none for a control that runs, so this is its own.
 */
defineProps<{
  words: string
  seconds: number
}>()
</script>

<template>
  <span class="running" data-part="running">
    <span class="running-mark" aria-hidden="true" />
    <span class="running-words" data-part="running-words">{{ `${words} … ${seconds} s` }}</span>
  </span>
</template>

<style scoped>
.running {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

/* a ring with one quarter open, in the control's own ink, turning */
.running-mark {
  display: inline-block;
  width: 0.9em;
  height: 0.9em;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: running-turn 0.9s linear infinite;
}

@keyframes running-turn {
  to { transform: rotate(360deg); }
}

/* still for a reader who asked the system for less motion: the ring closed, the words counting on */
@media (prefers-reduced-motion: reduce) {
  .running-mark {
    animation: none;
    border-top-color: currentColor;
    border-style: dotted;
  }
}
</style>
