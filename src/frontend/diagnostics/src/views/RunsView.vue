<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import { usd } from '@/cost_format'
import { shortCommand } from '@/run_format'
import { useRunsStore } from '@/stores/runs_store'

/**
 * Every run of the pipeline, newest first, both knowledge bases together, one line each (21.a): what was run, when, how it
 * ended, what it cost, the batches it sent. A run opens its own page, the place of a replay's trace in the review demo
 * (69.a). A base whose runs are not listed says why: not served, or no pipeline database on this machine.
 */
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
      <DataTable v-if="runs.runs.length" table-class="run-rows ruled" wide>
        <template #head>
          <tr>
            <th>Run</th>
            <th>Base</th>
            <th>started</th>
            <th>command</th>
            <th>outcome</th>
            <th class="cost">USD</th>
          </tr>
        </template>
        <tbody>
          <tr v-for="run in runs.runs" :key="`${run.knowledge_base}/${run.run_id}`" :data-run="`${run.knowledge_base}/${run.run_id}`">
            <td class="run-id">
              <RouterLink :to="{ name: 'run', params: { kb: run.knowledge_base, run: run.run_id } }">#{{ run.run_id }}</RouterLink>
            </td>
            <td><KnowledgeBaseMark :kb="run.knowledge_base" /></td>
            <td class="when"><HumanTime :at="run.started_at" /></td>
            <td>
              <span class="command" :title="run.command">{{ shortCommand(run.command) }}</span>
              <span v-if="run.note" class="run-note">{{ run.note }}</span>
              <span v-if="run.batch_ids.length" class="batches">{{ run.batch_ids.length }} {{ run.batch_ids.length === 1 ? 'batch' : 'batches' }}</span>
            </td>
            <td>{{ run.outcome ?? '' }}</td>
            <td class="cost">{{ run.cost_usd === null ? '' : usd(run.cost_usd) }}</td>
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
