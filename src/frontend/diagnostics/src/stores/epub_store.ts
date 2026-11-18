import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getEpubSection, getEpubWork } from '@/api/api_client'
import type { EpubSection, EpubWork } from '@/types/api/epub_types'
import type { KnowledgeBase } from '@/types/api/source_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * A licensed EPUB work and the section on show (123.a), as the HTML store keeps an HTML work's: each answer matched by the
 * request it answers (`workOf`, `sectionOf`), so a slow answer for another work or section never stands for the one asked
 * for after it.
 */
export const useEpubStore = defineStore('epub', () => {
  const work = ref<EpubWork | null>(null)
  const workError = ref<Error | null>(null)
  const workFor = ref('')
  let workAsked = ''
  const section = ref<EpubSection | null>(null)
  const sectionError = ref<Error | null>(null)
  const sectionFor = ref('')
  let sectionAsked = ''

  async function loadWork(knowledgeBase: KnowledgeBase, sourceId: string): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, sourceId])
    workAsked = asked
    workError.value = null
    try {
      const answer = await getEpubWork(knowledgeBase, sourceId)
      if (workAsked === asked) {
        work.value = answer
        workFor.value = asked
      }
    } catch (caught) {
      if (workAsked === asked) workError.value = asError(caught)
    }
  }

  async function loadSection(knowledgeBase: KnowledgeBase, sourceId: string, label: string): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, sourceId, label])
    sectionAsked = asked
    sectionError.value = null
    try {
      const answer = await getEpubSection(knowledgeBase, sourceId, label)
      if (sectionAsked === asked) {
        section.value = answer
        sectionFor.value = asked
      }
    } catch (caught) {
      if (sectionAsked === asked) sectionError.value = asError(caught)
    }
  }

  /** The work, when the answer on hand is the one asked for it; null while it is on its way. */
  function workOf(knowledgeBase: KnowledgeBase, sourceId: string): EpubWork | null {
    return workFor.value === JSON.stringify([knowledgeBase, sourceId]) ? work.value : null
  }

  /** The section, when the answer on hand is the one asked for it; null while it is on its way. */
  function sectionOf(knowledgeBase: KnowledgeBase, sourceId: string, label: string): EpubSection | null {
    return sectionFor.value === JSON.stringify([knowledgeBase, sourceId, label]) ? section.value : null
  }

  return { workError, sectionError, loadWork, loadSection, workOf, sectionOf }
})
