<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore, type FoldName } from '@/stores/settings_store'

/**
 * The one fold of every view (decision 179, the operator: "the same style and indentation concept"): a row with its mark and its
 * title, the content one indent step (`--indent-step`) right of the title at every depth, so two folds at one depth share
 * one x. A count stands apart from the name ("Lab · 3 judgements tried beside the pipeline"), never run into it, so it does
 * not read as a numbering. A fold may be remembered in the reader's settings (`remember`), or opened by its view (`open`),
 * as when it holds what the view points to. A row of a grid whose columns must align at every depth (a chapter, a
 * reading) sets `markInTitle`: the mark then stands in its title cell, and `flat` leaves the content's indent to its rows.
 */
const props = withDefaults(defineProps<{
  title?: string
  count?: string | null
  // opened by the view, whatever the reader last chose
  open?: boolean
  remember?: FoldName
  markInTitle?: boolean
  flat?: boolean
}>(), { title: '', count: null, open: false, remember: undefined, markInTitle: false, flat: false })

const emit = defineEmits<{ toggle: [open: boolean] }>()
// the settings are asked only by a fold that is remembered, so a fold needs no store where nothing is kept
const settingsStore = props.remember ? useSettingsStore() : null

const isOpen = computed(() => props.open || (props.remember && settingsStore ? settingsStore.settings.foldsOpen[props.remember] === true : false))

function onToggle(event: Event): void {
  const opened = (event.target as HTMLDetailsElement).open
  if (props.remember && settingsStore) settingsStore.setFoldOpen(props.remember, opened)
  emit('toggle', opened)
}
</script>

<template>
  <details class="fold" :class="{ flat, 'mark-in-title': markInTitle }" :open="isOpen" :data-fold="remember ?? null" @toggle="onToggle">
    <summary class="fold-row">
      <span v-if="!markInTitle" class="fold-mark" aria-hidden="true" />
      <span class="fold-title">
        <slot name="title">{{ title }}<span v-if="count" class="fold-count" data-part="fold-count">{{ ` · ${count}` }}</span></slot>
      </span>
    </summary>
    <div class="fold-body">
      <slot />
    </div>
  </details>
</template>

<style scoped>
.fold-row {
  display: flex;
  align-items: baseline;
  list-style: none;
  cursor: pointer;
}

.fold-row::-webkit-details-marker {
  display: none;
}

/* the mark takes one step; the title starts after it */
.fold-mark {
  flex: 0 0 var(--indent-step);
}

.fold-mark::before,
.mark-in-title :deep(.fold-inline-mark)::before {
  content: '▸';
  color: var(--color-text-secondary);
}

/* in a grid row's title cell the mark takes the same one step, so a title stands where a fold's own would */
.mark-in-title :deep(.fold-inline-mark) {
  display: inline-block;
  width: var(--indent-step);
}

.fold[open] > .fold-row > .fold-mark::before,
.fold.mark-in-title[open] > .fold-row :deep(.fold-inline-mark)::before {
  content: '▾';
}

.fold-title {
  flex: 1 1 auto;
  min-width: 0;
}

.fold-count {
  color: var(--color-text-secondary);
}

/* the content one step right of the title: the mark's step plus one */
.fold-body {
  padding-left: calc(2 * var(--indent-step));
}

.fold.flat > .fold-body {
  padding-left: 0;
}
</style>
