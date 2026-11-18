<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import StateCounts from '@/components/StateCounts.vue'
import { pageCount } from '@/page_count'
import { useSourceStore } from '@/stores/source_store'

/**
 * Every work of every knowledge base served, one row each, each marked with its knowledge base: the free catalog in its
 * order, then the licensed works, which have no catalog entry and so only an id and a title. Its structure says how the
 * work is cut, by its format's model (the operator's 4.a): a work read page by page shows its pages' check states and opens its page
 * list; an HTML work its sections by heading and their chunks, and opens its outline (the operator's 6.a).
 */
const store = useSourceStore()
const { works, error, loaded } = storeToRefs(store)

onMounted(() => {
  void store.loadWorks()
})
</script>

<template>
  <section class="sources">
    <h1 class="view-title">Sources</h1>
    <!-- no answer and no failure yet: on its way, from the first frame on -->
    <LoadingLine v-if="!loaded && !error" />
    <ApiFailure v-else-if="error" :error="error" @retry="store.loadWorks()" />
    <p v-else-if="loaded && works.length === 0" class="empty">The catalog lists no works.</p>
    <DataTable v-else-if="loaded" table-class="works ruled">
      <template #head>
        <tr>
          <th>Work</th>
          <th>Knowledge base</th>
          <!-- how the work is cut, by its format's model (the operator's 4.a): a PDF by its pages, an HTML work by its headings -->
          <th>Structure</th>
          <th>Authors</th>
          <th>Publisher</th>
          <th>Year</th>
          <th>Format</th>
          <!-- the catalog's topic shelf (trading_finance, architecture), not the Shelf view's counts (the operator's 23.a) -->
          <th>Topic</th>
          <th>Licence</th>
        </tr>
      </template>
      <tbody>
        <tr v-for="work in works" :key="`${work.knowledge_base}/${work.id}`" :data-work="work.id" :data-kb="work.knowledge_base">
          <td>
            <RouterLink
              v-if="work.readings"
              class="work-title"
              :to="{ name: 'work', params: { kb: work.knowledge_base, work: work.id } }"
            >
              {{ work.title }}
            </RouterLink>
            <RouterLink
              v-else-if="work.format === 'html'"
              class="work-title"
              :to="{ name: 'html-work', params: { kb: work.knowledge_base, work: work.id } }"
            >
              {{ work.title }}
            </RouterLink>
            <span v-else class="work-title">{{ work.title }}</span>
            <span class="work-id">{{ work.id }}</span>
            <!-- a few words about a licensed copy, from the local licensed catalog (N1.a): "stand-in file", "lecture slides" -->
            <span v-if="work.notes" class="work-notes" data-part="work-notes">{{ work.notes }}</span>
          </td>
          <td><KnowledgeBaseMark :kb="work.knowledge_base" /></td>
          <td data-cell="structure">
            <template v-if="work.readings">
              <span class="page-count">{{ pageCount(work.readings.pages) }} · read and judged</span>
              <StateCounts :counts="work.readings.states" />
            </template>
            <span v-else-if="typeof work.sections === 'number' && typeof work.chunks === 'number'" class="page-count">
              {{ work.sections.toLocaleString('en') }} sections by heading · {{ work.chunks.toLocaleString('en') }} chunks
            </span>
            <span v-else-if="work.structure_why_not" class="not-built" :title="work.structure_why_not">
              sections by heading · search index not built
            </span>
          </td>
          <td>{{ work.authors }}</td>
          <td>{{ work.publisher }}</td>
          <!-- a licensed copy's edition beside its year, where the catalog names one (N1.a) -->
          <td>{{ work.year }}<span v-if="work.edition" class="edition" data-part="edition">{{ `${work.year ? ' · ' : ''}${work.edition} edition` }}</span></td>
          <td>{{ work.format }}</td>
          <td>{{ work.shelf }}</td>
          <td>{{ work.licence }}</td>
        </tr>
      </tbody>
    </DataTable>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.empty {
  color: var(--color-text-secondary);
}

.works th {
  text-align: left;
  color: var(--color-text-secondary);
  font-weight: normal;
  white-space: nowrap;
  border-bottom: 1px solid var(--color-border);
}

.works th,
.works td {
  padding: var(--space-xs) var(--space-md) var(--space-xs) 0;
  vertical-align: top;
}

.work-title {
  display: block;
}

a.work-title {
  color: var(--color-accent);
  text-decoration: none;
}

a.work-title:hover {
  text-decoration: underline;
}

/* the id is what a ticket and a reading key name, so it stays on screen beneath the title */
.work-id,
.work-notes,
.page-count,
.not-built {
  display: block;
  color: var(--color-text-secondary);
}
</style>
