<script setup lang="ts">
import { computed, ref } from 'vue'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import FindingList from '@/components/FindingList.vue'
import PersonVerdictList from '@/components/PersonVerdictList.vue'
import InlineSegments from '@/components/reading/InlineSegments.vue'
import ReadingTable from '@/components/reading/ReadingTable.vue'
import MathTex from '@/components/reading/MathTex.vue'
import { correctionLabel, lookedSaid } from '@/person_words'
import type { PageChunks, ReadingBlock, ReadingError, StandingCorrection } from '@/types/api/page_types'
import { counted } from '@/counted'

/**
 * A reading block by block, in the reader's order, each drawn by its class: prose as segments, a formula typeset, a table
 * from its parsed cells, a listing as code, any other body as its text. Every block shows its id and class, the names a
 * judge's finding and the raw text use, and the judge's findings about it stand right beneath it. A derived block, such as
 * a figure's description, says so: it is never quoted. Page furniture stays quiet.
 *
 * A block a person corrected shows the correction first, as its content (decision 229.a, the operator: "what you really want to see first is the correction"), in the look of a person's correction and saying it is not served yet; the reader's text
 * stands beneath it, muted and labelled, as it is in the reading, which the correction never changes.
 *
 * A validator's error that names a block stands on it, in the look a finding has beneath its block (decision 228.a), with
 * the way to its line in the raw text; muted, and saying so, where a person has looked at the block or the page.
 */
const props = withDefaults(defineProps<{
  blocks: ReadingBlock[]
  highlight?: string | null
  // the validator's errors on the reading, parted by the API; each stands on the block it names
  errors?: ReadingError[]
  // "as served" (the operator, 21 Nov: quoted is a subset of readable): a block never quoted greyed, still readable, every
  // quoted one in the form the search and the chat quote; with the page's chunks, where each begins and what it shares (W4)
  asServed?: boolean
  chunks?: PageChunks | null
}>(), { highlight: null, errors: () => [], asServed: false, chunks: null })

// each quoted block's served form in the runs the API cut it into by the chunks; without them, the form whole
const servedParts = computed(() => new Map((props.chunks?.blocks ?? []).map(block => [block.block, block.parts])))
function partsOf(block: ReadingBlock): PageChunks['blocks'][number]['parts'] {
  return servedParts.value.get(block.id) ?? [{ text: block.served ?? '', chunk: null, shared: false, starts: null }]
}
const overlapOf = (number: number): number => props.chunks?.chunks.find(chunk => chunk.number === number)?.overlap ?? 0

function errorsOn(block: ReadingBlock): ReadingError[] {
  return props.errors.filter(error => error.block === block.id)
}

// A figure's labels as read from the image (the operator on finance p. 94: "the line break here is spam"; on p. 387: "mostly the description is more interesting than the values"): an ungrouped figure's labels stand as one wrapped run parted by " · ",
// folded beyond a dozen; a photo's always, whatever their count. A grouped figure keeps its boxes; the raw text keeps the
// reader's lines.
const LABELS_SHOWN = 12

function labelsOf(block: ReadingBlock): string[] {
  return (block.text ?? '').split('\n').map(line => line.trim()).filter(Boolean)
}

function foldsLabels(block: ReadingBlock): boolean {
  return Boolean(block.decorative) || block.attrs.kind === 'photo' || labelsOf(block).length > LABELS_SHOWN
}

// a figure the API marks as decoration (194.a: "just a decorative image"), such as chapter art: named so, quiet, its labels folded
function foldTitle(block: ReadingBlock): string {
  if (block.decorative) return 'Chapter art'
  return describedBy(block) ?? labelsCount(block)
}

function foldCount(block: ReadingBlock): string | null {
  if (block.decorative) return labelsCount(block)
  return describedBy(block) ? labelsCount(block) : null
}

// what the folded figure shows, from its description's first sentence, where the reader wrote one for it
function describedBy(block: ReadingBlock): string | null {
  const description = props.blocks.find(one => one.block_class === 'description' && one.attrs.of === block.id)
  if (!description) return null
  const text = description.text ?? (description.segments ?? []).map(segment => segment.content).join('')
  const sentence = /^.*?[.!?](?=\s|$)/.exec(text.trim())
  return (sentence ? sentence[0] : text.trim()) || null
}

