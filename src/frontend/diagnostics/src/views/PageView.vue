<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { pageImageUrl } from '@/api/api_client'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import AnalysisSection from '@/components/base/AnalysisSection.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import DetailList from '@/components/base/DetailList.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HintPanel from '@/components/base/HintPanel.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import { isDecided } from '@/listed_state'
import LoadingLine from '@/components/base/LoadingLine.vue'
import CategoryMark from '@/components/CategoryMark.vue'
import DataTable from '@/components/base/DataTable.vue'
import FindingList from '@/components/FindingList.vue'
import IntegrityMark from '@/components/IntegrityMark.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import PageJump from '@/components/PageJump.vue'
import PageLadderLines from '@/components/PageLadderLines.vue'
import UnreadPage from '@/components/UnreadPage.vue'
import PagerLinks from '@/components/base/PagerLinks.vue'
import RecordZone from '@/components/base/RecordZone.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import PersonVerdictList from '@/components/PersonVerdictList.vue'
import ReaderRuleList from '@/components/ReaderRuleList.vue'
import VerdictDialog from '@/components/VerdictDialog.vue'
import ReadingBlocks from '@/components/reading/ReadingBlocks.vue'
import ReasonList from '@/components/ReasonList.vue'
import StateMark from '@/components/StateMark.vue'
import { usePageStore } from '@/stores/page_store'
import { useSettingsStore } from '@/stores/settings_store'
import { useVerdictStore } from '@/stores/verdict_store'
import { useViewName } from '@/view_name'
import { lookedSaid, verdictBy } from '@/person_words'
import { readingCost, usd } from '@/cost_format'
import { counted, noun } from '@/counted'
import { overlapHint } from '@/overlap_hint'
import type { Attempt, Judgement, PersonVerdict } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One page: a line of what matters most, the rest folded into details, then the original beside its reading. The original
 * is the image the reader received, rendered again from the PDF, and the line says whether the bytes match. The reading is
 * shown as the core parsed it, or raw, escaped and exactly as stored, or as the text the search and the chat quote (the operator's
 * 20.a), which a page quoted from its text layer opens on. A finding of the judge stands beneath the block it
 * names; the line above points to those blocks, and a finding about the page as a whole stands there in full. The block
 * under the pointer, or else the one chosen, is framed on the original where the reader placed it.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
  page: number
}>()

type Mode = 'readable' | 'raw'

const store = usePageStore()
const { detailError, chunksError, recallError } = storeToRefs(store)
const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)
const mode = ref<Mode>('readable')
// the raw text's line a validator's error asked for, marked there (228.a)
const rawLine = ref<number | null>(null)
const highlight = ref<string | null>(null)
const hovered = ref<string | null>(null)
const pane = ref<HTMLElement | null>(null)
const boxElement = ref<HTMLElement | null>(null)
const readingBlocks = ref<InstanceType<typeof ReadingBlocks> | null>(null)
const verdictOpen = ref(false)
const analysis = ref<InstanceType<typeof AnalysisSection> | null>(null)
const address = useRoute()

watch(() => [props.kb, props.work, props.page] as const, ([kb, work, page]) => {
  highlight.value = null
  hovered.value = null
  verdictOpen.value = false
  rawLine.value = null
  void store.loadPage(kb, work, page)
}, { immediate: true })

// an answer for another page, still on screen while this one loads, is not shown as this one: matched by the request it
// answers, not by its fields, so a row that named another knowledge base than its address could not hang the view
const shown = computed(() => store.pageOf(props.kb, props.work, props.page))
useViewName(() => (shown.value ? `${shown.value.title} p. ${shown.value.pdf_page}` : null))
// "as served" (the operator, 21 Nov: quoted is a subset of readable): the readable view with every block never quoted greyed and
// every quoted one in the form the search and the chat quote, the page's chunks drawn across them (W4), asked for when it is
// switched on. Where the page serves something else in its reading's place, nothing of the reading is served, and it says so
const asServed = ref(false)
const servedBy = computed(() => shown.value?.ladder?.served_by ?? null)
const chunks = computed(() => store.chunksOf(props.kb, props.work, props.page))
const servedMode = computed(() => asServed.value && mode.value === 'readable' && !recallId.value && !servedBy.value)
watch(() => [servedMode.value, props.kb, props.work, props.page] as const, ([on, kb, work, page]) => {
  if (on) void store.loadChunks(kb, work, page)
}, { immediate: true })
const chunkHintOpen = ref(false)
const chunksShare = computed(() => chunks.value?.chunks.some(chunk => chunk.overlap > 0) ?? false)
const firstChunk = computed(() => chunks.value?.chunks.find(chunk => chunk.start !== null) ?? null)
const lastChunk = computed(() => [...(chunks.value?.chunks ?? [])].reverse().find(chunk => chunk.start !== null) ?? null)
const imageUrl = computed(() => pageImageUrl(props.kb, props.work, props.page))

// A judgement recalled on the page (181.a, the operator: "you see what the old judge looked like, applied to the page"): the
// address names it, `?judgement=<reading key>:<version>:<again>`, so it can be sent. While one is recalled the analysis
// shows the reading it judged with its findings, framed and marked in the overlay colour; the record above stays standing.
const recallId = computed(() => (typeof address.query.judgement === 'string' && address.query.judgement ? address.query.judgement : null))

// A person's verdict from here (213.b): offered only where the app was started with --allow-verdicts, and only on the
// standing reading, never on a recalled judgement; once its export has finished the page is asked again, in place
const verdictStore = useVerdictStore()
void verdictStore.loadForm()
const verdictsTaken = computed(() => Boolean(verdictStore.form?.enabled) && !recallId.value)
function verdictRecorded(): void {
  verdictOpen.value = false
  void store.reloadPage(props.kb, props.work, props.page)
}
const recalled = computed(() => (recallId.value ? store.recallOf(props.kb, props.work, props.page, recallId.value) : null))
watch(() => [props.kb, props.work, props.page, recallId.value] as const, async ([kb, work, page, judgement]) => {
  if (!judgement) return
  highlight.value = null
  hovered.value = null
  mode.value = 'readable'
  await store.loadRecall(kb, work, page, judgement)
  await nextTick()
  const element = analysis.value?.$el as HTMLElement | undefined
  element?.scrollIntoView?.({ block: 'start' })
}, { immediate: true })
// what the analysis shows: the reading the page shows, or the recalled one; the image it was read from sizes its frames
const analysisReading = computed(() => (recallId.value ? recalled.value?.reading ?? null : shown.value?.reading ?? null))
const analysisRaw = computed(() => (recallId.value ? recalled.value?.raw ?? null : shown.value?.raw ?? null))
const analysisSize = computed(() => (recallId.value ? recalled.value?.image_size : shown.value?.trace?.image_size) ?? [])
const standing = computed(() => ({ name: 'page', params: { kb: props.kb, work: props.work, page: props.page } }))
function recallLink(recall: string) {
  return { ...standing.value, query: { judgement: recall } }
}

function choose(chosen: Mode): void {
  mode.value = chosen
  rawLine.value = null
}

// every page opens on its reading, a page served from its text layer too (227.a, the operator: a control used again and again never
// moves; the head says what is served). A page that serves something else in its reading's place shows that text in its
// coverage's "text served" fold (21 Nov), the quoted tab gone into "as served"
watch(shown, page => {
  if (page) choose('readable')
})
// the route in its parts as the API parts it (184): "noted · vision reading · claude-sonnet-5-5 · page/1 · validator page/1.2"
const routeSaid = computed(() => (shown.value
  ? [shown.value.route_level, shown.value.route_source, ...(shown.value.route_reader ?? [])].filter(Boolean).join(' · ') || shown.value.route
  : ''))
