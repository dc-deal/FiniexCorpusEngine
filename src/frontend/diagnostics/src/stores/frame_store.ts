import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAppInfo } from '@/api/api_client'
import type { AppInfo } from '@/types/api/app_types'

/** The name a view gave itself, at the address it gave it for. */
interface ViewName {
  path: string
  name: string
}

/**
 * The frame around every view: the tool's name as the app config holds it, read through the API and never written here
 * (decision 149.c), and the name the view on show gives itself once its data says what it is, such as a work's title and
 * page, for the header and the browser tab.
 */
export const useFrameStore = defineStore('frame', () => {
  const info = ref<AppInfo | null>(null)
  const error = ref<Error | null>(null)
  // kept with its address: a name given at a page left behind is not the name of the view on show
  const named = ref<ViewName | null>(null)

  async function loadInfo(): Promise<void> {
    error.value = null
    try {
      info.value = await getAppInfo()
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error(String(caught))
    }
  }

  function nameView(path: string, name: string): void {
    named.value = { path, name }
  }

  return { info, error, named, loadInfo, nameView }
})
