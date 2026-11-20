<script setup lang="ts">
import { computed, ref } from 'vue'
import HintToggle from '@/components/base/HintToggle.vue'
import type { CardRow } from '@/components/base/card_row'
import HoverCard from '@/components/base/HoverCard.vue'
import LadderBar from '@/components/LadderBar.vue'
import LadderLegend from '@/components/LadderLegend.vue'
import type { Ladder, Rung } from '@/types/api/ladder_types'

/**
 * How far a work or the corpus is refined (the operator's U1.a, 20 Nov), in the same five levels everywhere: text served,
 * keyword search, semantic search, read, checked, each a meter against the whole and a line in the API's words. Wherever the
 * levels stand in words, each carries its number before its word and its share beside its meter, both the API's (the
 * operator's L1.a): the number says which line a meter in the table's cell is, which keeps only its five meters.
 *
 * Compact, for a table's cell: the five meters stacked, their words, every state of the read pages and why a file is held or
 * not served in the card under the pointer and on the keyboard's focus (the operator: "the details go into hints or
 * expandable parts, not more columns"). In the card each level takes two lines (line 1, 20 Nov, the operator: "teils
 * platzproblem"): its number, word, meter and share, then its words a step in beneath, across the card; the levels a block of
 * their own, so the meters stand under each other as in the cell and the states' long labels beneath never narrow them. Full,
 * for a work's record and the overview: a line per level, its word, its meter, its share and its figures, and where the record
 * is narrow the figures on a line of their own beneath, as in the card; on the overview (`linked`) a level the Pages view can
 * list opens its pages, and each base's part stands in the level's card; what the levels mean is a hint on demand, and a
 * slot takes the details' fold.
 */
const props = withDefaults(defineProps<{
  ladder: Ladder
  compact?: boolean
  linked?: boolean
}>(), { compact: false, linked: false })

const legendOpen = ref(false)

// the card's rows beneath its levels (which stand in its lead, each with its number, its meter as the column draws it and its
// share, so the eye finds in the card the line a coloured bit in the column stands for: "the card follows the colours", L1.a):
// apart under a rule, each state of the read pages as the lists count it, the read pages' breakdown and no meter, the issues in
// the API's words; then why the file is held or not served. A row without a value is left out by the card
const cardRows = computed<CardRow[]>(() => [
  ...props.ladder.states.map(state => ({ label: state.value.replace(/_/g, ' '),
    value: state.said ?? `${state.count.toLocaleString('en')}${state.served ? ` · ${state.served.toLocaleString('en')} served` : ''}`,
    group: 'states', caption: 'read pages by state', indent: true })),
  { label: 'held', value: props.ladder.held, group: 'file' },
  { label: 'not served', value: props.ladder.not_served, group: 'file' },
])

/** A level's share as the line shows it, "98 %"; nothing where the level is not measured (hatched). */
const shareOf = (rung: Rung): string => (rung.share === null ? '' : `${rung.share} %`)

/** A corpus level's part per knowledge base, as its card's rows. */
function byBase(rung: Rung) {
  return Object.entries(rung.by_base ?? {}).map(([base, count]) => ({ label: base, value: (count as number).toLocaleString('en') }))
}

const hasParts = (rung: Rung): boolean => Object.keys(rung.by_base ?? {}).length > 0
const opens = (rung: Rung): boolean => props.linked && rung.pages_filter !== null && rung.pages_filter !== undefined
</script>

<template>
  <HoverCard v-if="compact" class="ladder-card" title="Coverage" :rows="cardRows">
    <template #lead>
      <span class="card-levels" data-part="card-levels">
        <span v-for="rung in ladder.rungs" :key="rung.level" class="card-level" :data-row="rung.level">
          <span class="card-label"><span class="level-number">{{ rung.number }}</span> {{ rung.level }}</span>
          <LadderBar :count="rung.count" :of="rung.of" :issues="rung.issues" :warn="rung.warn" :data-level="rung.level" />
          <span class="level-share" :data-share="rung.level">{{ shareOf(rung) }}</span>
          <span class="card-said">{{ rung.said }}</span>
        </span>
      </span>
    </template>
    <span class="ladder-compact" data-part="ladder" :aria-label="ladder.rungs.map(rung => `${rung.number} ${rung.level}: ${rung.said}`).join('; ')">
      <LadderBar v-for="rung in ladder.rungs" :key="rung.level" :count="rung.count" :of="rung.of" :issues="rung.issues" :warn="rung.warn"
                 :data-level="rung.level" />
    </span>
  </HoverCard>
  <div v-else class="ladder-full" data-part="ladder">
    <div class="rungs">
      <template v-for="rung in ladder.rungs" :key="rung.level">
        <span class="rung-level" :data-level="rung.level"><span class="level-number">{{ rung.number }}</span> {{ rung.level }}</span>
        <LadderBar class="rung-bar" :count="rung.count" :of="rung.of" :issues="rung.issues" :warn="rung.warn" :data-level="rung.level" />
        <span class="level-share" :data-share="rung.level">{{ shareOf(rung) }}</span>
        <span class="rung-said" :data-said="rung.level">
          <HoverCard v-if="hasParts(rung)" :title="`${rung.number} ${rung.level}`" :rows="byBase(rung)">
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

/* the card's levels, a block across the card: a level's number and word, its meter as wide as a short word (the same forms
   and colours as the column's) and its share on one line, its words on the next, a step in and across the card. The words span
   the last column, which takes what is left, so their length never widens the word's column and the five meters stand under
   each other; the states beneath keep the card's own columns */
.card-levels {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: max-content 4rem 5ch minmax(0, 1fr);
  align-items: center;
  column-gap: var(--space-sm);
}

.card-level {
  display: contents;
}

.card-levels .card-label {
  color: var(--color-text-secondary);
}

.card-said {
  grid-column: 1 / -1;
  padding-left: var(--indent-step);
  margin-bottom: 2px;
}

/* a level's share beside its meter, its figures right-aligned and of one width, so the lines' shares read down a column */
.level-share {
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}

.level-number {
  font-variant-numeric: tabular-nums;
}

/* the full ladder: a line per level, its word as wide as the longest, its meter, its figures the rest; on a phone a level's
   words wrap at their space, the meter narrows and the figures keep 12 characters, so the record never runs past the window
   (measured at 390 px: the meter took its 8 rem first and left the figures 19 px, 10 px over the window) */
.ladder-full {
  width: 100%;
  min-width: 0;
  container-type: inline-size;
}

.rungs {
  display: grid;
  grid-template-columns: minmax(min-content, max-content) minmax(3rem, 8rem) max-content minmax(12ch, 1fr);
  align-items: center;
  gap: 2px var(--space-sm);
}

.rung-level {
  color: var(--color-text-secondary);
}

/* where the record is narrow, a level takes two lines, as in the card (line 1, 20 Nov): its word, meter and share, then its
   figures a step in beneath, across the ladder; the words' last column takes what is left, so the meters stand under each other */
@container (max-width: 32rem) {
  .rungs {
    grid-template-columns: minmax(min-content, max-content) minmax(2rem, 4rem) max-content minmax(0, 1fr);
  }

  .rung-said {
    grid-column: 1 / -1;
    padding-left: var(--indent-step);
    margin-bottom: 2px;
  }
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