// the reading shown among the page's readings, by the numbers the API gives them: "reading 2 of 2"
const readingOf = computed(() => {
  const attempts = shown.value?.attempts ?? []
  const current = attempts.find(attempt => attempt.shown)
  return current ? `reading ${current.number} of ${attempts.length}` : ''
})
// A page opens on its first finding (decision 186, the operator: "can already be focused right on entry"): the block
// the address names (`?focus=b05`, as the Issues' links carry it), else the API's first in reading order, framed on the
// image and brought into view in the reading's own pane, so the record above it never moves. A page without one opens at
// its top.
watch(shown, async page => {
  if (!page || recallId.value) return
  const named = typeof address.query.focus === 'string' && address.query.focus ? address.query.focus : null
  const focus = named ?? page.focus
  if (!focus) return
  highlight.value = focus
  await nextTick()
  readingBlocks.value?.scrollToBlock(focus, true)
})
// where everything is fine nothing is printed: a class that did not move and a first attempt say nothing
const classMoved = computed(() => shown.value?.trace && shown.value.trace.class_when_collected !== shown.value.trace.class_now)
// a reading file that is no longer what was checked is said in the line, in the core's word and what it means; a whole
// file, or a page without a reading, says nothing (69.a: a tampered reading found by its hash, a deleted one by its gap)
const INTEGRITY_SAYS: Record<string, string> = {
  tampered: 'the reading file differs from the text that was checked',
  missing: 'the reading file is gone',
}
const readingChanged = computed(() => !!shown.value && shown.value.integrity in INTEGRITY_SAYS)
// a person's accept or reject decides what is served (the API's `person`, as the core's `human_standing` decides), and any
// verdict settles a page the check listed to look at (`listed_state`, 211.a): then their line comes first and the check's
// state recedes, kept and named as the check's; a note on a page the check passed changes nothing, so the state keeps its place
const personDecides = computed(() => isDecided(shown.value?.listed_state)
  || shown.value?.person?.standing === 'accepted' || shown.value?.person?.standing === 'rejected')
const headOrder = computed(() => (personDecides.value ? ['person', 'state'] : ['state', 'person']))
// What the pipeline did stands in the Reading History; what was tried beside it stands in the Lab below, labelled, never
// served, nothing deleted (decision 150.a, the operator: "save everything, but keep it apart"): a prototype's judgement, and a judge asked
// again. Read from the export's own fields, `counts`, `again` and `version_state`; a judgement that counts is never the Lab's.
function inLab(judgement: Judgement): boolean {
  return !judgement.counts && (judgement.again > 0 || judgement.version_state === 'prototype')
}

// each keeps its place in the export's list as its name, the one that counts first, the rest by date
interface Listed {
  judgement: Judgement
  at: number
}

function byDate(a: Listed, b: Listed): number {
  return (a.judgement.stored_at ?? '').localeCompare(b.judgement.stored_at ?? '')
}

function pipelineJudgements(judgements: Judgement[]): Listed[] {
  const listed = judgements.map((judgement, at) => ({ judgement, at })).filter(one => !inLab(one.judgement))
  return [...listed.filter(one => one.judgement.counts), ...listed.filter(one => !one.judgement.counts).sort(byDate)]
}

// the readings the pipeline bought: the one shown first, the earlier ones below it, newest first (the operator, 2026-11-10). A reading
// a reader prototype made (210.a, the API's `prototype`) is never the pipeline's: it stands in the Lab, never in the history
const pipelineAttempts = computed(() => (shown.value?.attempts ?? []).filter(attempt => !attempt.prototype))
const attemptsInOrder = computed(() => {
  const attempts = pipelineAttempts.value
  return [...attempts.filter(attempt => attempt.shown), ...attempts.filter(attempt => !attempt.shown).reverse()]
})
const prototypeReadings = computed(() => (shown.value?.attempts ?? []).filter(attempt => attempt.prototype))

// every judgement tried beside the pipeline, by the reading it judged, in the history's order of readings; then every
// judgement of a reader prototype's reading, which is the Lab's whole
const lab = computed(() => [
  ...attemptsInOrder.value.flatMap(attempt => attempt.judgements
    .map((judgement, at) => ({ judgement, at }))
    .filter(one => inLab(one.judgement))
    .sort(byDate)
    .map(one => ({ ...one, attempt }))),
  ...prototypeReadings.value.flatMap(attempt => attempt.judgements
    .map((judgement, at) => ({ judgement, at }))
    .sort(byDate)
    .map(one => ({ ...one, attempt }))),
])
// a reader prototype's reading no judge has judged yet: its own row, so the Lab still names it
const unjudgedPrototypes = computed(() => prototypeReadings.value.filter(attempt => !attempt.judgements.length))

// a Lab row's reading in words: "reading 2, shown here", and for a reader prototype's "reading 3, page/2 (prototype), never
// served", as line 1 names it (210.a)
function labReadingOf(attempt: Attempt): string {
  const kept = attempt.prototype ? `, ${attempt.reader_version ?? 'a reader'} (prototype), never served` : ''
  return `reading ${attempt.number}${attempt.shown ? ', shown here' : ''}${kept}`
}

// what the history and the Lab hold, in their fold's title: "2 readings · shown: reading 2 · 1 judgement counts"
const historySaid = computed(() => {
  const attempts = pipelineAttempts.value
  const current = attempts.find(attempt => attempt.shown)
  const counting = attempts.flatMap(attempt => attempt.judgements).filter(judgement => judgement.counts).length
  return [counted(attempts.length, 'reading'), current ? `shown: reading ${current.number}` : '',
    counting ? `${counted(counting, 'judgement')} ${noun(counting, 'counts', 'count')}` : ''].filter(Boolean).join(' · ')
})
// "1 reading and 4 judgements tried beside the pipeline, never served"
const labSaid = computed(() => `${[prototypeReadings.value.length ? counted(prototypeReadings.value.length, 'reading') : '',
  lab.value.length ? counted(lab.value.length, 'judgement') : ''].filter(Boolean).join(' and ')} tried beside the pipeline, never served`)

// the fold that holds the recalled judgement's row stands open, so the row it came from can be seen
const recallInLab = computed(() => lab.value.some(one => one.judgement.recall === recallId.value))
const historyHoldsRecall = computed(() => attemptsInOrder.value.some(attempt => holdsRecall(attempt.judgements)))
function holdsRecall(judgements: Judgement[]): boolean {
  return judgements.some(judgement => judgement.recall === recallId.value && !inLab(judgement))
}

// a page's readings over time stand where there is more than one, a choice was recorded, a reading was judged more than
// once by the pipeline, or the Lab names a reading: how a page healed, and how its judges differed (147.a)
const history = computed(() => {
  const attempts = attemptsInOrder.value
  const judgedAgain = attempts.some(attempt => pipelineJudgements(attempt.judgements).length > 1)
  if (!(attempts.length > 1 || shown.value?.chosen || judgedAgain || lab.value.length || unjudgedPrototypes.value.length)) return null
  return attempts
})

// a person's verdicts on one reading, beneath its judgements
function peopleOf(readingKey: string): PersonVerdict[] {
  return (shown.value?.human ?? []).filter(person => person.reading_key === readingKey)
}

// a pipeline judgement's role in one word: the one that counts, or one that does not
function roleOf(judgement: Judgement): { word: string, part: string } {
  return judgement.counts ? { word: 'counts', part: 'counts' } : { word: 'not counted', part: 'uncounted' }
}

// a Lab judgement's kind in one word: a judge asked again, or a prototype's
function labKindOf(judgement: Judgement): { word: string, part: string } {
  if (judgement.again) return { word: 'asked again', part: 'again' }
  // on a reader prototype's reading even a judge that counts elsewhere counts for nothing here
  return judgement.version_state === 'prototype' ? { word: 'prototype', part: 'prototype' } : { word: 'not counted', part: 'uncounted' }
}

