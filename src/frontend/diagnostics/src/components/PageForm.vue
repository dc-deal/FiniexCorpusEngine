<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import DataTable from '@/components/base/DataTable.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import ReaderRuleList from '@/components/ReaderRuleList.vue'
import { readingCost } from '@/cost_format'
import type { IconName } from '@/icon_registry'
import type { PageForm, ShownVerdicts } from '@/types/api/page_types'

/**
 * A page's readings and verdicts in one form (issue #18, the operator's design): three tabs, Readings, Lab and Verdicts, each
 * with its count. Readings and Lab show one row per reading, time · model · cost · version · result · show, and a row folds
 * open to its verdicts in the same columns, a judge's and a person's alike, the result one word and its reason beside it as
 * the Verdicts tab parts them (47.a); Verdicts shows the verdicts as shown (decision 26):
 * those that apply now to the reading the analysis shows, the served one's from the page, a recalled one's from the recall,
 * a caption saying which, and the tab and its table framed as the analysis is while recalled; in focus as then, at the
 * recall's moment (29.d), and for a recalled trial none at all: the tab stays in its place, greyed, "–", its card saying
 * why, and the Lab opens (38.a). Newest first everywhere (31.a); a judge's word is the result that counts, its own word
 * struck beside it where code overruled it (32.a). The pattern is always the same: a
 * reading, then its verdicts; in the pipeline or in the Lab, the difference one flag. Each row says what it is in front, a
 * glyph and a word, the API's (the operator, 27 Nov: by indentation alone a reading and a judge were hard to tell apart);
 * the verdicts stay indented beneath their reading. Every word and count is the API's; the
 * keys and a reading's own bookkeeping stand in a row's card under the pointer, never in a column. The tabs are the
 * prompts view's own (one look, 221.a), and a tab click moves no control. The row the page shows while recalled is framed,
 * dashed, in whichever tab holds it (27.a).
 */
const props = defineProps<{
  form: PageForm
  // the judgement shown on the page, and the address that shows another (181.a)
  recallId: string | null
  recallTo: (recall: string) => RouteLocationRaw
  // the Verdicts tab while a reading or a judgement is recalled: the recall's own, the verdicts on the recalled reading
  recalledVerdicts?: ShownVerdicts | null
}>()

const emit = defineEmits<{ block: [id: string] }>()

type Tab = 'readings' | 'lab' | 'verdicts'
// the verdicts as shown (decision 26): the recall's while one is shown, else the served reading's
const verdicts = computed(() => props.recalledVerdicts ?? props.form.verdicts)
// a recalled trial has no verdicts (38.a): the tab cannot be the one shown, so the Lab is, where its row is framed
watch(() => verdicts.value.why_not, why => {
  if (why && picked.value === 'verdicts') picked.value = 'lab'
}, { immediate: true })
const picked = ref<Tab>('readings')
const tabs = computed(() => [
  { key: 'readings' as const, label: 'Readings', count: props.form.readings_count },
  { key: 'lab' as const, label: 'Lab', count: props.form.lab_count },
  { key: 'verdicts' as const, label: 'Verdicts', count: verdicts.value.count ?? '–' },
])
const holdsRecall = (rows: PageForm['readings']) => rows.some(reading => reading.recall === props.recallId
  || reading.verdicts.some(verdict => verdict.recall === props.recallId))
// a recalled judgement opens the tab and the reading that hold it, so the row it came from is seen
watch(() => props.recallId, recall => {
  if (recall && holdsRecall(props.form.lab)) picked.value = 'lab'
  else if (recall && holdsRecall(props.form.readings)) picked.value = 'readings'
}, { immediate: true })

// the readings folded open, in each tab apart (a pipeline reading stands in Readings and in the Lab, 37.a): the one shown,
// and the one holding a recalled judgement, opened again as a recall changes
const open = ref(new Set<string>())
const foldKey = (tab: Tab, key: string) => `${tab}:${key}`
watch(() => [props.form, props.recallId] as const, ([form]) => {
  const held = (tab: Tab, rows: PageForm['readings']) => rows
    .filter(reading => reading.shown || reading.verdicts.some(verdict => verdict.recall === props.recallId))
    .map(reading => foldKey(tab, reading.key))
  open.value = new Set([...open.value, ...held('readings', form.readings), ...held('lab', form.lab)])
}, { immediate: true })
function toggle(key: string): void {
  const next = new Set(open.value)
  const at = foldKey(picked.value, key)
  if (next.has(at)) next.delete(at)
  else next.add(at)
  open.value = next
}
const isOpen = (key: string) => open.value.has(foldKey(picked.value, key))

