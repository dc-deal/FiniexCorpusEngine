import { defineStore } from 'pinia'
import { ref } from 'vue'
import { callLibrarian, getLibrarian } from '@/api/api_client'
import type { LibrarianCall, LibrarianInfo } from '@/types/api/librarian_types'
import type { FormValues } from '@/librarian_form'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/**
 * The Librarian page (L1.a): the tools the running librarian lists, and for each tool its form as a person left it and the
 * answer of its last call, so a tab shows them again when it is chosen again. A call is made once for its arguments: the
 * address that names it, read again, makes no second one; Run makes it again on purpose.
 */
export const useLibrarianStore = defineStore('librarian', () => {
  const info = ref<LibrarianInfo | null>(null)
  const infoError = ref<Error | null>(null)
  const calls = ref<Record<string, LibrarianCall>>({})
  const callErrors = ref<Record<string, Error>>({})
  const forms = ref<Record<string, FormValues>>({})
  const running = ref<string | null>(null)
  const asked: Record<string, string> = {}  // each tool's last call, as its arguments

  async function loadInfo(): Promise<void> {
    infoError.value = null
    try {
      info.value = await getLibrarian()
    } catch (caught) {
      infoError.value = asError(caught)
    }
  }

  async function run(tool: string, args: Record<string, unknown>, again = false): Promise<void> {
    const key = JSON.stringify(args)
    if (!again && asked[tool] === key) return
    asked[tool] = key
    running.value = tool
    const errors = { ...callErrors.value }
    Reflect.deleteProperty(errors, tool)
    callErrors.value = errors
    try {
      calls.value = { ...calls.value, [tool]: await callLibrarian(tool, args) }
    } catch (caught) {
      callErrors.value = { ...callErrors.value, [tool]: asError(caught) }
    } finally {
      if (running.value === tool) running.value = null
    }
  }

  function keepForm(tool: string, values: FormValues): void {
    forms.value = { ...forms.value, [tool]: values }
  }

  return { info, infoError, calls, callErrors, forms, running, loadInfo, run, keepForm }
})
