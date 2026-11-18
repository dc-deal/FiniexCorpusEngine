<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { giveVerdict, previewTable } from '@/api/api_client'
import AppButton from '@/components/base/AppButton.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import ReadingTable from '@/components/reading/ReadingTable.vue'
import { useVerdictStore } from '@/stores/verdict_store'
import { canSend, correctionOffered, needsNote, payloadOf, prefillOf, type VerdictDraft } from '@/verdict_rules'
import type { Cell, PageDetail } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { VerdictForm } from '@/types/api/verdict_types'

/**
 * A person's verdict on the reading a page shows (decision 213.b, the operator: "the last proper feature before the freeze"), given
 * here instead of on the command line: the verdict, its reason in the core's words, the page as a whole or one of its
 * blocks (the first finding's by default), a note (required where the reason says it is in the note), the person's
 * assessment of the judge where the page has a finding, and a correction of the chosen block (224.b), started from the
 * block's text or the person's last correction of it, a table's previewed as the table it would be (204.a's path).
 *
 * Sent, the verdict is recorded at once and the export that shows it in every view runs in the background; the dialog
 * says so, follows the export, and the page is loaded again when it has finished. The person may move on meanwhile.
 * Its lines stand on the page head's grid, one look for a record and for what a person adds to it.
 */
const props = defineProps<{
  page: PageDetail
  knowledgeBase: KnowledgeBase
  work: string
  form: VerdictForm
}>()

const emit = defineEmits<{
  close: []
  recorded: []
}>()

const store = useVerdictStore()
const blocks = computed(() => props.page.reading?.blocks ?? [])
const hasFindings = computed(() => Boolean(props.page.findings_at?.length || props.page.page_findings.length))
const blockOf = (id: string) => blocks.value.find(block => block.id === id)

const draft = reactive<VerdictDraft>({ verdict: '', reason: '', block: props.page.focus ?? '', note: '', judgeAssessment: '', correction: '' })
const prefill = ref('')
// the correction starts again from the chosen block's text, or the person's last correction of it
watch(() => draft.block, id => {
  prefill.value = prefillOf(blockOf(id))
  draft.correction = prefill.value
}, { immediate: true })

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

const sending = ref(false)
const said = ref('')
const failed = ref(false)
let left = false
onBeforeUnmount(() => {
  left = true
  clearTimeout(previewTimer)
})

async function send(): Promise<void> {
  if (!canSend(draft) || sending.value) return
  sending.value = true
  failed.value = false
  said.value = ''
  try {
    const given = await giveVerdict(payloadOf(draft, prefill.value, props.knowledgeBase, props.work, props.page.pdf_page))
    said.value = 'Recorded · the view updates after the export (about a minute)'
    const error = await store.followExport(props.knowledgeBase, given.export.finished, () => left)
    if (left) return
    if (error) {
      failed.value = true
      said.value = `Recorded · the export failed: ${error}`
      return
    }
    emit('recorded')
  } catch (caught) {
    failed.value = true
    said.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <section class="verdict-dialog" role="dialog" aria-labelledby="verdict-title" data-part="verdict-dialog">
    <p id="verdict-title" class="dialog-title">A person's verdict on PDF page {{ page.pdf_page }}</p>
    <LabelledLines :label-chars="12">
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
        <select v-model="draft.block" data-part="block">
          <option value="">the page as a whole</option>
          <option v-for="block in blocks" :key="block.id" :value="block.id">{{ `${block.id} ${block.block_class}` }}</option>
        </select>
      </LabelledLine>
      <LabelledLine label="Note">
        <textarea v-model="draft.note" rows="3" data-part="note" />
        <span v-if="needsNote(draft.reason)" class="hint" data-part="note-needed">required: this reason is said in the note</span>
      </LabelledLine>
      <LabelledLine v-if="hasFindings" label="The judge">
        <select v-model="draft.judgeAssessment" data-part="assessment">
          <option value="">no assessment</option>
          <option v-for="option in form.assessments" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </LabelledLine>
      <LabelledLine v-if="correctionOffered(draft.block)" label="Correction">
        <textarea v-model="draft.correction" rows="8" class="correction-field" data-part="correction-field" />
        <span class="hint">the block as it should read, sent only where changed; never written into the reading</span>
        <div v-if="preview" class="correction-preview person-correction" data-part="correction-preview">
          <span class="hint">as a table:</span>
          <ReadingTable :rows="preview" />
        </div>
      </LabelledLine>
    </LabelledLines>
    <p class="dialog-actions">
      <AppButton :disabled="!canSend(draft) || sending" data-part="send" @click="send">Record the verdict</AppButton>
      <AppButton variant="quiet" data-part="cancel" @click="emit('close')">Close</AppButton>
    </p>
    <p v-if="said" class="dialog-said" :class="{ failed }" role="status" data-part="verdict-said">{{ said }}</p>
  </section>
</template>

<style scoped>
.verdict-dialog {
  margin: var(--space-sm) 0;
  padding: var(--space-sm) var(--space-md);
  background-color: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.dialog-title {
  font-weight: bold;
  margin-bottom: var(--space-xs);
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
.correction-field {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* a person's correction in its one look (base.css), as it will stand in the block */
.correction-preview {
  width: 100%;
}

.hint {
  color: var(--color-text-secondary);
}

.dialog-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.dialog-said {
  margin-top: var(--space-xs);
  color: var(--color-text-secondary);
}

.dialog-said.failed {
  color: var(--color-error);
}
</style>
