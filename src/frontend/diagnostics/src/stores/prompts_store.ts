import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getPrompts } from '@/api/api_client'
import type { PromptList } from '@/types/api/prompts_types'

/** Every version of the reader's and the judge's instructions, as the core keeps them (148.a). */
export const usePromptsStore = defineStore('prompts', () => {
  const prompts = ref<PromptList | null>(null)
  const error = ref<Error | null>(null)

  async function loadPrompts(): Promise<void> {
    error.value = null
    try {
      prompts.value = await getPrompts()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  return { prompts, error, loadPrompts }
})
