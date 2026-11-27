<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { useErrorsStore } from '@/stores/errors_store'
import type { ErrorClass } from '@/types/api/errors_types'
import { counted } from '@/counted'

/**
 * Error classes (line 1's order for the operator's 146.a, 147.a): what kind of error recurs, in which class of block and in which
 * work. The judge's findings by kind, block class and work, the void ones apart; beside them stage 2's, the reading against
 * the text layer, by kind and work. Each class with its count and its pages, each page one click from its view; the pages
 * are drawn when a class is opened, as one may hold hundreds. Every count is the API's.
 */
const store = useErrorsStore()
const { errors, error } = storeToRefs(store)
const opened = ref<Set<string>>(new Set())

onMounted(() => {
  void store.loadErrors()
})

function keyOf(one: ErrorClass): string {
  return [one.stage, one.kind, one.block_class ?? '', one.void, one.knowledge_base, one.source_id].join('/')
}

function onToggle(one: ErrorClass, open: boolean): void {
  const next = new Set(opened.value)
  if (open) next.add(keyOf(one))
  else next.delete(keyOf(one))
  opened.value = next
}

const judged = computed(() => (errors.value?.classes ?? []).filter(one => one.stage === 'judge'))
const countingFindings = computed(() => judged.value.filter(one => !one.void))
const voided = computed(() => judged.value.filter(one => one.void))
const layer = computed(() => (errors.value?.classes ?? []).filter(one => one.stage === 'stage 2'))
const tables = computed(() => [
  { key: 'judge', title: "The judge's findings that count", note: 'by kind, block class and work', rows: countingFindings.value, classes: true },
  { key: 'void', title: 'Struck by code: findings that name no difference', note: 'kept apart, never counted', rows: voided.value, classes: true },
  { key: 'stage2', title: 'Stage 2, the reading against the text layer', note: 'by kind and work', rows: layer.value, classes: false },
])
</script>

<template>
  <section class="errors-view">
    <h1 class="view-title">Errors</h1>
    <ApiFailure v-if="error" :error="error" @retry="store.loadErrors()" />
    <LoadingLine v-else-if="!errors" />
    <template v-else>
      <section v-for="table in tables" :key="table.key" class="error-table" :data-table="table.key">
        <h2 class="table-title">{{ table.title }} <span class="note">{{ table.note }}</span></h2>
        <p v-if="!table.rows.length" class="note">None.</p>
        <DataTable v-else table-class="error-rows ruled">
          <template #head>
            <tr>
              <th>Kind</th>
              <th v-if="table.classes">Block class</th>
              <th>Work</th>
              <th class="number">Findings</th>
              <th>Pages</th>
            </tr>
          </template>
          <tbody>
            <tr v-for="one in table.rows" :key="keyOf(one)" :data-class="keyOf(one)">
              <td>{{ one.kind }}</td>
              <td v-if="table.classes">{{ one.block_class ?? '' }}</td>
              <td><KnowledgeBaseMark :kb="one.knowledge_base" /> {{ one.title }}</td>
              <td class="number">{{ one.findings.toLocaleString('en') }}</td>
              <td>
                <FoldSection class="pages" :title="counted(one.pages.length, 'page')" @toggle="open => onToggle(one, open)">
                  <span v-if="opened.has(keyOf(one))" class="page-links">
                    <RouterLink
                      v-for="page in one.pages"
                      :key="page"
                      :to="{ name: 'page', params: { kb: one.knowledge_base, work: one.source_id, page } }"
                    >p. {{ page }}</RouterLink>
                  </span>
                </FoldSection>
              </td>
            </tr>
          </tbody>
        </DataTable>
      </section>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.error-table {
  margin-bottom: var(--space-lg);
}

.table-title {
  font-weight: normal;
  margin-bottom: var(--space-xs);
}

.note {
  color: var(--color-text-secondary);
}

.error-rows th {
  text-align: left;
  font-weight: normal;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.error-rows th,
.error-rows td {
  padding: 2px var(--space-md) 2px 0;
  vertical-align: top;
}

.number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.page-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
  max-width: 48rem;
}

.page-links a {
  color: var(--color-accent);
  text-decoration: none;
}

.page-links a:hover {
  text-decoration: underline;
}
</style>
