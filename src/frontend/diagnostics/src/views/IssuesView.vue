<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import FacetBar from '@/components/base/FacetBar.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import GroupedPageRows from '@/components/GroupedPageRows.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import StateMark from '@/components/StateMark.vue'
import { applyFacets } from '@/components/base/facet_filter'
import { queryValues } from '@/address_query'
import { DECIDED, DECIDED_BY_REVIEW, isDecided, standingOf } from '@/listed_state'
import { categoryOf } from '@/page_category'
import { useIssuesStore } from '@/stores/issues_store'
import type { IssueRow } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { FacetDefinition, FacetSelection, SortDefinition } from '@/types/facet_types'

/**
 * The pages a person should look at, over every work of every knowledge base served: an issue the judge or a check found,
 * what the provider blocked or the reader declined, what a stopped work left. Each page keeps the core's word for its
 * state. Within the capstone the list stands in for tickets: from "something is wrong here" one click to the page, its
 * original and its reading.
 */
const store = useIssuesStore()
const { issues, error } = storeToRefs(store)
const route = useRoute()
const router = useRouter()

onMounted(() => {
  void store.loadIssues()
})

// The choice lives in the address (the operator's 24.a), `#/issues?state=issue&kb=free`: a page opened from the narrowed list and
// left by the browser's back lands on the same list, and the list can be passed on as a link. A toggle replaces the address
// rather than adding a step, so back leaves the list instead of undoing its toggles one by one.
const FACET_KEYS = ['state', 'person', 'review', 'category', 'kb']
const selection = computed<FacetSelection>({
  get: () => Object.fromEntries(FACET_KEYS.map(key => [key, queryValues(route.query, key)])),
  set: chosen => {
    const query = Object.fromEntries(FACET_KEYS.map(key => [key, chosen[key] ?? []] as const).filter(([, values]) => values.length > 0))
    void router.replace({ name: 'issues', query })
  },
})

/** A facet's value as the row states it; a row without one states none, and is matched only while nothing is picked. */
const said = (value: string): string[] => (value ? [value] : [])
// each facet's values in the order the API lists them, the core's state order among them
const orderOf = (counts: { value: string }[]): string[] => counts.map(count => count.value)

// The facet bar of the sources list, here too (Y1.a, stage C): the facets the data holds, each value with how many of the rows the other
// facets leave carry it (the operator's Q4.a); the knowledge base a choice only where more than one is served
const facets = computed<FacetDefinition<IssueRow>[]>(() => {
  if (!issues.value) return []
  const listed: FacetDefinition<IssueRow>[] = [
    { id: 'state', label: 'State', valuesOf: row => [row.listed_state ?? row.check.state], order: orderOf(issues.value.states) },
  ]
  // a person's standing verdict (166.a): "judged by a person" is one click, where a person judged any listed page
  if (issues.value.people.length) {
    listed.push({ id: 'person', label: 'A person', valuesOf: row => said(standingOf(row.person, true)), order: orderOf(issues.value.people) })
  }
  // an automated review's, never counted as a person's (the operator's 2.a, 18 Nov)
  if (issues.value.reviews.length) {
    listed.push({ id: 'review', label: 'Automated review', valuesOf: row => said(standingOf(row.person, false)),
      order: orderOf(issues.value.reviews) })
  }
  // what kind of page (172.a)
  if (issues.value.categories.length > 1) {
    listed.push({ id: 'category', label: 'Category', valuesOf: row => [categoryOf(row)], order: orderOf(issues.value.categories) })
  }
  if (issues.value.knowledge_bases.length > 1) {
    listed.push({ id: 'kb', label: 'Knowledge base', valuesOf: row => [row.knowledge_base], order: orderOf(issues.value.knowledge_bases) })
  }
  return listed
})
// the pages stand in the order the API serves them: one order, so the bar draws no sort control
const AS_SERVED: SortDefinition<IssueRow>[] = [{ id: 'served', label: 'as served', compare: () => 0 }]

const rows = computed(() => applyFacets({ rows: issues.value?.rows ?? [], definitions: facets.value, selection: selection.value }))
// the pages a person settled leave the open list for a fold of their own (211.a, the operator: "take pages judged by a person out of the issues"), kept there as a record; the API says which (`listed_state`)
const open = computed(() => rows.value.filter(row => !isDecided(row.listed_state)))
const decided = computed(() => rows.value.filter(row => row.listed_state === DECIDED))
// and the pages an automated review settled, in a fold of their own below (Q.a, 18 Nov): the core serves them by the review,
// but no person decided them
const reviewed = computed(() => rows.value.filter(row => row.listed_state === DECIDED_BY_REVIEW))
// the pages that are not content stand after the rest, as their issues are noted, not repaired (172.a); the API orders them
const toRepair = computed(() => open.value.filter(row => !row.apart))
const apart = computed(() => open.value.filter(row => row.apart))
// no page waits for a person: said only where every listed page is settled, never because a filter hid the open ones
const noneOpen = computed(() => (issues.value?.rows ?? []).every(row => isDecided(row.listed_state)))
function settledSaid(count: number): string {
  return `${count} ${count === 1 ? 'page' : 'pages'}, the check's state kept in each`
}
</script>

<template>
  <section class="issues">
    <h1 class="view-title">Issues</h1>
    <ApiFailure v-if="error" :error="error" @retry="store.loadIssues()" />
    <LoadingLine v-else-if="!issues" />
    <p v-else-if="issues.rows.length === 0" class="empty">No page needs a look.</p>
    <template v-else>
      <FacetBar v-model:selection="selection" :rows="issues.rows" :facets="facets" :sorts="AS_SERVED" sort="served">
        <!-- a value keeps its look in the panel (Q3.a): a state its glyph, word and colour, a verdict whose it is -->
        <template #value="{ facet, value }">
          <StateMark v-if="facet === 'state'" :state="value" />
          <PersonStanding v-else-if="facet === 'person' || facet === 'review'"
                          :mark="{ standing: value as 'accepted' | 'rejected' | 'noted', by_a_person: facet === 'person' }" />
          <KnowledgeBaseMark v-else-if="facet === 'kb'" :kb="value as KnowledgeBase" />
          <template v-else>{{ value }}</template>
        </template>
      </FacetBar>
      <GroupedPageRows v-if="toRepair.length" :rows="toRepair" />
      <section v-if="apart.length" class="apart" data-part="apart">
        <h2 class="apart-title">Not content: noted, not repaired <span class="apart-hint">exercises, indexes, contents, front and back matter</span></h2>
        <GroupedPageRows :rows="apart" />
      </section>
      <p v-if="noneOpen" class="empty" data-part="none-open">No page needs a look.</p>
      <!-- what a person settled, folded below the open pages: their record stays one click away. Flat, so its columns stand
           where the open lists' do, in one grid with them -->
      <FoldSection v-if="decided.length" class="decided" title="Decided by a person" :count="settledSaid(decided.length)" data-part="decided" flat>
        <GroupedPageRows :rows="decided" />
      </FoldSection>
      <FoldSection v-if="reviewed.length" class="decided" title="Decided by an automated review" :count="settledSaid(reviewed.length)"
                   data-part="reviewed" flat>
        <GroupedPageRows :rows="reviewed" />
      </FoldSection>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.apart,
.decided {
  margin-top: var(--space-lg);
}

.apart-title {
  font-weight: normal;
  margin-bottom: var(--space-xs);
}

.apart-hint {
  color: var(--color-text-secondary);
  margin-left: var(--space-sm);
}

.empty {
  color: var(--color-text-secondary);
}
</style>
