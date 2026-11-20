<script setup lang="ts">
import { autoUpdate, computePosition, flip, hide as hidden, offset, shift, size } from '@floating-ui/dom'
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import type { CardRow } from '@/components/base/card_row'
import { HOVER_DELAY } from '@/hover_delay'

/**
 * Data under the pointer (decision 179): a small card that holds data only, rows of a label and a value, its title naming
 * what it is about, where a browser tooltip stood. It opens on the keyboard's focus at once and on the pointer once it has
 * rested there (`HOVER_DELAY`, the operator's C1.b), so a pointer passing over opens nothing. An empty value leaves its row
 * out; rows of one group stand together, a thin rule and the next group's caption between them (`CardRow`). A view may set
 * its own block before the rows (`lead`): a ladder's levels, each its number, meter, share and words (the operator, 20 Nov).
 *
 * It stands wholly inside the window, always (the operator, 20 Nov: "denk auch daran dass tooltips immer im Bild sein
 * müssen"), placed by Floating UI, which Reka UI's own popovers use: fixed to the window, so a table's scroll box never cuts
 * it; beneath its host, above it where the room beneath is short and the room above is enough (`flip`), shifted to keep
 * within the window's sides (`shift`), and where it fits neither, on the side with more room (`bestFit`), as tall as that
 * room and scrolling inside (`size`). It is placed again whenever the page scrolls, the window is resized or the card or its
 * host changes size (`autoUpdate`), and it closes when its host leaves the window. A card that scrolls is the one card that
 * takes the pointer: the pointer may cross from the host into it, where it stays open until the pointer leaves it, and the
 * keyboard reaches it by Tab from its host. Every other card lets the pointer through to what lies beneath (12 Nov).
 */
const props = defineProps<{
  title: string
  rows: CardRow[]
}>()

const slots = defineSlots<{
  default?: () => unknown
  lead?: () => unknown
}>()

const EDGE = 8 // the room kept from the window's edges
const GAP = 4 // between the host and its card

const shown = ref(false)
const place = ref<{ top: string, left: string }>({ top: '0px', left: '0px' })
const scrolls = ref(false)
const host = ref<HTMLElement | null>(null)
const card = ref<HTMLElement | null>(null)
let stopPlacing: (() => void) | undefined

async function placeCard(): Promise<void> {
  const reference = host.value
  const floating = card.value
  if (!reference || !floating) {
    return
  }
  const spot = await computePosition(reference, floating, {
    strategy: 'fixed',
    placement: 'bottom-start',
    middleware: [
      offset(GAP),
      flip({ padding: EDGE, fallbackStrategy: 'bestFit', crossAxis: false }),
      shift({ padding: EDGE }),
      size({
        padding: EDGE,
        apply({ availableHeight, elements }) {
          elements.floating.style.maxHeight = `${Math.max(0, Math.floor(availableHeight))}px`
        },
      }),
      hidden({ strategy: 'referenceHidden' }),
    ],
  })
  // a host the window draws and that has left it (a host drawn nowhere, as in a test's document, is never taken for one)
  if (spot.middlewareData.hide?.referenceHidden && reference.getClientRects().length > 0) {
    close()
    return
  }
  place.value = { top: `${spot.y}px`, left: `${spot.x}px` }
  // more than a pixel over its room: a card whose room was rounded down by a fraction does not scroll for it
  scrolls.value = floating.scrollHeight - floating.clientHeight > 1
}

async function show(): Promise<void> {
  clearTimeout(leaving)
  if (shown.value) {
    return
  }
  shown.value = true
  await nextTick()
  if (host.value && card.value) {
    stopPlacing = autoUpdate(host.value, card.value, () => void placeCard())
  }
}

// the pointer's wait before the card opens, cancelled when the pointer leaves first; and, for a card that scrolls, the
// pointer's way across the gap into it before the card closes
let waiting: ReturnType<typeof setTimeout> | undefined
let leaving: ReturnType<typeof setTimeout> | undefined

function onPointer(): void {
  clearTimeout(leaving)
  clearTimeout(waiting)
  if (shown.value) {
    return
  }
  if (HOVER_DELAY.pointerMs <= 0) {
    void show()
    return
  }
  waiting = setTimeout(() => void show(), HOVER_DELAY.pointerMs)
}

function onLeave(): void {
  clearTimeout(waiting)
  if (scrolls.value) {
    leaving = setTimeout(close, HOVER_DELAY.crossMs)
    return
  }
  close()
}

/** The keyboard's focus leaving: the card stays open while the focus moves into it, a card that scrolls taking Tab. */
function onFocusOut(event: FocusEvent): void {
  if (event.relatedTarget instanceof Node && host.value?.contains(event.relatedTarget)) {
    return
  }
  close()
}

function close(): void {
  clearTimeout(waiting)
  clearTimeout(leaving)
  stopPlacing?.()
  stopPlacing = undefined
  shown.value = false
  scrolls.value = false
}

onBeforeUnmount(close)

const filled = computed(() => props.rows.filter(row => row.value))

/** Whether a shown row opens a new group, below a rule: the first only where a lead stands above it. */
function opensGroup(index: number): boolean {
  return index === 0 ? Boolean(slots.lead) : filled.value[index]!.group !== filled.value[index - 1]!.group
}
</script>

<template>
  <span ref="host" class="hover-card-host" tabindex="0" @mouseenter="onPointer" @mouseleave="onLeave" @focusin="show" @focusout="onFocusOut">
    <slot />
    <span
      v-if="shown"
      ref="card"
      class="hover-card"
      :class="{ scrolls }"
      role="tooltip"
      data-part="hover-card"
      :data-scrolls="scrolls || undefined"
      :tabindex="scrolls ? 0 : undefined"
      :style="place"
    >
      <span class="card-title">{{ title }}</span>
      <slot name="lead" />
      <template v-for="(row, index) in filled" :key="row.label">
        <template v-if="opensGroup(index)">
          <span class="card-rule" data-part="card-rule" />
          <span v-if="row.caption" class="card-caption">{{ row.caption }}</span>
        </template>
        <span class="card-row" :data-row="row.label" :data-indent="row.indent || undefined">
          <span class="card-label">{{ row.label }}</span>
          <span class="card-value">{{ row.value }}</span>
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

/* as wide as its content up to its measure, wherever it stands: Floating UI sets only where */
.hover-card {
  position: fixed;
  z-index: 20;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-content: start;
  gap: 2px var(--space-sm);
  width: max-content;
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
  overflow-y: hidden;
  /* it holds data only, nothing to click: a pointer passes through it to what it covers, so a card left open over a row
     never takes the click meant for what lies beneath (found 12 Nov: a card over the Issues' fold held a click) */
  pointer-events: none;
}

/* the one exception: a card taller than the room on either side scrolls inside, and takes the pointer to be scrolled */
.hover-card.scrolls {
  overflow-y: auto;
  overscroll-behavior: contain;
  pointer-events: auto;
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
