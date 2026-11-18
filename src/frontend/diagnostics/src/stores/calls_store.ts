import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCalls } from '@/api/api_client'
import type { CallList } from '@/types/api/calls_types'

/** The search server's call log as the API reads it: who asked what, which pages answered, how long it took. */
export const useCallsStore = defineStore('calls', () => {
  const list = ref<CallList | null>(null)
  const error = ref<Error | null>(null)

  async function loadCalls(): Promise<void> {
    error.value = null
    try {
      list.value = await getCalls()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { list, error, loadCalls }
})
