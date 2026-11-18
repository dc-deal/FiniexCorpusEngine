<script setup lang="ts">
/**
 * Something on its way: a line that moves, so the waiting is visibly WORK and not an empty view, and
 * the word beside it.
 */
</script>

<template>
  <div class="loading" aria-busy="true">
    <span class="loading-line" aria-hidden="true" />
    <span class="loading-text">Loading…</span>
  </div>
</template>

<style scoped>
.loading {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) 0;
}

.loading-text {
  color: var(--color-text-secondary);
}

/* still for a reader who asked the system for less motion, where the word alone says it */
.loading-line {
  display: block;
  height: 2px;
  width: 100%;
  background: linear-gradient(90deg, transparent, var(--color-accent), transparent) 0 0 / 40% 100% no-repeat;
  animation: loading-sweep 1.2s ease-in-out infinite;
}

@keyframes loading-sweep {
  from { background-position: -40% 0; }
  to { background-position: 140% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .loading-line {
    animation: none;
    background: var(--color-border);
  }
}
</style>
