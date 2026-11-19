<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { counted } from '@/counted'
import { usd } from '@/cost_format'
import { shortCommand } from '@/run_format'
import { useOverviewStore } from '@/stores/overview_store'
import type { Figure } from '@/types/api/overview_types'

/**
 * The corpus at a glance (the operator's O3.a, 19 Nov: "today there is only one corpus"): one headline, summed in the API over
 * the knowledge bases served, each figure's part per base in its card; then the latest runs of both, newest first, each with
 * its base's mark. A base the sums leave out says why, under `--public-only` the licensed one. The tables of counts by route,
 * state, verdict, category, model and the integrity of each reading file are gone: each of their counts stays in the
 * Pages list's filters, and the integrity of some 10,200 files is no longer asked on every load. Every figure is the API's.
 */
const store = useOverviewStore()
const { overview, overviewError } = storeToRefs(store)

onMounted(() => {
  void store.loadOverview()
})

const headline = computed(() => overview.value?.headline ?? null)

/** A figure's detail, each knowledge base's part of it, as its card's rows. */
function parts(figure: Figure | { by_base: Record<string, number> } | null | undefined, say = (value: number) => value.toLocaleString('en')) {
  return Object.entries(figure?.by_base ?? {}).map(([base, value]) => ({ label: base, value: say(value as number) }))
}

// what the work cost, each base's part and then each provider's, the API's sums (line 1, 19 Nov: the per-model tables go,
// the providers stay in this card)
const costRows = computed(() => [...parts(headline.value?.cost_usd, usd),
  ...Object.entries(headline.value?.cost_usd.by_provider ?? {}).map(([provider, value]) => ({ label: `${provider} (provider)`, value: usd(value) }))])

// the share of the planned pages that passed, the API's, said as a person reads a share
const share = computed(() => (typeof headline.value?.share_passed === 'number'
  ? `${(headline.value.share_passed * 100).toFixed(1)} % of planned`
  : null))
</script>

<template>
  <section class="overview">
    <h1 class="view-title">Overview</h1>
    <ApiFailure v-if="overviewError" :error="overviewError" @retry="store.loadOverview()" />
    <LoadingLine v-else-if="!overview || !headline" />
    <template v-else>
      <!-- a knowledge base the sums leave out, and why: under --public-only the licensed one, so the free one stands alone -->
      <p v-for="left in headline.left_out" :key="left.knowledge_base" class="left-out" data-part="left-out" :data-kb="left.knowledge_base">
        <KnowledgeBaseMark :kb="left.knowledge_base" /> {{ left.why }}
      </p>
      <p v-for="left in headline.shelf_left_out" :key="`shelf-${left.knowledge_base}`" class="left-out" data-part="shelf-left-out"
         :data-kb="left.knowledge_base">
        <KnowledgeBaseMark :kb="left.knowledge_base" /> {{ left.why }}
      </p>

      <!-- the corpus in one line: each figure the sum over the bases served, its part per base in its card (O3.a) -->
      <div class="tiles" data-part="headline">
        <HoverCard v-if="headline.works" class="tile-card" title="Works on the shelf" :rows="parts(headline.works)">
          <RouterLink class="tile" to="/sources" data-tile="works">
            <span class="tile-value">{{ headline.works.total.toLocaleString('en') }}</span>
            <span class="tile-label">works</span>
          </RouterLink>
        </HoverCard>
        <HoverCard v-if="headline.planned" class="tile-card" title="Pages planned" :rows="parts(headline.planned)">
          <RouterLink class="tile" to="/shelf" data-tile="planned">
            <span class="tile-value">{{ headline.planned.total.toLocaleString('en') }}</span>
            <span class="tile-label">pages planned</span>
          </RouterLink>
        </HoverCard>
        <HoverCard v-if="headline.passed" class="tile-card" title="Pages passed" :rows="parts(headline.passed)">
          <RouterLink class="tile" to="/shelf" data-tile="passed">
            <span class="tile-value">{{ headline.passed.total.toLocaleString('en') }}</span>
            <span class="tile-label">passed</span>
            <span v-if="share" class="tile-share" data-part="share">{{ share }}</span>
          </RouterLink>
        </HoverCard>
        <HoverCard v-if="headline.served" class="tile-card" title="Pages the search serves" :rows="parts(headline.served)">
          <RouterLink class="tile" to="/shelf" data-tile="served">
            <span class="tile-value">{{ headline.served.total.toLocaleString('en') }}</span>
            <span class="tile-label">pages served</span>
          </RouterLink>
        </HoverCard>
        <HoverCard class="tile-card" title="Pages to look at" :rows="parts(headline.to_look_at)">
          <RouterLink class="tile" to="/issues" data-tile="to_look_at">
            <span class="tile-value">{{ headline.to_look_at.total.toLocaleString('en') }}</span>
            <span class="tile-label">to look at</span>
          </RouterLink>
        </HoverCard>
        <HoverCard class="tile-card" title="USD spent" :rows="costRows">
          <div class="tile" data-tile="cost">
            <span class="tile-value">{{ usd(headline.cost_usd.total) }}</span>
            <span class="tile-label">USD spent</span>
          </div>
        </HoverCard>
      </div>

      <section class="band" data-band="runs">
        <h2 class="band-title">Runs <span class="band-hint">the latest, newest first</span></h2>
        <p v-if="!overview.runs" class="note">{{ overview.runs_why_not }}</p>
        <DataTable v-else table-class="run-rows ruled" wide>
          <template #head>
            <tr>
              <th />
              <th>Base</th>
              <th>Started</th>
              <th>Command</th>
              <th>Outcome</th>
              <th class="cost">USD</th>
            </tr>
          </template>
          <tbody>
            <tr v-for="run in overview.runs" :key="`${run.knowledge_base}/${run.run_id}`" :data-run="`${run.knowledge_base}/${run.run_id}`">
              <td class="run-id"><RouterLink :to="{ name: 'run', params: { kb: run.knowledge_base, run: run.run_id } }">#{{ run.run_id }}</RouterLink></td>
              <td><KnowledgeBaseMark :kb="run.knowledge_base" /></td>
              <td class="when"><HumanTime :at="run.started_at" /></td>
              <td>
                <span class="command" :title="run.command">{{ shortCommand(run.command) }}</span>
                <span v-if="run.note" class="run-note">{{ run.note }}</span>
                <FoldSection v-if="run.batch_ids.length" class="batches" :title="counted(run.batch_ids.length, 'batch', 'batches')">
                  <span class="batch-ids">{{ run.batch_ids.join(', ') }}</span>
                </FoldSection>
              </td>
              <!-- a run that recorded no end says so in the API's words, what that means in its card (line 1, 19 Nov) -->
              <td class="outcome">
                <HoverCard v-if="run.outcome_why" title="Outcome" :rows="[{ label: 'means', value: run.outcome_why }]">
                  <span class="no-end">{{ run.outcome }}</span>
                </HoverCard>
                <template v-else>{{ run.outcome ?? '' }}</template>
              </td>
              <td class="cost">{{ run.cost_usd === null ? '' : usd(run.cost_usd) }}</td>
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

.left-out,
.note {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}

/* the corpus in one line of figures: the number above, its word beneath; a figure that opens a list looks like a link */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.tile-card.hover-card-host {
  display: block;
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  height: 100%;
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
.tile-share {
  color: var(--color-text-secondary);
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
