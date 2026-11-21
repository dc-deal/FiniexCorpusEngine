import { defineStore } from 'pinia'
import { ref } from 'vue'

/** How long a toast stands, unless a person holds it by pointing at it or focusing it (the operator, 21 Nov: about 4 s). */
export const TOAST_MS = 4000

/** A short word that something was done, and a line on what follows from it. */
export interface Toast {
  id: number
  text: string
  detail?: string | null
  failed?: boolean
}

interface Clock {
  timer?: ReturnType<typeof setTimeout>
  left: number  // what is left of its time
  since: number  // when its time last started running
  held: boolean
}

/**
 * The app's one way to say a moment of "done" (the operator, 21 Nov: "Verdict recorded" after the panel closes; later "saved"
 * moments the same): toasts near the window's top right, each for about 4 s, held while a person points at it or focuses
 * it, its time running on from where it stood once they leave. A toast's line can follow what it set going, as a verdict's
 * export, while it stands.
 */
export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])
  const clocks = new Map<number, Clock>()
  let next = 1

  function dismiss(id: number): void {
    clearTimeout(clocks.get(id)?.timer)
    clocks.delete(id)
    toasts.value = toasts.value.filter(toast => toast.id !== id)
  }

  function run(id: number): void {
    const clock = clocks.get(id)
    if (!clock || clock.held) return
    clock.since = Date.now()
    clock.timer = setTimeout(() => dismiss(id), clock.left)
  }

  /** Shows a toast and returns its id, to change its line or take it away. */
  function show(toast: Omit<Toast, 'id'>): number {
    const id = next++
    toasts.value = [...toasts.value, { ...toast, id }]
    clocks.set(id, { left: TOAST_MS, since: Date.now(), held: false })
    run(id)
    return id
  }

  /** Changes what a toast says, while it stands; a toast already gone is left gone. Whether it still stood. */
  function update(id: number, change: Partial<Omit<Toast, 'id'>>): boolean {
    if (!toasts.value.some(toast => toast.id === id)) return false
    toasts.value = toasts.value.map(toast => (toast.id === id ? { ...toast, ...change } : toast))
    return true
  }

  /** Holds a toast while a person points at it or focuses it. */
  function hold(id: number): void {
    const clock = clocks.get(id)
    if (!clock || clock.held) return
    clearTimeout(clock.timer)
    clock.left = Math.max(0, clock.left - (Date.now() - clock.since))
    clock.held = true
  }

  /** Lets a held toast's time run on from where it stood. */
  function release(id: number): void {
    const clock = clocks.get(id)
    if (!clock || !clock.held) return
    clock.held = false
    run(id)
  }

  return { toasts, show, update, hold, release, dismiss }
})