function labelsCount(block: ReadingBlock): string {
  const count = labelsOf(block).length
  return `${counted(count, 'label')}${block.attrs.kind === 'photo' ? ' read from the photo' : ''}`
}

// the block under the pointer, so the page beside it can show where the reader placed that block
const emit = defineEmits<{
  hover: [id: string | null]
  // a note's marker asks for its note, which the page brings into view as it does a finding's block (206.a)
  jump: [id: string]
  // a validator's error asks for its line in the raw text (228.a)
  raw: [line: number]
}>()

const list = ref<HTMLElement | null>(null)

// the attributes worth a glance; the box and the rest stay in the raw text
const SHOWN_ATTRS = ['label', 'kind', 'grouped', 'number', 'marker', 'of', 'form', 'cont', 'status', 'conf']

function shownAttrs(block: ReadingBlock): string {
  return SHOWN_ATTRS.filter(name => block.attrs[name]).map(name => `${name}=${block.attrs[name]}`).join(' ')
}

/**
 * A grouped figure's body as the reader wrote it under the contract (`grouped=1`): one group per drawn container, the
 * groups parted by a blank line, each its title line first and its members below (the operator on accounting p. 305, 10 Nov: the
 * eleven T-accounts ran together as one line). Display only: the text is the reading's, unchanged, and the raw mode shows
 * it as stored.
 */
// An attribute that carries printed words (decision 190.a): a glossary entry's term stands before its definition, as the
// core's quotable text has it ("accrual-basis accounting: an accounting system in which ..."), a bibliography entry's key,
// its printed number, before the entry, and a contents entry's target, its printed page, after it
function termOf(block: ReadingBlock): string | null {
  return block.block_class === 'glossary_entry' ? block.attrs.term ?? null : null
}

function keyOf(block: ReadingBlock): string | null {
  return block.block_class === 'bib_entry' ? block.attrs.key ?? null : null
}

function targetOf(block: ReadingBlock): string | null {
  return block.block_class === 'toc_entry' ? block.attrs.target ?? null : null
}

// what a correction's line says after its label: that the search and the chat still quote the reading, and who gave it;
// when follows, said as a person says it
function givenSaid(correction: StandingCorrection): string {
  return `· ${['not served yet', correction.given_by].filter(Boolean).join(' · ')}${correction.given_at ? ' · ' : ''}`
}

// whether the reading holds a body for the block to draw beneath a correction: a table the reader marked unreadable has none
// (accounting p. 524, b11), and the line beneath the correction says so rather than label nothing
function hasBody(block: ReadingBlock): boolean {
  return Boolean(block.segments || block.rows || block.text) || block.latex !== null || block.code !== null
}

function groupsOf(text: string): { title: string, lines: string[] }[] {
  return text.split(/\n[ \t]*\n/)
    .map(group => group.split('\n').filter(line => line.trim()))
    .filter(lines => lines.length > 0)
    .map(([title, ...lines]) => ({ title, lines }))
}

/**
 * Brings a block into view, top first, so it is read from its start. Asked for by every click that chooses a block, not
 * by a change of the marked one: a second click on the same block, after the reader scrolled away, must bring it back, and
 * so must a click that switches back from the raw text and mounts this list anew (review, 2026-11-04). Only the column the
 * reading scrolls in moves, so the line and the pointer above it stay in sight: scrolled with the window, they slid out
 * and took the page's title with them (browser check, 2026-11-04). Where the column itself is out of sight, as on a narrow
 * screen with the original above it, the window brings the block in after all. At once, not smoothly: a smooth scroll of
 * column and window left the block's beginning above the edge. The native `scrollIntoView({ container: 'nearest' })` would
 * scroll the column alone, but TypeScript 5.9's DOM types do not know it (lib.dom.d.ts, checked 2026-11-04).
 */
