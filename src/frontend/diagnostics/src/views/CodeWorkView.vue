<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import CodeUnitTable, { type UnitRow } from '@/components/CodeUnitTable.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import LanguageMark from '@/components/LanguageMark.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import { useCodeStore } from '@/stores/code_store'
import { useViewName } from '@/view_name'
import { recordRoute } from '@/edition_route'
import { counted } from '@/counted'
import type { CodeWork } from '@/types/api/code_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * A book's companion code (#12, the operator's 3.a, 23 Nov): its folders, each a fold of its files, each file with what the
 * core's catalog says of its unit; the core's count of its units by category once in its head. A file opens its text
 * numbered. The way back names the book it accompanies, as an edition's record names its work (E1.a). The code is the
 * publisher's and licensed, so it never leaves this machine: no screenshot, test or file holds it.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
}>()

const store = useCodeStore()
const { workError } = storeToRefs(store)

watch(() => [props.kb, props.work] as const, ([kb, work]) => {
  void store.loadWork(kb, work)
}, { immediate: true })

const shown = computed(() => store.workOf(props.kb, props.work))
useViewName(() => shown.value?.title ?? null)
const bookRoute = computed(() => (shown.value?.companion ? recordRoute(shown.value.companion, props.kb) : null))

function rowsOf(folder: CodeWork['folders'][number]): UnitRow[] {
  return folder.files.map(file => ({ key: file.label, name: file.name, unit: file.unit,
    to: { name: 'code-page', params: { kb: props.kb, work: props.work, label: file.label } } }))
}
</script>

<template>
  <section class="code-work">
    <p class="trail" data-part="trail">
      <RouterLink to="/sources">Sources</RouterLink>
      <template v-if="shown?.companion">
        <span class="trail-step" aria-hidden="true"> › </span>
        <RouterLink v-if="bookRoute" :to="bookRoute" data-part="trail-book">{{ shown.companion.title }}</RouterLink>
        <span v-else data-part="trail-book">{{ shown.companion.title }}</span>
      </template>
    </p>
    <ApiFailure v-if="workError" :error="workError" @retry="store.loadWork(kb, work)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <h1 class="view-title">{{ shown.title }}</h1>
      <p class="work-id"><KnowledgeBaseMark :kb="shown.knowledge_base" /> <LanguageMark :language="shown.language" /> {{ shown.work }}</p>
      <p class="summary" data-part="summary">
        <span>{{ counted(shown.files, 'file') }}<template v-if="shown.code_language"> of {{ shown.code_language }}</template></span>
        <span class="route">{{ shown.route }}</span>
        <span v-if="shown.licence" class="licence" data-part="licence">{{ shown.licence }}</span>
      </p>
      <!-- the core's own count of its units by category, once for the work (line 1, 23 Nov) -->
      <p v-if="shown.categories.length" class="categories" data-part="categories">
        <span>{{ counted(shown.units, 'unit') }} in the catalog:</span>
        <span v-for="one in shown.categories" :key="one.category" class="category" :data-category="one.category">
          {{ one.category }} <span class="figure">{{ one.units.toLocaleString('en') }}</span>
        </span>
      </p>
      <p v-else-if="shown.catalog_said" class="none" data-part="catalog-said">{{ shown.catalog_said }}</p>
      <FoldSection
        v-for="folder in shown.folders"
        :key="folder.title ?? ''"
        :title="folder.title ?? 'files'"
        :count="counted(folder.count, 'file')"
        :data-folder="folder.title ?? ''"
        open
      >
        <CodeUnitTable :rows="rowsOf(folder)" />
      </FoldSection>
    </template>
  </section>
</template>

<style scoped>
.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover {
  text-decoration: underline;
}

.trail-step,
.work-id,
.route,
.licence,
.none {
  color: var(--color-text-secondary);
}

.work-id {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.summary,
.categories {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-sm);
}

.figure {
  font-variant-numeric: tabular-nums;
}
</style>
