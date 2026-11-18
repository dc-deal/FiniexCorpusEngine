import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getShelf } from '@/api/api_client'
import type { Shelf } from '@/types/api/shelf_types'

/** The shelf as the core last wrote it: every work, how far it is converted, why pages did not pass. */
export const useShelfStore = defineStore('shelf', () => {
  const shelf = ref<Shelf | null>(null)
  const error = ref<Error | null>(null)

  async function loadShelf(): Promise<void> {
    error.value = null
    try {
      shelf.value = await getShelf()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { shelf, error, loadShelf }
})
