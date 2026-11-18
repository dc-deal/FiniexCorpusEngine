import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'openUnits.v1'
// how many works keep their opened chapters: the oldest one gives way, so the entry never grows without end
const WORKS_KEPT = 40

/** A work's opened chapters by a key of their own, the works in the order last touched, oldest first. */
type OpenUnits = Record<string, string[]>

function readStored(): OpenUnits {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    // nothing stored is trusted: a work keeps only a list of strings
    return Object.fromEntries(Object.entries(parsed as Record<string, unknown>)
      .filter((entry): entry is [string, string[]] => Array.isArray(entry[1]) && entry[1].every(key => typeof key === 'string')))
  } catch {
    // a corrupt or unreadable entry is the same as none: a remembered fold never breaks the app
    return {}
  }
}

/**
 * Which chapters of a work the reader opened (the operator, 2026-11-10: opened, a page clicked, and on coming back all was folded
 * again). Kept in this browser, per work. A chapter is known by a key of its own, its first page and title, never by the
 * outline's id, which is renumbered whenever the core cuts the outline anew.
 */
export const useOpenUnitsStore = defineStore('openUnits', () => {
  const opened = ref<OpenUnits>(readStored())

  function persist(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(opened.value))
    } catch {
      // a full or blocked storage must not break the app: the fold simply does not survive
    }
  }

  function isOpen(work: string, unit: string): boolean {
    return opened.value[work]?.includes(unit) ?? false
  }

  function setOpen(work: string, unit: string, open: boolean): void {
    if (isOpen(work, unit) === open) return
    const { [work]: current = [], ...others } = opened.value
    const next = open ? [...current, unit] : current.filter(key => key !== unit)
    // the work touched last stands last, and the oldest give way beyond the limit
    const kept = Object.entries(others).slice(-(WORKS_KEPT - 1))
    opened.value = Object.fromEntries(next.length ? [...kept, [work, next]] : kept)
    persist()
  }

  return { isOpen, setOpen }
})
