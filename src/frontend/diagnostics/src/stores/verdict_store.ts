import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getVerdictForm, proposeCorrection } from '@/api/api_client'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { Proposal, ProposalRequest, VerdictForm, VerdictGiven } from '@/types/api/verdict_types'

/** A verdict just recorded, as the panel hands it to its page: what it was about, the verdict, the export it set going. */
export interface RecordedVerdict {
  block: string  // '' for the page as a whole
  verdict: string
  export: VerdictGiven['export']
}

/** A proposal asked of the core and not yet answered: when it was asked, and its answer to come. */
export interface Asking {
  started: number
  answer: Promise<Proposal>
}

function proposalKey(asked: ProposalRequest): string {
  return [asked.knowledge_base, asked.work, asked.pdf_page, asked.block].join('/')
}

// how often the view asks whether the export after a verdict has finished: an export takes 40 s on an idle machine and
// about a minute on a busy one (line 1's run, 12 Nov: 41 s and 53 s)
const FOLLOW_EVERY_MS = 2000

/**
 * A person's verdict from the page view (213.b): whether it is taken here at all, asked once, and the export a verdict sets
 * going, followed until it has finished, so the page is loaded again with the verdict in it. A ✦ proposal still out is kept
 * here by its block, not in the panel (the operator, 21 Nov): closing the panel never cancels the core's call, which is paid
 * and kept, and the panel opened again on the block waits on the same call, counting on, rather than ask a second time.
 */
export const useVerdictStore = defineStore('verdict', () => {
  const form = ref<VerdictForm | null>(null)
  const asking = new Map<string, Asking>()

  /** The proposal for a block: the one still out if there is one, else asked now. */
  function propose(asked: ProposalRequest): Asking {
    const key = proposalKey(asked)
    const out = asking.get(key)
    if (out) return out
    const one = { started: Date.now(), answer: proposeCorrection(asked).finally(() => asking.delete(key)) }
    asking.set(key, one)
    return one
  }

  /** The proposal still out for a block, if one is. */
  function proposing(asked: ProposalRequest): Asking | null {
    return asking.get(proposalKey(asked)) ?? null
  }

  // one poll for every export that runs or waits, every 2 s until none does (E1.a): the header's hourglass, a page's reload
  // and a toast's line all read what it brings
  let following = false
  async function follow(): Promise<void> {
    if (following) return
    following = true
    try {
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, FOLLOW_EVERY_MS))
        try {
          form.value = await getVerdictForm()
        } catch {
          continue  // a request lost now and then: ask again
        }
        if (!form.value.exports.some(status => status.running || status.pending)) return
      }
    } finally {
      following = false
    }
  }

  async function loadForm(): Promise<void> {
    if (form.value) return
    try {
      form.value = await getVerdictForm()
    } catch {
      form.value = null  // no verdicts where the API cannot say: the view stays read-only
      return
    }
    if (form.value.exports.some(status => status.running || status.pending)) void follow()
  }

  /** A verdict just recorded: the export it set going stands at once, as the record answered, and is followed. */
  function recordedNow(status: VerdictGiven['export']): void {
    if (form.value) {
      form.value = { ...form.value, exports: form.value.exports.map(one => (one.knowledge_base === status.knowledge_base
        ? { ...status, waiting: one.waiting } : one)) }
    }
    void follow()
  }

  /** The number of exports of a base that have finished, as last asked. */
  function finishedOf(knowledgeBase: KnowledgeBase): number {
    return form.value?.exports.find(status => status.knowledge_base === knowledgeBase)?.finished ?? 0
  }

  /**
   * Waits until an export of the base has finished after `since` exports, by the one poll; resolves with the error the export
   * reported, or null.
   */
  function followExport(knowledgeBase: KnowledgeBase, since: number): Promise<string | null> {
    void follow()
    const ended = (value: VerdictForm | null) => {
      const status = value?.exports.find(one => one.knowledge_base === knowledgeBase)
      return status && status.finished > since && !status.running ? status : null
    }
    return new Promise(resolve => {
      const now = ended(form.value)
      if (now) {
        resolve(now.last_error ?? null)
        return
      }
      const stop = watch(form, value => {
        const status = ended(value)
        if (!status) return
        stop()
        resolve(status.last_error ?? null)
      })
    })
  }

  return { form, loadForm, recordedNow, finishedOf, followExport, propose, proposing }
})
