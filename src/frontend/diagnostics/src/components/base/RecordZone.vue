<script setup lang="ts">
/**
 * The record of a view with an analysis part (decision 183, the operator: "the upper area could have a limit on its width, like the chapter overview"): its head, chips, history and details in the standard content width, centred, while
 * the analysis below it alone takes the wide container (`AnalysisSection`).
 */
</script>

<template>
  <div class="record-zone" data-zone="record">
    <slot />
  </div>
</template>

<style scoped>
.record-zone {
  max-width: var(--content-max-width);
  margin-inline: auto;
}
</style>
