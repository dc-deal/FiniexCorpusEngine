import { defineStore } from 'pinia'
import { ref } from 'vue'
import { searchPages } from '@/api/api_client'
import type { Corpus, SearchAnswer } from '@/types/api/search_types'

// the request an answer belongs to; JSON keeps any character of the question from running into the corpus
function key(query: string, corpus: Corpus): string {
  return JSON.stringify([query, corpus])
}

/**
 * The search on show. Each answer replaces the last, and an answer that arrives after the reader asked something else is
 * dropped: the first search after a start can take up to a minute, and a later question must not be overwritten by it.
 */
export const useSearchStore = defineStore('search', () => {
  const answer = ref<SearchAnswer | null>(null)
  const answerFor = ref('')
  const error = ref<Error | null>(null)
  let asked = ''

  async function search(query: string, corpus: Corpus): Promise<void> {
    const wanted = key(query, corpus)
    asked = wanted
    error.value = null
    try {
      const result = await searchPages(query, corpus)
      if (asked === wanted) {
        answer.value = result
        answerFor.value = wanted
      }
    } catch (caught) {
      if (asked === wanted) error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  /** The answer, when the one on hand answers this question; null while it is on its way. */
  function answerOf(query: string, corpus: Corpus): SearchAnswer | null {
    return answerFor.value === key(query, corpus) ? answer.value : null
  }

  return { answer, error, search, answerOf }
})
