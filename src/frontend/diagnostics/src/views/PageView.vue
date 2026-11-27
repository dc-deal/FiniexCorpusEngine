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
import HumanTime from '@/components/base/HumanTime.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import { isDecided } from '@/listed_state'
import LoadingLine from '@/components/base/LoadingLine.vue'
import CategoryMark from '@/components/CategoryMark.vue'
import FindingList from '@/components/FindingList.vue'
import IntegrityMark from '@/components/IntegrityMark.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import PageJump from '@/components/PageJump.vue'
import PageLadderLines from '@/components/PageLadderLines.vue'
import UnreadPage from '@/components/UnreadPage.vue'
import PageForm from '@/components/PageForm.vue'
import NumberedText from '@/components/base/NumberedText.vue'
import PagerLinks from '@/components/base/PagerLinks.vue'
import RecordRows from '@/components/base/RecordRows.vue'
import RecordZone from '@/components/base/RecordZone.vue'
import PersonStanding from '@/components/PersonStanding.vue'
import PersonVerdictList from '@/components/PersonVerdictList.vue'
import VerdictPanel from '@/components/VerdictPanel.vue'
import ChunkGroups from '@/components/reading/ChunkGroups.vue'
import ReadingBlocks from '@/components/reading/ReadingBlocks.vue'
import ReasonList from '@/components/ReasonList.vue'
import StateMark from '@/components/StateMark.vue'
import { usePageStore } from '@/stores/page_store'
import { useSettingsStore } from '@/stores/settings_store'
import { useToastStore } from '@/stores/toast_store'
import { useVerdictStore, type RecordedVerdict } from '@/stores/verdict_store'
import { durationWords } from '@/export_clock'
import { useViewName } from '@/view_name'
import { lookedSaid, verdictBy } from '@/person_words'
import { readingCost } from '@/cost_format'
import { counted } from '@/counted'
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
// the verdict panel (V1.a): closed (null), or open on the whole page ('') or on a block; the panel itself asks before it
// turns where a change would be lost
const verdictTarget = ref<string | null>(null)
const verdictPanel = ref<InstanceType<typeof VerdictPanel> | null>(null)
// the same panel gives a verdict or promotes a Lab reading (#18)
const panelMode = ref<'verdict' | 'promote'>('verdict')
function openVerdict(target: string): void {
  panelMode.value = 'verdict'
  if (verdictTarget.value === null || !verdictPanel.value) verdictTarget.value = target
  else verdictPanel.value.retarget(target)
}
function openPromote(): void {
  panelMode.value = 'promote'
  if (verdictTarget.value === null) verdictTarget.value = ''
}
// the Lab readings the core promotes, as the API marks them
const promotable = computed(() => shown.value?.form?.lab.filter(reading => reading.promotable) ?? [])
// the judgement the page shows the person: the recalled one, else the served reading's standing one (#17)
const answersJudgement = computed(() => (recallId.value
  ? (shown.value?.attempts ?? []).flatMap(attempt => attempt.judgements).find(judgement => judgement.recall === recallId.value)?.judgement_key
  : shown.value?.form?.shown_judgement) ?? null)
const analysis = ref<InstanceType<typeof AnalysisSection> | null>(null)
const address = useRoute()

watch(() => [props.kb, props.work, props.page] as const, ([kb, work, page]) => {
  highlight.value = null
  hovered.value = null
  verdictTarget.value = null
  rawLine.value = null
  void store.loadPage(kb, work, page)
}, { immediate: true })

