<script setup lang="ts">
import HumanTime from '@/components/base/HumanTime.vue'
import { STANDING, verdictLabel } from '@/person_words'
import type { PersonVerdict } from '@/types/api/page_types'

/**
 * A person's verdicts (146.a), each as a verdict reads beneath a block (178.a), so one kind of thing has one look wherever
 * it stands (the operator, 11 Nov): "A person's verdict: accepted · the reason · b03 · maintainer · yesterday, 21:41", the note a
 * line of its own beneath. The reason in the person's own words where there are some, what it is about, its tag, and who
 * gave it when. One given on an earlier reading of the page does not apply to the reading shown, and says so rather than
 * disappearing. Shown in the page's details, beneath the reading it judged in the history, and beside a block it names.
 */
const props = defineProps<{
  people: PersonVerdict[]
  // the page's own list names the block a verdict is about; beside a block it goes without saying
  namesBlocks?: boolean
}>()

// the fields a verdict carries after its word, each with its own class, in the line's order; who gave it is followed by
// when, said as a person says it (the space before the time stands inside the text, where the template cannot drop it).
// A dot that parts two fields is bound to the word before it, so a long line wraps after a dot, never before one (the operator,
// 11 Nov: a wrapped line began with the parting dot; seen again on accounting p. 398, 12 Nov)
const PARTED = ' · '

function partsOf(person: PersonVerdict): { part: string, text: string, at?: string | null }[] {
  const by = person.given_by ?? ''
  return [
    { part: 'person-reason', text: person.reason === 'other' ? '' : person.reason_text || person.reason || '' },
    { part: 'person-about', text: props.namesBlocks ? (person.block ?? 'the page') : '' },
    { part: 'person-tag', text: person.tag ? `tag ${person.tag}` : '' },
    { part: 'person-given', text: person.given_at ? (by ? `${by}${PARTED}` : '') : by, at: person.given_at },
    // archived by a reset (191.a): shown, greyed, with the reset's time; never applying
    { part: 'person-archived', text: person.archived ? 'archived by a reset ' : '', at: person.archived ? person.archived_at : null },
    { part: 'person-earlier', text: person.applies || person.archived ? '' : 'given on an earlier reading: does not apply to this one' },
  ].filter(one => one.text || one.at)
}
</script>

<template>
  <ul class="people ruled">
    <li v-for="(person, at) in people" :key="at" :class="[person.verdict, { earlier: !person.applies, archived: person.archived }]" :data-person="at">
      <p class="person-line">
        <span class="part-label">{{ `${verdictLabel(person)}:` }}</span>{{ ' ' }}<span class="person-verdict">{{ STANDING[person.verdict] ?? person.verdict }}</span><span
          v-for="one in partsOf(person)" :key="one.part" :class="one.part">{{ `${PARTED}${one.text}` }}<HumanTime v-if="one.at" :at="one.at" /></span>
      </p>
      <!-- the note a line of its own beneath, as beneath a block: a long one never breaks the verdict's line -->
      <p v-if="person.note" class="person-note" data-part="person-note">{{ person.note }}</p>
    </li>
  </ul>
</template>

<style scoped>
.people {
  list-style: none;
}

.people li {
  padding: 1px 0;
}

/* one run of text, so a long reason wraps word by word and a line breaks after a parting dot, never before it */
.person-line {
  max-width: 100ch;
}

/* whose words follow: a bold name, as a finding's voices have it (178.a) */
.part-label {
  color: var(--color-text-secondary);
  font-weight: bold;
}

/* the note set in under the line, held to a line a person reads at once */
.person-note {
  padding-left: calc(1em + var(--space-sm));
  max-width: 100ch;
}

.person-about,
.person-tag,
.person-note,
.person-given,
.person-earlier {
  color: var(--color-text-secondary);
}

.person-verdict {
  color: var(--color-text-primary);
}

.accept .person-verdict {
  color: var(--color-positive);
}

.reject .person-verdict {
  color: var(--color-error);
}

/* a verdict on an earlier reading recedes: it is kept, not counted */
/* a verdict archived by a reset recedes the same way: kept, never counted (191.a) */
.archived .person-verdict,
.archived .person-reason,
.person-archived,
.earlier .person-verdict,
.earlier .person-reason {
  color: var(--color-text-secondary);
}
</style>