// a folded reading's judgements in one line: "1 judgement: judge/1 counts · 3 in the Lab"
function judgementsWord(judgements: Judgement[]): string {
  const kept = judgements.filter(judgement => !inLab(judgement))
  const tried = judgements.length - kept.length
  const counting = kept.filter(judgement => judgement.counts).map(judgement => `${judgement.version ?? 'judge'} counts`)
  const others = kept.length - counting.length
  const head = kept.length
    ? `${counted(kept.length, 'judgement')}: ${[...counting, others ? `${others} not counted` : ''].filter(Boolean).join(' · ')}`
    : ''
  return [head, tried ? `${tried} in the Lab` : ''].filter(Boolean).join(' · ')
}

// a judgement's findings in a few words: how many, the severity of those that stand, and how many the core found void, so a
// row shows a minor finding under an ok verdict without opening the page (line 1's check-along on finance p. 94):
// "1 finding: minor", "2 findings: 1 major, 1 minor", "1 finding: void"
function findingsWord(judgement: Judgement): string {
  const all = judgement.findings.length
  if (all === 0) return 'no findings'
  const standing = judgement.findings.filter(finding => !finding.void)
  const nothing = all - standing.length
  const severities = [...new Set(standing.map(finding => finding.severity ?? 'unrated'))]
    .map(severity => ({ severity, count: standing.filter(finding => (finding.severity ?? 'unrated') === severity).length }))
  const parts = [...severities.map(one => (all === 1 ? one.severity : `${one.count} ${one.severity}`)),
    nothing ? (all === 1 ? 'void' : `${nothing} void`) : '']
  return `${counted(all, 'finding')}: ${parts.filter(Boolean).join(', ')}`
}

// stage 2's figures as a reader says them: a share to three places
function share(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toFixed(3) : '?'
}

// The raw text with its lines numbered as the validator counts them (228.a, the operator on accounting p. 338: "line 86? then please line numbers in the read-only editor too"): line 1 is the front matter's first `---`. The numbers stand in a gutter beside the
// text, never in it, so the text copied is the text stored. A validator's error opens it at its line, marked.
const rawText = ref<HTMLElement | null>(null)
const rawLines = computed(() => (analysisRaw.value ?? '').split('\n'))
// The lines a validator's error names, marked as a compiler marks them (line 1's A.a, 18 Nov): the whole block the API says
// it names (`lines`), since the validator names the line a block opens on while what it found may stand lines below, and
// the fault's own line strongest: the one page/1.4 names in its message (`at_line`), else the line the error names. An
// error a person has looked at marks its lines quietly, as its entry above recedes; where two errors meet on a line, the
// stronger mark stands.
type LineMark = 'error-looked' | 'error-block' | 'error-named'
const LINE_MARK_RANK: Record<LineMark, number> = { 'error-looked': 0, 'error-block': 1, 'error-named': 2 }
const errorLines = computed(() => {
  const marks = new Map<number, LineMark>()
  for (const error of analysisReading.value?.error_places ?? []) {
    if (!error.line) continue
    const exact = error.at_line ?? error.line
    const [first = error.line, last = first] = error.lines ?? []
    const named = new Set([...Array.from({ length: last - first + 1 }, (_, at) => first + at), exact])
    for (const line of named) {
      const kind: LineMark = error.looked ? 'error-looked' : line === exact ? 'error-named' : 'error-block'
      const had = marks.get(line)
      if (!had || LINE_MARK_RANK[kind] > LINE_MARK_RANK[had]) marks.set(line, kind)
    }
  }
  return marks
})
async function showRaw(line: number): Promise<void> {
  mode.value = 'raw'
  rawLine.value = line
  await nextTick()
  rawText.value?.querySelector(`[data-line="${line}"]`)?.scrollIntoView?.({ block: 'center', behavior: 'auto' })
}

// every click brings the block into view, also from the raw text and also a second time: the scroll is the click's own
async function showBlock(id: string): Promise<void> {
  mode.value = 'readable'
  highlight.value = id
  await nextTick()
  readingBlocks.value?.scrollToBlock(id)
}

/**
 * The frame of the block on show: the one under the pointer, else the one chosen. Its box is the reader's claim in pixels
 * of the image it received, so it is placed in percent of that image and scales with the picture. A block without a box of
 * its own that names the block it is about (`of`), such as a figure's description, which the reader wrote and the page
 * does not print, frames that block instead, dashed and labelled as such: "b05 describes b03" (the operator, 10 Nov). A block
 * without either draws no frame.
 */
const box = computed(() => {
  const id = hovered.value ?? highlight.value
  const blocks = analysisReading.value?.blocks ?? []
  const block = blocks.find(candidate => candidate.id === id)
  const [width, height] = analysisSize.value
  if (!block || !width || !height) return null
  const target = block.bbox ? block : blocks.find(candidate => candidate.id === block.attrs.of && candidate.bbox)
  if (!target?.bbox) return null
  const described = target !== block
  const [x0, y0, x1, y1] = target.bbox
  return {
    id: block.id,
    described,
    label: described ? `${block.id} ${block.block_class === 'description' ? 'describes' : 'is about'} ${target.id}` : block.id,
    style: {
      left: `${x0 / width * 100}%`,
      top: `${y0 / height * 100}%`,
      width: `${(x1 - x0) / width * 100}%`,
      height: `${(y1 - y0) / height * 100}%`,
    },
  }
})

// The original's pane as tall as the window shows beneath its top, and never more than 85 % of the window: where the record
// above it is short, as with the coverage folded to one line (21 Nov), a pane of 85 % reached past the window's foot, and a
// frame low on the page stood there, out of the window and out of the pane's own reach (found by the browser check of
// Kelly p. 7). Measured again as the window scrolls or changes size; a pane low in the window keeps a room of its own.
const PANE_LEAST = 240
const paneRoom = ref<number | null>(null)
function measurePane(): void {
  const frame = pane.value
  if (!frame) return
  const top = Math.max(0, frame.getBoundingClientRect().top)
  paneRoom.value = Math.max(PANE_LEAST, Math.min(window.innerHeight * 0.85, window.innerHeight - top - 8))
}
let measuring = 0
function onWindowMoved(): void {
  cancelAnimationFrame(measuring)
  measuring = requestAnimationFrame(measurePane)
}
onMounted(() => {
  window.addEventListener('scroll', onWindowMoved, { passive: true })
  window.addEventListener('resize', onWindowMoved)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(measuring)
  window.removeEventListener('scroll', onWindowMoved)
  window.removeEventListener('resize', onWindowMoved)
})
watch(pane, () => nextTick(measurePane))

// A frame outside the visible part of the original brings it into view: only the original's own pane scrolls, never the
// window, so the reading under the pointer stays where it is.
watch(box, async () => {
  await nextTick()
  measurePane()
  await nextTick()
  const frame = pane.value
  const element = boxElement.value
  if (!frame || !element) return
  const top = element.offsetTop
  if (top < frame.scrollTop || top + element.offsetHeight > frame.scrollTop + frame.clientHeight) {
    frame.scrollTo?.({ top: Math.max(0, top - frame.clientHeight / 4) })
  }
})
</script>

