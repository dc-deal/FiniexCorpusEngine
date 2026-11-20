<script setup lang="ts" generic="R extends CardRow">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import type { CardRow } from '@/components/base/card_row'
import { HOVER_DELAY } from '@/hover_delay'

/**
 * Data under the pointer (decision 179): a small card that holds data only, rows of a label and a value, its title naming
 * what it is about, where a browser tooltip stood. It opens on the keyboard's focus at once and on the pointer once it has
 * rested there (`HOVER_DELAY`, the operator's C1.b), so a pointer passing over opens nothing, and it stands fixed
 * to the window, so a table's own scroll box never cuts it; beneath its host, or above it where the window's foot would
 * cut it (found on SR 11-7 p. 5, a note's marker at the window's foot, 11 Nov). An empty value leaves its row out. A view may
 * draw a row's label and value itself through the `label` and `value` slots, a level's number before its word and its meter
 * beside its words (the operator, 20 Nov: "the card follows the colours"); a row may carry what that needs beside its label
 * and value. Rows of one group stand together, a thin rule and the next group's caption between them (`CardRow`).
 */
const props = defineProps<{
  title: string
  rows: R[]
}>()

defineSlots<{
  default?: () => unknown
  label?: (props: { row: R }) => unknown
  value?: (props: { row: R }) => unknown
}>()

const shown = ref(false)
const place = ref<{ top: string, left: string }>({ top: '0px', left: '0px' })
const host = ref<HTMLElement | null>(null)
const card = ref<HTMLElement | null>(null)

async function show(): Promise<void> {
  const box = host.value?.getBoundingClientRect()
  if (!box) {
    shown.value = true
    return
  }
  const width = Math.min(448, window.innerWidth - 16)
  const left = `${Math.max(8, Math.min(box.left, window.innerWidth - width - 8))}px`
  place.value = { top: `${box.bottom + 4}px`, left }
  shown.value = true
  // measured once drawn: a card that would run past the window's foot opens above its host, where there is room
  await nextTick()
  const height = card.value?.getBoundingClientRect().height ?? 0
  if (box.bottom + 4 + height > window.innerHeight - 8 && box.top - 4 - height >= 8) {
    place.value = { top: `${box.top - 4 - height}px`, left }
  }
}

// the pointer's wait before the card opens, cancelled when the pointer leaves first
let waiting: ReturnType<typeof setTimeout> | undefined

function onPointer(): void {
  clearTimeout(waiting)
  if (HOVER_DELAY.pointerMs <= 0) {
    void show()
    return
  }
  waiting = setTimeout(() => void show(), HOVER_DELAY.pointerMs)
}

function hide(): void {
  clearTimeout(waiting)
  shown.value = false
}

onBeforeUnmount(() => clearTimeout(waiting))

const filled = computed(() => props.rows.filter(row => row.value))

/** Whether a shown row opens a new group, below a rule: never the first. */
function opensGroup(index: number): boolean {
  return index > 0 && filled.value[index]!.group !== filled.value[index - 1]!.group
}
</script>

<template>
  <span ref="host" class="hover-card-host" tabindex="0" @mouseenter="onPointer" @mouseleave="hide" @focusin="show" @focusout="hide">
    <slot />
    <span v-if="shown" ref="card" class="hover-card" role="tooltip" data-part="hover-card" :style="place">
      <span class="card-title">{{ title }}</span>
      <template v-for="(row, index) in filled" :key="row.label">
        <template v-if="opensGroup(index)">
          <span class="card-rule" data-part="card-rule" />
          <span v-if="row.caption" class="card-caption">{{ row.caption }}</span>
        </template>
        <span class="card-row" :data-row="row.label" :data-indent="row.indent || undefined">
          <span class="card-label"><slot name="label" :row="row">{{ row.label }}</slot></span>
          <span class="card-value"><slot name="value" :row="row">{{ row.value }}</slot></span>
        </span>
      </template>
    </span>
  </span>
</template>

<style scoped>
.hover-card-host {
  display: inline-flex;
  align-items: center;
}

.hover-card {
  position: fixed;
  z-index: 20;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 2px var(--space-sm);
  max-width: min(28rem, calc(100vw - 1rem));
  padding: var(--space-xs) var(--space-sm);
  background-color: var(--color-bg-overlay);
  border: 1px solid var(--color-border-overlay);
  box-shadow: var(--shadow-overlay);
  border-radius: 4px;
  font-style: normal;
  font-weight: normal;
  color: var(--color-text-primary);
  white-space: normal;
  text-decoration: none;
  /* it holds data only, nothing to click: a pointer passes through it to what it covers, so a card left open over a row
     never takes the click meant for what lies beneath (found 12 Nov: a card over the Issues' fold held a click) */
  pointer-events: none;
}

.card-title {
  grid-column: 1 / -1;
  font-weight: bold;
}

.card-row {
  display: contents;
}

.card-label {
  color: var(--color-text-secondary);
}

/* a group apart: a thin rule across the card, the group's caption beneath it, its rows a step in where they are a part */
.card-rule {
  grid-column: 1 / -1;
  margin: 2px 0;
  border-top: 1px solid var(--color-border-overlay);
}

.card-caption {
  grid-column: 1 / -1;
  color: var(--color-text-secondary);
}

.card-row[data-indent] .card-label {
  padding-left: var(--indent-step);
}
</style>
