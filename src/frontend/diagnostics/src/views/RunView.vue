<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import DetailList from '@/components/base/DetailList.vue'
import { useRunsStore } from '@/stores/runs_store'
import { useViewName } from '@/view_name'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One run whole (21.a): the command as it was given, when it ran and how it ended, the code it ran (its commit, and
 * whether the tree held uncommitted changes), its cost by provider, its batches, and the pages it chose a reading for,
 * each opening its page view. For the review demo (69.a) this is the trace of the replay run.
 */
const props = defineProps<{
  kb: KnowledgeBase
  run: number
}>()

const store = useRunsStore()
const { runError } = storeToRefs(store)

watch(() => [props.kb, props.run] as const, ([kb, run]) => {
  void store.loadRun(kb, run)
}, { immediate: true })

const shown = computed(() => store.runOf(props.kb, props.run))
useViewName(() => (shown.value ? `Run #${shown.value.run_id}` : null))
</script>

<template>
  <section class="run-view">
    <p class="trail"><RouterLink to="/runs">Runs</RouterLink></p>
    <ApiFailure v-if="runError" :error="runError" @retry="store.loadRun(kb, run)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <h1 class="view-title">Run #{{ shown.run_id }} <KnowledgeBaseMark :kb="shown.knowledge_base" /></h1>
      <pre class="command">{{ shown.command }}</pre>
      <DetailList class="facts">
        <dt>started</dt>
        <dd><HumanTime :at="shown.started_at" /></dd>
        <dt>ended</dt>
        <dd><HumanTime v-if="shown.ended_at" :at="shown.ended_at" /><template v-else>not recorded</template></dd>
        <dt>outcome</dt>
        <dd>{{ shown.outcome ?? 'not recorded' }}</dd>
        <dt>code</dt>
        <dd v-if="shown.code_commit" data-fact="code">
          <span class="hash" :title="shown.code_commit">{{ shown.code_commit.slice(0, 12) }}</span>
          <template v-if="shown.code_clean === false"> · with uncommitted changes</template>
          <template v-else-if="shown.code_clean"> · clean</template>
          <span v-if="shown.code_sha256" class="hash secondary" :title="shown.code_sha256"> · code sha256 {{ shown.code_sha256.slice(0, 12) }}</span>
        </dd>
        <dd v-else>not recorded</dd>
        <dt>cost</dt>
        <dd data-fact="cost">
          {{ shown.cost_usd === null ? 'not recorded' : `${shown.cost_usd.toFixed(4)} USD` }}
          <span v-for="(usd, provider) in shown.cost_by_provider ?? {}" :key="provider" class="provider" :data-provider="provider">
            · {{ provider }} {{ usd.toFixed(4) }}
          </span>
        </dd>
        <template v-if="shown.batch_ids.length">
          <dt>batches</dt>
          <dd class="hash">{{ shown.batch_ids.join(', ') }}</dd>
        </template>
        <template v-if="shown.note">
          <dt>note</dt>
          <dd>{{ shown.note }}</dd>
        </template>
      </DetailList>

      <h2 class="chose-title">Pages it chose a reading for</h2>
      <p v-if="!shown.chose.length" class="none">This run chose no reading.</p>
      <DataTable v-else table-class="chose-rows ruled" wide>
        <template #head>
          <tr>
            <th>Work</th>
            <th>PDF page</th>
            <th>why</th>
            <th>chosen</th>
          </tr>
        </template>
        <tbody>
          <tr v-for="(page, at) in shown.chose" :key="`${page.file}/${page.pdf_page}`" :data-page="page.pdf_page">
            <!-- a work's title once, where its pages begin: a run may choose dozens of pages of one book -->
            <td class="work">{{ at === 0 || shown.chose[at - 1].title !== page.title ? page.title : '' }}</td>
            <td>
              <RouterLink v-if="page.source_id" :to="{ name: 'page', params: { kb: shown.knowledge_base, work: page.source_id, page: page.pdf_page } }">
                p. {{ page.pdf_page }}
              </RouterLink>
              <template v-else>p. {{ page.pdf_page }}</template>
            </td>
            <td>{{ page.why }}</td>
            <td class="when"><HumanTime :at="page.chosen_at" /></td>
          </tr>
        </tbody>
      </DataTable>
    </template>
  </section>
</template>

<style scoped>
.trail a,
.chose-rows a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover,
.chose-rows a:hover {
  text-decoration: underline;
}

.view-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.command {
  white-space: pre-wrap;
  word-break: break-all;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: var(--color-bg-surface);
  margin-bottom: var(--space-md);
}

.facts {
  margin-bottom: var(--space-lg);
}

.secondary,
.provider,
.none,
.when {
  color: var(--color-text-secondary);
}

.hash {
  word-break: break-all;
}

.chose-title {
  margin-bottom: var(--space-sm);
}

.chose-rows th {
  font-weight: normal;
  text-align: left;
  color: var(--color-text-secondary);
  padding: 0 var(--space-sm) var(--space-xs) 0;
  white-space: nowrap;
}

.chose-rows .when {
  white-space: nowrap;
}

.chose-rows td {
  padding: 2px var(--space-sm) 2px 0;
  vertical-align: top;
}
</style>
