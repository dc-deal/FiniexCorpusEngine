<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import { sayTime } from '@/human_time'
import { verdictLabel } from '@/person_words'
import type { PersonMark } from '@/types/api/page_types'

/**
 * A person's standing verdict on the reading a page shows (decision 166.a), beside the judge's state wherever it stands:
 * "accepted", "rejected" or "noted", with a person's glyph; under the pointer a card holds the verdict's reason, note,
 * who gave it and when. The API decides which verdict stands, as the core decides what is served; a note never changes it.
 */
defineProps<{
  mark: PersonMark | null | undefined
}>()
</script>

<template>
  <HoverCard
    v-if="mark"
    :title="verdictLabel(mark)"
    :rows="[{ label: 'verdict', value: mark.standing }, { label: 'reason', value: mark.reason }, { label: 'note', value: mark.note },
            { label: 'given by', value: mark.given_by }, { label: 'given', value: mark.given_at ? sayTime(mark.given_at).text : null }]"
  >
    <span class="person-standing" :class="mark.standing" :data-person="mark.standing">
      <AppIcon :name="mark.by_a_person === false ? 'review' : `person-${mark.standing}`" />
      <span class="person-word">{{ mark.standing }}</span>
    </span>
  </HoverCard>
</template>

<style scoped>
.person-standing {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  white-space: nowrap;
}

.accepted {
  color: var(--color-positive);
}

.rejected {
  color: var(--color-error);
}

.noted {
  color: var(--color-text-secondary);
}
</style>