const rows = computed(() => (picked.value === 'lab' ? props.form.lab : props.form.readings))
const KIND_ICON: Record<'reading' | 'judge' | 'person' | 'review', IconName> = { reading: 'kind-reading', judge: 'kind-judge',
  person: 'kind-person', review: 'kind-review' }
const ICON: Record<'ok' | 'issue' | 'none' | 'note', IconName> = { ok: 'status-ok', issue: 'status-error', none: 'status-unknown',
  note: 'status-unknown' }
</script>

<template>
  <section class="page-form" data-part="page-form">
    <div class="tabs" role="tablist" aria-label="The page's readings and verdicts">
      <template v-for="one in tabs" :key="one.key">
        <!-- a recalled trial has no verdicts: the tab keeps its place, greyed, its card saying why (38.a) -->
        <HoverCard v-if="one.key === 'verdicts' && verdicts.why_not" title="Verdicts" :rows="[{ label: 'why not', value: verdicts.why_not }]">
          <AppButton size="compact" role="tab" aria-selected="false" disabled :data-tab="one.key" data-off="yes">
            {{ one.label }} <span class="tab-count">{{ one.count }}</span>
          </AppButton>
        </HoverCard>
        <AppButton
          v-else
          size="compact"
          role="tab"
          :aria-selected="picked === one.key ? 'true' : 'false'"
          :marked="picked === one.key"
          :data-tab="one.key"
          :class="{ overlay: one.key === 'verdicts' && verdicts.recalled }"
          :data-overlay="one.key === 'verdicts' && verdicts.recalled ? 'yes' : null"
          @click="picked = one.key"
        >
          {{ one.label }} <span class="tab-count">{{ one.count }}</span>
        </AppButton>
      </template>
    </div>

    <!-- Readings and Lab: one row per reading, folding open to its verdicts in the same columns -->
    <DataTable
      v-if="picked !== 'verdicts'"
      role="tabpanel"
      table-class="form-readings ruled"
      :columns="[{ width: '8rem' }, { width: '8rem' }, { width: '11rem' }, { width: '7rem' }, { width: '11rem' }, { width: '7.5rem' }, {},
                 { width: '7rem' }]"
      min-width="70rem"
      fixed
      :data-panel="picked"
    >
      <template #head>
        <tr>
          <th>Kind</th>
          <th>Time</th>
          <th>Model</th>
          <th>Cost</th>
          <th>Version</th>
          <th>Result</th>
          <th>Reason</th>
          <th>Show</th>
        </tr>
      </template>
      <tbody v-if="!rows.length">
        <tr><td colspan="8" class="none">none</td></tr>
      </tbody>
      <tbody v-for="reading in rows" :key="reading.key" :data-reading="reading.key" :class="{ shown: reading.shown }">
        <tr class="reading-row" :class="{ 'recalled-source': reading.recall && reading.recall === recallId }">
          <td class="kind-cell">
            <button
              type="button"
              class="fold-mark"
              :aria-expanded="isOpen(reading.key) ? 'true' : 'false'"
              :disabled="!reading.verdicts.length"
              :aria-label="isOpen(reading.key) ? 'fold its verdicts' : 'open its verdicts'"
              data-part="fold-reading"
              @click="toggle(reading.key)"
            >{{ reading.verdicts.length ? (isOpen(reading.key) ? '▾' : '▸') : '·' }}</button>
            <span class="kind" :data-kind="reading.kind_said"><AppIcon :name="KIND_ICON[reading.kind_said]" /> {{ reading.kind_said }}</span>
          </td>
          <td class="time-cell"><HoverCard title="Reading" :rows="reading.hover"><HumanTime :at="reading.time" /></HoverCard></td>
          <td>{{ reading.model }}</td>
          <td class="secondary">{{ readingCost(reading.cost_usd ?? null) }}</td>
          <td>
            <RouterLink v-if="reading.version" class="version" :to="{ name: 'prompts', query: { version: reading.version } }">{{ reading.version }}</RouterLink>
          </td>
          <td class="result" :class="reading.result_state" :data-result="reading.result_state">
            <AppIcon :name="ICON[reading.result_state]" /> {{ reading.result_said }}
          </td>
          <td class="reason" data-part="reason">
            {{ reading.reason_said ?? '' }}
            <span v-if="reading.promoted_said" class="promoted" data-part="promoted">· {{ reading.promoted_said }}</span>
          </td>
          <td>
            <span v-if="reading.served_said" class="shown-mark" data-part="shown">● {{ reading.served_said }}</span>
            <span v-else-if="reading.recall && reading.recall === recallId" class="on-page" data-part="recalled-here"><AppIcon name="recalled" /> on the page</span>
            <!-- one active way into a reading (42.a): where a judge beneath it shows it with its findings, its own show is greyed -->
            <HoverCard v-else-if="reading.show_why_not" title="Show" :rows="[{ label: 'why not', value: reading.show_why_not }]">
              <span class="show-off" data-part="show-reading-off"><AppButton variant="link" disabled>show</AppButton></span>
            </HoverCard>
            <RouterLink v-else-if="reading.recall" :to="recallTo(reading.recall)" data-part="show-reading">show</RouterLink>
          </td>
        </tr>
        <template v-if="isOpen(reading.key)">
          <template v-for="(verdict, at) in reading.verdicts" :key="at">
            <tr
              class="verdict-row"
              :class="[verdict.kind, { standing: verdict.standing, 'recalled-source': verdict.recall && verdict.recall === recallId }]"
              :data-verdict="`${reading.key}/${at}`"
            >
              <td class="indented">
                <span class="kind" :data-kind="verdict.kind_said"><AppIcon :name="KIND_ICON[verdict.kind_said]" /> {{ verdict.kind_said }}</span>
              </td>
              <td>
                <HoverCard :title="verdict.kind === 'judge' ? 'Judgement' : 'Verdict'" :rows="verdict.hover">
                  <HumanTime v-if="verdict.time" :at="verdict.time" /><span v-else>no time</span>
                </HoverCard>
              </td>
              <td>{{ verdict.model }}</td>
              <td class="secondary">{{ verdict.kind === 'judge' ? readingCost(verdict.cost_usd ?? null) : '' }}</td>
              <td>
                <RouterLink v-if="verdict.version" class="version" :to="{ name: 'prompts', query: { version: verdict.version } }">{{ verdict.version }}</RouterLink>
                <span v-if="verdict.version_said" class="secondary">{{ verdict.version ? ' · ' : '' }}{{ verdict.version_said }}</span>
              </td>
              <td class="result" :class="verdict.state" :data-result="verdict.state">
                <AppIcon :name="ICON[verdict.state]" /> {{ verdict.verdict_said }}
                <s v-if="verdict.overruled" class="overruled" data-part="overruled">{{ verdict.overruled }}</s>
              </td>
              <td class="reason" data-part="reason">{{ verdict.reason_said ?? '' }}</td>
              <td>
                <span v-if="verdict.recall && verdict.recall === recallId" class="on-page" data-part="recalled-here"><AppIcon name="recalled" /> on the page</span>
                <!-- a show that would change nothing stays in place, greyed, its card saying why (decision 25) -->
                <HoverCard v-else-if="verdict.show_why_not" title="Show" :rows="[{ label: 'why not', value: verdict.show_why_not }]">
                  <span class="show-off" data-part="show-off"><AppButton variant="link" disabled>show</AppButton></span>
                </HoverCard>
                <RouterLink v-else-if="verdict.recall" :to="recallTo(verdict.recall)" data-part="recall">show</RouterLink>
                <AppButton v-else-if="verdict.block" variant="link" :data-jump="verdict.block" @click="emit('block', verdict.block)">{{ verdict.block }}</AppButton>
              </td>
            </tr>
            <!-- the rules a judge proposed for the reader (202.a), right beneath its verdict, read-only -->
            <tr v-if="verdict.rules?.length" class="verdict-rules" :data-rules="`${reading.key}/${at}`">
              <td colspan="8"><ReaderRuleList :rules="verdict.rules" /></td>
            </tr>
          </template>
        </template>
      </tbody>
    </DataTable>

    <!-- Verdicts: the verdicts as shown, on the reading the analysis shows, its caption saying which (decision 26) -->
    <div v-else class="verdicts-panel" :class="{ overlay: verdicts.recalled }" data-part="verdicts-panel">
    <p class="verdicts-said" :class="{ recalled: verdicts.recalled }" data-part="verdicts-said">
      <AppIcon v-if="verdicts.recalled" name="recalled" /> {{ verdicts.said }}
      <HumanTime v-if="verdicts.said_at" :at="verdicts.said_at" />
    </p>
    <DataTable
      role="tabpanel"
      table-class="form-verdicts ruled"
      :columns="[{ width: '7.5rem' }, { width: '8rem' }, { width: '10rem' }, { width: '7rem' }, { width: '11rem' }, { width: '11rem' }, {},
                 { width: '16rem' }]"
      min-width="78rem"
      fixed
      data-panel="verdicts"
    >
      <template #head>
        <tr>
          <th>Kind</th>
          <th>Standing</th>
          <th>Time</th>
          <th>Verdict</th>
          <th>Reason</th>
          <th>About</th>
          <th>Judge</th>
          <th>By</th>
        </tr>
      </template>
      <tbody>
        <tr v-if="!verdicts.rows.length"><td colspan="8" class="none">none</td></tr>
        <tr
          v-for="(row, at) in verdicts.rows"
          :key="at"
          class="verdict-line"
          :class="{ history: !row.standing, 'recalled-source': row.recall && row.recall === recallId }"
          :data-verdict-row="at"
          :data-standing="row.standing ? 'true' : 'false'"
        >
          <td><span class="kind" :data-kind="row.kind_said"><AppIcon :name="KIND_ICON[row.kind_said]" /> {{ row.kind_said }}</span></td>
          <td><span class="standing-mark" :data-standing-said="row.standing_said">{{ row.recalled ? '↺' : row.standing ? '●' : '○' }} {{ row.standing_said }}</span></td>
          <td><HoverCard :title="row.kind === 'judge' ? 'Judgement' : 'Verdict'" :rows="row.hover"><HumanTime v-if="row.time" :at="row.time" /><span v-else>no time</span></HoverCard></td>
          <td class="result" :class="row.state" :data-result="row.state">
            <AppIcon :name="ICON[row.state]" /> {{ row.verdict }}
            <s v-if="row.overruled" class="overruled" data-part="overruled">{{ row.overruled }}</s>
          </td>
          <td>{{ row.reason ?? '' }}</td>
          <td>{{ row.about }}</td>
          <td :class="{ secondary: row.kind === 'judge' }" data-part="judge-said">{{ row.judge_said }}</td>
          <td class="secondary">{{ row.who_said }}</td>
        </tr>
      </tbody>
    </DataTable>
    </div>
  </section>
