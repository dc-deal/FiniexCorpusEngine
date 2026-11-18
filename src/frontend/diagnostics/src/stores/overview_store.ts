import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getOverview, getPages } from '@/api/api_client'
import type { Overview, PageList } from '@/types/api/overview_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * The overview, and the pages behind one of its figures. An answer for filters the reader has since left is dropped, and a
 * view takes the page list by the filters it answers.
 */
export const useOverviewStore = defineStore('overview', () => {
  const overview = ref<Overview | null>(null)
  const overviewError = ref<Error | null>(null)
  const pageList = ref<PageList | null>(null)
  const pagesError = ref<Error | null>(null)
  const listFor = ref('')
  let asked = ''

  async function loadOverview(): Promise<void> {
    overviewError.value = null
    try {
      overview.value = await getOverview()
    } catch (caught) {
      overviewError.value = asError(caught)
    }
  }

  async function loadPages(filters: Record<string, string>): Promise<void> {
    const key = JSON.stringify(filters)
    asked = key
    pagesError.value = null
    try {
      const answer = await getPages(filters)
      if (asked === key) {
        pageList.value = answer
        listFor.value = key
      }
    } catch (caught) {
      if (asked === key) pagesError.value = asError(caught)
    }
  }

  /** The pages, when the list on hand answers these filters; null while it is on its way. */
  function pagesOf(filters: Record<string, string>): PageList | null {
    return listFor.value === JSON.stringify(filters) ? pageList.value : null
  }

  return { overview, overviewError, pagesError, loadOverview, loadPages, pagesOf }
})
