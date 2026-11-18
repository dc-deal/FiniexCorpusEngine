<script setup lang="ts">
import DataTable from '@/components/base/DataTable.vue'
import IntegrityMark from '@/components/IntegrityMark.vue'
import { usd } from '@/cost_format'
import StateMark from '@/components/StateMark.vue'
import type { ModelRow, ModelSection, Section } from '@/types/api/overview_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One box of the overview: each value of a field once, its count in each knowledge base beside it (the operator's 16.a), each count
 * opening the pages it counts. "—" where a value does not occur in a knowledge base, or the base is not served. The counts
 * are the API's; this lays them out and names the filter each one stands for. A box of which model did what (17.a) shows
 * beside each count what that work cost.
 */
withDefaults(defineProps<{
  section: Section | ModelSection
  bases: KnowledgeBase[]
  paid?: boolean
}>(), { paid: false })

function formatted(count: number | null): string {
  return count === null ? '—' : count.toLocaleString('en')
}

function costOf(row: Section['rows'][number] | ModelRow, kb: KnowledgeBase): string {
  const cost = 'free_usd' in row ? row[`${kb}_usd` as const] : null
  return cost === null ? '—' : usd(cost)
}
</script>

<template>
  <section class="box" :data-field="section.field" :data-section="section.title">
    <DataTable :table-class="paid ? 'box-rows ruled paid' : 'box-rows ruled'" wide>
      <template #head>
        <tr>
          <th class="box-title">{{ section.title }}</th>
          <template v-for="kb in bases" :key="kb">
            <th class="base-column">{{ kb }}</th>
            <th v-if="paid" class="base-column">USD</th>
          </template>
        </tr>
      </template>
      <tbody>
        <tr v-for="row in section.rows" :key="row.value" :data-value="row.value">
          <td class="box-value">
            <StateMark v-if="section.field === 'state'" :state="row.value" />
            <IntegrityMark v-else-if="section.field === 'integrity'" :state="row.value" />
            <template v-else>{{ row.value }}</template>
          </td>
          <template v-for="kb in bases" :key="kb">
            <td class="box-count" :data-kb="kb">
              <RouterLink
                v-if="section.linked && row[kb] !== null"
                :to="{ name: 'pages', query: { knowledge_base: kb, [section.field]: row.value } }"
              >
                {{ formatted(row[kb]) }}
              </RouterLink>
              <template v-else>{{ formatted(row[kb]) }}</template>
            </td>
            <td v-if="paid" class="box-count box-usd" :data-kb-usd="kb">{{ costOf(row, kb) }}</td>
          </template>
        </tr>
      </tbody>
    </DataTable>
    <p v-if="section.note" class="box-note">{{ section.note }}</p>
  </section>
</template>

<style scoped>
.box {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: var(--color-bg-surface);
  padding: var(--space-sm) var(--space-md);
}

.box-rows th {
  font-weight: normal;
  color: var(--color-text-secondary);
  text-align: left;
  padding-bottom: var(--space-xs);
}

.box-rows .box-title {
  color: var(--color-text-primary);
}

/* a base's name stands over its numbers, right-aligned as they are */
.box-rows .base-column {
  text-align: right;
  width: 6rem;
}

/* four number columns: each a little narrower, so the name beside them keeps its room */
.box-rows.paid .base-column {
  width: 5.5rem;
}

.box-rows td {
  padding: 2px 0;
  vertical-align: top;
}

.box-value {
  padding-right: var(--space-md);
}

/* the counts line up as numbers: right-aligned, in one column per knowledge base */
.box-count {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}

.box-count a {
  color: var(--color-accent);
  text-decoration: none;
}

.box-count a:hover {
  text-decoration: underline;
}

.box-note {
  color: var(--color-text-secondary);
}
</style>