</template>

<style scoped>
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}

.tab-count,
.secondary,
.none {
  color: var(--color-text-secondary);
}

/* what a row is, in front of it: a glyph and a word, in the ink of the row */
.kind {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  white-space: nowrap;
}

.promoted {
  color: var(--color-text-secondary);
}

/* the row a recall came from (181.a): the overlay's role, always dashed, its "on the page" in that role with its glyph */
tr.recalled-source {
  outline: 1px dashed var(--color-annotation);
  outline-offset: -1px;
}

.on-page {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-annotation);
  white-space: nowrap;
}

/* the fold's mark, a control in its own fixed place at the row's start, so the kinds stand in one column */
.fold-mark {
  width: 1.5em;
  border: none;
  background: none;
  color: var(--color-accent);
  cursor: pointer;
  font: inherit;
}

.fold-mark:disabled {
  color: var(--color-text-secondary);
  cursor: default;
}

.kind-cell,
.time-cell {
  white-space: nowrap;
}

/* a verdict stands one step in, beneath the reading it judged, in the same columns */
.indented {
  padding-left: calc(1.5em + var(--space-xs));
}

.result {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.result.ok {
  color: var(--color-positive);
}

.result.issue {
  color: var(--color-error);
}

.result.none,
.result.note {
  color: var(--color-text-secondary);
}

.version {
  color: var(--color-accent);
  text-decoration: none;
}

.version:hover {
  text-decoration: underline;
}

/* the reading the page shows: its row marked by a glyph and a word */
.shown-mark,
.standing-mark {
  white-space: nowrap;
}

/* the verdicts as shown say which reading they are on; while it is recalled, in the overlay's role with its glyph, and
   the tab and its table framed, dashed, as the analysis is (decision 26) */
.verdicts-said {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-xs);
}

.verdicts-said.recalled {
  color: var(--color-annotation);
}

.verdicts-panel.overlay,
.tabs .overlay {
  outline: 2px dashed var(--color-annotation);
  outline-offset: 2px;
}

/* a judge's own word where code struck the findings it rested on (32.a): beside the result that counts, struck, quieter */
.overruled {
  color: var(--color-text-secondary);
  margin-left: var(--space-xs);
}

/* a verdict no longer standing: quieter, still readable */
.verdict-line.history {
  color: var(--color-text-secondary);
}

.verdict-line.history .result {
  opacity: 0.8;
}
</style>
