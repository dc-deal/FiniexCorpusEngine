import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getPage, getWorkPages } from '@/api/api_client'
import { usePageStore } from '@/stores/page_store'
import type { PageDetail, WorkPages } from '@/types/api/page_types'
import { aPageDetail, aPageRow, aWorkPages } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getWorkPages: vi.fn(),
}))

describe('usePageStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getPage).mockReset()
    vi.mocked(getWorkPages).mockReset()
  })

  it('drops an answer that arrives after the reader moved on', async () => {
    let answerSlow: (page: PageDetail) => void = () => {}
    vi.mocked(getPage)
      .mockReturnValueOnce(new Promise(resolve => { answerSlow = resolve }))
      .mockResolvedValueOnce(aPageDetail({ pdf_page: 5 }))
    const store = usePageStore()
    const slow = store.loadPage('free', 'kelly', 4)
    await store.loadPage('free', 'kelly', 5)
    answerSlow(aPageDetail({ pdf_page: 4 }))
    await slow
    expect(store.detail?.pdf_page).toBe(5)
  })

  it('hands an answer to the request it answers, whatever its own fields say', async () => {
    // a page list that names another knowledge base than its address is still the answer to that address
    vi.mocked(getWorkPages).mockResolvedValue({ ...aWorkPages([aPageRow()]), knowledge_base: 'free' })
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ knowledge_base: 'free', pdf_page: 9 }))
    const store = usePageStore()
    await store.loadWorkPages('licensed', 'kelly')
    await store.loadPage('licensed', 'kelly', 4)
    expect(store.pagesOf('licensed', 'kelly')?.pages).toHaveLength(1)
    expect(store.pagesOf('free', 'kelly')).toBeNull()
    expect(store.pageOf('licensed', 'kelly', 4)?.pdf_page).toBe(9)
    expect(store.pageOf('licensed', 'kelly', 9)).toBeNull()
  })

  it('takes the same id in another knowledge base for another work', async () => {
    let answerFree: (pages: WorkPages) => void = () => {}
    vi.mocked(getWorkPages)
      .mockReturnValueOnce(new Promise(resolve => { answerFree = resolve }))
      .mockResolvedValueOnce({ ...aWorkPages([aPageRow({ pdf_page: 7 })]), knowledge_base: 'licensed' })
    const store = usePageStore()
    const free = store.loadWorkPages('free', 'kelly')
    await store.loadWorkPages('licensed', 'kelly')
    answerFree(aWorkPages([aPageRow({ pdf_page: 1 })]))
    await free
    expect(store.workPages?.knowledge_base).toBe('licensed')
    expect(vi.mocked(getWorkPages).mock.calls).toEqual([['free', 'kelly'], ['licensed', 'kelly']])
  })
})
