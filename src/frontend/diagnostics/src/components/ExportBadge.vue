<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import { exportClock } from '@/export_clock'
import { useElapsed } from '@/use_elapsed'
import { useVerdictStore } from '@/stores/verdict_store'

/**
 * The header's word on an export a verdict waits for (the operator's E1.a, 21 Nov: a verdict recorded was taken for "nothing
 * saved" while the licensed export ran for minutes, unseen), on every view: while one runs or waits, an hourglass that turns,
 * still for a reader who asked for less motion, and "licensed export · 3 of about 5 min", or "· running 3 min" where no export
 * of the base has finished to tell. A click opens a card: the base, since when, whether one more waits, and the verdicts
 * that wait for it. When it ends, "✓ served" for 4 s; a failure stays in the error role until clicked away. Every figure
 * is the API's (`ExportStatus`); the words are the view's.
 */
const store = useVerdictStore()
const { form } = storeToRefs(store)
const exports = computed(() => form.value?.exports ?? [])
const busy = computed(() => exports.value.find(status => status.running || status.pending) ?? null)
const since = computed(() => (busy.value?.started_at ? Date.parse(busy.value.started_at) : null))
const elapsed = useElapsed(() => since.value)
const open = ref(false)

// an export that has just ended: served for 4 s, or its error until a person clicks it away
const SERVED_MS = 4000
const ended = ref<{ base: string, error: string | null } | null>(null)
let servedTimer: ReturnType<typeof setTimeout> | undefined
watch(() => exports.value.map(status => ({ base: status.knowledge_base, busy: status.running || status.pending, finished: status.finished,
  error: status.last_error ?? null })), (now, before) => {
  for (const status of now) {
    const was = before?.find(one => one.base === status.base)
    if (!was?.busy || status.busy || status.finished <= was.finished) continue
    clearTimeout(servedTimer)
    open.value = false
    ended.value = { base: status.base, error: status.error }
    if (!status.error) servedTimer = setTimeout(() => { ended.value = null }, SERVED_MS)
  }
})
onBeforeUnmount(() => clearTimeout(servedTimer))
</script>

<template>
  <div v-if="busy || ended" class="export-badge" data-part="export-badge">
    <AppButton v-if="busy" variant="quiet" size="compact" :aria-expanded="open" data-part="export-running" @click="open = !open">
      <AppIcon name="hourglass" class="hourglass" />
      <span data-part="export-clock">{{ `${busy.knowledge_base} export · ${exportClock(elapsed, busy.expected_seconds)}` }}</span>
    </AppButton>
    <AppButton v-else-if="ended?.error" variant="quiet" size="compact" class="export-failed" role="alert" data-part="export-failed"
               @click="ended = null">
      <AppIcon name="status-error" /> {{ `${ended.base} export failed: ${ended.error}` }}
    </AppButton>
    <span v-else class="export-served" data-part="export-served"><AppIcon name="status-ok" /> served</span>
    <!-- what the export is, and what it serves once it is done -->
    <div v-if="open && busy" class="export-card" data-part="export-card">
      <LabelledLines :label-chars="9">
        <LabelledLine label="Base">{{ busy.knowledge_base }}</LabelledLine>
        <LabelledLine label="Since"><HumanTime v-if="busy.started_at" :at="busy.started_at" /><template v-else>waiting to start</template></LabelledLine>
        <LabelledLine label="Next" data-part="export-next">{{ busy.pending ? 'one more export waits after this one' : 'none waits after it' }}</LabelledLine>
        <LabelledLine label="Serves" data-part="export-waiting">
          <ul v-if="busy.waiting.length" class="waiting">
            <li v-for="(one, at) in busy.waiting" :key="at" :data-waiting="at">
              {{ `${one.source_id ?? 'a page'} · p. ${one.pdf_page} · ${one.block || 'the page'} · ${one.verdict} · recorded ` }}<HumanTime :at="one.given_at" />
            </li>
          </ul>
          <template v-else>no verdict waits for it</template>
        </LabelledLine>
      </LabelledLines>
    </div>
  </div>
</template>

<style scoped>
.export-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
}

/* the hourglass turns over and over, as one does; still for a reader who asked for less motion, the words counting on */
.hourglass {
  animation: hourglass-turn 2.4s ease-in-out infinite;
}

@keyframes hourglass-turn {
  0%, 40% { transform: rotate(0deg); }
  50%, 90% { transform: rotate(180deg); }
  100% { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .hourglass {
    animation: none;
  }
}

.export-failed {
  color: var(--color-error);
}

.export-served {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-positive);
}

/* the card beneath the badge, over the view, as the frame's menu stands */
.export-card {
  position: absolute;
  top: calc(100% + var(--space-xs));
  right: 0;
  z-index: var(--z-menu);
  width: max-content;
  max-width: min(36rem, calc(100vw - 2 * var(--space-md)));
  padding: var(--space-sm) var(--space-md);
  background-color: var(--color-bg-surface);
  border: 1px solid var(--color-border-overlay);
  box-shadow: var(--shadow-overlay);
}

.waiting {
  list-style: none;
}
</style>