// an answer for another page, still on screen while this one loads, is not shown as this one: matched by the request it
// answers, not by its fields, so a row that named another knowledge base than its address could not hang the view
const shown = computed(() => store.pageOf(props.kb, props.work, props.page))
useViewName(() => (shown.value ? `${shown.value.title} p. ${shown.value.pdf_page}` : null))
// "as served" (the operator, 21 Nov: quoted is a subset of readable), chunk first: the page as the chunks semantic search holds
// of it, each a group of the quoted blocks it holds in the form the search and the chat quote, a block never quoted hidden;
// asked for when it is switched on. Where the page serves something else in its reading's place, nothing of the reading is
// served, and it says so
const asServed = ref(false)
const servedBy = computed(() => shown.value?.ladder?.served_by ?? null)
const chunks = computed(() => store.chunksOf(props.kb, props.work, props.page))
const servedMode = computed(() => asServed.value && mode.value === 'readable' && !recallId.value && !servedBy.value)
watch(() => [servedMode.value, props.kb, props.work, props.page] as const, ([on, kb, work, page]) => {
  if (on) void store.loadChunks(kb, work, page)
}, { immediate: true })
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
// a recorded verdict (the operator, 21 Nov): the panel closed at once; the page asked again at once, so the verdict stands in
// its Check row as waiting for the export (E1.a); a toast says it, how long the export may take and where to follow it, and
// follows it; the page loads its own data again once the export's `finished` moves, below
const toasts = useToastStore()
async function verdictRecorded(given: RecordedVerdict): Promise<void> {
  verdictTarget.value = null
  const { kb, work, page } = props
  verdictStore.recordedNow(given.export)
  void store.reloadPage(kb, work, page)
  const what = given.verdict === 'promote' ? 'Promotion recorded · a Lab reading is the page\'s' : `Verdict recorded · ${given.block || 'the page'} · ${given.verdict}`
  const text = `${what} — the index rebuild may take ${durationWords(given.export.expected_seconds)}`
  const id = toasts.show({ text, detail: `the ${kb} export runs in the background: follow it at the hourglass in the header` })
  const error = await verdictStore.followExport(kb, given.export.finished)
  if (!error) toasts.update(id, { detail: 'served from now on' })
  // a failed export is said even where the first toast has gone: the verdict stands recorded, its export not yet
  else if (!toasts.update(id, { detail: `the export failed: ${error}`, failed: true })) {
    toasts.show({ text: `Verdict recorded · ${given.block || 'the page'} · ${given.verdict}`, detail: `the export failed: ${error}`, failed: true })
  }
}
// an export of this page's base has finished, this view's or any other: the page loads its own data again, so a verdict
// that waited stands as a person's mark, and its route with it. Read from the base's own status, which is unknown until the
// form is loaded, so loading it is no export that ended
watch(() => verdictStore.form?.exports.find(status => status.knowledge_base === props.kb)?.finished, (now, before) => {
  if (before !== undefined && now !== undefined && now > before) void store.reloadPage(props.kb, props.work, props.page)
})
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
// in the Check line (H1.a): a person's verdict that decides before the check's state, any other after it
const personFirst = computed(() => personDecides.value && !!shown.value?.person)
// stage 2's figures as a reader says them: a share to three places
function share(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toFixed(3) : '?'
}

// The raw text with its lines numbered as the validator counts them (228.a, the operator on accounting p. 338: "line 86? then please line numbers in the read-only editor too"): line 1 is the front matter's first `---`. The numbers stand in a gutter beside the
// text, never in it, so the text copied is the text stored. A validator's error opens it at its line, marked.
const rawText = ref<InstanceType<typeof NumberedText> | null>(null)
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
  rawText.value?.scrollToLine(line)
}

