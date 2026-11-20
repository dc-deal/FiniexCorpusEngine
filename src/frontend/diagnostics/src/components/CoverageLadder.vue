<script setup lang="ts">
import { computed, ref } from 'vue'
import HintToggle from '@/components/base/HintToggle.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import LadderBar from '@/components/LadderBar.vue'
import LadderLegend from '@/components/LadderLegend.vue'
import type { Ladder, Rung } from '@/types/api/ladder_types'

/**
 * How far a work or the corpus is refined (the operator's U1.a, 20 Nov), in the same five levels everywhere: text served,
 * keyword search, semantic chunks, read, checked, each a meter against the whole and a line in the API's words.
 *
 * Compact, for a table's cell: the five meters stacked, their words, every state of the read pages and why a file is held or
 * not served in the card under the pointer and on the keyboard's focus (the operator: "the details go into hints or
 * expandable parts, not more columns"). Full, for a work's record and the overview: a line per level, its word, its meter and
 * its figures; on the overview (`linked`) a level the Pages view can list opens its pages, and each base's part stands in the
 * level's card; what the levels mean is a hint on demand, and a slot takes the details' fold.
 */
const props = withDefaults(defineProps<{
  ladder: Ladder
  compact?: boolean
  linked?: boolean
}>(), { compact: false, linked: false })

const legendOpen = ref(false)

// the card of the compact ladder: each level's line, then each state of the read pages as the lists count it, then why the
// file is held from providers or not served; a row without a value is left out by the card
const cardRows = computed(() => [
  ...props.ladder.rungs.map(rung => ({ label: rung.level, value: rung.said })),
  // a state to look at with how many of its pages the core serves all the same (18 Nov), as its column said it before U1.a
  ...props.ladder.states.map(state => ({ label: state.value.replace(/_/g, ' '),
    value: `${state.count.toLocaleString('en')}${state.served ? ` · ${state.served.toLocaleString('en')} served` : ''}` })),
  { label: 'held', value: props.ladder.held },
  { label: 'not served', value: props.ladder.not_served },
])

/** A corpus level's part per knowledge base, as its card's rows. */
function byBase(rung: Rung) {
  return Object.entries(rung.by_base ?? {}).map(([base, count]) => ({ label: base, value: (count as number).toLocaleString('en') }))
}

const hasParts = (rung: Rung): boolean => Object.keys(rung.by_base ?? {}).length > 0
const opens = (rung: Rung): boolean => props.linked && rung.pages_filter !== null && rung.pages_filter !== undefined
</script>

<template>
  <HoverCard v-if="compact" class="ladder-card" title="Coverage" :rows="cardRows">
    <span class="ladder-compact" data-part="ladder" :aria-label="ladder.rungs.map(rung => `${rung.level}: ${rung.said}`).join('; ')">
      <LadderBar v-for="rung in ladder.rungs" :key="rung.level" :count="rung.count" :of="rung.of" :data-level="rung.level" />
    </span>
  </HoverCard>
  <div v-else class="ladder-full" data-part="ladder">
    <div class="rungs">
      <template v-for="rung in ladder.rungs" :key="rung.level">
        <span class="rung-level" :data-level="rung.level">{{ rung.level }}</span>
        <LadderBar class="rung-bar" :count="rung.count" :of="rung.of" :data-level="rung.level" />
        <span class="rung-said" :data-said="rung.level">
          <HoverCard v-if="hasParts(rung)" :title="rung.level" :rows="byBase(rung)">
            <RouterLink v-if="opens(rung)" class="rung-link" :to="{ name: 'pages', query: rung.pages_filter ?? {} }">{{ rung.said }}</RouterLink>
            <span v-else>{{ rung.said }}</span>
          </HoverCard>
          <RouterLink v-else-if="opens(rung)" class="rung-link" :to="{ name: 'pages', query: rung.pages_filter ?? {} }">{{ rung.said }}</RouterLink>
          <template v-else>{{ rung.said }}</template>
        </span>
      </template>
    </div>
    <div class="ladder-foot">
      <HintToggle id="ladder" v-model:open="legendOpen" />
      <slot />
    </div>
    <LadderLegend v-if="legendOpen" :rungs="ladder.rungs" @close="legendOpen = false" />
  </div>
</template>

<style scoped>
/* the compact ladder: five meters stacked, as wide as the cell gives, the card's host holding them */
.ladder-card.hover-card-host {
  display: block;
}

.ladder-compact {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0.35em 0;
}

/* the full ladder: a line per level, its word as wide as the longest, its meter, its figures the rest; on a phone a level's
   words wrap at their space, the meter narrows and the figures keep 12 characters, so the record never runs past the window
   (measured at 390 px: the meter took its 8 rem first and left the figures 19 px, 10 px over the window) */
.ladder-full {
  width: 100%;
  min-width: 0;
}

.rungs {
  display: grid;
  grid-template-columns: minmax(min-content, max-content) minmax(3rem, 8rem) minmax(12ch, 1fr);
  align-items: center;
  gap: 2px var(--space-sm);
}

.rung-level {
  color: var(--color-text-secondary);
}

.rung-said :deep(.hover-card-host) {
  display: inline;
}

.rung-link {
  color: var(--color-accent);
  text-decoration: none;
}

.rung-link:hover {
  text-decoration: underline;
}

.ladder-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
  margin-top: 2px;
}
</style>