// `paneOnly` keeps the window where it stands, as when a page opens on its first finding (186)
function scrollToBlock(id: string, paneOnly = false): void {
  // looked up in this list, not in the document: an id is unique within one reading only
  const element = Array.from(list.value?.children ?? []).find(child => (child as HTMLElement).dataset.block === id)
  if (!(element instanceof HTMLElement)) return
  const column = scrollingColumn(element)
  if (column) column.scrollTop += element.getBoundingClientRect().top - column.getBoundingClientRect().top
  const top = element.getBoundingClientRect().top
  if (paneOnly) return
  if (!column || top < 0 || top >= window.innerHeight) element.scrollIntoView?.({ block: 'start', behavior: 'auto' })
}

defineExpose({ scrollToBlock })

// the nearest ancestor that scrolls vertically and has something to scroll
function scrollingColumn(element: HTMLElement): HTMLElement | null {
  for (let at = element.parentElement; at; at = at.parentElement) {
    const overflow = getComputedStyle(at).overflowY
    if ((overflow === 'auto' || overflow === 'scroll') && at.scrollHeight > at.clientHeight) return at
  }
  return null
}
</script>

<template>
  <ol ref="list" class="blocks">
    <li
      v-for="block in blocks"
      :id="`block-${block.id}`"
      :key="block.id"
      class="block"
      :class="[block.group, { highlighted: block.id === highlight, 'has-findings': block.findings.length > 0,
                              'not-served': asServed && !block.served }]"
      :data-block="block.id"
      @mouseenter="emit('hover', block.id)"
      @mouseleave="emit('hover', null)"
    >
      <div class="block-head">
        <span class="block-id">{{ block.id }}</span>
        <span class="block-class">{{ block.block_class }}</span>
        <span v-if="shownAttrs(block)" class="block-attrs">{{ shownAttrs(block) }}</span>
        <span v-if="block.content === 'D'" class="derived">derived, never quoted</span>
      </div>
      <!-- a person's correction first, as the block's content (229.a): a table's as a table, any other as its text -->
      <div v-if="block.correction" class="standing-correction" data-part="standing-correction">
        <p class="correction-said"><span class="part-label">{{ correctionLabel(block.correction) }}</span><span class="correction-given" data-part="correction-given">{{ givenSaid(block.correction) }}<HumanTime v-if="block.correction.given_at" :at="block.correction.given_at" /></span></p>
        <ReadingTable v-if="block.correction.rows" class="person-correction" data-part="correction-content" :rows="block.correction.rows" />
        <p v-else class="person-correction correction-text" data-part="correction-content">{{ block.correction.text }}</p>
        <p class="part-label as-read-said" data-part="as-read-said">{{ hasBody(block) ? 'The reading, as the reader wrote it:' : 'The reading holds no text for this block.' }}</p>
      </div>
      <!-- the reading's own text, muted beneath a correction, as it stands in the reading -->
      <div class="block-content" :class="{ 'as-read': block.correction }" :data-part="block.correction ? 'as-read' : undefined">
      <!-- the printed words an attribute carries stand with the body, no space of the template's own between them (190.a) -->
      <!-- as served: the block in the form the search and the chat quote, each chunk's beginning a dashed line (W4) -->
      <div v-if="asServed && block.served" class="block-body served-form" data-part="served-form"><template
        v-for="(part, at) in partsOf(block)" :key="at"
      ><span v-if="part.starts" class="chunk-start" :data-chunk-start="part.starts">chunk {{ part.starts }} of {{ chunks?.chunks.length }}<HoverCard
        v-if="overlapOf(part.starts)"
        title="Shared with the chunk before"
        :rows="[{ label: 'characters', value: overlapOf(part.starts).toLocaleString('en') }, { label: 'with', value: `chunk ${part.starts - 1}` }]"
      ><span class="shared-count">{{ overlapOf(part.starts) }} shared</span></HoverCard></span><span
        :class="{ overlap: part.shared }" :data-chunk="part.chunk ?? undefined"
      >{{ part.text }}</span></template></div>
      <p v-else-if="block.segments" class="block-body"><strong v-if="termOf(block)" class="entry-term" data-part="entry-term">{{ termOf(block) }}</strong>{{ termOf(block) ? ': ' : '' }}<span v-if="keyOf(block)" class="entry-key" data-part="entry-key">{{ `${keyOf(block)} ` }}</span><InlineSegments :segments="block.segments" @jump="emit('jump', $event)" /><span v-if="targetOf(block)" class="entry-target" data-part="entry-target">{{ ` ${targetOf(block)}` }}</span></p>
      <div v-else-if="block.latex !== null" class="block-body formula">
        <MathTex :latex="block.latex" display />
        <span v-if="block.attrs.label" class="formula-label">({{ block.attrs.label }})</span>
      </div>
      <ReadingTable v-else-if="block.rows" class="block-body" :rows="block.rows" @jump="emit('jump', $event)" />
      <pre v-else-if="block.code !== null" class="block-body code">{{ block.code }}</pre>
      <!-- a grouped figure: each drawn container its own small box, its title first -->
      <div v-else-if="block.text && block.attrs.grouped === '1'" class="block-body groups">
        <div v-for="(group, g) in groupsOf(block.text)" :key="g" class="text-group" :data-group="g">
          <p class="group-title">{{ group.title }}</p>
          <p v-for="(line, l) in group.lines" :key="l" class="group-line">{{ line }}</p>
        </div>
      </div>
      <!-- an ungrouped figure's labels in one wrapped run, folded beyond a dozen and always for a photo, the fold's title saying
           what the figure shows where a description says it -->
      <div v-else-if="block.text && block.block_class === 'figure'" class="block-body labels" data-part="figure-labels">
        <FoldSection
          v-if="foldsLabels(block)"
          class="labels-fold"
          :class="{ 'chapter-art': block.decorative }"
          :title="foldTitle(block)"
          :count="foldCount(block)"
          :data-decorative="block.decorative ?? undefined"
        >
          <p class="label-run">{{ labelsOf(block).join(' · ') }}</p>
        </FoldSection>
        <p v-else class="label-run">{{ labelsOf(block).join(' · ') }}</p>
      </div>
      <!-- any other body line by line, as the reader wrote it -->
      <p v-else-if="block.text" class="block-body text"><strong v-if="termOf(block)" class="entry-term" data-part="entry-term">{{ termOf(block) }}</strong>{{ termOf(block) ? ': ' : '' }}<span v-if="keyOf(block)" class="entry-key" data-part="entry-key">{{ `${keyOf(block)} ` }}</span>{{ block.text }}<span v-if="targetOf(block)" class="entry-target" data-part="entry-target">{{ ` ${targetOf(block)}` }}</span></p>
      </div>
      <!-- the validator's errors on this block, in a finding's look (228.a): red until a person has looked, then muted -->
      <ul v-if="errorsOn(block).length" class="block-errors ruled" data-part="block-errors">
        <li v-for="(error, at) in errorsOn(block)" :key="at" :class="{ looked: error.looked }" :data-error="at">
          <p class="voice">
            <AppIcon name="finding" class="error-mark" />
            <span class="part-label">The validator's error:</span>
            <span class="error-message">{{ error.message }}</span>
          </p>
          <!-- beneath, set in as a finding's evidence is: the way to its line, and who has looked -->
          <p v-if="error.line || error.looked" class="error-after">
            <AppButton v-if="error.line" variant="link" data-part="show-raw" @click="emit('raw', error.at_line ?? error.line)">{{ `show raw, line ${error.at_line ?? error.line}` }}</AppButton>{{ error.line && error.looked ? ' · ' : '' }}<span
              v-if="error.looked" class="error-looked" data-part="error-looked">{{ lookedSaid(error) }}</span>
          </p>
        </li>
      </ul>
      <!-- the findings speak one voice a line, a person's verdict that applies to this reading the last of them (178.a); a
           verdict on a block without findings, or one given on an earlier reading, stands in its own list as before -->
      <template v-if="block.findings.length">
        <FindingList class="block-findings" :findings="block.findings" :people="block.people.filter(person => person.applies)" :standing="block.correction ?? null" />
        <PersonVerdictList
          v-if="block.people.some(person => !person.applies)"
          class="block-findings"
          :people="block.people.filter(person => !person.applies)"
        />
      </template>
      <PersonVerdictList v-else-if="block.people.length" class="block-findings" :people="block.people" />
    </li>
  </ol>