// every click brings the block into view, also from the raw text and also a second time: the scroll is the click's own
async function showBlock(id: string): Promise<void> {
  mode.value = 'readable'
  asServed.value = false
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
  const id = hovered.value ?? highlight.value ?? (verdictTarget.value || null)
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
          <AppButton v-if="verdictsTaken" size="compact" :active="verdictTarget !== null && panelMode === 'verdict'" data-part="give-verdict" @click="openVerdict('')">
            Give a verdict
          </AppButton>
          <AppButton v-if="verdictsTaken && promotable.length" size="compact" :active="verdictTarget !== null && panelMode === 'promote'" data-part="promote" @click="openPromote">
            Promote a Lab reading
          </AppButton>
        </header>

        <!-- the page's record (the operator's H1.a, 21 Nov): always the same rows in one order, Check, Route, Reading, Findings,
             Coverage, Reading History, Lab, Details, each one line that folds open for more; a row that has nothing says so in
             one word, on a page no reader has read too, so the layout never moves from page to page. Every word is the API's,
             each said once; the labels in one column (`RecordRows`) -->
        <RecordRows class="summary page-facts" data-part="page-facts">
          <!-- the check: a person's verdict first where it decides, the check's state then receding, its glyph and word kept (the
               operator, 11 Nov: red "issue" beside green "accepted"), named the check's, so a page a person settled (211.a) still
               says what the check found; its reasons, then the page's one sentence in the line's words, the sentence that stood
               above the record (H1.a). Folded beneath: the check's three stages and a person -->
          <FoldSection label="Check" remember="page.check" :plain="!shown.read" :class="{ overruled: personDecides }">
            <template #title>
              <span class="row-line" data-part="check-line">
                <span v-if="personFirst" class="person-verdict" data-part="person-verdict" :data-by="verdictBy(shown.person)">
                  <span class="person-by">{{ verdictBy(shown.person) }}</span><PersonStanding :mark="shown.person" />
                </span>
                <StateMark :state="shown.check.state" :quiet="personDecides" />
                <ReasonList v-if="shown.check.reasons.length" :reasons="shown.check.reasons" />
                <span v-if="shown.check_said" class="check-said" data-part="check-said">{{ `· ${shown.check_said}` }}</span>
                <span v-if="readingChanged" class="reading-changed">
                  <IntegrityMark :state="shown.integrity" />: {{ INTEGRITY_SAYS[shown.integrity] }}
                </span>
                <span v-if="!personFirst && shown.person" class="person-verdict" data-part="person-verdict" :data-by="verdictBy(shown.person)">
                  <span class="person-by">{{ verdictBy(shown.person) }}</span><PersonStanding :mark="shown.person" />
                </span>
                <!-- a person checked the page: no re-read without a reason (191.a) -->
                <span v-if="shown.protected" class="protected" data-part="protected"><AppIcon name="protected" /> protected</span>
                <!-- a verdict recorded and not yet in the export (E1.a): shown at once, marked as waiting, dashed as what is
                     not yet the standing state is -->
                <span v-for="(one, at) in shown.waiting ?? []" :key="at" class="waiting-verdict" data-part="waiting-verdict">
                  <AppIcon name="hourglass" />
                  <span>{{ `your verdict: ${one.verdict} · ${one.block || 'the page'} · recorded ` }}<HumanTime :at="one.given_at" />{{ ' · served once the export is done' }}</span>
                </span>
              </span>
            </template>
            <DetailList v-if="shown.trace" class="check-stages">
              <!-- the three stages of the check, each its own row, then a person (the operator: "in the details, all three stages one by one") -->
              <dt>Stage 1 · format</dt>
              <dd data-stage="1">
                at collect {{ shown.trace.class_when_collected }} · under today's validator {{ shown.trace.class_now }}
                <span class="secondary">· validator {{ shown.trace.validator }}</span>
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
            </DetailList>
          </FoldSection>
          <!-- the route in its parts as the API parts it (184), then the provider's own words where a call failed, else the
               route's why where nothing else here says it (`why_line`); folded beneath, each part named and the route's whole why.
               A page no reader has read says what serves it -->
          <FoldSection label="Route" remember="page.route" :plain="!shown.read">
            <template #title>
              <span class="row-line" data-part="route-line">
                <span class="route">{{ shown.read ? routeSaid : shown.route_why }}</span>
                <span v-if="shown.trace?.error_message" class="error-message">{{ shown.trace.error_message }}</span>
                <span v-else-if="shown.read && shown.why_line" class="route-why">{{ shown.why_line }}</span>
              </span>
            </template>
            <LabelledLines class="route-parts" data-part="route-parts" :label-chars="7">
              <LabelledLine v-if="shown.route_level" label="Level">{{ shown.route_level }}</LabelledLine>
              <LabelledLine v-if="shown.route_source" label="Source">{{ shown.route_source }}</LabelledLine>
              <LabelledLine v-if="shown.route_reader?.length" label="Reader">{{ shown.route_reader.join(', ') }}</LabelledLine>
              <LabelledLine v-if="shown.route_why" label="Why">{{ shown.route_why }}</LabelledLine>
            </LabelledLines>
          </FoldSection>
          <!-- the reading shown among the page's readings, what the reader said the page is where it is not content, a class that
               moved, a retry, its cost, whether the image is the one it read, and a person's reset (191.a: the reading discarded,
               the text layer served until a new reading is due) -->
          <FoldSection label="Reading" plain>
            <template #title>
              <span v-if="shown.read" class="row-line" data-part="reading-line">
                <span v-if="shown.category && shown.category !== 'content'" class="reading-part" data-part="category">
                  <CategoryMark :category="shown.category" :said="shown.category_said" :kind="shown.page_kind" />
                </span>
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
                <span v-if="shown.reset" class="reading-part reset" data-part="reset">
                  {{ `a person reset the page${shown.reset.reason ? `: ${shown.reset.reason}` : ''}` }}
                  <HumanTime v-if="shown.reset.given_at" :at="shown.reset.given_at" />
                </span>
              </span>
              <span v-else class="none">none</span>
            </template>
          </FoldSection>
          <!-- what the findings come to (184): each block a jump, with a finding's own look (the operator, 12 Nov, on accounting p. 524:
               "the red flag or red text ... so that they catch the eye at once by their colour"): the flag and the gravest
               severity of its findings that stand, in that severity's role, as beneath the block; where code voided them all,
               the flag and the ruling recede. Then what that means for the page, as the API says it, and how many findings are
               about the page as a whole, which stand folded beneath, a person's verdict on the whole page the last voice (178.a) -->
          <FoldSection class="found-at" label="Findings" remember="page.findings" :plain="!shown.page_findings.length">
            <template #title>
              <span v-if="shown.findings_at?.length || shown.page_findings.length" class="row-line" data-part="findings-line">
                <span v-for="one in shown.findings_at ?? []" :key="one.block" class="finding-at" :class="one.severity ?? 'void'" :data-finding-at="one.block">
                  <AppIcon name="finding" class="finding-mark" />
                  <AppButton variant="link" :data-jump="one.block" @click="showBlock(one.block)">{{ one.block }}</AppButton>
                  <span v-if="one.severity" class="finding-severity" :data-severity="one.severity">{{ one.severity }}</span>
                  <span v-else class="finding-said" :data-said="one.said">{{ one.said }}</span>
                </span>
                <span v-if="shown.findings_outcome" class="findings-outcome" data-part="findings-outcome">{{ `· ${shown.findings_outcome}` }}</span>
                <span v-if="shown.page_findings.length" class="page-findings-said" data-part="page-findings-said">
                  {{ `· ${counted(shown.page_findings.length, 'finding')} on the page as a whole` }}
                </span>
              </span>
              <span v-else class="none">none</span>
            </template>
            <FindingList
              class="page-findings"
              :findings="shown.page_findings"
              :people="shown.human.filter(person => person.applies && !person.block)"
              names-blocks
            />
          </FoldSection>
          <!-- the page's own ladder (V2.a): its text layer, the text served, keyword search, its chunks, its reading; the text
               served folded until asked for -->
          <PageLadderLines v-if="shown.ladder" :ladder="shown.ladder" label="Coverage" />
          <FoldSection v-else label="Coverage" plain><template #title><span class="none">none</span></template></FoldSection>


        <!-- the reading's trace: its line the model, the contract and when it was stored -->
        <FoldSection v-if="shown.trace" class="details" :open="settings.pageDetailsOpen" label="Details" @toggle="settingsStore.setPageDetailsOpen">
          <template #title>
            <span class="row-line secondary" data-part="details-line">
              {{ `${shown.trace.model} · ${shown.trace.contract} · stored` }} <HumanTime :at="shown.trace.stored_at" />
            </span>
          </template>
          <DetailList>
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
        <FoldSection v-else label="Details" plain><template #title><span class="none">none</span></template></FoldSection>
        </RecordRows>
        <!-- the page's readings and verdicts in one form (#18): Readings, Lab and Verdicts, each with its count -->
        <PageForm
          v-if="shown.form"
          :form="shown.form"
          :recall-id="recallId"
          :recall-to="recallLink"
          :recalled-verdicts="recallId ? recalled?.verdicts ?? null : null"
          @block="showBlock"
        />
      </template>
    </RecordZone>

    <!-- a page no reader has read (V2.a): its own image below the record, in the wide container where a read page's
         analysis stands, as wide as its image column and centred (the operator, 23 Nov); nothing of a reading, which it has not -->
    <UnreadPage v-if="shown && !detailError && !shown.read" :page="shown" :image-url="imageUrl" />

    <!-- the analysis (181.a): the original beside its reading, under its own heading, the one part that takes the wide
         container (183); framed as an overlay while a judgement is recalled -->
    <AnalysisSection v-if="shown && !detailError && shown.read" ref="analysis" :overlay="!!recallId">
      <!-- the way back from a recall (27.a): at the head line's start, before words whose length varies, so it stays under
           the pointer from one recall to the next -->
      <template v-if="recallId" #lead>
        <RouterLink :to="standing" class="show-standing" data-part="show-standing">Show standing</RouterLink>
      </template>
      <template #hint>
        <span v-if="!recallId" class="analysis-hint">the image the reader received, beside its reading</span>
        <!-- while a judgement is recalled the analysis says so in its own heading, the overlay's glyph and words -->
        <span v-else class="analysis-recalled" data-part="analysis-recalled">
          <AppIcon name="recalled" /> recalled, not the standing view:
          {{ recalled ? recalled.said : recallError ? 'a judgement this page does not have' : 'a judgement' }}
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
            <!-- as served, chunk first (21 Nov): the page as the chunks semantic search holds of it, each a group of the quoted
                 blocks it holds; a block never quoted lies in none and is not shown -->
            <ApiFailure v-if="servedMode && chunksError" :error="chunksError" @retry="store.loadChunks(kb, work, page)" />
            <LoadingLine v-else-if="servedMode && !chunks" />
            <ChunkGroups v-else-if="servedMode && chunks" :chunks="chunks" @hover="hovered = $event" />
            <ReadingBlocks
              v-else-if="mode === 'readable'"
              ref="readingBlocks"
              :blocks="analysisReading.blocks"
              :highlight="highlight"
              :errors="analysisReading.error_places ?? []"
              :verdicts="verdictsTaken"
              :verdict-block="verdictTarget || null"
              @verdict="openVerdict"
              @hover="hovered = $event"
              @jump="showBlock"
              @raw="showRaw"
            />
            <!-- the raw text numbered as the validator counts it, in the one numbered look (NumberedText) -->
            <NumberedText
              v-else
              ref="rawText"
              class="raw"
              data-part="raw"
              :text="analysisRaw ?? ''"
              :marked="rawLine ? { first: rawLine, last: rawLine } : null"
              :marks="errorLines"
            />
          </template>
        </div>
      </div>
    </AnalysisSection>
    <!-- the verdict beside the page, over it, the page beneath unmoved (V1.a) -->
    <VerdictPanel
      v-if="verdictsTaken && verdictTarget !== null && verdictStore.form && shown"
      ref="verdictPanel"
      :page="shown"
      :knowledge-base="kb"
      :work="work"
      :form="verdictStore.form"
      :target="verdictTarget"
      :mode="panelMode"
      :lab-readings="promotable"
      :answers-judgement="answersJudgement"
      @close="verdictTarget = null"
      @recorded="verdictRecorded"
      @target="verdictTarget = $event"
    />
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

