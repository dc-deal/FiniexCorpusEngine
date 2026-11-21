<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { giveVerdict, previewTable } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import AppButton from '@/components/base/AppButton.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import ReadingTable from '@/components/reading/ReadingTable.vue'
import { usd } from '@/cost_format'
import RunningMark from '@/components/base/RunningMark.vue'
import { useElapsed } from '@/use_elapsed'
import { useVerdictStore } from '@/stores/verdict_store'
import { canSend, correctionOffered, needsNote, payloadOf, prefillOf, type VerdictDraft } from '@/verdict_rules'
import type { Cell, PageDetail } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { Proposal, ProposalRequest, VerdictForm } from '@/types/api/verdict_types'
import { type Asking, type RecordedVerdict } from '@/stores/verdict_store'

/**
 * A person's verdict on the reading a page shows (decision 213.b), in a panel beside the page (the operator's V1.a, 21 Nov:
 * the form inside the page shifted the layout, "nothing I hate more"): it slides in from the window's right edge, below a
 * narrow width from its foot, and stands over the page without moving it; the page beneath stays to be scrolled and clicked.
 * Esc and Close shut it, asking first where a change would be lost; a ⚖ on another block points it there, asking the same.
 *
 * Its fields and its route are the inline form's of before: the verdict, its reason in the core's words, the page as a whole
 * or one of its blocks, a note (required where the reason says it is in the note), the person's assessment of the judge
 * where the block, or for the whole page the page, has a finding, and a correction of the chosen block (224.b) beneath the
 * block's current text, read only, so the reading behind the panel is not needed; a table's previewed as the table it
 * would be (204.a). For a block, ✦ fill with AI (W2.a, F1.a) asks a model for a correction and fills the whole form from it,
 * every field still a person's to change: the verdict, its reason, the judge's assessment and the note by the core's fixed
 * rules and the model's reading of the image, the correction by the model; beside it what the model sees in the image,
 * whether it agrees with the judge, its flags, the block's current text against its correction word by word and its cost.
 * Nothing is recorded until a person records it.
 */
const props = defineProps<{
  page: PageDetail
  knowledgeBase: KnowledgeBase
  work: string
  form: VerdictForm
  target: string  // the block it opens on, '' for the page as a whole
}>()

const emit = defineEmits<{
  close: []
  recorded: [given: RecordedVerdict]
  target: [block: string]
}>()

const store = useVerdictStore()
const blocks = computed(() => props.page.reading?.blocks ?? [])
const hasFindings = computed(() => Boolean(props.page.findings_at?.length || props.page.page_findings.length))
const blockOf = (id: string) => blocks.value.find(block => block.id === id)

// a proposal for the chosen block (W2.a), set apart when the block changes; while it is asked, when it was asked, so the
// button counts the seconds (the operator, 21 Nov), and a proposal that came while the person typed, waiting for their word
const proposal = ref<Proposal | null>(null)
const proposingSince = ref<number | null>(null)
const proposing = computed(() => proposingSince.value !== null)
const proposingFor = useElapsed(() => proposingSince.value)
const proposeRefused = ref<string | null>(null)
const arrived = ref<Proposal | null>(null)

const draft = reactive<VerdictDraft>({ verdict: '', reason: '', block: props.target, note: '', judgeAssessment: '', correction: '' })
const prefill = ref('')
// the correction starts again from the chosen block's text, or the person's last correction of it; the page outlines the block
watch(() => draft.block, id => {
  prefill.value = prefillOf(blockOf(id))
  draft.correction = prefill.value
  proposal.value = null
  proposeRefused.value = null
  proposingSince.value = null
  arrived.value = null
  emit('target', id)
  // a proposal still out for this block, asked before the panel was closed: waited on again, counting on
  const out = id ? store.proposing(requestOf(id)) : null
  if (out) void waitFor(out, id)
}, { immediate: true })

// the judge is assessed where what the verdict is about has a finding: the block's own, or for the whole page the page's
const judgeOffered = computed(() => (draft.block
  ? Boolean(blockOf(draft.block)?.findings.some(finding => !finding.void))
  : hasFindings.value))

// a change a person would lose by closing or pointing the panel elsewhere
const dirty = computed(() => Boolean(draft.verdict || draft.reason || draft.note.trim() || draft.judgeAssessment)
  || draft.correction !== prefill.value)
