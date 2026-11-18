import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { searchPages } from '@/api/api_client'
import { router } from '@/router'
import SearchView from '@/views/SearchView.vue'
import type { SearchAnswer, SearchHit } from '@/types/api/search_types'
import { KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  searchPages: vi.fn(),
}))

// The router is one for the whole file: a view left mounted by an earlier test would answer the next test's address too
enableAutoUnmount(afterEach)

/** A hit as the API serves it, on a free page, so it may stand in a tracked file; its words are invented. */
function aHit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    score: 12.34,
    knowledge_base: 'free',
    work: 'carta-conversano-kelly-2020',
    title: 'Kelly criterion paper',
    page: { label: '4', pdf: '4', printed: '4' },
    section: '2 The model',
    where: 'corpus/readings/carta-conversano-kelly-2020/p0004.md',
    snippet: 'The Kelly fraction maximises the growth rate.',
    terms_found: ['kelly', 'fraction'],
    terms_missing: [],
    licence: 'CC BY',
    route: 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)',
    reading_key: '2b2d48e77b246c95',
    view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 4 },
    ...overrides,
  }
}

function anAnswer(overrides: Partial<SearchAnswer> = {}): SearchAnswer {
  return { state: 'found', query: 'kelly fraction', corpus: 'all', knowledge_bases: ['free'], hits: [aHit()], error: null, ...overrides }
}

async function mountAt(path: string) {
  await router.push(path)
  const view = mount(SearchView, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return view
}

describe('SearchView', () => {
  beforeEach(() => {
    vi.mocked(searchPages).mockReset()
  })

  it('says the index is still being built while the first search waits, never an empty list (line 1, 10 Nov)', async () => {
    vi.mocked(searchPages).mockReturnValue(new Promise(() => {}))  // an answer that has not come yet
    const view = await mountAt('/search?q=kelly%20fraction')
    expect(view.find('[aria-busy="true"]').exists()).toBe(true)
    expect(view.find('.waiting .search-note').text()).toBe('The first search after a start waits until its index is built, up to about a minute.')
    expect(view.find('[data-hit]').exists()).toBe(false)
    expect(view.find('.nothing').exists()).toBe(false)
  })

  it('says it is the keyword search, no model, and sends a question in words to the chat (the operator, 16 Nov)', async () => {
    vi.mocked(searchPages).mockReturnValue(new Promise(() => {}))
    const view = await mountAt('/search?q=rsi')
    const kind = view.find('[data-part="search-kind"]')
    expect(kind.text()).toContain('BM25 over the words of every page')
    expect(kind.text()).toContain('no model at all, neither embeddings nor a language model')
    expect(kind.text()).toContain('the semantic (hybrid) search')
    expect(kind.find('[data-part="to-chat"]').attributes('href')).toBe('#/chat')
    expect(view.find('.view-title').text()).toBe('Search · BM25, no model')
  })

  it('asks what the address asks, and lists each hit with its pages, source, licence and route', async () => {
    vi.mocked(searchPages).mockResolvedValue(anAnswer())
    const view = await mountAt('/search?q=kelly%20fraction')
    expect(vi.mocked(searchPages)).toHaveBeenCalledWith('kelly fraction', 'all')
    const hit = view.find('[data-hit="0"]')
    expect(hit.find('a.hit-title').attributes('href')).toBe(`#/free/sources/${KELLY}/page/4`)
    expect(hit.find('.page-label').text()).toBe('p. 4 (PDF p. 4)')
    expect(hit.find('[data-kb="free"]').exists()).toBe(true)
    expect(hit.find('.licence').text()).toBe('CC BY')
    expect(hit.find('.route').text()).toContain('vision reading')
    expect(hit.find('.snippet').text()).toBe('The Kelly fraction maximises the growth rate.')
    expect(hit.find('.hit-foot').exists()).toBe(false)
  })

  it('names the file of a hit the diagnostics does not show yet, and the words a hit lacks', async () => {
    vi.mocked(searchPages).mockResolvedValue(anAnswer({
      hits: [aHit({
        view: null,
        page: { label: 's2', pdf: null, printed: null },
        where: 'https://en.wikipedia.org/wiki/Kelly_criterion#Definition',
        route: 'html, parsed by section',
        terms_missing: ['fraction'],
      })],
    }))
    const view = await mountAt('/search?q=kelly%20fraction')
    const hit = view.find('[data-hit="0"]')
    expect(hit.find('a.hit-title').exists()).toBe(false)
    expect(hit.find('.page-label').text()).toBe('s2')
    expect(hit.find('.where').text()).toContain('#Definition')
    expect(hit.find('.missing').text()).toBe('missing: fraction')
  })

  it('gives the PDF page alone where no number is printed on it', async () => {
    vi.mocked(searchPages).mockResolvedValue(anAnswer({ hits: [aHit({ page: { label: '2', pdf: '2', printed: null } })] }))
    const view = await mountAt('/search?q=kelly')
    expect(view.find('.page-label').text()).toBe('PDF p. 2')
  })

  it('says nothing found as an answer', async () => {
    vi.mocked(searchPages).mockResolvedValue(anAnswer({ state: 'nothing found', query: 'zebra', hits: [] }))
    const view = await mountAt('/search?q=zebra')
    expect(view.find('.nothing').text()).toContain('Nothing found for “zebra”')
    expect(view.find('.hits').exists()).toBe(false)
  })

  it('offers a corpus only where the search holds two knowledge bases', async () => {
    vi.mocked(searchPages)
      .mockResolvedValueOnce(anAnswer())
      .mockResolvedValueOnce(anAnswer({ knowledge_bases: ['free', 'licensed'] }))
    const single = await mountAt('/search?q=kelly%20fraction')
    expect(single.find('.corpus').exists()).toBe(false)

    const both = await mountAt('/search?q=kelly%20fraction')
    expect(both.findAll('.corpus button').map(button => button.text())).toEqual(['all', 'free', 'licensed'])
  })

  it('puts a new question into the address, and asks it', async () => {
    vi.mocked(searchPages).mockResolvedValue(anAnswer({ query: 'growth rate' }))
    const view = await mountAt('/search')
    expect(vi.mocked(searchPages)).not.toHaveBeenCalled()
    await view.find('input.question').setValue('growth rate')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('growth rate')
    expect(vi.mocked(searchPages)).toHaveBeenCalledWith('growth rate', 'all')
  })
})
