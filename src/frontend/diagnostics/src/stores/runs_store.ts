import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getRun, getRuns } from '@/api/api_client'
import type { RunDetail, RunList } from '@/types/api/runs_types'
import type { KnowledgeBase } from '@/types/api/source_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * The pipeline's runs, and the one run on show. A run's answer is matched by the request it answers (`runOf`), so a slow
 * answer for another run never stands for the one asked for after it.
 */
export const useRunsStore = defineStore('runs', () => {
  const runs = ref<RunList | null>(null)
  const runsError = ref<Error | null>(null)
  const run = ref<RunDetail | null>(null)
  const runError = ref<Error | null>(null)
  const runFor = ref('')
  let runAsked = ''

  async function loadRuns(): Promise<void> {
    runsError.value = null
    try {
      runs.value = await getRuns()
    } catch (caught) {
      runsError.value = asError(caught)
    }
  }

  async function loadRun(knowledgeBase: KnowledgeBase, runId: number): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, runId])
    runAsked = asked
    runError.value = null
    try {
      const answer = await getRun(knowledgeBase, runId)
      if (runAsked === asked) {
        run.value = answer
        runFor.value = asked
      }
    } catch (caught) {
      if (runAsked === asked) runError.value = asError(caught)
    }
  }

  /** The run, when the answer on hand is the one asked for this run; null while it is on its way. */
  function runOf(knowledgeBase: KnowledgeBase, runId: number): RunDetail | null {
    return runFor.value === JSON.stringify([knowledgeBase, runId]) ? run.value : null
  }

  return { runs, runsError, runError, loadRuns, loadRun, runOf }
})
