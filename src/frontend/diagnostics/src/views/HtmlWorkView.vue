<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import HtmlOutlineNode from '@/components/HtmlOutlineNode.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { useHtmlStore } from '@/stores/html_store'
import { useSettingsStore } from '@/stores/settings_store'
import { useViewName } from '@/view_name'
import type { HtmlNode } from '@/types/api/html_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import { counted } from '@/counted'

/**
 * An HTML work (the operator's 6.a, an exception to the feature seal named as such): its outline by heading in the work's own flow,
 * folded, each heading with the range of its section labels and its sections and chunks; or every section flat in a table.
 * A section opens its chunks. Every figure is the search index's, through the API; where the index is not built on this
 * machine, the view says so and names the command. The choice of chapters or table is the page lists' own setting.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
}>()

const store = useHtmlStore()
const { workError } = storeToRefs(store)
const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)

watch(() => [props.kb, props.work] as const, ([kb, work]) => {
  void store.loadWork(kb, work)
}, { immediate: true })

const shown = computed(() => store.workOf(props.kb, props.work))
useViewName(() => shown.value?.title ?? null)
const asChapters = computed(() => settings.value.workPagesView === 'chapters')

// the outline as the API sent it, arranged for drawing: each heading's sub-headings in the work's order
const childrenOf = computed(() => {
  const map = new Map<string | null, HtmlNode[]>()
  for (const node of shown.value?.outline ?? []) map.set(node.parent, [...map.get(node.parent) ?? [], node])
  return map
})
</script>

<template>
  <section class="html-work">
    <p class="trail"><RouterLink to="/sources">Sources</RouterLink></p>
    <ApiFailure v-if="workError" :error="workError" @retry="store.loadWork(kb, work)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <h1 class="view-title">{{ shown.title }}</h1>
      <p class="work-id"><KnowledgeBaseMark :kb="shown.knowledge_base" /> {{ shown.source_id }}</p>
      <p v-if="shown.why_not" class="why-not">{{ shown.why_not }}</p>
      <template v-else>
        <p class="summary">
          <span>{{ counted(shown.sections, 'section') }} by heading · {{ counted(shown.chunks, 'chunk') }}</span>
          <span class="route">{{ shown.route }}</span>
          <span v-if="shown.licence" class="licence">{{ shown.licence }}</span>
        </p>
        <div class="view-switch">
          <AppButton size="compact" :active="asChapters" @click="settingsStore.setWorkPagesView('chapters')">chapters</AppButton>
          <AppButton size="compact" :active="!asChapters" @click="settingsStore.setWorkPagesView('table')">table</AppButton>
        </div>
        <div v-if="asChapters" class="outline ruled">
          <HtmlOutlineNode v-for="node in childrenOf.get(null) ?? []" :key="node.id" :node="node" :children-of="childrenOf" :kb="kb" :work="work" />
        </div>
        <DataTable v-else table-class="sections ruled">
          <template #head>
            <tr>
              <th>Section</th>
              <th>Heading path</th>
              <th class="number">Chunks</th>
              <th class="number">Characters</th>
            </tr>
          </template>
          <tbody>
            <tr v-for="row in shown.rows" :key="row.label" :data-section="row.label">
              <td><RouterLink :to="{ name: 'html-section', params: { kb, work, section: row.label } }">{{ row.label }}</RouterLink></td>
              <td>{{ row.heading_path }}</td>
              <td class="number">{{ row.chunks.toLocaleString('en') }}</td>
              <td class="number">{{ row.characters.toLocaleString('en') }}</td>
            </tr>
          </tbody>
        </DataTable>
      </template>
    </template>
  </section>
</template>

<style scoped>
.trail a,
.sections a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover,
.sections a:hover {
  text-decoration: underline;
}

.work-id,
.why-not,
.route,
.licence {
  color: var(--color-text-secondary);
}

.work-id {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-sm);
}

.view-switch {
  display: flex;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}

.sections th {
  text-align: left;
  font-weight: normal;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.sections th,
.sections td {
  padding: 2px var(--space-md) 2px 0;
  vertical-align: top;
}

.sections .number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
