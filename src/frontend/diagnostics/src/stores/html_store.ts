import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getHtmlArticle, getHtmlWork } from '@/api/api_client'
import type { HtmlArticle, HtmlWork } from '@/types/api/html_types'
import type { KnowledgeBase } from '@/types/api/source_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * An HTML work and the article on show. Each answer is matched by the request it answers (`workOf`, `articleOf`), so a
 * slow answer for another work or article never stands for the one asked for after it. A section of the article on hand
 * needs no request: the view scrolls to it.
 */
export const useHtmlStore = defineStore('html', () => {
  const work = ref<HtmlWork | null>(null)
  const workError = ref<Error | null>(null)
  const workFor = ref('')
  let workAsked = ''
  const article = ref<HtmlArticle | null>(null)
  const articleError = ref<Error | null>(null)
  const articleFor = ref('')
  let articleAsked = ''

  async function loadWork(knowledgeBase: KnowledgeBase, sourceId: string): Promise<void> {
    const asked = JSON.stringify([knowledgeBase, sourceId])
    workAsked = asked
    workError.value = null
    try {
      const answer = await getHtmlWork(knowledgeBase, sourceId)
      if (workAsked === asked) {
        work.value = answer
        workFor.value = asked
      }
    } catch (caught) {
      if (workAsked === asked) workError.value = asError(caught)
    }
  }

  /** The article that holds a section; none is asked for where the article on hand already holds it. */
  async function loadArticle(knowledgeBase: KnowledgeBase, sourceId: string, label: string): Promise<void> {
    if (articleOf(knowledgeBase, sourceId, label)) return
    const asked = JSON.stringify([knowledgeBase, sourceId, label])
    articleAsked = asked
    articleError.value = null
    try {
      const answer = await getHtmlArticle(knowledgeBase, sourceId, label)
      if (articleAsked === asked) {
        article.value = answer
        articleFor.value = JSON.stringify([knowledgeBase, sourceId])
      }
    } catch (caught) {
      if (articleAsked === asked) articleError.value = asError(caught)
    }
  }

  /** The work, when the answer on hand is the one asked for it; null while it is on its way. */
  function workOf(knowledgeBase: KnowledgeBase, sourceId: string): HtmlWork | null {
    return workFor.value === JSON.stringify([knowledgeBase, sourceId]) ? work.value : null
  }

  /** The article on hand, when it is of this work and holds this section; null while the one that does is on its way. */
  function articleOf(knowledgeBase: KnowledgeBase, sourceId: string, label: string): HtmlArticle | null {
    if (articleFor.value !== JSON.stringify([knowledgeBase, sourceId]) || !article.value) return null
    return article.value.entries.some(entry => entry.label === label) ? article.value : null
  }

  return { workError, articleError, loadWork, loadArticle, workOf, articleOf }
})
