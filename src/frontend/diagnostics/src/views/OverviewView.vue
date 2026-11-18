<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import OverviewSection from '@/components/OverviewSection.vue'
import { usd } from '@/cost_format'
import { shortCommand } from '@/run_format'
import { useOverviewStore } from '@/stores/overview_store'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * The whole pipeline at a glance, the knowledge bases side by side (the operator, 2026-11-05; compact boxes, 16.a), in bands
 * with a heading each, their boxes flowing in two balanced columns (18.a). On top, a row of key figures per knowledge
 * base, the works and pages read each with what the search serves beneath (1.a); then which model did what, in pages and
 * in USD (17.a). Then boxes in which each value stands once, its count in
 * each knowledge base
 * beside it: how each page's text was made, its state, why it was judged or not, the verdicts, the reasons a page carries,
 * and what the search holds of every medium. Every count of pages opens the pages it counts. Last, the latest runs.
 * Every figure is the API's; a knowledge base this app does not serve says why.
 */
const store = useOverviewStore()
const { overview, overviewError } = storeToRefs(store)

onMounted(() => {
  void store.loadOverview()
})

const bases = computed<KnowledgeBase[]>(() => (overview.value?.bases ?? []).map(base => base.knowledge_base))

// the search's own count, as its start banner gives it; while its index is still being built, said so rather than guessed
function inTheSearch(count: number | null | undefined): string {
  return typeof count === 'number' ? `${count.toLocaleString('en')} in the search` : 'search index building'
}
</script>

<template>
  <section class="overview">
    <h1 class="view-title">Overview</h1>
    <ApiFailure v-if="overviewError" :error="overviewError" @retry="store.loadOverview()" />
    <LoadingLine v-else-if="!overview" />
    <template v-else>
      <div class="headlines">
        <article v-for="base in overview.bases" :key="base.knowledge_base" class="headline" :data-kb="base.knowledge_base">
          <h2 class="headline-title"><KnowledgeBaseMark :kb="base.knowledge_base" /></h2>
          <p v-if="!base.served" class="not-served">{{ base.why_not }}</p>
          <div v-else class="tiles">
            <!-- what was read beside what the search serves (the operator's 1.a): the server's banner counts every route, an HTML
                 source and legacy Markdown too, so its 15 works and these 11 are both right and must not look alike -->
            <RouterLink class="tile" to="/sources" data-tile="works">
              <span class="tile-value">{{ base.works.toLocaleString('en') }}</span>
              <span class="tile-label">works read page by page</span>
              <span class="tile-served" data-part="served">{{ inTheSearch(base.served_works) }}</span>
            </RouterLink>
            <RouterLink class="tile" :to="{ name: 'pages', query: { knowledge_base: base.knowledge_base } }" data-tile="pages">
              <span class="tile-value">{{ base.pages.toLocaleString('en') }}</span>
              <span class="tile-label">pages read</span>
              <span class="tile-served" data-part="served">{{ inTheSearch(base.served_pages) }}</span>
            </RouterLink>
            <div class="tile" data-tile="judged">
              <span class="tile-value">{{ base.judged.toLocaleString('en') }}</span>
              <span class="tile-label">judged</span>
            </div>
            <RouterLink class="tile" to="/issues" data-tile="to_look_at">
              <span class="tile-value">{{ base.to_look_at.toLocaleString('en') }}</span>
              <span class="tile-label">to look at</span>
            </RouterLink>
            <div class="tile" data-tile="cost">
              <span class="tile-value">{{ usd(base.cost_usd) }}</span>
              <span class="tile-label">USD spent</span>
            </div>
          </div>
        </article>
      </div>

      <section class="band" data-band="cost">
        <h2 class="band-title">Cost <span class="band-hint">which model did what</span></h2>
        <div class="band-boxes">
          <OverviewSection v-for="section in overview.models" :key="section.title" :section="section" :bases="bases" paid />
        </div>
      </section>

      <section class="band" data-band="pipeline">
        <h2 class="band-title">Pages through the pipeline</h2>
        <div class="band-boxes">
          <OverviewSection v-for="section in overview.sections" :key="section.title" :section="section" :bases="bases" />
        </div>
      </section>

      <section class="band" data-band="search">
        <h2 class="band-title">Search</h2>
        <div class="band-boxes">
          <OverviewSection :section="overview.search" :bases="bases" />
        </div>
      </section>

      <section class="band" data-band="runs">
        <h2 class="band-title">Runs <span class="band-hint">the latest, newest first</span></h2>
        <div class="runs-grid">
          <section v-for="base in overview.bases" :key="base.knowledge_base" class="box runs" :data-kb="base.knowledge_base">
            <h3 class="box-title"><KnowledgeBaseMark :kb="base.knowledge_base" /></h3>
            <p v-if="!base.served" class="note">{{ base.why_not }}</p>
            <p v-else-if="!base.runs" class="note">No runs recorded on this machine: the pipeline database is local and not tracked.</p>
            <DataTable v-else table-class="run-rows ruled" wide>
              <template #head>
                <tr>
                  <th />
                  <th>started</th>
                  <th>command</th>
                  <th>outcome</th>
                  <th class="cost">USD</th>
                </tr>
              </template>
              <tbody>
                <tr v-for="run in base.runs" :key="run.run_id" :data-run="run.run_id">
                  <td class="run-id"><RouterLink :to="{ name: 'run', params: { kb: base.knowledge_base, run: run.run_id } }">#{{ run.run_id }}</RouterLink></td>
                  <td class="when"><HumanTime :at="run.started_at" /></td>
                  <td>
                    <span class="command" :title="run.command">{{ shortCommand(run.command) }}</span>
                    <span v-if="run.note" class="run-note">{{ run.note }}</span>
                    <FoldSection v-if="run.batch_ids.length" class="batches" :title="`${run.batch_ids.length} ${run.batch_ids.length === 1 ? 'batch' : 'batches'}`">
                      <span class="batch-ids">{{ run.batch_ids.join(', ') }}</span>
                    </FoldSection>
                  </td>
                  <td>{{ run.outcome ?? '' }}</td>
                  <td class="cost">{{ run.cost_usd === null ? '' : usd(run.cost_usd) }}</td>
                </tr>
              </tbody>
            </DataTable>
          </section>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

/* the knowledge bases side by side; one above the other on a narrow screen */
.headlines,
.runs-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
  align-items: start;
}