<template>
  <section class="page-view">
    <!-- the record in the standard width, the analysis below it alone wide (decision 183) -->
    <RecordZone>
      <p class="trail">
        <RouterLink to="/sources">Sources</RouterLink>
        ›
        <RouterLink :to="{ name: 'work', params: { kb, work } }">{{ shown?.title ?? work }}</RouterLink>
        <KnowledgeBaseMark v-if="shown" :kb="shown.knowledge_base" />
      </p>
      <ApiFailure v-if="detailError" :error="detailError" @retry="store.loadPage(kb, work, page)" />
      <LoadingLine v-else-if="!shown" />
      <template v-else>
        <!-- previous and next first, in boxes of one width, so they stay under the pointer page after page; the title, whose
             length varies with the printed number, follows them (the operator, 10 Nov) -->
        <header class="page-head">
          <PagerLinks
            :previous="shown.previous_page !== null ? { to: { name: 'page', params: { kb, work, page: shown.previous_page } }, label: `p. ${shown.previous_page}` } : null"
            :next="shown.next_page !== null ? { to: { name: 'page', params: { kb, work, page: shown.next_page } }, label: `p. ${shown.next_page}` } : null"
            width="6.5rem"
            label="Previous and next page"
          >
            <PageJump :kb="kb" :work="work" />
          </PagerLinks>
          <h1 class="view-title">
            PDF page {{ shown.pdf_page }}<span v-if="shown.printed_label" class="printed"> · printed {{ shown.printed_label }}</span>
          </h1>
          <!-- a recalled judgement (181.a) says so in the top row, in the overlay colour, its glyph and words with it, and the
               way back beside it -->
          <p v-if="recallId" class="recall-chip" data-part="recall-chip">
            <AppIcon name="recalled" />
            <span>Recalled: {{ recalled ? recalled.said : recallError ? 'a judgement this page does not have' : 'a judgement' }}</span>
            <RouterLink :to="standing" class="show-standing" data-part="show-standing">Show standing</RouterLink>
          </p>
          <AppButton v-if="verdictsTaken" size="compact" :active="verdictOpen" data-part="give-verdict" @click="verdictOpen = !verdictOpen">
            Give a verdict
          </AppButton>
        </header>

        <!-- a page that is not plainly ok says so in one plain sentence first, the API's (the operator on accounting p. 524: the head
             "reads as code"); its chips follow -->
        <p v-if="shown.said" class="said" data-part="said">{{ shown.said }}</p>
        <!-- a page no reader has read (V2.a): its state, what serves it, its own ladder, the text served and its image; nothing
             of a reading, which it has not -->
        <UnreadPage v-if="!shown.read" :page="shown" :image-url="imageUrl" />
        <template v-else>
        <!-- the page's record as labelled lines (decision 184, the operator: "I would rather have this line with labels"), the labels in
             one column and the values in another (the operator, 11 Nov): its state and a person's verdict, its category where it is not
             content, its route and why, its reading, and its findings, each block a jump to it. Every word is the API's, and
             each is said once: the person's reason and note stand in their card and beneath the block they judged -->
        <!-- the label column as wide as the longest label the record has ("A person:", "Category:", "Findings:"), plus one
             for the bold, so the values stand in one place from page to page -->
        <LabelledLines class="summary page-facts" data-part="page-facts" :label-chars="10">
          <!-- the verdict that decides first: a person's before the check's state, which then recedes, its glyph and word kept
               (the operator, 11 Nov: red "issue" beside green "accepted"). The line is named the check's, so a page a person settled
               (211.a) still says what the check found, never hidden, and never read as the person's -->
          <template v-for="line in headOrder" :key="line">
            <LabelledLine v-if="line === 'state'" label="Check" :class="{ overruled: personDecides }">
              <StateMark :state="shown.check.state" :quiet="personDecides" />
              <ReasonList v-if="shown.check.reasons.length" :reasons="shown.check.reasons" />
              <span v-if="readingChanged" class="reading-changed">
                <IntegrityMark :state="shown.integrity" />: {{ INTEGRITY_SAYS[shown.integrity] }}
              </span>
            </LabelledLine>
            <LabelledLine v-else-if="shown.person || shown.protected" :label="verdictBy(shown.person)">
              <PersonStanding :mark="shown.person" />
              <!-- a person checked the page: no re-read without a reason (191.a) -->
              <span v-if="shown.protected" class="protected" data-part="protected"><AppIcon name="protected" /> protected</span>
            </LabelledLine>
          </template>
          <!-- a person's reset (191.a): the reading discarded, the text layer served until a new reading is due -->
          <LabelledLine v-if="shown.reset" label="Reset" data-part="reset">
            <span>{{ `a person reset the page${shown.reset.reason ? `: ${shown.reset.reason}` : ''}` }}</span>
            <HumanTime v-if="shown.reset.given_at" :at="shown.reset.given_at" />
          </LabelledLine>
          <LabelledLine v-if="shown.category && shown.category !== 'content'" label="Category">
            <CategoryMark :category="shown.category" :said="shown.category_said" :kind="shown.page_kind" />
          </LabelledLine>
          <LabelledLine label="Route">
            <HoverCard
              title="Route"
              :rows="[{ label: 'level', value: shown.route_level }, { label: 'source', value: shown.route_source },
                      { label: 'reader', value: shown.route_reader?.join(', ') }, { label: 'why', value: shown.route_why }]"
            >
              <span class="route">{{ routeSaid }}</span>
            </HoverCard>
          </LabelledLine>
          <!-- the provider's own words where a call failed, else the route's why where nothing else here says it (`why_line`) -->
          <LabelledLine v-if="shown.why_line || shown.trace!.error_message" label="Why">
            <span v-if="shown.trace!.error_message" class="error-message">{{ shown.trace!.error_message }}</span>
            <span v-else class="route-why">{{ shown.why_line }}</span>
          </LabelledLine>
          <LabelledLine label="Reading">
            <span v-if="readingOf" class="reading-part">{{ readingOf }}</span>
            <span v-if="classMoved" class="class-move reading-part">{{ shown.trace!.class_when_collected }} → {{ shown.trace!.class_now }}</span>
            <span v-if="shown.trace!.attempt > 0" class="retry reading-part">retry {{ shown.trace!.attempt }}</span>
            <span class="cost reading-part" data-part="reading-cost">{{ readingCost(shown.trace!.cost_usd) }}</span>
            <span v-if="!shown.image.available" class="image-mark missing reading-part">
              <AppIcon name="status-unknown" /> original not available
            </span>
            <span v-else-if="shown.image.same_as_read" class="image-mark same reading-part">
              <AppIcon name="status-ok" /> image as read
            </span>
            <span v-else class="image-mark differs reading-part">
              <AppIcon name="status-error" /> image differs from the one read
            </span>
          </LabelledLine>
          <!-- what the findings come to (184): each block a jump, with a finding's own look (the operator, 12 Nov, on accounting p. 524:
               "the red flag or red text ... so that they catch the eye at once by their colour"): the flag and the gravest
               severity of its findings that stand, in that severity's role, as beneath the block; where code voided them all,
               the flag and the ruling recede. Then what that means for the page, as the API says it -->
          <LabelledLine v-if="shown.findings_at?.length" class="found-at" label="Findings">
            <span v-for="one in shown.findings_at" :key="one.block" class="finding-at" :class="one.severity ?? 'void'" :data-finding-at="one.block">
              <AppIcon name="finding" class="finding-mark" />
              <AppButton variant="link" :data-jump="one.block" @click="showBlock(one.block)">{{ one.block }}</AppButton>
              <span v-if="one.severity" class="finding-severity" :data-severity="one.severity">{{ one.severity }}</span>
              <span v-else class="finding-said" :data-said="one.said">{{ one.said }}</span>
            </span>
            <span v-if="shown.findings_outcome" class="findings-outcome" data-part="findings-outcome">{{ `· ${shown.findings_outcome}` }}</span>
          </LabelledLine>
          <!-- the page's own ladder (V2.a): its text layer, the text served, keyword search, its chunks, its reading; the text
               served folded until asked for -->
          <LabelledLine v-if="shown.ladder" label="Coverage" data-part="page-coverage"><PageLadderLines :ladder="shown.ladder" /></LabelledLine>
        </LabelledLines>
        <VerdictDialog v-if="verdictsTaken && verdictOpen && verdictStore.form" :page="shown" :knowledge-base="kb" :work="work"
                       :form="verdictStore.form" @close="verdictOpen = false" @recorded="verdictRecorded" />

        <!-- the findings about the page as a whole, a person's verdict on the whole page that applies to this reading the last
             voice (178.a) -->
        <FindingList
          v-if="shown.page_findings.length"
          class="page-findings"
          :findings="shown.page_findings"
          :people="shown.human.filter(person => person.applies && !person.block)"
          names-blocks
        />

        <!-- every reading bought for the page (the operator, 2026-11-10: "retries should fold open"): the one shown here first and
             open, the earlier ones below it, newest first, folded to one line each. Opened, a reading's pipeline judgements
             stand in one table, the one that counts first, and a person's verdicts beneath; what was tried beside the
             pipeline stands in the Lab below (150.a). The others' text stays in the private store, so they stand by their record -->
        <!-- a fold, folded by default and kept as the reader leaves it (decision 183), its title saying what it holds -->
        <FoldSection v-if="history" class="history" remember="page.history" :open="historyHoldsRecall" title="Reading History" :count="historySaid">
          <!-- the readings' lines keep their columns and scroll in their own box on a narrow screen (159.a) -->
          <div class="readings ruled scroll-x">
            <!-- each reading a fold (179), its line a grid in the fold's title, so its columns align from one reading to the next -->
            <FoldSection
              v-for="attempt in history"
              :key="attempt.reading_key"
              class="reading-entry"
              :class="{ current: attempt.shown }"
              :open="attempt.shown || holdsRecall(attempt.judgements)"
              :data-reading="attempt.reading_key"
            >
              <template #title>
                <span class="reading-line">
                  <span class="reading-number">reading {{ attempt.number }}</span>
                  <span class="purpose" data-part="purpose">{{ attempt.purpose ?? '' }}</span>
                  <span>{{ attempt.model }}</span>
                  <span class="secondary">{{ attempt.mode ?? '' }}</span>
                  <span class="secondary">{{ attempt.class_now }}</span>
                  <!-- what the check made of this reading; the verdict only where the state does not already say it -->
                  <span class="attempt-check">
                    <template v-if="attempt.check">
                      <StateMark :state="attempt.check.state" />
                      <span v-if="attempt.check.verdict && attempt.check.state !== 'ok'" class="verdict"> · judged {{ attempt.check.verdict }}</span>
                      <span v-if="attempt.check.came_from" class="verdict"> · {{ attempt.check.came_from }}</span>
                    </template>
                    <span v-else class="not-checked">not checked</span>
                  </span>
                  <span class="secondary"><HumanTime :at="attempt.stored_at" /></span>
                  <!-- the line's last column holds the rest, so nothing falls into a row of its own under the marker -->
                  <span class="reading-tail">
                    <span v-if="attempt.shown" class="shown-here">shown here</span>
                    <span class="judgements-word" data-part="judgements">{{ judgementsWord(attempt.judgements) }}</span>
                    <IntegrityMark v-if="attempt.shown && readingChanged" :state="shown.integrity" />
                    <span v-if="attempt.deviation" class="deviation">{{ attempt.deviation }}</span>
                  </span>
                </span>
              </template>
              <div class="reading-body">
                <!-- the reader's own count and cell stand here, folded: the line numbers the page's readings across readers -->
                <p class="secondary" data-part="reader-attempt">
                  {{ [`the reader's attempt ${attempt.attempt}`, attempt.cell ? `cell ${attempt.cell}` : '',
                      attempt.retry_of_number ? `re-read of reading ${attempt.retry_of_number}` : '',
                      readingCost(attempt.cost_usd ?? null)].filter(Boolean).join(' · ') }}
                </p>
                <p class="hash secondary">reading key {{ attempt.reading_key }}</p>
                <!-- why the reading stands as it does (the operator, 18 Nov: "reading 2 · malformed · issue" said what, not why):
                     the check's reasons in the core's words, and the validator's own messages where the reading failed its
                     format check, which say it also where no check ran on the reading, as on one its format retry replaced -->
                <LabelledLines v-if="attempt.check?.reasons.length || attempt.format_errors.length" class="attempt-why" data-part="attempt-why">
                  <LabelledLine v-if="attempt.check?.reasons.length" label="Why">
                    <span data-part="attempt-reasons">{{ attempt.check.reasons.join(' · ') }}</span>
                  </LabelledLine>
                  <LabelledLine v-if="attempt.format_errors.length" label="Format check">
                    <ul class="format-errors">
                      <li v-for="(error, at) in attempt.format_errors" :key="at" data-part="format-error">
                        <AppIcon name="status-error" /> {{ error }}
                      </li>
                    </ul>
                  </LabelledLine>
                </LabelledLines>
                <!-- its pipeline judgements in aligned columns (147.a): the one that counts first, then the rest by date; the role
                     a column of its own, so the eye can run down it; what does not count recedes -->
                <DataTable v-if="pipelineJudgements(attempt.judgements).length" table-class="judgements ruled">
                  <template #head>
                    <tr>
                      <th>Version</th>
                      <th>Role</th>
                      <th>Verdict → outcome</th>
                      <th>The judge's own</th>
                      <th>Findings</th>
                      <th>Model · mode</th>
                      <th class="number">USD</th>
                      <th>Stored</th>
                      <th />
                    </tr>
                  </template>
                  <tbody>
                    <tr
                      v-for="{ judgement, at } in pipelineJudgements(attempt.judgements)"
                      :key="at"
                      class="judgement"
                      :class="{ uncounted: !judgement.counts, 'recalled-source': judgement.recall === recallId }"
                      :data-judgement="`${attempt.number}/${at}`"
                    >
                      <td>
                        <RouterLink v-if="judgement.version" class="judge-version" :to="{ name: 'prompts', query: { version: judgement.version } }">
                          {{ judgement.version }}
                        </RouterLink>
                        <span v-else class="judge-version">judge</span>
                      </td>
                      <td><span class="badge" :data-part="roleOf(judgement).part">{{ roleOf(judgement).word }}</span></td>
                      <td class="judgement-verdict">{{ judgement.verdict }} → {{ judgement.outcome }}</td>
                      <td class="secondary">{{ judgement.judge_outcome && judgement.judge_outcome !== judgement.outcome ? judgement.judge_outcome : '' }}</td>
                      <td class="judgement-findings">{{ findingsWord(judgement) }}</td>
                      <td class="secondary">{{ [judgement.model, judgement.mode].filter(Boolean).join(' · ') }}</td>
                      <td class="secondary number">{{ typeof judgement.cost_usd === 'number' ? usd(judgement.cost_usd) : '' }}</td>
                      <td class="secondary"><HumanTime :at="judgement.stored_at" /></td>
                      <td class="recall-cell">
                        <span v-if="judgement.recall === recallId" class="recall-current" data-part="recalled-here"><AppIcon name="recalled" /> on the page</span>
                        <RouterLink v-else-if="judgement.recall" :to="recallLink(judgement.recall)" class="recall-link" data-part="recall">show on the page</RouterLink>
                      </td>
                    </tr>
                  </tbody>
                </DataTable>
                <p v-else class="secondary">{{ attempt.judgements.length ? 'judged in the Lab alone' : 'no judge has judged this reading' }}</p>
                <PersonVerdictList v-if="peopleOf(attempt.reading_key).length" class="reading-people" :people="peopleOf(attempt.reading_key)" names-blocks />
              </div>
            </FoldSection>
          </div>
          <p v-if="shown.chosen" class="chosen">
            Chosen <HumanTime :at="shown.chosen.chosen_at" /> by run {{ shown.chosen.run_id }}: {{ shown.chosen.why }}
          </p>
        </FoldSection>

        <!-- the Lab (150.a): what was tried beside the pipeline on this page, kept and labelled, never served: a prototype's
             judgement, a judge asked again, and a reader prototype's reading with its judgements (210.a). Folded, since the
             history above is what the page went through -->
        <!-- the count set apart from the name, so "Lab 3" never reads as a numbering (179) -->
        <FoldSection v-if="lab.length || unjudgedPrototypes.length" class="lab" remember="page.lab" :open="recallInLab" title="Lab" :count="labSaid">
          <DataTable table-class="judgements ruled">
            <template #head>
              <tr>
                <th>Reading</th>
                <th>Version</th>
                <th>Kind</th>
                <th>Verdict → outcome</th>
                <th>The judge's own</th>
                <th>Findings</th>
                <th>Model · mode</th>
                <th class="number">USD</th>
                <th>Stored</th>
                <th />
              </tr>
            </template>
            <tbody>
              <template v-for="{ judgement, at, attempt } in lab" :key="`${attempt.reading_key}/${at}`">
              <tr
                class="judgement lab-judgement"
                :class="{ 'recalled-source': judgement.recall === recallId }"
                :data-judgement="`${attempt.number}/${at}`"
              >
                <td class="secondary" :data-reader="attempt.prototype ? attempt.reader_version : null">{{ labReadingOf(attempt) }}</td>
                <td>
                  <RouterLink v-if="judgement.version" class="judge-version" :to="{ name: 'prompts', query: { version: judgement.version } }">
                    {{ judgement.version }}
                  </RouterLink>
                  <span v-else class="judge-version">judge</span>
                </td>
                <td><span class="badge" :data-part="labKindOf(judgement).part">{{ labKindOf(judgement).word }}</span></td>
                <td>{{ judgement.verdict }} → {{ judgement.outcome }}</td>
                <td class="secondary">{{ judgement.judge_outcome && judgement.judge_outcome !== judgement.outcome ? judgement.judge_outcome : '' }}</td>
                <td>{{ findingsWord(judgement) }}</td>
                <td class="secondary">{{ [judgement.model, judgement.mode].filter(Boolean).join(' · ') }}</td>
                <td class="secondary number">{{ typeof judgement.cost_usd === 'number' ? usd(judgement.cost_usd) : '' }}</td>
                <td class="secondary"><HumanTime :at="judgement.stored_at" /></td>
                <td class="recall-cell">
                  <span v-if="judgement.recall === recallId" class="recall-current" data-part="recalled-here"><AppIcon name="recalled" /> on the page</span>
                  <RouterLink v-else-if="judgement.recall" :to="recallLink(judgement.recall)" class="recall-link" data-part="recall">show on the page</RouterLink>
                </td>
              </tr>
              <!-- the rules a judge proposed for the reader (202.a), right beneath the judgement that proposed them, read-only -->
              <tr v-if="judgement.reader_rules?.length" class="lab-rules" :data-rules="`${attempt.number}/${at}`">
                <td colspan="10"><ReaderRuleList :rules="judgement.reader_rules" /></td>
              </tr>
              </template>
              <tr v-for="attempt in unjudgedPrototypes" :key="attempt.reading_key" class="lab-reading" :data-reading="attempt.reading_key">
                <td class="secondary" :data-reader="attempt.reader_version">{{ labReadingOf(attempt) }}</td>
                <td colspan="9" class="secondary">no judge has judged this reading</td>
              </tr>
            </tbody>
          </DataTable>
        </FoldSection>

        <FoldSection class="details" :open="settings.pageDetailsOpen" title="Details" @toggle="settingsStore.setPageDetailsOpen">
          <DetailList>
            <!-- the three stages of the check, each its own row, then a person (the operator: "in the details, all three stages one by one") -->
            <dt>Stage 1 · format</dt>
            <dd data-stage="1">
              at collect {{ shown.trace!.class_when_collected }} · under today's validator {{ shown.trace!.class_now }}
              <span class="secondary">· validator {{ shown.trace!.validator }}</span>
            </dd>
            <dt>Stage 2 · text layer</dt>
            <dd data-stage="2">
              <template v-if="shown.check.stage2">
                <span v-if="shown.check.stage2.has_layer === false">the PDF has no text layer here</span>
                <span v-else>recall {{ share(shown.check.stage2.recall) }} · precision {{ share(shown.check.stage2.precision) }}</span>
                <span class="secondary"> · {{ shown.check.stage2.suspicious ? 'suspicious' : 'not suspicious' }}</span>
                <ul v-if="shown.check.stage2.findings.length" class="stage-list ruled">
                  <li v-for="(finding, at) in shown.check.stage2.findings" :key="at" data-part="stage2-finding">
                    {{ [finding.kind, finding.block, finding.detail, finding.severity].filter(Boolean).join(' · ') }}
                  </li>
                </ul>
                <ul v-if="shown.check.stage2.unverifiable.length" class="stage-list ruled">
                  <li v-for="(block, at) in shown.check.stage2.unverifiable" :key="at" class="secondary" data-part="unverifiable">
                    {{ ['cannot check', block.block, block.cls ? `(${block.cls})` : null].filter(Boolean).join(' ') }}: {{ block.why }}
                  </li>
                </ul>
              </template>
              <span v-else class="secondary">no stage 2 report holds this reading</span>
            </dd>
            <dt>Stage 3 · judge</dt>
            <!-- one fact a line, each named, in the page head's look (the operator, 16 Nov: "purely visual finalizing only"; 221.a) -->
            <dd data-stage="3">
              <LabelledLines :label-chars="8">
                <LabelledLine label="Why" data-part="stage3-why">{{ shown.check.why_judged }}</LabelledLine>
                <LabelledLine v-if="shown.check.verdict" label="Verdict" data-part="stage3-verdict">
                  {{ shown.check.verdict.verdict }}, counts as {{ shown.check.verdict.outcome }}
                  <span v-if="shown.check.verdict.judge_outcome && shown.check.verdict.judge_outcome !== shown.check.verdict.outcome" class="secondary">
                    (the judge's own outcome: {{ shown.check.verdict.judge_outcome }})
                  </span>
                  <span v-if="shown.check.verdict.void" class="secondary"> · {{ shown.check.verdict.void }} void</span>
                </LabelledLine>
                <LabelledLine v-if="shown.check.judge" label="Judge" data-part="stage3-judge">
                  <RouterLink v-if="shown.check.judge.version" :to="{ name: 'prompts', query: { version: shown.check.judge.version } }" data-part="judge-version">
                    {{ shown.check.judge.version }}
                  </RouterLink>
                  <span class="secondary">{{ shown.check.judge.version ? `· ${shown.check.judge.model}` : shown.check.judge.model }}</span>
                </LabelledLine>
              </LabelledLines>
            </dd>
            <dt>{{ shown.human.length && shown.human.every(person => person.by_a_person === false) ? verdictBy(shown.human[0]) : 'A person' }}</dt>
            <dd data-stage="person">
              <PersonVerdictList v-if="shown.human.length" :people="shown.human" names-blocks />
              <span v-else class="secondary">no person has judged this page</span>
            </dd>
            <dt>Reading key</dt>
            <dd class="hash">{{ shown.trace!.reading_key }}</dd>
            <dt>Model</dt>
            <dd>{{ shown.trace!.model }}</dd>
            <dt>Contract</dt>
            <dd>{{ shown.trace!.contract }} · validator {{ shown.trace!.validator }} · form {{ shown.trace!.form }}</dd>
            <template v-if="shown.trace!.error_type">
              <dt>Error</dt>
              <dd>{{ shown.trace!.error_type }}</dd>
            </template>
            <dt>Attempt</dt>
            <dd>{{ shown.trace!.attempt }}</dd>
            <dt>Cost</dt>
            <dd>{{ readingCost(shown.trace!.cost_usd) }}</dd>
            <dt>Stored</dt>
            <dd><HumanTime :at="shown.trace!.stored_at" /></dd>
            <template v-if="shown.trace!.text_sha256">
              <dt>Text sha256</dt>
              <dd class="hash">{{ shown.trace!.text_sha256 }}</dd>
            </template>
            <dt>Image</dt>
            <dd>
              {{ shown.trace!.image_size.join(' × ') }} px · resolution {{ shown.trace!.resolution }} ·
              <span class="hash">{{ shown.trace!.image_sha256 }}</span>
            </dd>
          </DetailList>
        </FoldSection>
        </template>
      </template>
    </RecordZone>

    <!-- the analysis (181.a): the original beside its reading, under its own heading, the one part that takes the wide
         container (183); framed as an overlay while a judgement is recalled -->
    <AnalysisSection v-if="shown && !detailError && shown.read" ref="analysis" :overlay="!!recallId">
      <template #hint>
        <span v-if="!recallId" class="analysis-hint">the image the reader received, beside its reading</span>
        <!-- while a judgement is recalled the analysis says so in its own heading too, the overlay's glyph and words -->
        <span v-else class="analysis-recalled" data-part="analysis-recalled">
          <AppIcon name="recalled" /> recalled, not the standing view: {{ recalled?.said ?? 'a judgement' }}
        </span>
      </template>
      <ApiFailure v-if="recallId && recallError" :error="recallError" @retry="store.loadRecall(kb, work, page, recallId)" />
      <p v-else-if="recalled?.why_not" class="no-reading" data-part="recall-missing">{{ recalled.why_not }}</p>
      <div class="side-by-side">
        <figure class="original">
          <div v-if="shown.image.available" ref="pane" class="original-pane" :style="paneRoom ? { maxHeight: `${paneRoom}px` } : undefined">
            <div class="page-frame">
              <img
                :src="imageUrl"
                :width="shown.image.width ?? undefined"
                :height="shown.image.height ?? undefined"
                :alt="`PDF page ${shown.pdf_page} as the reader received it`"
              >
              <div v-if="box" ref="boxElement" class="block-box" :class="{ described: box.described, recalled: recallId }" :style="box.style" :data-box="box.id">
                <span class="block-box-label">{{ box.label }}</span>
              </div>
            </div>
          </div>
          <p v-else class="image-missing"><AppIcon name="status-unknown" /> {{ shown.image.why_not }}</p>
        </figure>

        <div class="reading">
          <p v-if="!recallId && !shown.reading" class="no-reading">
            {{ shown.integrity === 'missing' ? 'The reading file is gone: there is no reading to show.' : 'No reading came back for this page.' }}
          </p>
          <div class="mode">
            <template v-if="analysisReading">
              <AppButton size="compact" :active="mode === 'readable'" @click="choose('readable')">readable</AppButton>
              <AppButton size="compact" :active="mode === 'raw'" @click="choose('raw')">raw</AppButton>
              <!-- a mode of readable, the standing reading's alone: a recalled judgement serves nothing of its own -->
              <template v-if="mode === 'readable' && !recallId">
                <span v-if="servedBy" class="as-served-off" data-part="as-served-off">
                  <AppIcon name="quoted" /> as served: {{ servedBy }} serves this page in its reading's place, so nothing of the reading is served
                </span>
                <AppButton v-else size="compact" :active="asServed" data-part="as-served" @click="asServed = !asServed">
                  <AppIcon name="quoted" /> as served
                </AppButton>
              </template>
            </template>
          </div>
          <template v-if="analysisReading">
            <!-- the validator's errors, each with the way to its block and to its line in the raw text (228.a); muted, and saying
                 so, where a person has looked, never hidden -->
            <ul v-if="analysisReading.error_places?.length" class="parse-errors ruled" role="alert" data-part="parse-errors">
              <li v-for="(error, at) in analysisReading.error_places" :key="at" :class="{ looked: error.looked }" :data-error="at">
                <AppIcon name="status-error" />
                <span class="error-said">{{ error.said }}</span>
                <AppButton v-if="error.block" variant="link" data-part="error-block" @click="showBlock(error.block)">{{ error.block }}</AppButton>
                <AppButton v-if="error.line" variant="link" data-part="show-raw" @click="showRaw(error.at_line ?? error.line)">show raw</AppButton>
                <span v-if="error.looked" class="error-looked" data-part="error-looked">{{ `· ${lookedSaid(error)}` }}</span>
              </li>
            </ul>
            <!-- a recalled judgement's findings about the page as a whole, in the same voices as beside a block -->
            <FindingList v-if="recalled?.page_findings.length" class="page-findings" :findings="recalled.page_findings" names-blocks />
            <!-- as served: the page's chunks of semantic search, where each begins and what it shares, said above the blocks;
                 a chunk not placed in words, never drawn by guess (W4) -->
            <div v-if="servedMode" class="chunks-head" data-part="chunks-head">
              <ApiFailure v-if="chunksError" :error="chunksError" @retry="store.loadChunks(kb, work, page)" />
              <LoadingLine v-else-if="!chunks" />
              <template v-else>
                <p class="chunks-said">
                  <span>{{ chunks.count_said ?? chunks.said }}</span>
                  <span v-if="chunks.held_back" class="held-back" data-part="held-back">kept: {{ chunks.held_back }}</span>
                  <HintToggle v-if="chunksShare" id="overlap" v-model:open="chunkHintOpen" />
                </p>
                <HintPanel v-if="chunksShare && chunkHintOpen" id="overlap" @close="chunkHintOpen = false">
                  <p class="legend" data-part="overlap-legend">{{ overlapHint(chunks.splitter) }}</p>
                </HintPanel>
                <p v-if="chunks.not_placed" class="not-placed" role="alert" data-part="not-placed"><AppIcon name="status-error" /> {{ chunks.not_placed }}</p>
                <p v-if="firstChunk?.continues_from" class="continues" data-part="continues-from">
                  chunk {{ firstChunk.number }} continues from p. {{ firstChunk.continues_from }}
                </p>
              </template>
            </div>
            <ReadingBlocks
              v-if="mode === 'readable'"
              ref="readingBlocks"
              :blocks="analysisReading.blocks"
              :highlight="highlight"
              :errors="analysisReading.error_places ?? []"
              :as-served="servedMode"
              :chunks="servedMode ? chunks : null"
              @hover="hovered = $event"
              @jump="showBlock"
              @raw="showRaw"
            />
            <p v-if="servedMode && lastChunk?.continues_on" class="continues" data-part="continues-on">
              chunk {{ lastChunk.number }} continues on p. {{ lastChunk.continues_on }}
            </p>
            <pre v-else ref="rawText" class="raw" data-part="raw" :style="{ '--gutter': `${String(rawLines.length).length}ch` }"><span v-for="(line, at) in rawLines" :key="at" class="raw-line" :class="[{ marked: at + 1 === rawLine }, errorLines.get(at + 1)]" :data-line="at + 1" :data-error-line="errorLines.get(at + 1)">{{ at < rawLines.length - 1 ? `${line}\n` : line }}</span></pre>
          </template>
        </div>
      </div>
    </AnalysisSection>
  </section>
</template>

<style scoped>
.trail {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

.trail a,
.details a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover,
.details a:hover {
  text-decoration: underline;
}

.page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm) var(--space-lg);
}

