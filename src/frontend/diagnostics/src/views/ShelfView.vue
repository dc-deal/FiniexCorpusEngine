<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { useShelfStore } from '@/stores/shelf_store'
import type { ShelfRow } from '@/types/api/shelf_types'

/**
 * The shelf (decision 129.a, the operator's 22.a): every work of both knowledge bases, how far it is converted and why pages did
 * not pass, as the core last counted it. A reason's count opens the work's pages on exactly that reason's route; what
 * passed but is not served says why. Every figure is the core's, the share passed included; a knowledge base without a
 * shelf says how to build it.
 */
const store = useShelfStore()
const { shelf, error } = storeToRefs(store)

onMounted(() => {
  void store.loadShelf()
})

// the core's reason words, as a reader says them
const REASON_WORDS: Record<string, string> = { no_page: 'no page' }

function percent(share: number | null | undefined): string {
  return typeof share === 'number' ? `${Math.round(share * 100)} %` : ''
}

function reasonLink(row: ShelfRow, route: string) {
  return { name: 'work', params: { kb: row.knowledge_base, work: row.source_id! }, query: { route } }
}
</script>

<template>
  <section class="shelf-view">
    <h1 class="view-title">Shelf</h1>
    <ApiFailure v-if="error" :error="error" @retry="store.loadShelf()" />
    <LoadingLine v-else-if="!shelf" />
    <template v-else>
      <section v-for="base in shelf.bases" :key="base.knowledge_base" class="base" :data-kb="base.knowledge_base">
        <h2 class="base-title">
          <KnowledgeBaseMark :kb="base.knowledge_base" />
          <span v-if="base.built_at" class="built">built <HumanTime :at="base.built_at" /></span>
        </h2>
        <p v-if="base.why_not" class="why-not">{{ base.why_not }}</p>
        <template v-else>
          <!-- a shelf counted from another export than the one served here: its counts and the pages a reason opens may part -->
          <p v-if="base.in_step === false" class="out-of-step" data-part="out-of-step">
            <AppIcon name="status-unknown" /> This shelf was built from another export than the one served here: until it is
            built again, a count and the pages its link opens may differ.
          </p>
          <p class="totals">
            <span v-for="(count, name) in base.totals" :key="name" :data-total="name">
              <span class="value">{{ count.toLocaleString('en') }}</span> {{ String(name).replace(/_/g, ' ') }}
            </span>
          </p>
          <DataTable table-class="shelf-rows ruled" wide>
            <template #head>
              <tr>
                <th>Work</th>
                <th>format</th>
                <th class="number">planned</th>
                <th class="number">passed</th>
                <th class="number">share</th>
                <th>not passed</th>
                <th class="number">served</th>
                <th class="number">from readings</th>
                <th>passed, not served</th>
              </tr>
            </template>
            <tbody>
              <tr v-for="row in base.works" :key="`${row.work}/${row.source_id}/${row.file}`" :data-work="row.source_id ?? row.work">
                <td class="title">
                  <RouterLink v-if="row.has_pages && row.source_id" :to="{ name: 'work', params: { kb: row.knowledge_base, work: row.source_id } }">
                    {{ row.title }}
                  </RouterLink>
                  <template v-else>{{ row.title }}</template>
                  <span v-if="row.held" class="note">{{ row.held }}</span>
                  <span v-if="row.not_served" class="note">{{ row.not_served }}</span>
                  <!-- a count the core cannot explain is the core's own bug: said in the open, never folded -->
                  <span v-if="'unexplained' in row.unplaced" class="unexplained-note">
                    <AppIcon name="status-error" /> {{ row.unplaced.unexplained }} passed but not served, unexplained
                  </span>
                </td>
                <td class="format">{{ row.format }}</td>
                <td class="number">{{ row.planned?.toLocaleString('en') ?? '' }}</td>
                <td class="number">{{ row.passed?.toLocaleString('en') ?? '' }}</td>
                <td class="number" data-cell="share">{{ percent(row.share_passed) }}</td>
                <td class="reasons">
                  <template v-for="reason in row.not_passed" :key="reason.reason">
                    <RouterLink v-if="row.has_pages && row.source_id && reason.route" :to="reasonLink(row, reason.route)" :data-reason="reason.reason">
                      {{ reason.count.toLocaleString('en') }} {{ REASON_WORDS[reason.reason] ?? reason.reason }}
                    </RouterLink>
                    <span v-else :data-reason="reason.reason">{{ reason.count.toLocaleString('en') }} {{ REASON_WORDS[reason.reason] ?? reason.reason }}</span>
                  </template>
                </td>
                <td class="number">{{ row.served.pages.toLocaleString('en') }}</td>
                <td class="number">{{ row.served.from_readings.toLocaleString('en') }}</td>
                <td class="unplaced">
                  <FoldSection v-if="row.unplaced_total" :class="{ unexplained: 'unexplained' in row.unplaced }" :title="row.unplaced_total.toLocaleString('en')">
                    <p v-for="(count, why) in row.unplaced" :key="why" :data-why="why">{{ count.toLocaleString('en') }}: {{ why }}</p>
                  </FoldSection>
                </td>
              </tr>
            </tbody>
          </DataTable>
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.base {
  margin-bottom: var(--space-lg);
}

.base-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-weight: normal;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-xs);
  margin-bottom: var(--space-sm);
}

.built,
.why-not,
.note,
.format,
.totals {
  color: var(--color-text-secondary);
}

.totals {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-sm);
}

.value {
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.shelf-rows th {
  font-weight: normal;
  text-align: left;
  color: var(--color-text-secondary);
  padding: 0 var(--space-sm) var(--space-xs) 0;
  white-space: nowrap;
}

.shelf-rows td {
  padding: 2px var(--space-sm) 2px 0;
  vertical-align: top;
}

.shelf-rows .number {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.note {
  display: block;
}

.reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
}

a {
  color: var(--color-accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

/* a count the core cannot explain is its own bug: it must not hide in a fold */
.unplaced .unexplained :deep(.fold-row),
.unplaced [data-why="unexplained"],
.unexplained-note {
  color: var(--color-error);
}

.unexplained-note,
.out-of-step {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.out-of-step {
  color: var(--color-warning);
  margin-bottom: var(--space-sm);
}
</style>
