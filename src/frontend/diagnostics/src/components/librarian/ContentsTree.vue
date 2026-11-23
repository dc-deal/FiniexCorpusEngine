<script setup lang="ts">
import type { Contents } from '@/types/api/librarian_types'

/**
 * A work's table of contents as `toc` answers it (L1.a): its entries as a tree, each level one indent step deeper, each page
 * a call of `open_page` here, as a client would read it next; where its entries come from, and how many deeper ones were
 * left out by the depth asked for; where a title asked for (`under`) matched more than one entry, the others, each a call too
 * (#15).
 */
defineProps<{
  contents: Contents
}>()

function openPage(work: string, page: string) {
  return { name: 'librarian', query: { tool: 'open_page', work, page } }
}
</script>

<template>
  <div class="contents-tree" data-part="contents-tree">
    <p class="secondary">
      {{ contents.title ?? contents.work }}<template v-if="contents.source"> · from its {{ contents.source }}</template>
      <template v-if="contents.left_out"> · {{ contents.left_out }} deeper entries left out</template>
    </p>
    <p v-if="contents.other_matches?.length" class="secondary" data-part="other-matches">
      it matched too:<template v-for="(entry, at) in contents.other_matches" :key="at">{{ at ? ' ·' : '' }} {{ entry.title }}
        <RouterLink v-if="entry.page && contents.work" :to="openPage(contents.work, entry.page)">{{ entry.page }}</RouterLink></template>
    </p>
    <ol class="entries">
      <li v-for="(entry, at) in contents.entries" :key="at" class="entry" :style="{ paddingLeft: `calc(${entry.level - 1} * var(--indent-step))` }"
          :data-level="entry.level">
        <span>{{ entry.title }}</span>
        <RouterLink v-if="entry.page && contents.work" :to="openPage(contents.work, entry.page)" data-part="open-page">{{ entry.page }}</RouterLink>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.secondary {
  color: var(--color-text-secondary);
}

.entries {
  list-style: none;
  margin-top: var(--space-xs);
}

.entry {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
}
</style>
