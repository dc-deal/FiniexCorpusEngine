import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { FacetSelection } from '@/types/facet_types'

const STORAGE_KEY = 'settings.v1'
const SCHEMA_VERSION = 1

/** How a work's pages are shown: by the work's own order, or as one flat table (the operator: the table only on request). */
export type WorkPagesView = 'chapters' | 'table'

/** The folds a reader's choice is kept for (decision 183): a page's Reading History and its Lab. */
export type FoldName = 'page.history' | 'page.lab' | 'ladder.details' | 'page.served' | 'page.coverage'
const FOLD_NAMES: readonly string[] = ['page.history', 'page.lab', 'ladder.details', 'page.served', 'page.coverage'] satisfies FoldName[]

/**
 * What a facet bar keeps across a reload (Y1.a, F5): its picks, its search and its sort, as the FiniexViewer keeps them.
 * An empty `selection` is a bar the reader cleared, and stays cleared.
 */
export interface StoredFacets {
  selection?: FacetSelection
  search: string
  sort: string
}

/** How the reader prefers the views to behave. What they look at belongs to the URL, never here. */
export interface Settings {
  // the page view's check and trace, open or folded
  pageDetailsOpen: boolean
  // a work's pages by its chapters or as a table, where the work has chapters
  workPagesView: WorkPagesView
  // a work's routes, folded to their one line or open as their table (159.a)
  routesOpen: boolean
  // the named folds the reader opened (true) or folded (false); a fold not named here takes its default, folded
  foldsOpen: Partial<Record<FoldName, boolean>>
  // each facet bar's state by the bar's own name, one entry per bar (Y1.a); a bar nobody touched has none
  bars: Record<string, StoredFacets>
}

const DEFAULTS: Settings = { pageDetailsOpen: false, workPagesView: 'chapters', routesOpen: false, foldsOpen: {}, bars: {} }
const WORK_PAGES_VIEWS: readonly string[] = ['chapters', 'table'] satisfies WorkPagesView[]

/** What is written to storage: the settings plus the schema they were written under. */
interface StoredSettings extends Settings {
  version: number
}

/** A stored list of words, the words alone: anything else in it is dropped. */
function words(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : []
}

/** One stored bar, field by field: a field of the wrong shape takes its empty value, a facet without a word is dropped. */
function readFacets(value: unknown): StoredFacets {
  const stored = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const facets: StoredFacets = {
    search: typeof stored['search'] === 'string' ? stored['search'] : '',
    sort: typeof stored['sort'] === 'string' ? stored['sort'] : '',
  }
  const selection = stored['selection']
  if (selection && typeof selection === 'object' && !Array.isArray(selection)) {
    facets.selection = {}
    for (const [facet, picked] of Object.entries(selection)) {
      const valid = words(picked)
      if (valid.length) facets.selection[facet] = valid
    }
  }
  return facets
}

/**
 * A stored value brought in line with this build, field by field. Nothing stored is trusted: the result starts from the
 * defaults and takes a stored field only when it passes its own check, so an unknown key is never copied and a missing
 * one takes its default. The version guards what a field check cannot: a field that kept its name and changed its meaning.
 */
export function reconcile(stored: unknown): Settings {
  if (!stored || typeof stored !== 'object') return { ...DEFAULTS }
  const raw = stored as Partial<StoredSettings>
  if (raw.version !== SCHEMA_VERSION) return { ...DEFAULTS }
  const settings: Settings = { ...DEFAULTS, foldsOpen: {}, bars: {} }
  if (typeof raw.pageDetailsOpen === 'boolean') settings.pageDetailsOpen = raw.pageDetailsOpen
  if (typeof raw.routesOpen === 'boolean') settings.routesOpen = raw.routesOpen
  if (raw.foldsOpen && typeof raw.foldsOpen === 'object') {
    for (const [name, open] of Object.entries(raw.foldsOpen)) {
      if (FOLD_NAMES.includes(name) && typeof open === 'boolean') settings.foldsOpen[name as FoldName] = open
    }
  }
  if (typeof raw.workPagesView === 'string' && WORK_PAGES_VIEWS.includes(raw.workPagesView)) {
    settings.workPagesView = raw.workPagesView
  }
  if (raw.bars && typeof raw.bars === 'object' && !Array.isArray(raw.bars)) {
    for (const [bar, facets] of Object.entries(raw.bars)) settings.bars[bar] = readFacets(facets)
  }
  return settings
}

function readStored(): unknown {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    // another version's entry is removed rather than left behind: nothing will ever read it again
    if (parsed && typeof parsed === 'object' && (parsed as Partial<StoredSettings>).version !== SCHEMA_VERSION) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return parsed
  } catch {
    // a corrupt or unreadable entry is the same as none: a preference never breaks the app
    return null
  }
}

/** The reader's preferences, kept in this browser under one versioned key. */
export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings>(reconcile(readStored()))

  function persist(): void {
    try {
      const payload: StoredSettings = { version: SCHEMA_VERSION, ...settings.value }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // a full or blocked storage must not break the app: the preference simply does not survive
    }
  }

  function setPageDetailsOpen(open: boolean): void {
    if (settings.value.pageDetailsOpen === open) return
    settings.value.pageDetailsOpen = open
    persist()
  }

  function setWorkPagesView(view: WorkPagesView): void {
    if (settings.value.workPagesView === view) return
    settings.value.workPagesView = view
    persist()
  }

  function setRoutesOpen(open: boolean): void {
    if (settings.value.routesOpen === open) return
    settings.value.routesOpen = open
    persist()
  }

  function setFoldOpen(name: FoldName, open: boolean): void {
    if (settings.value.foldsOpen[name] === open) return
    settings.value.foldsOpen = { ...settings.value.foldsOpen, [name]: open }
    persist()
  }

  /** A facet bar's state, written whole each time the reader changes it (Y1.a). */
  function setFacets(bar: string, facets: StoredFacets): void {
    settings.value.bars = { ...settings.value.bars, [bar]: facets }
    persist()
  }

  return { settings, setPageDetailsOpen, setWorkPagesView, setRoutesOpen, setFoldOpen, setFacets }
})
