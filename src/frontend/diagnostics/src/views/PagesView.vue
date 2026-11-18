<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import GroupedPageRows from '@/components/GroupedPageRows.vue'
import { useOverviewStore } from '@/stores/overview_store'

/**
 * The pages behind a figure of the overview: every page served that matches the filters in the address, by knowledge base,
 * work and page. The filters stand above the list, each one removable, so a figure's pages can be widened from here.
 */
const FILTERS: Record<string, string> = {
  knowledge_base: 'knowledge base',
  state: 'state',
  person: 'a person',
  category: 'category',
  route: 'route',
  integrity: 'reading file',
  why_judged: 'why judged',
  verdict: 'verdict',
  reason: 'reason',
  reader: 'read by',
  judge: 'judged by',
  provider: 'provider',
}

const route = useRoute()
const store = useOverviewStore()
const { pagesError } = storeToRefs(store)

const filters = computed<Record<string, string>>(() => Object.fromEntries(Object.keys(FILTERS)
  .filter(name => typeof route.query[name] === 'string' && route.query[name] !== '')
  .map(name => [name, String(route.query[name])])))

watch(filters, chosen => {
  void store.loadPages(chosen)
}, { immediate: true })

const list = computed(() => store.pagesOf(filters.value))

function without(name: string): Record<string, string> {
  return Object.fromEntries(Object.entries(filters.value).filter(([key]) => key !== name))
}
</script>

<template>
  <section class="pages-view">
    <p class="trail"><RouterLink to="/overview">Overview</RouterLink></p>
    <h1 class="view-title">Pages</h1>
    <p class="filters">
      <span v-if="!Object.keys(filters).length" class="no-filter">every page served</span>
      <span v-for="(value, name) in filters" :key="name" class="filter" :data-filter="name">
        <span class="filter-name">{{ FILTERS[name] }}:</span> {{ value }}
        <RouterLink class="remove" :to="{ name: 'pages', query: without(name) }" :aria-label="`drop the ${FILTERS[name]} filter`">
          ×
        </RouterLink>
      </span>
    </p>
    <ApiFailure v-if="pagesError" :error="pagesError" @retry="store.loadPages(filters)" />
    <LoadingLine v-else-if="!list" />
    <p v-else-if="list.rows.length === 0" class="empty">No page matches these filters.</p>
    <GroupedPageRows v-else :rows="list.rows" />
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
  margin-bottom: var(--space-md);
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
.no-filter,
.empty {
  color: var(--color-text-secondary);
}

.remove {
  color: var(--color-accent);
  text-decoration: none;
}
</style>
