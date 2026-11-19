<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import GroupedPageRows from '@/components/GroupedPageRows.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import StateMark from '@/components/StateMark.vue'
import { applyFacets } from '@/components/base/facet_filter'
import { queryValues } from '@/address_query'
import { counted } from '@/counted'
import { useOverviewStore } from '@/stores/overview_store'
import type { IssueRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { FacetDefinition, FacetSelection, SortDefinition } from '@/types/facet_types'

/**
 * Every page served, narrowed with the facet bar (the operator's P1.a, 19 Nov), by knowledge base, work and page. The
 * overview's tables of counts left for this: each count is a value of a facet here, its pages one pick away. The list loads
 * once, each page with its words in every field (the API's `filtered_by`), and the bar counts them in the browser (Q4.a). The
 * choice stands in the address, as in the Issues, so a link from anywhere opens the pages it names (`?state=blocked`) and
 * the browser's back returns to them. The integrity of a reading file is no facet: the API asks the disk for it only when
 * the address names it (`?integrity=tampered`), never on a load, and it stands above the bar, removable.
 */
const WORDED: { id: string, label: string }[] = [
  { id: 'state', label: 'State' }, { id: 'route', label: 'Route' }, { id: 'verdict', label: 'Verdict' },
  { id: 'reason', label: 'Reason' }, { id: 'category', label: 'Category' }, { id: 'why_judged', label: 'Why judged' },
  { id: 'person', label: 'A person' }, { id: 'review', label: 'Automated review' }, { id: 'reader', label: 'Read by' },
  { id: 'judge', label: 'Judged by' }, { id: 'provider', label: 'Provider' },
]
const FACET_KEYS = ['knowledge_base', ...WORDED.map(one => one.id)]

const route = useRoute()
const router = useRouter()
const store = useOverviewStore()
const { pagesError } = storeToRefs(store)

const integrity = computed(() => (typeof route.query.integrity === 'string' && route.query.integrity ? route.query.integrity : null))
// what the API is asked: every page, or those whose reading file is in the state the address names
const asked = computed((): Record<string, string> => (integrity.value ? { integrity: integrity.value } : {}))
watch(asked, filters => {
  void store.loadPages(filters)
}, { immediate: true })
const list = computed(() => store.pagesOf(asked.value))

const selection = computed<FacetSelection>({
  get: () => Object.fromEntries(FACET_KEYS.map(key => [key, queryValues(route.query, key)])),
  set: chosen => {
    const query: Record<string, string | string[]> = Object.fromEntries(FACET_KEYS.map(key => [key, chosen[key] ?? []] as const)
      .filter(([, values]) => values.length > 0))
    if (integrity.value) query.integrity = integrity.value
    void router.replace({ name: 'pages', query })
  },
})

const facets = computed<FacetDefinition<IssueRow>[]>(() => [
  { id: 'knowledge_base', label: 'Knowledge base', valuesOf: row => [row.knowledge_base] },
  ...WORDED.map(one => ({
    id: one.id,
    label: one.label,
    valuesOf: (row: IssueRow) => row.filtered_by?.[one.id] ?? [],
    // the check states in the core's order, as the API gives it; every other facet's values alphabetically
    order: one.id === 'state' ? list.value?.state_order : undefined,
  })),
])
// the pages stand as the API serves them, by base, work and page: one order, so the bar draws no sort control
const AS_SERVED: SortDefinition<IssueRow>[] = [{ id: 'served', label: 'as served', compare: () => 0 }]

const shown = computed(() => applyFacets({ rows: list.value?.rows ?? [], definitions: facets.value, selection: selection.value }))

// A long list draws its first pages and says how many more there are, every page one click away: the whole of both bases,
// 10,224 pages, drew some 147,000 elements (measured natively, 19 Nov), drawn again on every pick
const SHOWN_FIRST = 500
const everyPage = ref(false)
const drawn = computed(() => (everyPage.value ? shown.value : shown.value.slice(0, SHOWN_FIRST)))

function withoutIntegrity(): Record<string, string | string[]> {
  return Object.fromEntries(Object.entries(route.query).filter(([key]) => key !== 'integrity')) as Record<string, string | string[]>
}
</script>

<template>
  <section class="pages-view">
    <p class="trail"><RouterLink to="/overview">Overview</RouterLink></p>
    <h1 class="view-title">Pages</h1>
    <!-- the reading file's state, which the API answers from the disk and the bar cannot: removable, as before -->
    <p v-if="integrity" class="filters">
      <span class="filter" data-filter="integrity">
        <span class="filter-name">reading file:</span> {{ integrity }}
        <RouterLink class="remove" :to="{ name: 'pages', query: withoutIntegrity() }" aria-label="drop the reading file filter">×</RouterLink>
      </span>
    </p>
    <ApiFailure v-if="pagesError" :error="pagesError" @retry="store.loadPages(asked)" />
    <LoadingLine v-else-if="!list" />
    <template v-else>
      <FacetBar v-model:selection="selection" :rows="list.rows" :facets="facets" :sorts="AS_SERVED" sort="served">
        <!-- a value keeps its look in the panel (Q3.a): a state its glyph, word and colour, a verdict whose it is -->
        <template #value="{ facet, value }">
          <StateMark v-if="facet === 'state'" :state="value" />
          <PersonStanding v-else-if="facet === 'person' || facet === 'review'"
                          :mark="{ standing: value as 'accepted' | 'rejected' | 'noted', by_a_person: facet === 'person' }" />
          <KnowledgeBaseMark v-else-if="facet === 'knowledge_base'" :kb="value as KnowledgeBase" />
          <template v-else>{{ value }}</template>
        </template>
      </FacetBar>
      <p v-if="shown.length === 0" class="empty">No page matches these filters.</p>
      <template v-else>
        <GroupedPageRows :rows="drawn" />
        <p v-if="drawn.length < shown.length" class="more" data-part="more">
          the first {{ drawn.length.toLocaleString('en') }} of {{ counted(shown.length, 'page') }}: narrow them with the bar, or
          <AppButton variant="link" data-part="show-every-page" @click="everyPage = true">show every page</AppButton>
        </p>
      </template>
    </template>
  </section>
</template>

<style scoped>
.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.view-title {
  margin-bottom: var(--space-sm);
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-sm);
  margin-bottom: var(--space-sm);
}

.filter {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-xs);
  padding: 1px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.filter-name,
.empty,
.more {
  color: var(--color-text-secondary);
}

.more {
  margin-top: var(--space-sm);
}

.remove {
  color: var(--color-accent);
  text-decoration: none;
}
</style>
