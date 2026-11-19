import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { useSettingsStore } from '@/stores/settings_store'
import { useFacetState } from '@/use_facet_state'
import type { FacetState } from '@/use_facet_state'

// derived from the FiniexViewer's with the facet bar (Y1.a); the state is kept in this app's `settings.v1`, and the
// viewer's default selection and scope are left out, as no view here uses them (stage C)
function mountBar(): FacetState {
  let api!: FacetState
  mount(defineComponent({
    setup() {
      api = useFacetState('sources', 'title')
      return () => null
    },
  }))
  return api
}

/** What a reload finds: the stored settings, read again by a fresh store. */
function reload(): void {
  setActivePinia(createPinia())
}

describe('useFacetState', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('opens an untouched bar unnarrowed, on its default sort', () => {
    const bar = mountBar()
    expect(bar.selection.value).toEqual({})
    expect(bar.search.value).toBe('')
    expect(bar.sort.value).toBe('title')
  })

  it('brings back what the reader left after a reload: narrowing, search and sort', async () => {
    const bar = mountBar()
    bar.selection.value = { format: ['html'] }
    bar.search.value = 'kelly'
    bar.sort.value = 'year'
    await flushPromises()

    reload()
    const again = mountBar()
    expect(again.selection.value).toEqual({ format: ['html'] })
    expect(again.search.value).toBe('kelly')
    expect(again.sort.value).toBe('year')
  })

  it('keeps a cleared bar cleared after a reload, its sort kept', async () => {
    const bar = mountBar()
    bar.selection.value = { format: ['html'] }
    bar.sort.value = 'year'
    await flushPromises()
    bar.selection.value = {}
    await flushPromises()

    reload()
    const again = mountBar()
    expect(again.selection.value).toEqual({})
    expect(again.sort.value).toBe('year')
  })

  it('stores nothing for a bar nobody touched', async () => {
    mountBar()
    await flushPromises()
    expect(useSettingsStore().settings.bars).toEqual({})
    expect(localStorage.getItem('settings.v1')).toBeNull()
  })
})
