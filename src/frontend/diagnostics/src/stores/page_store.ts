import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getPage, getPageChunks, getRecall, getWorkPages } from '@/api/api_client'
import type { PageChunks, PageDetail, Recalled, WorkPages } from '@/types/api/page_types'
import type { KnowledgeBase } from '@/types/api/source_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

// the request an answer belongs to; JSON keeps any character of an id from running into the next part
function key(...parts: (string | number)[]): string {
  return JSON.stringify(parts)
}

/**
 * The pages of the work on show and the one page on show. Each answer replaces the last, and an answer that arrives
 * after the reader moved on is dropped: a slow page must not overwrite the one asked for after it. A view takes an answer
 * by the request it answers (`pagesOf`, `pageOf`), never by the answer's own fields, so data that named another knowledge
 * base than its address would still be shown rather than wait forever (review, 2026-11-04).
 */
export const usePageStore = defineStore('page', () => {
  const workPages = ref<WorkPages | null>(null)
  const pagesError = ref<Error | null>(null)
  const pagesFor = ref('')
  const detail = ref<PageDetail | null>(null)
  const detailError = ref<Error | null>(null)
  const detailFor = ref('')
  const chunks = ref<PageChunks | null>(null)
  const chunksError = ref<Error | null>(null)
  const chunksFor = ref('')
  const recalled = ref<Recalled | null>(null)
  const recallError = ref<Error | null>(null)
  const recallFor = ref('')
  let recallAsked = ''
  let pagesAsked = ''
  let detailAsked = ''
  let chunksAsked = ''

  async function loadWorkPages(knowledgeBase: KnowledgeBase, sourceId: string): Promise<void> {
    const asked = key(knowledgeBase, sourceId)
    pagesAsked = asked
    pagesError.value = null
    if (pagesFor.value !== asked) {
      workPages.value = null
      pagesFor.value = ''
    }
    try {
      const answer = await getWorkPages(knowledgeBase, sourceId)
      if (pagesAsked === asked) {
        workPages.value = answer
        pagesFor.value = asked
      }
    } catch (caught) {
      if (pagesAsked === asked) pagesError.value = asError(caught)
    }
  }

  async function loadPage(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<void> {
    const asked = key(knowledgeBase, sourceId, pdfPage)
    detailAsked = asked
    detailError.value = null
    detail.value = null
    detailFor.value = ''
    try {
      const answer = await getPage(knowledgeBase, sourceId, pdfPage)
      if (detailAsked === asked) {
        detail.value = answer
        detailFor.value = asked
      }
    } catch (caught) {
      if (detailAsked === asked) detailError.value = asError(caught)
    }
  }

  /**
   * The page asked again after it changed, as after a person's verdict and its export (213.b): the answer on screen stays
   * until the new one comes, so the view does not drop to its loading line; nothing changes if the person has moved on.
   */
  async function reloadPage(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<void> {
    const asked = key(knowledgeBase, sourceId, pdfPage)
    if (detailAsked !== asked) return
    try {
      const answer = await getPage(knowledgeBase, sourceId, pdfPage)
      if (detailAsked === asked) {
        detail.value = answer
        detailFor.value = asked
      }
    } catch {
      // the page on screen stays; the next visit asks again
    }
  }

  /** A read page's chunks placed in its quoted blocks, asked only when they are to be shown (W4); asked once per page. */
  async function loadChunks(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<void> {
    const asked = key(knowledgeBase, sourceId, pdfPage)
    if (chunksAsked === asked && !chunksError.value) return
    chunksAsked = asked
    chunksError.value = null
    chunks.value = null
    chunksFor.value = ''
    try {
      const answer = await getPageChunks(knowledgeBase, sourceId, pdfPage)
      if (chunksAsked === asked) {
        chunks.value = answer
        chunksFor.value = asked
      }
    } catch (caught) {
      if (chunksAsked === asked) chunksError.value = asError(caught)
    }
  }

  /** One judgement of a page shown as it judged (181.a); the last asked wins, as for the page. */
  async function loadRecall(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number, judgement: string): Promise<void> {
    const asked = key(knowledgeBase, sourceId, pdfPage, judgement)
    recallAsked = asked
    recallError.value = null
    if (recallFor.value !== asked) {
      recalled.value = null
      recallFor.value = ''
    }
    try {
      const answer = await getRecall(knowledgeBase, sourceId, pdfPage, judgement)
      if (recallAsked === asked) {
        recalled.value = answer
        recallFor.value = asked
      }
    } catch (caught) {
      if (recallAsked === asked) recallError.value = asError(caught)
    }
  }

  /** The recalled judgement, when the answer on hand is the one asked; null while it is on its way. */
  function recallOf(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number, judgement: string): Recalled | null {
    return recallFor.value === key(knowledgeBase, sourceId, pdfPage, judgement) ? recalled.value : null
  }

  /** The page's chunks, when the answer on hand is the one asked for this page; null while it is on its way. */
  function chunksOf(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): PageChunks | null {
    return chunksFor.value === key(knowledgeBase, sourceId, pdfPage) ? chunks.value : null
  }

  /** The work's pages, when the answer on hand is the one asked for this work; null while it is on its way. */
  function pagesOf(knowledgeBase: KnowledgeBase, sourceId: string): WorkPages | null {
    return pagesFor.value === key(knowledgeBase, sourceId) ? workPages.value : null
  }

  /** The page, when the answer on hand is the one asked for this page; null while it is on its way. */
  function pageOf(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): PageDetail | null {
    return detailFor.value === key(knowledgeBase, sourceId, pdfPage) ? detail.value : null
  }

  return { workPages, pagesError, detail, detailError, chunks, chunksError, recallError, loadWorkPages, loadPage, reloadPage,
    loadChunks, loadRecall, pagesOf, pageOf, chunksOf, recallOf }
})