</template>

<style scoped>
/* every block in a fine box of its own (the operator, 2026-11-09), its label inside at the top, the boxes close together so the
   pane stays compact; the raw text stays one text, as stored */
.blocks {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.block {
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--color-row-rule);
}

/* as served: a block never quoted recedes, still to be read; a quoted one in its served form, as the search holds it */
.block.not-served {
  opacity: 0.45;
}

.served-form {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* where a chunk of semantic search begins: a dashed line across the block, the annotation's role, as an HTML section's
   chunks are marked; the text it shares with the chunk before dashed beneath, as there */
.chunk-start {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-sm);
  margin: var(--space-xs) 0 2px;
  padding-top: 2px;
  border-top: 1px dashed var(--color-annotation);
  color: var(--color-text-secondary);
  white-space: normal;
}

.overlap {
  text-decoration: underline dashed var(--color-annotation);
  text-underline-offset: 3px;
}

/* a block the judge found fault with keeps a neutral edge inside its box: its findings beneath carry the severity, each
   as a glyph and a word in its colour, so the edge claims none of its own (a red edge beside a minor finding said two
   things) */
.block.has-findings {
  box-shadow: inset 2px 0 0 var(--color-text-secondary);
}

/* the block on show is framed, not only named: the edge says which block is meant */
.block.highlighted {
  box-shadow: inset 2px 0 0 var(--color-accent);
  background-color: var(--color-bg-elevated);
}

