<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import CoverageLadder from '@/components/CoverageLadder.vue'
import EditionBar from '@/components/EditionBar.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import HtmlOutlineNode from '@/components/HtmlOutlineNode.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import LadderDetails from '@/components/LadderDetails.vue'
import RecordTrail from '@/components/RecordTrail.vue'
import { useEpubStore } from '@/stores/epub_store'
import { useSettingsStore } from '@/stores/settings_store'
import { useViewName } from '@/view_name'
import type { HtmlNode } from '@/types/api/html_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import { counted } from '@/counted'

/**
 * A licensed EPUB work (decision 123.a, the operator's P1.a), shown as a free HTML work is: its outline by heading in the
 * book's own order, folded, each heading with the range of its section labels and its sections; or every section flat in a
 * table with its characters and images. A section opens its text with its images. The labels are the librarian's, so a
 * search hit's `s12` is this view's `s12`. The outline is the HTML works' own component, opening the EPUB's section route.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
}>()

const store = useEpubStore()
const { workError } = storeToRefs(store)
const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)

watch(() => [props.kb, props.work] as const, ([kb, work]) => {
  void store.loadWork(kb, work)
}, { immediate: true })

const shown = computed(() => store.workOf(props.kb, props.work))
useViewName(() => shown.value?.title ?? null)
const asChapters = computed(() => settings.value.workPagesView === 'chapters')

// the outline as the API sent it, arranged for drawing: each heading's sub-headings in the book's order
const childrenOf = computed(() => {
  const map = new Map<string | null, HtmlNode[]>()
  for (const node of shown.value?.outline ?? []) map.set(node.parent, [...map.get(node.parent) ?? [], node])
  return map
})
</script>

<template>
  <section class="epub-work">
    <RecordTrail :editions="shown?.editions" :kb="kb" />
    <ApiFailure v-if="workError" :error="workError" @retry="store.loadWork(kb, work)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <h1 class="view-title">{{ shown.title }}</h1>
      <!-- its work's editions (E1.a), each a link to its record, this one's own marked -->
      <EditionBar v-if="shown.editions" :editions="shown.editions" :kb="kb" />
      <p class="work-id"><KnowledgeBaseMark :kb="shown.knowledge_base" /> {{ shown.source_id }}</p>
      <p class="summary" data-part="summary">
        <span>{{ counted(shown.sections, 'section') }} by heading · {{ counted(shown.images, 'image') }}</span>
        <span class="route">{{ shown.route }}</span>
        <!-- the catalog's licence, as the sources list shows it -->
        <span v-if="shown.licence" class="licence" data-part="licence">{{ shown.licence }}</span>
      </p>
      <!-- how far it is refined (U1.a), as a PDF work's record says it: a kept edition's in neutral words (E1.a) -->
      <div v-if="shown.ladder" class="epub-coverage" data-part="coverage-ladder">
        <CoverageLadder :ladder="shown.ladder"><LadderDetails :ladder="shown.ladder" /></CoverageLadder>
      </div>
      <div class="view-switch">
        <AppButton size="compact" :active="asChapters" @click="settingsStore.setWorkPagesView('chapters')">chapters</AppButton>
        <AppButton size="compact" :active="!asChapters" @click="settingsStore.setWorkPagesView('table')">table</AppButton>
      </div>
      <div v-if="asChapters" class="outline ruled">
        <HtmlOutlineNode
          v-for="node in childrenOf.get(null) ?? []"
          :key="node.id"
          :node="node"
          :children-of="childrenOf"
          :kb="kb"
          :work="work"
          section-route="epub-section"
          :chunked="false"
        />
      </div>
      <DataTable v-else table-class="sections ruled">
        <template #head>
          <tr>
            <th>Section</th>
            <th>Heading path</th>
            <th class="number">Characters</th>
            <th class="number">Images</th>
          </tr>
        </template>
        <tbody>
          <tr v-for="row in shown.rows" :key="row.label" :data-section="row.label">
            <td><RouterLink :to="{ name: 'epub-section', params: { kb, work, section: row.label } }">{{ row.label }}</RouterLink></td>
            <td>{{ row.heading_path }}</td>
            <td class="number">{{ row.characters.toLocaleString('en') }}</td>
            <td class="number">{{ row.images ? row.images.toLocaleString('en') : '' }}</td>
          </tr>
        </tbody>
      </DataTable>
    </template>
  </section>
</template>

<style scoped>
.sections a {
  color: var(--color-accent);
  text-decoration: none;
}

.sections a:hover {
  text-decoration: underline;
}

.work-id,
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

.sections .number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
