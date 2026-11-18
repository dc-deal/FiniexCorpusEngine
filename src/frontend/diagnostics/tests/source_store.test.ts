import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getWorks } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { useSourceStore } from '@/stores/source_store'
import { aWork } from './work_fixture'

vi.mock('@/api/api_client', () => ({ getWorks: vi.fn() }))

describe('useSourceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getWorks).mockReset()
  })

  it('holds the works the API served, and says it has loaded', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork()])
    const store = useSourceStore()
    await store.loadWorks()
    expect(store.works.map(work => work.id)).toEqual(['openstax_principles_of_finance_2e'])
    expect(store.loaded).toBe(true)
  })

  it('is not loaded before the first answer, so no list reads as an empty catalog', () => {
    expect(useSourceStore().loaded).toBe(false)
  })

  it('keeps the failure and stays unloaded when the API refuses', async () => {
    vi.mocked(getWorks).mockRejectedValue(new ApiError(500, 'Internal Server Error'))
    const store = useSourceStore()
    await store.loadWorks()
    expect(store.error).toBeInstanceOf(ApiError)
    expect(store.loaded).toBe(false)
  })

  it('clears an earlier failure when asked again', async () => {
    vi.mocked(getWorks).mockRejectedValueOnce(new ApiError(null, 'Network Error')).mockResolvedValueOnce([aWork()])
    const store = useSourceStore()
    await store.loadWorks()
    await store.loadWorks()
    expect(store.error).toBeNull()
    expect(store.works).toHaveLength(1)
  })
})
