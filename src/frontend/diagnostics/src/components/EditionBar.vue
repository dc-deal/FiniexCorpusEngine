<script setup lang="ts">
import { editionRoute } from '@/edition_route'
import type { Editions, KnowledgeBase } from '@/types/api/source_types'

/**
 * A work's editions on each edition's record (the operator's E1.a, 20 Nov): an edition is a level under its work, so every
 * edition's record names them all, one part an edition: its mark and word (● served, ○ kept, one look with the Sources card's
 * editions block), its label, a link to that edition's record; this record's own marked and no link. Which edition is served
 * changes only by a core command, so the bar shows and never chooses.
 */
defineProps<{
  editions: Editions
  kb: KnowledgeBase
}>()
</script>

<template>
  <nav class="edition-bar" data-part="edition-bar" aria-label="Editions">
    <template v-for="edition in editions.editions" :key="edition.key">
      <RouterLink
        v-if="edition.key !== editions.current && editionRoute(edition, kb)"
        class="edition"
        :data-edition="edition.key"
        :to="editionRoute(edition, kb)!"
      >
        <span class="edition-mark" aria-hidden="true">{{ edition.served ? '●' : '○' }}</span> {{ edition.label }} · {{ edition.served ? 'served' : 'kept' }}
      </RouterLink>
      <span v-else class="edition" :class="{ current: edition.key === editions.current }" :data-edition="edition.key"
            :aria-current="edition.key === editions.current ? 'page' : undefined">
        <span class="edition-mark" aria-hidden="true">{{ edition.served ? '●' : '○' }}</span> {{ edition.label }} · {{ edition.served ? 'served' : 'kept' }}
      </span>
    </template>
  </nav>
</template>

<style scoped>
.edition-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-sm);
  margin: var(--space-xs) 0 var(--space-sm);
}

/* an edition a part with an edge, the record's own drawn as chosen, the others links in the accent role */
.edition {
  padding: 0 var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  text-decoration: none;
}

a.edition {
  color: var(--color-accent);
}

a.edition:hover {
  border-color: var(--color-accent);
}

.edition.current {
  border-color: var(--color-text-secondary);
  color: var(--color-text-primary);
  font-weight: bold;
}
</style>
