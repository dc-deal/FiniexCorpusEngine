import type { ReadingBlock } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { VerdictRequest } from '@/types/api/verdict_types'

/**
 * The page view's verdict dialog in rules (decision 213.b, 224.b), apart from its drawing so each can be tested: what it
 * takes, what it requires, and what it sends. The core checks every value again and says in its own words what it
 * refuses; these rules only spare a person a round trip.
 */
export interface VerdictDraft {
  verdict: string
  reason: string
  block: string  // '' for the page as a whole
  note: string
  judgeAssessment: string  // '' for none
  correction: string
}

// the reason whose words are a placeholder: the note says it, so a note is required (the core refuses `other` without one)
const SAID_IN_THE_NOTE = 'other'

export function needsNote(reason: string): boolean {
  return reason === SAID_IN_THE_NOTE
}

/** A correction is a block's text as it should read: offered only where one block is chosen. */
export function correctionOffered(block: string): boolean {
  return block !== ''
}

/**
 * What the correction's field starts from: the correction that stands for this block on the reading shown, as the API
 * chose it (229.a), so a new one starts from it; else the block's body as the reader wrote it, a table's as its HTML.
 */
export function prefillOf(block: ReadingBlock | undefined): string {
  if (!block) return ''
  return block.correction?.text ?? block.body ?? ''
}

/** Whether the draft can be sent: a verdict and a reason, and a note where the reason needs one. */
export function canSend(draft: VerdictDraft): boolean {
  return Boolean(draft.verdict && draft.reason && (!needsNote(draft.reason) || draft.note.trim()))
}

/**
 * The request the draft sends. A correction goes only with a block, and only where the person changed it from what the
 * field started with: an unchanged field would record the reader's own text, or a correction already given, again.
 */
export function payloadOf(draft: VerdictDraft, prefill: string, knowledgeBase: KnowledgeBase, work: string, pdfPage: number): VerdictRequest {
  const corrected = correctionOffered(draft.block) && draft.correction.trim() !== '' && draft.correction !== prefill
  return {
    knowledge_base: knowledgeBase,
    work,
    pdf_page: pdfPage,
    verdict: draft.verdict,
    reason: draft.reason,
    block: draft.block || null,
    note: draft.note.trim() || null,
    correction: corrected ? draft.correction : null,
    judge_assessment: draft.judgeAssessment || null,
  }
}
