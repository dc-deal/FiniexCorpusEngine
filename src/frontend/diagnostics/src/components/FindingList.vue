<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import ReadingTable from '@/components/reading/ReadingTable.vue'
import { assessmentLabel, correctionLabel, STANDING, verdictLabel } from '@/person_words'
import type { Finding, PersonVerdict, StandingCorrection } from '@/types/api/page_types'

/**
 * The judge's findings, each speaking with up to three voices, one labelled line each (decision 178.a, the operator on finance p. 5:
 * "who said what?"): the judge's finding, its kind and severity, struck through where void; the code's ruling, only
 * where the core voided it as naming no difference (146.a, 147.a), the rule in its hover; the judge's evidence, its label
 * on a line of its own and the evidence beneath. After the findings a person's verdict on this block, or on the page as a
 * whole, stands as a fourth voice: accepted, rejected or noted, its reason and its note. A void finding is never hidden,
 * and nothing in the reading was changed by it. Beside the block a finding names, the block is not named again; among the
 * page's own findings, one that names a block the reading lacks says so.
 */
const props = withDefaults(defineProps<{
  findings: Finding[]
  // the page's own findings: name the block of one that names a block the reading does not have
  namesBlocks?: boolean
  // a person's verdicts that apply to the reading shown and name this block, or the page as a whole
  people?: PersonVerdict[]
  // the correction that stands first in the block (229.a): not drawn again here, so a correction is shown once
  standing?: StandingCorrection | null
}>(), { people: () => [], standing: null })

// whether a person's correction is the one the block already shows first
function standsAbove(person: PersonVerdict): boolean {
  return Boolean(props.standing && person.correction === props.standing.text && person.given_at === props.standing.given_at)
}

// rule 146.a in a sentence, the hover of the code's ruling
const VOID_RULE = 'the finding quotes no difference between print and reading: the strings it quotes stand in the block and in the PDF\'s text layer'


// the reason in words beside the verdict; for the reason `other` the words are a placeholder, and the note beneath says it
function reasonOf(person: PersonVerdict): string {
  return person.reason === 'other' ? '' : person.reason_text || person.reason || ''
}
</script>

<template>
  <ul class="findings ruled">
    <li v-for="(finding, at) in findings" :key="at" :class="[finding.severity, { void: finding.void }]" :data-finding="at">
      <p class="voice" data-voice="judge">
        <AppIcon name="finding" class="finding-mark" />
        <span class="part-label">The judge's finding:</span>
        <span class="finding-kind">{{ finding.kind }}</span>
        <span class="severity">{{ finding.severity }}</span>
        <span v-if="namesBlocks && finding.block" class="missing-block">{{ finding.block }}, not in the reading</span>
      </p>
      <p v-if="finding.void" class="voice" data-voice="code">
        <span class="part-label">The code's ruling:</span>
        <!-- the rule in the library's card (203.a), where a browser tooltip stood -->
        <HoverCard title="The code's ruling" :rows="[{ label: 'rule', value: VOID_RULE }]">
          <span class="void-mark" data-part="void">void: the judge's evidence names no difference</span>
        </HoverCard>
      </p>
      <template v-if="finding.evidence">
        <p class="voice" data-voice="evidence"><span class="part-label">The judge's evidence:</span></p>
        <p class="evidence">{{ finding.evidence }}</p>
      </template>
    </li>
    <li v-for="(person, at) in people" :key="`person-${at}`" class="person" :class="person.verdict" :data-person="at">
      <!-- a verdict on the page as a whole speaks for a finding whose block no verdict names (the operator on finance p. 408); one run
           of text, its parting dot bound to the word before it, so a long reason never begins a line with the dot -->
      <p class="voice flow" data-voice="person">
        <span class="part-label">{{ `${verdictLabel(person, !person.block)}:` }}</span>{{ ' ' }}<span
          class="person-standing">{{ STANDING[person.verdict] ?? person.verdict }}</span><span
          v-if="reasonOf(person)" class="person-part">{{ ` · ${reasonOf(person)}` }}</span>
      </p>
      <!-- the note a line of its own beneath, as the judge's evidence is, so a long one never breaks the verdict's line (the operator,
           11 Nov: a wrapped note began its line with the parting dot) -->
      <p v-if="person.note" class="person-note" data-part="person-note">{{ person.note }}</p>
      <!-- a person's two manual parts (188.a, the operator: "both must be marked as a manual change"): the block as
           they say it reads, in the annotation role, dashed; and their assessment of the judge, their note above it. The
           correction that stands is drawn first in the block (229.a); one that does not, an earlier one, stays here. Nothing
           served changes: the quoted text stays the reader's -->
      <template v-if="person.correction && !standsAbove(person)">
        <p class="voice" data-voice="correction">
          <span class="part-label">{{ `${correctionLabel(person, Boolean(standing))}:` }}</span>
        </p>
        <!-- a table block's correction as a table (204.a), its cells the core's table parser gave the API, as a reading's
             are; any other correction as the text it is -->
        <ReadingTable v-if="person.correction_rows" class="correction person-correction" data-part="correction" :rows="person.correction_rows" />
        <p v-else class="correction person-correction" data-part="correction">{{ person.correction }}</p>
      </template>
      <p v-if="person.judge_assessment_text || person.judge_assessment" class="voice" data-voice="assessment">
        <!-- the judge the person rated, by name where the API knows it: beside a prototype's finding, the one they rated is
             another judge's (line 1's check-along on finance p. 119: judge/1's false alarm under judge/4's finding) -->
        <span class="part-label">{{ `${assessmentLabel(person, person.assessed)}:` }}</span>
        <span class="assessment" :data-assessment="person.judge_assessment">{{ person.judge_assessment_text || person.judge_assessment }}</span>
      </p>
    </li>
  </ul>
</template>

<style scoped>
/* the voices held to a line a person reads at once (the operator, 11 Nov), as the page's record is */
.findings {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 100ch;
}

/* each voice a line of its own, the lines after the judge's set in under its glyph */
.voice {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

/* a person's verdict reads as one run of text, wrapping word by word */
.voice.flow {
  display: block;
}

.voice + .voice,
.evidence,
.person-note,
.person .voice {
  padding-left: calc(1em + var(--space-sm));
}

/* a manual change in the look of a person's correction (base.css), set in under the voices */
.correction {
  margin-left: calc(1em + var(--space-sm));
}

.assessment {
  color: var(--color-text-primary);
}

/* the glyph and the severity's word carry the colour together, never the colour alone */
.finding-mark {
  align-self: center;
}

.major .finding-mark,
.major .severity {
  color: var(--color-error);
}

.minor .finding-mark,
.minor .severity {
  color: var(--color-warning);
}

.finding-kind {
  color: var(--color-text-primary);
}

.missing-block,
.evidence,
.person-note,
.person-part {
  color: var(--color-text-secondary);
}

/* whose words follow: a bold name (178.a), never struck with what it names */
.part-label {
  color: var(--color-text-secondary);
  font-weight: bold;
}

/* the card holds the rule: the dotted line says there is one */
.void-mark {
  text-decoration: underline dotted;
  cursor: help;
}

/* a void finding does not count: its severity loses its colour, its words recede, and the code's line says why */
.void .finding-mark,
.void .severity,
.void .finding-kind,
.void-mark {
  color: var(--color-text-secondary);
}

.void .finding-kind,
.void .severity {
  text-decoration: line-through;
}

.accept .person-standing {
  color: var(--color-positive);
}

.reject .person-standing {
  color: var(--color-error);
}
</style>
