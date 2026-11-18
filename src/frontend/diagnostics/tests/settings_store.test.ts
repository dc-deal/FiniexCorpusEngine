import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { reconcile, useSettingsStore } from '@/stores/settings_store'

const KEY = 'settings.v1'
const DEFAULTS = { pageDetailsOpen: false, workPagesView: 'chapters', routesOpen: false, foldsOpen: {} }

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts from the defaults when nothing is stored: details folded, a work by its chapters, its routes folded', () => {
    expect(useSettingsStore().settings).toEqual(DEFAULTS)
  })

  it('keeps a choice under one versioned key, and finds it again', () => {
    useSettingsStore().setPageDetailsOpen(true)
    useSettingsStore().setWorkPagesView('table')
    useSettingsStore().setRoutesOpen(true)
    useSettingsStore().setFoldOpen('page.history', true)
    const chosen = { pageDetailsOpen: true, workPagesView: 'table', routesOpen: true, foldsOpen: { 'page.history': true } }
    expect(JSON.parse(localStorage.getItem(KEY) ?? 'null')).toEqual({ version: 1, ...chosen })
    setActivePinia(createPinia())
    expect(useSettingsStore().settings).toEqual(chosen)
  })

  it('takes a stored view only when it is one the build knows', () => {
    expect(reconcile({ version: 1, workPagesView: 'tree' }).workPagesView).toBe('chapters')
    expect(reconcile({ version: 1, workPagesView: 'table' }).workPagesView).toBe('table')
  })

  it('reads an entry written before the routes could fold, the routes then folded', () => {
    expect(reconcile({ version: 1, pageDetailsOpen: true, workPagesView: 'table' }))
      .toEqual({ pageDetailsOpen: true, workPagesView: 'table', routesOpen: false, foldsOpen: {} })
  })

  it('removes an entry of another version instead of reading it', () => {
    localStorage.setItem(KEY, JSON.stringify({ version: 0, pageDetailsOpen: true }))
    expect(useSettingsStore().settings.pageDetailsOpen).toBe(false)
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('takes a stored field only when it passes its check, and never an unknown key', () => {
    expect(reconcile({ version: 1, pageDetailsOpen: 'yes', routesOpen: 'open', theme: 'dark' })).toEqual(DEFAULTS)
    // a fold is kept only under a name the build knows, and only as open or folded (decision 183)
    expect(reconcile({ version: 1, foldsOpen: { 'page.lab': true, 'page.anything': true, 'page.history': 'yes' } }).foldsOpen)
      .toEqual({ 'page.lab': true })
    expect(reconcile({ version: 1 })).toEqual(DEFAULTS)
    expect(reconcile(null)).toEqual(DEFAULTS)
  })

  it('treats a corrupt entry as none', () => {
    localStorage.setItem(KEY, '{not json')
    expect(useSettingsStore().settings.pageDetailsOpen).toBe(false)
  })

  it('never breaks the app when the storage refuses', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('full')
    })
    const store = useSettingsStore()
    expect(store.settings.pageDetailsOpen).toBe(false)
    expect(() => store.setPageDetailsOpen(true)).not.toThrow()
    expect(store.settings.pageDetailsOpen).toBe(true)
  })
})