/* the page's title in bold, at the one size every text has (the operator, 11 Nov: "I prefer everything uniform") */
.view-title {
  font-weight: bold;
}

.printed {
  color: var(--color-text-secondary);
}

/* a sentence, held to a line a person reads at once, as the record's values are (`LabelledLines`) */
.said {
  margin-top: var(--space-sm);
  max-width: 100ch;
}

.said + .summary {
  margin-top: var(--space-xs);
}

/* the page's record (184): one labelled line beneath the other, labels and values each in a column (`LabelledLines`) */
.page-facts {
  margin: var(--space-sm) 0 var(--space-sm);
}

/* the reading's facts parted as the route's are, by a quiet dot */
.reading-part + .reading-part::before {
  content: '· ';
  color: var(--color-text-secondary);
}

.protected {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-text-secondary);
}

.route,
.cost,
.image-mark.same {
  color: var(--color-text-secondary);
}

.image-mark {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.image-mark.differs {
  color: var(--color-error);
}

.image-mark.missing,
.image-missing {
  color: var(--color-warning);
}

.image-missing {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.finding-said,
.findings-outcome {
  color: var(--color-text-secondary);
}

/* a block with findings in the head, as a finding beneath its block: the flag and the severity's word carry the role
   together, never the colour alone; a block whose findings code voided recedes */
.finding-at {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.finding-at.major .finding-mark,
.finding-at.major .finding-severity {
  color: var(--color-error);
}

.finding-at.minor .finding-mark,
.finding-at.minor .finding-severity {
  color: var(--color-warning);
}

.finding-at.void .finding-mark {
  color: var(--color-text-secondary);
}

.page-findings {
  margin-bottom: var(--space-xs);
}

.history {
  margin-bottom: var(--space-sm);
}

/* a reading folded to one line, the fold's mark before it: its fields in columns that align from one reading to the
   next; what it was, in the core's words, wraps in its column rather than widening the line */
.reading-line {
  display: grid;
  grid-template-columns: 5rem 15rem minmax(9rem, max-content) 5rem 5rem minmax(10rem, max-content) 7.5rem minmax(0, 1fr);
  align-items: baseline;
  gap: 0 var(--space-md);
  padding: 2px 0;
}

/* the reading this page shows stands in full ink; the others recede */
.reading-entry {
  color: var(--color-text-secondary);
}

.reading-entry.current {
  color: var(--color-text-primary);
}

.reading-body {
  margin-bottom: var(--space-xs);
}

.reading-tail {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-md);
}

.chosen {
  margin-top: 2px;
}

.reading-people {
  margin-top: 2px;
}

/* the Lab: below the history and apart from it, folded to one line that says what it holds */
.lab {
  margin-bottom: var(--space-sm);
}

/* the pipeline's state where a person's accept or reject decides: the whole line recedes, the check's reasons with the
   mark; a changed reading file keeps its error role below, since that is not history */
.overruled :deep(.reasons) {
  color: var(--color-text-secondary);
}

/* a reading file that is no longer what was checked: the mark carries the error role, the sentence beside it too */
.reading-changed {
  color: var(--color-error);
}

.attempt-check {
  white-space: nowrap;
}

.verdict,
.not-checked,
.secondary {
  color: var(--color-text-secondary);
}

.badge {
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 0 var(--space-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

/* the judgement that counts reads first and in full ink; the rest recede, kept in sight */
.judgement:not(.uncounted) .badge {
  color: var(--color-text-primary);
}

tr.judgement.uncounted .judge-version,
tr.judgement.uncounted .judgement-verdict,
tr.judgement.uncounted .judgement-findings {
  color: var(--color-text-secondary);
}

.stage-list {
  list-style: none;
  margin-top: 2px;
}

.details {
  margin-bottom: var(--space-sm);
}

.hash {
  word-break: break-all;
}

/* the original and its reading side by side, each scrolling in a pane of the same height; on a narrow screen one above the other */
/* a recalled judgement (181.a): the overlay's role, the annotation colour, always dashed, its glyph and words with it */
.recall-chip,
.analysis-recalled,
.recall-current {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-annotation);
}

.recall-chip {
  border: 1px dashed var(--color-annotation);
  border-radius: 4px;
  padding: 0 var(--space-sm);
}

.show-standing {
  color: var(--color-accent);
  margin-left: var(--space-sm);
}

.analysis-recalled {
  font-weight: normal;
  margin-left: var(--space-sm);
}

tr.recalled-source {
  outline: 1px dashed var(--color-annotation);
  outline-offset: -1px;
}

.recall-cell {
  white-space: nowrap;
}

.recall-link {
  color: var(--color-accent);
}

.analysis-hint {
  font-weight: normal;
  color: var(--color-text-secondary);
  margin-left: var(--space-sm);
}

.side-by-side {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-md);
  align-items: start;
}

@media (max-width: 900px) {
  .side-by-side {
    grid-template-columns: minmax(0, 1fr);
  }
}

.original-pane {
  position: relative;
  max-height: 85vh;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

/* the frame is exactly the image, so a box placed in percent of it lands on the pixels it names */
.page-frame {
  position: relative;
  border: 1px solid var(--color-border);
  background-color: #ffffff;
}

.page-frame img {
  display: block;
  width: 100%;
  height: auto;
}

/* where the reader placed the block on show: a frame, not a fill, so the printed text inside stays legible. The element is
   exactly the bbox and its stroke stands just outside it, an outline rather than a border: a box hugs the printed text,
   and a 2px border drawn inside it covered the glyphs' outermost pixels, which read as a box a little off (the operator,
   18 Nov), though the element sat on the bbox to 0.03 px (measured on finance pp. 21 and 113 and Kelly p. 4) */
.block-box {
  position: absolute;
  outline: 2px solid var(--color-accent);
  background-color: color-mix(in srgb, var(--color-accent) 10%, transparent);
  pointer-events: none;
}

/* a block framed for another that has no box of its own: dashed, as the derived block's frame is borrowed, not placed */
.block-box.recalled {
  outline-color: var(--color-annotation);
  outline-style: dashed;
  background-color: color-mix(in srgb, var(--color-annotation) 10%, transparent);
}

.block-box.recalled .block-box-label {
  background-color: var(--color-annotation);
}

.block-box.described {
  outline-style: dashed;
  background-color: transparent;
}

/* the label stands on the stroke's outer edge, as the stroke stands outside the box */
.block-box-label {
  position: absolute;
  bottom: calc(100% + 2px);
  left: -2px;
  padding: 0 var(--space-xs);
  background-color: var(--color-accent);
  color: var(--color-bg-base);
  line-height: 1.3;
}

.reading {
  max-height: 85vh;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.mode {
  display: flex;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}

/* a validator's error has one look (221.a), above the reading and in the Reading History alike */
.parse-errors,
.format-errors {
  list-style: none;
  color: var(--color-error);
}

.parse-errors {
  margin-bottom: var(--space-sm);
}

.parse-errors li,
.format-errors li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-sm);
}

/* an error a person has looked at recedes, as the head's check does after a person's verdict, and says who looked */
.parse-errors .looked,
.error-looked {
  color: var(--color-text-secondary);
}

/* each line of the raw text with its number in a gutter the selection leaves out; a long line wraps under its own text */
.raw-line {
  display: block;
  padding-left: calc(var(--gutter) + var(--space-sm));
  text-indent: calc(-1 * (var(--gutter) + var(--space-sm)));
}

.raw-line::before {
  content: attr(data-line);
  display: inline-block;
  width: var(--gutter);
  margin-right: var(--space-sm);
  text-align: right;
  text-indent: 0;
  color: var(--color-text-secondary);
  user-select: none;
}

/* the line an error names, marked as the block on show is */
.raw-line.marked {
  background-color: var(--color-bg-elevated);
  box-shadow: inset 2px 0 0 var(--color-accent);
}

/* a validator's error in the raw text, as a compiler marks one: the block it names tinted, a bar in the error's role at the
   gutter, the named line stronger and its number in the role too, so the mark survives greyscale by its bar and weight */
.raw-line.error-block,
.raw-line.error-named {
  background-color: color-mix(in srgb, var(--color-error) 8%, transparent);
  box-shadow: inset 3px 0 0 var(--color-error);
}

.raw-line.error-named {
  background-color: color-mix(in srgb, var(--color-error) 18%, transparent);
}

.raw-line.error-named::before {
  color: var(--color-error);
  font-weight: bold;
}

/* an error a person has looked at: its block keeps a quiet bar, never the error's colour */
.raw-line.error-looked {
  box-shadow: inset 3px 0 0 var(--color-text-secondary);
}

/* the line a click asked for stays marked over an error's tint, so the jump is seen */
.raw-line.marked.error-block,
.raw-line.marked.error-named {
  outline: 1px solid var(--color-accent);
  outline-offset: -1px;
}

/* where the quoted text comes from: the route, in the words of the line above */
.raw {
  white-space: pre-wrap;
  word-break: break-word;
}

.no-reading,
.as-served-off,
.chunks-said,
.continues {
  color: var(--color-text-secondary);
}

/* as served, said where the page serves another text: no switch, the reason in its place */
.as-served-off {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.chunks-head {
  margin-bottom: var(--space-sm);
}

.chunks-said {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
}

.not-placed {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-error);
}

/* a chunk that runs over the page's edge, said at the page's top or foot (65.a), dashed as a chunk's border is */
.continues {
  padding: 2px 0;
  border-top: 1px dashed var(--color-annotation);
}
</style>
