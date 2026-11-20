<script setup lang="ts">
import { computed } from 'vue'

/**
 * One level of a coverage ladder as a meter (U1.a): a thin track the length of the whole and a fill as long as its part, one
 * neutral ink, since a level is a magnitude and no status. Its words are the ladder's, beside it or in its card; a level the
 * API does not measure here (`count` null) leaves the track empty and is marked as such, never drawn as nothing reached.
 */
const props = defineProps<{
  count: number | null | undefined
  of: number | null | undefined
}>()

// the fill's length, the drawing's only arithmetic: the figures it stands for are the API's
const share = computed(() => (typeof props.count === 'number' && props.of ? Math.min(1, props.count / props.of) : 0))
const known = computed(() => typeof props.count === 'number')
</script>

<template>
  <span
    class="ladder-bar"
    :class="{ unknown: !known }"
    role="meter"
    aria-valuemin="0"
    :aria-valuemax="of ?? 0"
    :aria-valuenow="known ? count ?? 0 : undefined"
    :data-share="known ? share.toFixed(3) : 'unknown'"
  >
    <span v-if="known && share > 0" class="ladder-fill" :style="{ width: `${share * 100}%` }" />
  </span>
</template>

<style scoped>
/* a thin track, its ends rounded; the fill in the secondary ink over the border's, which both themes keep apart */
.ladder-bar {
  position: relative;
  display: block;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background-color: var(--color-border);
  overflow: hidden;
}

.ladder-fill {
  position: absolute;
  inset: 0 auto 0 0;
  min-width: 2px;
  border-radius: 2px;
  background-color: var(--color-text-secondary);
}

/* not measured here: the track stands as an outline only, so it never reads as a level nothing reached */
.ladder-bar.unknown {
  background-color: transparent;
  box-shadow: inset 0 0 0 1px var(--color-border);
}
</style>
