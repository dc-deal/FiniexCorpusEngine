import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCodePage, getCodeWork } from '@/api/api_client'
import type { CodePage, CodeWork } from '@/types/api/code_types'
import type { KnowledgeBase } from '@/types/api/source_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * A book's companion code and the file on show (#12), as the EPUB store keeps a work and its section: each answer matched by
 * the request it answers (`workOf`, `pageOf`), so a slow answer for another work or file never stands for the one asked for
 * after it.
 */
export const useCodeStore = defineStore('code', () => {
  const work = ref<CodeWork | null>(null)
  const workError = ref<Error | null>(null)
  const workFor = ref('')
  let workAsked = ''
  const page = ref<CodePage | null>(null)
  const pageError = ref<Error | null>(null)
  const pageFor = ref('')
  let pageAsked = ''

  async function loadWork(knowledgeBase: KnowledgeBase, key: string): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, key])
    workAsked = asked
    workError.value = null
    try {
      const answer = await getCodeWork(knowledgeBase, key)
      if (workAsked === asked) {
        work.value = answer
        workFor.value = asked
      }
    } catch (caught) {
      if (workAsked === asked) workError.value = asError(caught)
    }
  }

  async function loadPage(knowledgeBase: KnowledgeBase, key: string, label: string): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, key, label])
    pageAsked = asked
    pageError.value = null
    try {
      const answer = await getCodePage(knowledgeBase, key, label)
      if (pageAsked === asked) {
        page.value = answer
        pageFor.value = asked
      }
    } catch (caught) {
      if (pageAsked === asked) pageError.value = asError(caught)
    }
  }

  /** The work, when the answer on hand is the one asked for it; null while it is on its way. */
  function workOf(knowledgeBase: KnowledgeBase, key: string): CodeWork | null {
    return workFor.value === JSON.stringify([knowledgeBase, key]) ? work.value : null
  }

  /** The file, when the answer on hand is the one asked for it; null while it is on its way. */
  function pageOf(knowledgeBase: KnowledgeBase, key: string, label: string): CodePage | null {
    return pageFor.value === JSON.stringify([knowledgeBase, key, label]) ? page.value : null
  }

  return { workError, pageError, loadWork, loadPage, workOf, pageOf }
})
