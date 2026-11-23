<script setup lang="ts">
import DataTable from '@/components/base/DataTable.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { knowledgeBaseOf } from '@/knowledge_base'
import { counted } from '@/counted'
import type { FoundWork, WorkRow } from '@/types/api/librarian_types'

/**
 * The works as `works` and `search_works` answer them (L1.a): the shelf as a table, a key a row, with its title and what it
 * is for, its edition, base, pages and route, and a kept edition named; or the works that hold a subject, best first, each
 * with how many of its pages hold a word and every word, and its best sections, each page a call of `open_page` here, as a
 * client would read it next.
 */
withDefaults(defineProps<{
  works?: WorkRow[] | null
  found?: FoundWork[] | null
}>(), { works: null, found: null })

function openPage(work: string, page: string) {
  return { name: 'librarian', query: { tool: 'open_page', work, page } }
}
</script>

<template>
  <DataTable v-if="works" table-class="works ruled" min-width="48rem" data-part="works-table">
    <template #head>
      <tr>
        <th>Work</th>
        <th>Title</th>
        <th>Edition</th>
        <th>Base</th>
        <th class="number">Pages</th>
        <th>Route</th>
      </tr>
    </template>
    <tbody>
      <tr v-for="work in works" :key="work.work" :data-work="work.work">
        <td class="key">{{ work.work }}</td>
        <td>
          {{ work.title }}
          <p v-if="work.subject" class="secondary subject">{{ work.subject }}</p>
          <p v-if="work.kept_for" class="secondary" data-part="kept-for">
            kept: {{ work.kept_for }} is searched<template v-if="work.pages_kept != null">; its own {{ counted(work.pages_kept, 'page') }}
              open by its key</template>
          </p>
          <p v-if="work.kept_editions.length" class="secondary" data-part="kept-editions">kept beside it: {{ work.kept_editions.join(', ') }}</p>
        </td>
        <td class="secondary">{{ work.edition_said ?? '' }}</td>
        <td><KnowledgeBaseMark v-if="knowledgeBaseOf(work.knowledge_base)" :kb="knowledgeBaseOf(work.knowledge_base)!" /></td>
        <td class="number">{{ work.pages ?? '' }}</td>
        <td class="secondary">{{ work.route ?? '' }}</td>
      </tr>
    </tbody>
  </DataTable>
  <ol v-else-if="found" class="found-works ruled" data-part="found-works">
    <li v-for="work in found" :key="work.work" class="found-work" :data-work="work.work">
      <p class="found-head">
        <span class="secondary">#{{ work.rank }}</span>
        <KnowledgeBaseMark v-if="knowledgeBaseOf(work.knowledge_base)" :kb="knowledgeBaseOf(work.knowledge_base)!" />
        <strong>{{ work.title ?? work.work }}</strong>
        <span class="secondary">{{ work.work }}</span>
        <span v-if="work.score !== null && work.score !== undefined" class="secondary">score {{ work.score }}</span>
        <span class="secondary" data-part="pages-matching">{{ work.pages_matching ?? 0 }} pages hold a word, {{ work.pages_with_every_term ?? 0 }} every one</span>
      </p>
      <p v-if="work.subject" class="secondary subject">{{ work.subject }}</p>
      <ul class="best-sections">
        <li v-for="(section, at) in work.best_sections" :key="at" data-part="best-section">
          <span>{{ section.section ?? '' }}</span>
          <RouterLink v-if="section.page" :to="openPage(work.work, section.page)" data-part="open-page">{{ section.page_said }}</RouterLink>
          <span v-if="section.score !== null && section.score !== undefined" class="secondary">score {{ section.score }}</span>
        </li>
      </ul>
    </li>
  </ol>
</template>

<style scoped>
.secondary {
  color: var(--color-text-secondary);
}

.key {
  white-space: nowrap;
}

.found-works {
  list-style: none;
}

.found-work {
  padding: var(--space-sm) 0;
}

.found-head,
.best-sections li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-xs) var(--space-md);
}

.best-sections {
  list-style: none;
  padding-left: var(--indent-step);
}
</style>
