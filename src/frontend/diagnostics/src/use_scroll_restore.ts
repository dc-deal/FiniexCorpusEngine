import { nextTick, onMounted, onUnmounted, watch } from 'vue'
import type { WatchSource } from 'vue'
import { useRoute } from 'vue-router'

/** Where the reader stood in each view, by the view's address, for the tab's session (Y1.a, F5). */
const STORAGE_KEY = 'scroll.v1'

function readAll(): Record<string, unknown> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    // an unreadable entry is the same as none: the view opens at its top
    return {}
  }
}

/**
 * Brings a reload (F5) back to where the reader stood (the operator's Y1.a, 19 Nov). The browser restores the scroll before
 * the data has come, on a page still too short to reach it, so the view says when its data is drawn (`ready`) and the
 * position is set then, once. Until it is, a scroll is the short page's and is not kept; after it, every scroll is kept for
 * this view's address in the tab's session storage. Every storage access is in try/catch: a blocked storage only means the
 * view opens at its top.
 */
export function useScrollRestore(ready: WatchSource<boolean>): void {
  const path = useRoute().fullPath
  let restored = false
  let frame = 0

  function keep(): void {
    if (!restored) return
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readAll(), [path]: Math.round(window.scrollY) }))
      } catch {
        // a full or blocked storage: the position simply does not survive a reload
      }
    })
  }

  onMounted(() => window.addEventListener('scroll', keep, { passive: true }))
  onUnmounted(() => {
    window.removeEventListener('scroll', keep)
    cancelAnimationFrame(frame)
  })

  watch(ready, async isReady => {
    if (!isReady || restored) return
    await nextTick()
    const stood = readAll()[path]
    if (typeof stood === 'number' && Number.isFinite(stood) && stood > 0) window.scrollTo(0, stood)
    restored = true
  }, { immediate: true })
}
