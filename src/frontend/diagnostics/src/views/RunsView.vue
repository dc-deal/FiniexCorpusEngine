<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { usd } from '@/cost_format'
import { counted } from '@/counted'
import { shortCommand } from '@/run_format'
import { useRunsStore } from '@/stores/runs_store'

/**
 * Every run of the pipeline, newest first, both knowledge bases together, one line each (21.a): what was run, when, how it
 * ended, what it cost, the batches it sent. A run opens its own page, the place of a replay's trace in the review demo
 * (69.a). A base whose runs are not listed says why: not served, or no pipeline database on this machine.
 */
// the base and the note go first, then the start and the cost; the run, its command and its outcome stay
const RUN_COLUMNS = [{}, { rank: 3 as const }, { rank: 2 as const }, {}, {}, { rank: 2 as const }]
const store = useRunsStore()
const { runs, runsError } = storeToRefs(store)

onMounted(() => {
  void store.loadRuns()
})
</script>

<template>
  <section class="runs-view">
    <h1 class="view-title">Runs</h1>
    <ApiFailure v-if="runsError" :error="runsError" @retry="store.loadRuns()" />
    <LoadingLine v-else-if="!runs" />
    <template v-else>
      <p v-for="base in runs.bases.filter(base => base.why_not)" :key="base.knowledge_base" class="not-listed" :data-kb="base.knowledge_base">
        <KnowledgeBaseMark :kb="base.knowledge_base" /> {{ base.why_not }}
      </p>
      <!-- ranked, so a narrow window keeps the run, its command and how it ended (the viewer's tip 5: the table ran 85 px past
           its box at 800 px): the base and a run's note go first, then when it started and what it cost -->
      <DataTable v-if="runs.runs.length" table-class="run-rows ruled" wide :columns="RUN_COLUMNS">
        <template #head>
          <tr>
            <th>Run</th>
            <th data-rank="3">Base</th>
            <th data-rank="2">Started</th>
            <th>Command</th>
            <th>Outcome</th>
            <th class="cost" data-rank="2">USD</th>
          </tr>
        </template>
        <tbody>
          <tr v-for="run in runs.runs" :key="`${run.knowledge_base}/${run.run_id}`" :data-run="`${run.knowledge_base}/${run.run_id}`">
            <td class="run-id">
              <RouterLink :to="{ name: 'run', params: { kb: run.knowledge_base, run: run.run_id } }">#{{ run.run_id }}</RouterLink>
            </td>
            <td data-rank="3"><KnowledgeBaseMark :kb="run.knowledge_base" /></td>
            <td class="when" data-rank="2"><HumanTime :at="run.started_at" /></td>
            <td>
              <span class="command" :title="run.command">{{ shortCommand(run.command) }}</span>
              <span v-if="run.note" class="run-note" data-rank="3">{{ run.note }}</span>
              <span v-if="run.batch_ids.length" class="batches">{{ counted(run.batch_ids.length, 'batch', 'batches') }}</span>
            </td>
            <!-- a run that recorded no end says so in the API's words, what that means in its card (line 1, 19 Nov) -->
            <td class="outcome">
              <HoverCard v-if="run.outcome_why" title="Outcome" :rows="[{ label: 'means', value: run.outcome_why }]">
                <span class="no-end">{{ run.outcome }}</span>
              </HoverCard>
              <template v-else>{{ run.outcome ?? '' }}</template>
            </td>
            <td class="cost" data-rank="2">{{ run.cost_usd === null ? '' : usd(run.cost_usd) }}</td>
          </tr>
        </tbody>
      </DataTable>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-md);
}

.not-listed {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
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

.run-id a {
  color: var(--color-accent);
  text-decoration: none;
}

.run-id a:hover {
  text-decoration: underline;
}

/* the number, the time and the cost never wrap; the command wraps only where it must */
.run-id,
.when,
.run-rows .cost {
  white-space: nowrap;
}

/* a word longer than the column, such as a work's key, breaks where it must rather than widening the table (27 Nov: a free
   work's key of 62 characters ran the table 35 px past its box at 800 px) */
.command {
  overflow-wrap: anywhere;
}

.when,
.run-rows .cost,
.run-note,
.batches {
  color: var(--color-text-secondary);
}

.run-rows .cost {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.run-note,
.batches {
  margin-left: var(--space-sm);
}
</style>
