<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import type { IconName } from '@/icon_registry'
import type { PageLadder, PageRung } from '@/types/api/ladder_types'

/**
 * A page's or a section's own ladder (the operator's V2.a, 20 Nov): its text layer, the text served, keyword search, its
 * semantic search, its reading and check, each a line of the level's word, a mark whether the page reaches it and the API's
 * words; then why the file is held back from providers, where it is, shown here all the same; then the text the librarian
 * serves for it, folded until asked for. The marks are form and word, never colour: a level a page does not reach is no fault.
 */
defineProps<{
  ladder: PageLadder
}>()

// reached, not reached, or not known here: three forms, one quiet ink
function markOf(rung: PageRung): IconName {
  return rung.reached === true ? 'level-reached' : rung.reached === false ? 'level-not-reached' : 'level-unknown'
}
</script>

<template>
  <div class="page-ladder" data-part="page-ladder">
    <div class="page-rungs">
      <template v-for="rung in ladder.rungs" :key="rung.level">
        <span class="rung-level">{{ rung.level }}</span>
        <span class="rung-mark" :data-reached="rung.reached === null ? 'unknown' : String(rung.reached)"><AppIcon :name="markOf(rung)" /></span>
        <span class="rung-said" :data-said="rung.level">{{ rung.said }}</span>
      </template>
    </div>
    <p v-if="ladder.held" class="held" data-part="held">
      <AppIcon name="kb-licensed" /> {{ ladder.held }}; shown here, on this machine only
    </p>
    <FoldSection class="served-text" title="text served" remember="page.served" data-part="served-text">
      <pre v-if="ladder.served_text" class="served-body">{{ ladder.served_text }}</pre>
      <p v-else class="served-none">{{ ladder.served_why_not ?? 'no text is served for it' }}</p>
    </FoldSection>
  </div>
</template>

<style scoped>
/* a line per level: its word as wide as the longest, the mark, the API's words the rest; where the record is narrow, as on a
   phone, a level's words wrap at their spaces, so the API's words keep the room to be read (measured at 390 px: held to one
   line, the levels took 18 characters and left the words 12) */
/* a container of its own width, as wide as its column: a size container has none of its own and would fold to nothing */
.page-ladder {
  container-type: inline-size;
  width: 100%;
  min-width: 0;
}

.page-rungs {
  display: grid;
  grid-template-columns: minmax(min-content, max-content) auto minmax(12ch, 1fr);
  align-items: center;
  gap: 2px var(--space-sm);
}

@container (max-width: 32rem) {
  .page-rungs {
    grid-template-columns: min-content auto minmax(0, 1fr);
  }
}

.rung-level,
.rung-mark,
.held,
.served-none {
  color: var(--color-text-secondary);
}

.rung-mark :deep(.app-icon) {
  width: 1em;
  height: 1em;
}

.held {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: 2px;
}

/* the served text as the librarian gives it: its own lines kept, wrapped in the column, escaped as text */
.served-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  max-height: 40rem;
  overflow-y: auto;
  margin: 0;
}
</style>
