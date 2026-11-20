<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/base/AppIcon.vue'
import type { IconName } from '@/icon_registry'

/**
 * A page's check state as a glyph and the core's own word, never as colour alone. Where everything is fine the mark
 * stays quiet; a page a person should look at takes the error or warning role. Where a person's accept or reject decides
 * what is served, the state is the pipeline's history and stays quiet too (`quiet`), its glyph and word kept.
 */
const props = defineProps<{
  state: string
  quiet?: boolean
  // a second word of the state, in the mark's own line and ink: "planned" for a page not read yet that a plan holds (V1.b)
  also?: string | null
}>()

interface Look {
  icon: IconName
  role: 'quiet' | 'warning' | 'error'
}

// The core's vocabulary: ok, ok_unjudged, issue, blocked, stopped; and `not_yet_checked` for a page no check run has
// reached yet, which is not known to be fine. It stays a string, so a state added later shows up unfamiliar rather than wrong.
const LOOKS: Record<string, Look> = {
  ok: { icon: 'status-ok', role: 'quiet' },
  ok_unjudged: { icon: 'status-unjudged', role: 'quiet' },
  issue: { icon: 'status-issue', role: 'error' },
  blocked: { icon: 'status-blocked', role: 'warning' },
  stopped: { icon: 'status-stopped', role: 'error' },
  not_yet_checked: { icon: 'status-unknown', role: 'warning' },
  // the lists' own bucket (211.a): a page to look at that a person settled; quiet, as nothing waits on it
  decided_by_a_person: { icon: 'status-decided', role: 'quiet' },
  // the same settled by an automated review (Q.a, 18 Nov), never counted as a person's
  decided_by_an_automated_review: { icon: 'status-reviewed', role: 'quiet' },
  // a PDF page no reader has read yet (V1.b): its own word, quiet and in no status colour, since nothing is wrong with it
  not_read: { icon: 'status-not-read', role: 'quiet' },
}

const look = computed<Look>(() => LOOKS[props.state] ?? { icon: 'status-unknown', role: 'warning' })
const word = computed(() => props.state.replace(/_/g, ' '))
</script>

<template>
  <span class="state-mark" :class="quiet ? 'quiet' : look.role" :data-state="state">
    <AppIcon :name="look.icon" />
    <span class="state-word">{{ word }}</span>
    <span v-if="also" class="state-also" data-part="state-also">{{ also }}</span>
  </span>
</template>

<style scoped>
.state-mark {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  white-space: nowrap;
}

/* the second word parted from the state as the routes' line parts its levels: "not read · planned" */
.state-also::before {
  content: '· ';
}

.quiet {
  color: var(--color-text-secondary);
}

.warning {
  color: var(--color-warning);
}

.error {
  color: var(--color-error);
}
</style>
