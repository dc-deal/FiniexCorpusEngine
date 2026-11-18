import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getWorks } from '@/api/api_client'
import type { Work } from '@/types/api/source_types'

/** The sources as the diagnostics API serves them. The store asks; components read and dispatch. */
export const useSourceStore = defineStore('source', () => {
  const works = ref<Work[]>([])
  const error = ref<Error | null>(null)
  // false until the first answer: an empty list before it is not "the catalog lists no works"
  const loaded = ref(false)

  async function loadWorks(): Promise<void> {
    error.value = null
    try {
      works.value = await getWorks()
      loaded.value = true
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { works, error, loaded, loadWorks }
})
