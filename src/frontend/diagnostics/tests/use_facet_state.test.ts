import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { useSettingsStore } from '@/stores/settings_store'
import { useFacetState } from '@/use_facet_state'
import type { FacetState, FacetStateOptions } from '@/use_facet_state'

// ported from the FiniexViewer with the facet bar (Y1.a); the state is kept in this app's `settings.v1`
const DEFAULT = { kb: ['free'] }

function mountBar(options: FacetStateOptions = {}): FacetState {
  let api!: FacetState
  mount(defineComponent({
    setup() {
      api = useFacetState('sources', 'title', options)
      return () => null
    },
  }))
  return api
}

/** What a reload finds: the stored settings, read again by a fresh store. */
function reload(): void {
  setActivePinia(createPinia())
}

function store(entry: object): void {
  localStorage.setItem('settings.v1', JSON.stringify({ version: 1, bars: { sources: entry } }))
}

describe('useFacetState', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('opens an untouched bar on its defaults', () => {
    const bar = mountBar({ defaultSelection: DEFAULT })
    expect(bar.selection.value).toEqual(DEFAULT)
    expect(bar.search.value).toBe('')
    expect(bar.sort.value).toBe('title')
  })

  it('brings back what the reader left after a reload: narrowing, search and sort', async () => {
    const bar = mountBar({ defaultSelection: DEFAULT })
    bar.selection.value = { format: ['html'] }
    bar.search.value = 'kelly'
    bar.sort.value = 'year'
    await flushPromises()

    reload()
    const again = mountBar({ defaultSelection: DEFAULT })
    expect(again.selection.value).toEqual({ format: ['html'] })
    expect(again.search.value).toBe('kelly')
    expect(again.sort.value).toBe('year')
  })

  /** Cleared is a choice: a reload must not hand the default back to a reader who removed it. */
  it('keeps a cleared bar cleared after a reload', async () => {
    const bar = mountBar({ defaultSelection: DEFAULT })
    bar.selection.value = {}
    await flushPromises()

    reload()
    expect(mountBar({ defaultSelection: DEFAULT }).selection.value).toEqual({})
  })

  it('stores nothing for a bar nobody touched', async () => {
    mountBar({ defaultSelection: DEFAULT })
    await flushPromises()
    expect(useSettingsStore().settings.bars).toEqual({})
    expect(localStorage.getItem('settings.v1')).toBeNull()
  })

  it('drops a narrowing stored for another scope and keeps its sort', () => {
    store({ selection: { state: ['blocked'] }, search: 'p. 3', sort: 'year', scope: 'work_a' })
    const bar = mountBar({ scope: () => 'work_b' })
    expect(bar.selection.value).toEqual({})
    expect(bar.search.value).toBe('')
    expect(bar.sort.value).toBe('year')
  })

  it('restores a narrowing stored for the same scope', () => {
    store({ selection: { state: ['blocked'] }, search: 'p. 3', sort: 'year', scope: 'work_a' })
    const bar = mountBar({ scope: () => 'work_a' })
    expect(bar.selection.value).toEqual({ state: ['blocked'] })
    expect(bar.search.value).toBe('p. 3')
  })

  it('drops the narrowing when the scope moves under a mounted bar, and stores the new scope', async () => {
    const work = ref('work_a')
    const bar = mountBar({ scope: () => work.value })
    bar.selection.value = { state: ['blocked'] }
    bar.search.value = 'p. 3'
    bar.sort.value = 'year'
    await flushPromises()

    work.value = 'work_b'
    await flushPromises()
    expect(bar.selection.value).toEqual({})
    expect(bar.search.value).toBe('')
    expect(bar.sort.value).toBe('year')
    expect(useSettingsStore().settings.bars['sources']).toMatchObject({ scope: 'work_b', search: '' })
  })
})