.block-findings {
  margin-top: var(--space-xs);
}

/* a correction first, its line saying whose it is; the reading beneath it recedes, kept whole and labelled (229.a) */
.standing-correction {
  margin-bottom: 2px;
}

.correction-said {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

.part-label {
  color: var(--color-text-secondary);
  font-weight: bold;
}

.correction-given {
  color: var(--color-text-secondary);
}

.correction-text {
  white-space: pre-line;
}

.as-read-said {
  margin-top: 2px;
}

.as-read {
  color: var(--color-text-secondary);
}

/* a validator's error on its block, as a finding stands beneath its block: the flag and the words in the error role until
   a person has looked, then receding, the person's look said beneath; never hidden (228.a) */
.block-errors {
  list-style: none;
  margin-top: var(--space-xs);
  max-width: 100ch;
}

.block-errors .voice {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

.error-mark {
  align-self: center;
  color: var(--color-error);
}

.error-message {
  color: var(--color-error);
}

.error-after {
  padding-left: calc(1em + var(--space-sm));
  color: var(--color-text-secondary);
}

.looked .error-mark,
.looked .error-message {
  color: var(--color-text-secondary);
}

.block-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  color: var(--color-text-secondary);
}

/* a marking, not a state: its words in the ink of what stands beside, the colour left to the state that has one (tip 6) */
.derived {
  color: var(--color-text-secondary);
}

.furniture,
.non_verbatim {
  opacity: 0.7;
}

.formula {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.formula-label {
  color: var(--color-text-secondary);
}

.code {
  overflow-x: auto;
}

/* a body's line breaks are the reader's: a figure's labels, one per line */
/* a figure's labels in one run, parted by a quiet dot (2c) */
.label-run {
  overflow-wrap: anywhere;
}

/* chapter art (194.a): there, never hidden, but quiet */
.labels-fold.chapter-art {
  color: var(--color-text-secondary);
}

.text {
  white-space: pre-line;
}

/* a grouped figure's containers side by side as far as the column allows, each in a fine box, its title above a rule */
.groups {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  align-items: flex-start;
}

.text-group {
  border: 1px solid var(--color-row-rule);
  padding: 2px var(--space-sm);
}

.group-title {
  font-weight: bold;
  border-bottom: 1px solid var(--color-row-rule);
  margin-bottom: 2px;
}
</style>