.headlines {
  margin-bottom: var(--space-lg);
}

/* a band: a heading over the boxes of one subject */
.band {
  margin-bottom: var(--space-lg);
}

.band-title {
  font-weight: normal;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-xs);
  margin-bottom: var(--space-sm);
}

.band-hint {
  text-transform: none;
  letter-spacing: normal;
  margin-left: var(--space-sm);
}

/* a band's boxes flow down two columns the browser balances, so a short box leaves no hole beside a long one */
.band-boxes {
  columns: 2;
  column-gap: var(--space-md);
}

.band-boxes > .box {
  break-inside: avoid;
  margin-bottom: var(--space-md);
}

@media (max-width: 900px) {
  .headlines,
  .runs-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .band-boxes {
    columns: 1;
  }
}

.headline-title {
  margin-bottom: var(--space-xs);
}

/* key figures: the number large, its word small beneath; a figure that opens a list looks like a link */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
  gap: var(--space-sm);
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: var(--color-bg-surface);
  color: var(--color-text-primary);
  text-decoration: none;
}

a.tile .tile-value {
  color: var(--color-accent);
}

a.tile:hover {
  border-color: var(--color-accent);
}

.tile-value {
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.tile-label,
.tile-served,
.not-served,
.note {
  color: var(--color-text-secondary);
}

/* the search's count stands beneath what was read, set apart by a rule so the two figures never read as one */
.tile-served {
  border-top: 1px solid var(--color-border);
  padding-top: 2px;
  margin-top: 2px;
}

.box {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: var(--color-bg-surface);
  padding: var(--space-sm) var(--space-md);
}

.box-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-weight: normal;
  margin-bottom: var(--space-xs);
}

.run-rows th {
  font-weight: normal;
  text-align: left;
  color: var(--color-text-secondary);
  padding: 0 var(--space-sm) var(--space-xs) 0;
}

.run-rows td {
  padding: 2px var(--space-sm) 2px 0;
  vertical-align: top;
}

/* one line a run: the number, the time and the cost never wrap; the command wraps only where it must */
.run-id,
.when,
.run-rows .cost {
  white-space: nowrap;
  color: var(--color-text-secondary);
}

/* a run's number opens its own page */
.run-id a {
  color: var(--color-accent);
  text-decoration: none;
}

.run-id a:hover {
  text-decoration: underline;
}

.run-rows .cost {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.run-note,
.batches {
  color: var(--color-text-secondary);
  margin-left: var(--space-sm);
}

.batches {
  display: inline-block;
}

.batch-ids {
  display: block;
  word-break: break-all;
}
</style>
