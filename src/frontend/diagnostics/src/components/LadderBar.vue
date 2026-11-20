<script setup lang="ts">
import { computed } from 'vue'

/**
 * One level of a coverage ladder as a meter (U1.a): a thin track the length of the whole and a fill as long as its part, one
 * neutral ink, since a level is a magnitude and no status. Colour only where a look is called for (the operator's C1.b, 20 Nov),
 * never alone, the words staying the card's:
 * - the pages the judge found bad (`issues`) stand as a segment after the checked ones, in the issue's role, apart by a gap
 *   and a pixel taller on each side, since under red-green blindness its red and the fill's grey stand only 5.3 (light) and
 *   7.8 (dark) apart (OKLab ΔE, measured with the dataviz validator), below the 8 a colour may carry alone;
 * - a level nothing reaches that should (`warn`: a work that serves no text at all) has its track in the warning role;
 * - a level the API does not measure here (`count` null: not vectorised yet, not read page by page) is a hatched track,
 *   neutral, never a level nothing reached; hatched and not dashed, since a dashed line is the annotation role's.
 */
const props = defineProps<{
  count: number | null | undefined
  of: number | null | undefined
  issues?: number | null
  warn?: boolean
}>()

// the drawing's only arithmetic, lengths: the figures they stand for are the API's
const share = computed(() => (typeof props.count === 'number' && props.of ? Math.min(1, props.count / props.of) : 0))
const issueShare = computed(() => (props.issues && props.of ? Math.min(1 - share.value, props.issues / props.of) : 0))
const known = computed(() => typeof props.count === 'number')
</script>

<template>
  <span
    class="ladder-bar"
    :class="{ unknown: !known, warn: warn && known }"
    role="meter"
    aria-valuemin="0"
    :aria-valuemax="of ?? 0"
    :aria-valuenow="known ? count ?? 0 : undefined"
    :data-share="known ? share.toFixed(3) : 'unknown'"
    :data-look="!known ? 'not measured' : warn ? 'warning' : issueShare > 0 ? 'issues' : 'quiet'"
  >
    <span v-if="known && share > 0" class="ladder-fill" :style="{ width: `${share * 100}%` }" />
    <span
      v-if="issueShare > 0"
      class="ladder-issues"
      :data-issues="issueShare.toFixed(3)"
      :style="{ left: `calc(${share * 100}% + 2px)`, width: `max(2px, calc(${issueShare * 100}% - 2px))` }"
    />
  </span>
</template>

<style scoped>
/* a thin track, its ends rounded; the fill in the secondary ink over the border's, which both themes keep apart. The track
   does not clip, so the issues' segment can stand a pixel over it on each side */
.ladder-bar {
  position: relative;
  display: block;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background-color: var(--color-border);
}

.ladder-fill {
  position: absolute;
  inset: 0 auto 0 0;
  min-width: 2px;
  max-width: 100%;
  border-radius: 2px;
  background-color: var(--color-text-secondary);
}

/* the pages the judge found bad: after the checked ones, a gap of the surface between, a pixel taller on each side */
.ladder-issues {
  position: absolute;
  top: -1px;
  bottom: -1px;
  border-radius: 2px;
  background-color: var(--color-error);
}

/* nothing served where text should be: the empty track in the warning role */
.ladder-bar.warn {
  background-color: transparent;
  box-shadow: inset 0 0 0 1px var(--color-warning);
}

/* not measured here: a hatched track in the neutral border ink, never a level nothing reached */
.ladder-bar.unknown {
  background-color: transparent;
  background-image: repeating-linear-gradient(135deg, var(--color-border) 0 2px, transparent 2px 4px);
  box-shadow: inset 0 0 0 1px var(--color-border);
}
</style>
