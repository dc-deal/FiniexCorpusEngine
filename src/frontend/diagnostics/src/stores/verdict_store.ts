import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getVerdictForm } from '@/api/api_client'
import type { KnowledgeBase } from '@/types/api/source_types'
import type { VerdictForm } from '@/types/api/verdict_types'

// how often the view asks whether the export after a verdict has finished: an export takes 40 s on an idle machine and
// about a minute on a busy one (line 1's run, 12 Nov: 41 s and 53 s)
const FOLLOW_EVERY_MS = 2000

/**
 * A person's verdict from the page view (213.b): whether it is taken here at all, asked once, and the export a verdict sets
 * going, followed until it has finished, so the page is loaded again with the verdict in it.
 */
export const useVerdictStore = defineStore('verdict', () => {
  const form = ref<VerdictForm | null>(null)

  async function loadForm(): Promise<void> {
    if (form.value) return
    try {
      form.value = await getVerdictForm()
    } catch {
      form.value = null  // no verdicts where the API cannot say: the view stays read-only
    }
  }

  /** The number of exports of a base that have finished, as last asked. */
  function finishedOf(knowledgeBase: KnowledgeBase): number {
    return form.value?.exports.find(status => status.knowledge_base === knowledgeBase)?.finished ?? 0
  }

  /**
   * Waits until an export of the base has finished after `since` exports, asking every 2 s; resolves with the error the
   * export reported, or null. `stopped` ends the wait early, as when the person leaves the page.
   */
  async function followExport(knowledgeBase: KnowledgeBase, since: number, stopped: () => boolean = () => false): Promise<string | null> {
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, FOLLOW_EVERY_MS))
      if (stopped()) return null
      try {
        form.value = await getVerdictForm()
      } catch {
        continue  // a request lost now and then: ask again
      }
      const status = form.value.exports.find(one => one.knowledge_base === knowledgeBase)
      if (status && status.finished > since && !status.running) return status.last_error ?? null
    }
  }

  return { form, loadForm, finishedOf, followExport }
})
