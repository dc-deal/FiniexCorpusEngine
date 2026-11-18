import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getErrorClasses } from '@/api/api_client'
import type { ErrorClassList } from '@/types/api/errors_types'

/** The findings of the export grouped into error classes, as the API counted them. */
export const useErrorsStore = defineStore('errors', () => {
  const errors = ref<ErrorClassList | null>(null)
  const error = ref<Error | null>(null)

  async function loadErrors(): Promise<void> {
    error.value = null
    try {
      errors.value = await getErrorClasses()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { errors, error, loadErrors }
})