const asking = ref<{ kind: 'close' } | { kind: 'retarget', block: string } | null>(null)

/** Shuts the panel, asking first where a change would be lost. */
function requestClose(): void {
  if (dirty.value) {
    asking.value = { kind: 'close' }
    return
  }
  emit('close')
}

/** Points the panel at another block, or the whole page, asking first where a change would be lost. */
function retarget(block: string): void {
  if (block === draft.block) return
  if (dirty.value) {
    asking.value = { kind: 'retarget', block }
    return
  }
  draft.block = block
}

function discard(): void {
  const asked = asking.value
  asking.value = null
  if (asked?.kind === 'close') {
    emit('close')
    return
  }
  if (asked?.kind === 'retarget') {
    Object.assign(draft, { verdict: '', reason: '', note: '', judgeAssessment: '' })
    draft.block = asked.block
  }
}

defineExpose({ retarget, requestClose })

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') requestClose()
}
onMounted(() => window.addEventListener('keydown', onKey))

// a table's correction shown as the table it would be, read by the core's table parser; asked a moment after typing stops
const preview = ref<Cell[][] | null>(null)
let previewTimer: ReturnType<typeof setTimeout> | undefined
watch(() => [draft.block, draft.correction] as const, ([id, text]) => {
  clearTimeout(previewTimer)
  preview.value = null
  if (!id || blockOf(id)?.block_class !== 'table' || !text.trim()) return
  previewTimer = setTimeout(() => {
    previewTable(text).then(answer => { preview.value = answer.rows ?? null }).catch(() => { preview.value = null })
  }, 400)
}, { immediate: true })

// ✦ propose (W2.a): asked of the core for the chosen block; a second ask answers from its store at no cost
// why the form cannot be filled: the core's refusal, its "no proposal" and why, or the form's word before any ask
const proposeWhyNot = computed(() => proposeRefused.value
  ?? (proposal.value && !proposal.value.prefill ? `no proposal: ${proposal.value.why ?? 'none given'}` : null)
  ?? (props.form.propose.available ? null : props.form.propose.why_not))

function requestOf(block: string): ProposalRequest {
  return { knowledge_base: props.knowledgeBase, work: props.work, pdf_page: props.page.pdf_page, block }
}

// what the person has put in the form, to tell whether they typed while the proposal was out
function typed(): string {
  return JSON.stringify([draft.verdict, draft.reason, draft.note, draft.judgeAssessment, draft.correction])
}

async function propose(): Promise<void> {
  if (!draft.block || proposeWhyNot.value || proposing.value) return
  await waitFor(store.propose(requestOf(draft.block)), draft.block)
}

/** Waits on a proposal for a block and fills the form from it; where the person typed meanwhile, asks first. */
async function waitFor(out: Asking, block: string): Promise<void> {
  proposingSince.value = out.started
  const before = typed()
  try {
    const answer = await out.answer
    if (left || draft.block !== block) return
    proposal.value = answer
    if (!answer.prefill) return
    if (typed() === before) fill(answer)
    else arrived.value = answer
  } catch (caught) {
    if (!left && draft.block === block) proposeRefused.value = caught instanceof ApiError ? caught.detail : String(caught)
  } finally {
    if (proposingSince.value === out.started) proposingSince.value = null
  }
}

function fillArrived(): void {
  if (arrived.value) fill(arrived.value)
  arrived.value = null
}

/** Every field as the proposal fills it (F1.a), each still the person's to change; a block left as it was keeps its text. */
function fill(answer: Proposal): void {
  const prefilled = answer.prefill
  if (!prefilled) return
  Object.assign(draft, { verdict: prefilled.verdict, reason: prefilled.reason, judgeAssessment: prefilled.judge_assessment ?? '',
    note: prefilled.note, correction: prefilled.correction ?? prefill.value })
}

// the flag a person must weigh before taking the proposal stands in the warning role
const WEIGH = 'the image shows no such error'

const sending = ref(false)
const said = ref('')
const failed = ref(false)
let left = false
onBeforeUnmount(() => {
  left = true
  clearTimeout(previewTimer)
  window.removeEventListener('keydown', onKey)
})

