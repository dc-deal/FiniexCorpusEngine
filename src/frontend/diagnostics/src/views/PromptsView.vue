<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import DataTable from '@/components/base/DataTable.vue'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import { usePromptsStore } from '@/stores/prompts_store'
import type { PromptFile, PromptVersion } from '@/types/api/prompts_types'

/**
 * Every version of the instructions a model is given (the operator's 148.a), by what each file is: one tab per part of the
 * registry (the reader's rules, its format, the judge, the class check), so a version of two files, such as page/1, stands
 * in two tabs. In a tab, one row per version, folded: its title, state, model, the day it was frozen, whether its sha256 is
 * the frozen one, and why it was made. Opened, a row shows its change from the version before it, the changed words
 * marked, or its whole text. A page's judge version links here with `?version=`, which opens that version's tab and row.
 * Every figure, label and diff is the API's.
 */
const store = usePromptsStore()
const { prompts, error } = storeToRefs(store)
const route = useRoute()

interface Row {
  key: string
  version: PromptVersion
  file: PromptFile
}

// what a file is when the registry names no part for it
const OTHER = 'other'

const chosen = computed(() => (typeof route.query.version === 'string' ? route.query.version : null))
const tabs = computed(() => {
  const list = prompts.value
  if (!list) return []
  const named = list.parts.map(part => ({ key: part.key, label: part.label, about: part.about }))
  const unnamed = list.versions.some(version => version.files.some(file => !file.part))
  return unnamed ? [...named, { key: OTHER, label: 'Other', about: 'files the registry names no part for' }] : named
})

const picked = ref<string | null>(null)
// the tab picked, else the one holding the version a link asked for, else the first
const tab = computed(() => {
  if (picked.value) return picked.value
  const asked = prompts.value?.versions.find(version => version.version === chosen.value)
  return asked?.files[0]?.part ?? tabs.value[0]?.key ?? null
})

function rowsOf(part: string): Row[] {
  return (prompts.value?.versions ?? []).flatMap(version => version.files
    .filter(file => (file.part ?? OTHER) === part)
    .map(file => ({ key: `${version.version}|${file.path}`, version, file })))
}

const rows = computed(() => (tab.value ? rowsOf(tab.value) : []))
const current = computed(() => tabs.value.find(one => one.key === tab.value) ?? null)
// the rows open; every row starts folded, but those of a version a link asked for
const opened = ref<Set<string>>(new Set())
// the text a row shows when opened: its change from the version before where it has one, else its whole text
const showing = ref<Record<string, 'change' | 'text'>>({})

function toggle(row: Row): void {
  const next = new Set(opened.value)
  if (!next.delete(row.key)) next.add(row.key)
  opened.value = next
}

function mode(row: Row): 'change' | 'text' {
  return showing.value[row.key] ?? (row.file.diff ? 'change' : 'text')
}

onMounted(() => {
  void store.loadPrompts()
})

// the version a link asked for opens in its own tab and comes into view once the list stands
watch([prompts, chosen], async ([list, wanted]) => {
  if (!list || !wanted) return
  picked.value = null
  const keys = list.versions.filter(version => version.version === wanted).flatMap(version => version.files.map(file => `${version.version}|${file.path}`))
  opened.value = new Set([...opened.value, ...keys])
  await nextTick()
  document.querySelector(`[data-version="${CSS.escape(wanted)}"]`)?.scrollIntoView?.({ block: 'start' })
}, { immediate: true })
</script>