/* the page's record (184, H1.a): its rows one beneath the other, labels and lines each in a column (`RecordRows`) */
.page-facts {
  margin: var(--space-sm) 0 var(--space-sm);
}

/* the route's line parted as the reading's is, by a quiet dot drawn, so the provider's words copied are its words alone */
.route + .error-message::before,
.route + .route-why::before {
  content: '· ';
  color: var(--color-text-secondary);
}

/* a row's one line: its parts side by side, wrapping in the line's column */
.row-line {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
}

.none,
.check-said,
.route-why,
.page-findings-said,
.person-by {
  color: var(--color-text-secondary);
}

.person-verdict {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

/* a verdict that waits for the export: not yet the standing state, so in the annotation's role and dashed beneath (E1.a) */
.waiting-verdict {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-annotation);
  border-bottom: 1px dashed var(--color-annotation);
}

.check-stages,
.route-parts {
  margin: 2px 0 var(--space-xs);
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


/* the pipeline's state where a person's accept or reject decides: the whole line recedes, the check's reasons with the
   mark; a changed reading file keeps its error role below, since that is not history */
.overruled :deep(.reasons) {
  color: var(--color-text-secondary);
}

/* a reading file that is no longer what was checked: the mark carries the error role, the sentence beside it too */
.reading-changed {
  color: var(--color-error);
}

.secondary {
  color: var(--color-text-secondary);
}

.stage-list {
  list-style: none;
  margin-top: 2px;
}

.hash {
  word-break: break-all;
}

/* the original and its reading side by side, each scrolling in a pane of the same height; on a narrow screen one above the other */
/* a recalled judgement (181.a): the overlay's role, the annotation colour, always dashed, its glyph and words with it */
.analysis-recalled {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-annotation);
}

/* the way back, a link at the analysis head line's start, at the line's weight for a link (27.a) */
.show-standing {
  color: var(--color-accent);
  font-weight: normal;
  white-space: nowrap;
}

.analysis-recalled {
  font-weight: normal;
  margin-left: var(--space-sm);
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

/* a validator's error has one look (221.a), above the reading */
.parse-errors {
  list-style: none;
  color: var(--color-error);
}

.parse-errors {
  margin-bottom: var(--space-sm);
}

.parse-errors li {
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

/* the raw text's numbered lines and their marks are the shared NumberedText's own (#12) */

.no-reading,
.as-served-off {
  color: var(--color-text-secondary);
}

/* as served, said where the page serves another text: no switch, the reason in its place */
.as-served-off {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

</style>