async function send(): Promise<void> {
  if (!canSend(draft) || sending.value) return
  sending.value = true
  failed.value = false
  said.value = ''
  try {
    const given = await giveVerdict(payloadOf(draft, prefill.value, props.knowledgeBase, props.work, props.page.pdf_page))
    // recorded: the panel closes at once, since nothing is lost, and its page says it and follows the export (21 Nov)
    emit('recorded', { block: draft.block, verdict: draft.verdict, export: given.export })
  } catch (caught) {
    failed.value = true
    said.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <aside class="verdict-panel" role="dialog" aria-modal="false" aria-labelledby="verdict-title" :aria-busy="proposing" data-part="verdict-panel">
    <header class="panel-head">
      <p id="verdict-title" class="panel-title">A person's verdict on PDF page {{ page.pdf_page }}</p>
      <AppButton variant="quiet" size="compact" data-part="close" @click="requestClose">Close</AppButton>
    </header>
    <!-- asked before a change is lost: by closing, or by pointing the panel at another block -->
    <p v-if="asking" class="panel-ask" role="alert" data-part="panel-ask">
      <span>{{ asking.kind === 'close' ? 'Close and lose what you changed?' : `Turn to ${asking.block || 'the whole page'} and lose what you changed?` }}</span>
      <AppButton size="compact" data-part="discard" @click="discard">{{ asking.kind === 'close' ? 'Close' : 'Turn' }}</AppButton>
      <AppButton variant="quiet" size="compact" data-part="keep" @click="asking = null">Keep</AppButton>
    </p>
    <div class="panel-body">
      <LabelledLines :label-chars="11">
        <LabelledLine label="Verdict" class="choices">
          <AppButton
            v-for="option in form.verdicts"
            :key="option.value"
            size="compact"
            :active="draft.verdict === option.value"
            :data-verdict="option.value"
            @click="draft.verdict = option.value"
          >{{ option.label }}</AppButton>
        </LabelledLine>
        <LabelledLine label="Reason">
          <select v-model="draft.reason" data-part="reason">
            <option value="" disabled>choose a reason</option>
            <option v-for="option in form.reasons" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </LabelledLine>
        <LabelledLine label="About">
          <select :value="draft.block" data-part="block" @change="retarget(($event.target as HTMLSelectElement).value)">
            <option value="">the page as a whole</option>
            <option v-for="block in blocks" :key="block.id" :value="block.id">{{ `${block.id} ${block.block_class}` }}</option>
          </select>
        </LabelledLine>
        <LabelledLine label="Note">
          <textarea v-model="draft.note" rows="3" data-part="note" />
          <span v-if="needsNote(draft.reason)" class="hint" data-part="note-needed">required: this reason is said in the note</span>
        </LabelledLine>
        <LabelledLine v-if="judgeOffered" label="The judge">
          <select v-model="draft.judgeAssessment" data-part="assessment">
            <option value="">no assessment</option>
            <option v-for="option in form.assessments" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </LabelledLine>
        <template v-if="correctionOffered(draft.block)">
          <!-- the block's text now, read only, so the reading behind the panel is not needed -->
          <LabelledLine label="Now">
            <pre class="current-text" data-part="current-text">{{ prefill }}</pre>
          </LabelledLine>
          <LabelledLine label="Correction">
            <textarea v-model="draft.correction" rows="8" class="correction-field" data-part="correction-field" />
            <span class="hint">the block as it should read, sent only where changed; never written into the reading</span>
            <div v-if="preview" class="correction-preview person-correction" data-part="correction-preview">
              <span class="hint">as a table:</span>
              <ReadingTable :rows="preview" />
            </div>
          </LabelledLine>
          <LabelledLine label="Proposal">
            <span class="propose-line">
              <AppButton size="compact" :disabled="Boolean(proposeWhyNot) || proposing" data-part="propose" @click="propose">
                <RunningMark v-if="proposing" words="asking the model" :seconds="proposingFor" />
                <template v-else>✦ fill with AI</template>
              </AppButton>
              <span v-if="proposeWhyNot" class="hint" data-part="propose-why-not">{{ proposeWhyNot }}</span>
            </span>
            <!-- the proposal came while the person typed: their word before it replaces what they typed -->
            <p v-if="arrived" class="panel-ask" role="alert" data-part="fill-ask">
              <span>The proposal came: fill the fields and replace what you typed?</span>
              <AppButton size="compact" data-part="fill-anyway" @click="fillArrived">Fill</AppButton>
              <AppButton variant="quiet" size="compact" data-part="keep-mine" @click="arrived = null">Keep mine</AppButton>
            </p>
            <div v-if="proposal && proposal.state === 'proposed'" class="proposal" data-part="proposal">
              <template v-if="proposal.prefill">
                <p data-part="image-shows"><span class="part-label">the image shows:</span> {{ proposal.image_shows }}</p>
                <p class="hint" data-part="agrees">{{ proposal.agrees_said }}</p>
                <p v-if="proposal.flags.length" class="flags" data-part="flags">
                  <span v-for="flag in proposal.flags" :key="flag" class="flag" :class="{ weigh: flag === WEIGH }" :data-flag="flag">{{ flag }}</span>
                </p>
                <p class="proposal-diff" data-part="proposal-diff"><span
                  v-for="(part, at) in proposal.diff" :key="at" :class="part.kind" :data-diff="part.kind"
                >{{ part.text }}</span></p>
                <p class="proposal-foot">
                  <span class="hint" data-part="filled-said">{{ proposal.prefill.said }}</span>
                  <span v-if="proposal.cost_usd !== null && proposal.cost_usd !== undefined" class="cost" data-part="proposal-cost">{{ `${usd(proposal.cost_usd)} USD` }}</span>
                </p>
              </template>
            </div>
          </LabelledLine>
        </template>
      </LabelledLines>
      <p class="panel-actions">
        <AppButton :disabled="!canSend(draft) || sending" data-part="send" @click="send">Record the verdict</AppButton>
      </p>
      <p v-if="said" class="panel-said" :class="{ failed }" role="status" data-part="verdict-said">{{ said }}</p>
    </div>
  </aside>
</template>

<style scoped>
/* over the page at the window's right edge, the page beneath unmoved and still its own: no backdrop, nothing reflows */
.verdict-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  width: min(32rem, 100vw);
  background-color: var(--color-bg-surface);
  border-left: 1px solid var(--color-border-overlay);
  box-shadow: var(--shadow-overlay);
  animation: slide-in 160ms ease-out;
}

/* below a narrow width it comes from the window's foot */
@media (max-width: 640px) {
  .verdict-panel {
    top: auto;
    left: 0;
    width: 100vw;
    height: min(70vh, 36rem);
    border-left: none;
    border-top: 1px solid var(--color-border-overlay);
    animation-name: rise;
  }
}

@keyframes slide-in {
  from {
    transform: translateX(100%);
  }
}

@keyframes rise {
  from {
    transform: translateY(100%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .verdict-panel {
    animation: none;
  }
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.panel-title {
  font-weight: bold;
}

.panel-ask {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-warning);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--space-sm) var(--space-md);
}

/* the lines' values as wide as the panel leaves them, never past its edge: a long reason, a wide table */
.panel-body :deep(.labelled-lines) {
  grid-template-columns: minmax(var(--label-width, 0), max-content) minmax(0, 1fr);
}

.panel-body select {
  max-width: 100%;
}

select,
textarea {
  color: var(--color-text-primary);
  background-color: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px var(--space-xs);
}

textarea {
  width: 100%;
  resize: vertical;
}

/* a correction is kept as written, its own line breaks too; a long line, as a table's HTML often is, wraps at the field's
   edge rather than running out of sight (accounting p. 524) */
.correction-field,
.current-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.current-text {
  max-height: 12rem;
  overflow-y: auto;
  padding: 2px var(--space-xs);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
}

.correction-preview {
  width: 100%;
  overflow-x: auto;
}

.hint,
.cost {
  color: var(--color-text-secondary);
}

.propose-line,
.proposal-foot,
.flags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
}

.proposal {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-top: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.flag {
  color: var(--color-text-secondary);
}

.flag.weigh {
  color: var(--color-warning);
}

/* the block's text now against the proposal, word by word: what goes struck through, what comes underlined */
.proposal-diff {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.proposal-diff .removed {
  color: var(--color-negative);
  text-decoration: line-through;
}

.proposal-diff .added {
  color: var(--color-positive);
  text-decoration: underline;
}

.panel-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.panel-said {
  margin-top: var(--space-xs);
  color: var(--color-text-secondary);
}

.panel-said.failed {
  color: var(--color-error);
}
</style>