<template>
  <section class="prompts-view">
    <h1 class="view-title">Prompts</h1>
    <ApiFailure v-if="error" :error="error" @retry="store.loadPrompts()" />
    <LoadingLine v-else-if="!prompts" />
    <template v-else>
      <p v-if="prompts.about" class="about">{{ prompts.about }}</p>
      <div class="tabs" role="tablist" aria-label="Parts of the instructions">
        <AppButton
          v-for="one in tabs"
          :key="one.key"
          size="compact"
          role="tab"
          :aria-selected="tab === one.key ? 'true' : 'false'"
          :marked="tab === one.key"
          :data-tab="one.key"
          @click="picked = one.key"
        >
          {{ one.label }} <span class="tab-count">{{ rowsOf(one.key).length }}</span>
        </AppButton>
      </div>
      <p v-if="current?.about" class="part-about" data-part="part-about">{{ current.about }}</p>
      <DataTable role="tabpanel" table-class="versions ruled" fixed>
        <template #head>
          <tr>
            <th class="col-version">Version</th>
            <th class="col-title">Title</th>
            <th class="col-state">State</th>
            <th class="col-model">Model</th>
            <th class="col-frozen">Frozen</th>
            <th class="col-hash">sha256</th>
            <th>Why</th>
          </tr>
        </template>
        <tbody
          v-for="row in rows"
          :key="row.key"
          class="version"
          :class="{ chosen: chosen === row.version.version, open: opened.has(row.key) }"
          :data-version="row.version.version"
        >
          <tr class="version-row" @click="toggle(row)">
            <td class="version-name">
              <AppButton variant="link" :aria-expanded="opened.has(row.key) ? 'true' : 'false'">{{ row.version.version }}</AppButton>
            </td>
            <td>{{ row.version.title ?? '' }}</td>
            <td><span class="badge" :class="row.version.state" data-part="state">{{ row.version.state }}</span></td>
            <td class="secondary">{{ row.version.model ?? '' }}</td>
            <td class="secondary"><HumanTime :at="row.version.frozen_on" /></td>
            <td :title="row.file.sha256">
              <span v-if="row.file.frozen_sha256 === row.file.sha256" class="hash-same" data-part="frozen"><AppIcon name="status-ok" /> as frozen</span>
              <span v-else-if="row.file.frozen_sha256" class="hash-differs" data-part="frozen"><AppIcon name="status-error" /> differs</span>
              <span v-else class="secondary" data-part="frozen">not frozen</span>
            </td>
            <td class="why-cell" :title="row.version.why ?? ''"><div class="why-line">{{ row.version.why ?? '' }}</div></td>
          </tr>
          <tr v-if="opened.has(row.key)" class="version-detail">
            <td colspan="7">
              <p v-if="row.version.why" class="why" data-part="why">{{ row.version.why }}</p>
              <p class="file-head">
                <span class="path">{{ row.file.path }}</span>
                <span class="hash" :title="row.file.sha256">sha256 {{ row.file.sha256.slice(0, 16) }}</span>
                <span v-if="row.file.frozen_sha256 && row.file.frozen_sha256 !== row.file.sha256" class="hash-differs">
                  frozen as {{ row.file.frozen_sha256.slice(0, 16) }}
                </span>
                <span v-if="row.file.diff" class="switch">
                  <AppButton size="compact" :active="mode(row) === 'change'" @click="showing[row.key] = 'change'">
                    change from {{ row.version.previous }}
                  </AppButton>
                  <AppButton size="compact" :active="mode(row) === 'text'" @click="showing[row.key] = 'text'">text</AppButton>
                </span>
              </p>
              <!-- a line kept, added or removed, its prefix the first channel; a replaced line's changed words marked -->
              <pre v-if="row.file.diff && mode(row) === 'change'" class="diff" data-part="diff"><span
                v-for="(line, at) in row.file.diff"
                :key="at"
                class="diff-line"
                :class="line.kind"
              ><span class="prefix">{{ line.kind === 'added' ? '+ ' : line.kind === 'removed' ? '− ' : '  ' }}</span><template v-if="line.parts"><span
                v-for="(piece, p) in line.parts"
                :key="p"
                :class="{ changed: piece.changed }"
              >{{ piece.text }}</span></template><template v-else>{{ line.text }}</template>
</span></pre>
              <pre v-else class="prompt-text" data-part="text">{{ row.file.text }}</pre>
            </td>
          </tr>
        </tbody>
      </DataTable>
    </template>
  </section>
</template>

<style scoped>
.view-title {
  margin-bottom: var(--space-sm);
}

.about,
.part-about,
.secondary,
.why,
.path,
.hash,
.hash-same,
.tab-count {
  color: var(--color-text-secondary);
}

.about {
  max-width: 72rem;
  margin-bottom: var(--space-md);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-bottom: var(--space-xs);
}

.part-about {
  margin-bottom: var(--space-sm);
}

/* a fixed layout: the columns take the widths below and the why the rest, so an opened version's long prompt lines wrap
   inside the window instead of widening the table past it (measured: 3,575 px in the automatic layout) */

.col-version {
  width: 8rem;
}

.col-title {
  width: 20rem;
}

.col-state {
  width: 7rem;
}

.col-model {
  width: 11rem;
}

.col-frozen {
  width: 7rem;
}

.col-hash {
  width: 8rem;
}

.versions th {
  text-align: left;
  font-weight: normal;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.versions th,
.versions td {
  padding: 2px var(--space-md) 2px 0;
  vertical-align: baseline;
}

.version-row {
  cursor: pointer;
}

.version-row:hover > td {
  background-color: var(--color-bg-hover);
}

.version-name {
  white-space: nowrap;
}

.version-name::before {
  content: '▸ ';
  color: var(--color-text-secondary);
}

.version.open .version-name::before {
  content: '▾ ';
}

/* the version a page's link asked for */
.version.chosen > tr > td:first-child {
  box-shadow: inset 2px 0 0 var(--color-accent);
  padding-left: var(--space-xs);
}

/* folded, the why is one line, whole in its hover and in the opened row */
.why-cell {
  color: var(--color-text-secondary);
}

.why-line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 0 var(--space-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.badge.active {
  color: var(--color-text-primary);
}

.version-detail > td {
  padding: var(--space-xs) 0 var(--space-sm) var(--space-md);
}

.why {
  margin-bottom: var(--space-xs);
  max-width: 72rem;
}

.file-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
}

/* the hash's state; named apart from a diff's `same` line, which once took this rule and stopped wrapping */
.hash-same,
.hash-differs {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  white-space: nowrap;
}

.hash-differs {
  color: var(--color-error);
}

.switch {
  display: inline-flex;
  gap: var(--space-xs);
}

.diff,
.prompt-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: var(--space-xs);
  max-height: 32rem;
  overflow-y: auto;
}

.diff-line {
  display: block;
}

.diff-line.same {
  color: var(--color-text-secondary);
}

/* the prefix carries add and remove; a faint tint repeats it, and the changed words alone are marked strongly */
.diff-line.added {
  background-color: color-mix(in srgb, var(--color-positive) 10%, transparent);
}

.diff-line.removed {
  background-color: color-mix(in srgb, var(--color-negative) 10%, transparent);
  color: var(--color-text-secondary);
}

.diff-line.added .changed {
  background-color: color-mix(in srgb, var(--color-positive) 35%, transparent);
  color: var(--color-text-primary);
}

.diff-line.removed .changed {
  text-decoration: line-through;
}
</style>
