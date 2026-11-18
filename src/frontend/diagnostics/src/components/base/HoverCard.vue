<script setup lang="ts">
import { nextTick, ref } from 'vue'

/**
 * Data under the pointer (decision 179): a small card that holds data only, rows of a label and a value, its title naming
 * what it is about, where a browser tooltip stood. It opens on the pointer and on the keyboard's focus, and stands fixed
 * to the window, so a table's own scroll box never cuts it; beneath its host, or above it where the window's foot would
 * cut it (found on SR 11-7 p. 5, a note's marker at the window's foot, 11 Nov). An empty value leaves its row out.
 */
const props = defineProps<{
  title: string
  rows: { label: string, value: string | null | undefined }[]
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

function filled() {
  return props.rows.filter(row => row.value)
}
</script>

<template>
  <span ref="host" class="hover-card-host" tabindex="0" @mouseenter="show" @mouseleave="shown = false" @focusin="show" @focusout="shown = false">
    <slot />
    <span v-if="shown" ref="card" class="hover-card" role="tooltip" data-part="hover-card" :style="place">
      <span class="card-title">{{ title }}</span>
      <span v-for="row in filled()" :key="row.label" class="card-row" :data-row="row.label">
        <span class="card-label">{{ row.label }}</span>
        <span class="card-value">{{ row.value }}</span>
      </span>
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
</style>
