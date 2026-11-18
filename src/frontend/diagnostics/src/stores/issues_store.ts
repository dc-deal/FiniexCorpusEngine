import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getIssues } from '@/api/api_client'
import type { IssueList } from '@/types/api/page_types'

/**
 * The pages a person should look at, over every work of every knowledge base served: the readings the judge found bad, those
 * the provider blocked or the reader declined, a stopped work's pages.
 */
export const useIssuesStore = defineStore('issues', () => {
  const issues = ref<IssueList | null>(null)
  const error = ref<Error | null>(null)

  async function loadIssues(): Promise<void> {
    error.value = null
    try {
      issues.value = await getIssues()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { issues, error, loadIssues }
})
