import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getWorks } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import SourcesView from '@/views/SourcesView.vue'
import type { Work } from '@/types/api/source_types'
import { aWork } from './work_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getWorks: vi.fn(),
}))

function mountView() {
  return mount(SourcesView, { global: { plugins: [createPinia(), router] } })
}

describe('SourcesView', () => {
  beforeEach(() => {
    vi.mocked(getWorks).mockReset()
  })

  it('shows that it is loading until the API answers', async () => {
    let answer: (works: Work[]) => void = () => {}
    vi.mocked(getWorks).mockReturnValue(new Promise(resolve => { answer = resolve }))
    const view = mountView()
    expect(view.find('[aria-busy="true"]').exists()).toBe(true)
    answer([aWork()])
    await flushPromises()
    expect(view.find('[aria-busy="true"]').exists()).toBe(false)
  })

  it('shows one row per work, with the id a ticket would name', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork(), aWork({ id: 'wikipedia_kelly_criterion', title: 'Kelly criterion' })])
    const view = mountView()
    await flushPromises()
    const rows = view.findAll('tbody tr')
    expect(rows.map(row => row.attributes('data-work'))).toEqual(['openstax_principles_of_finance_2e', 'wikipedia_kelly_criterion'])
    expect(rows[0].text()).toContain('openstax_principles_of_finance_2e')
  })

  it('heads the catalog\'s topic shelf "Topic", so it is not taken for the Shelf view\'s counts (23.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork()])
    const view = mountView()
    await flushPromises()
    const headings = view.findAll('thead th').map(cell => cell.text())
    expect(headings).toContain('Topic')
    expect(headings).not.toContain('Shelf')
    expect(view.findAll('tbody td')[headings.indexOf('Topic')].text()).toBe('trading_finance')
  })

  it('says each work\'s structure by its format\'s model, and an HTML work opens its outline (4.a, 6.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([
      aWork({ readings: { pages: 629, states: [{ value: 'ok', count: 629 }], routes: [], people: [], reviews: [], categories: [] } }),
      aWork({ id: 'wikipedia_trading_set', title: 'Wikipedia articles', format: 'html', year: null, sections: 130, chunks: 263 }),
      aWork({ id: 'kleppmann_accounting_for_computer_scientists', format: 'html', structure_why_not: 'No search index on this machine yet' }),
    ])
    const view = mountView()
    await flushPromises()
    expect(view.findAll('thead th').map(cell => cell.text())).toContain('Structure')
    const [pdf, html, unbuilt] = view.findAll('tbody tr')
    expect(pdf.find('[data-cell="structure"]').text()).toContain('629 pages · read and judged')
    expect(html.find('[data-cell="structure"]').text()).toBe('130 sections by heading · 263 chunks')
    expect(html.find('a.work-title').attributes('href')).toBe('#/free/html/wikipedia_trading_set')
    expect(unbuilt.find('[data-cell="structure"]').text()).toBe('sections by heading · search index not built')
  })

  it('leaves the year empty for a work without one, such as a set of living articles', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork({ id: 'wikipedia_trading_set', year: null })])
    const view = mountView()
    await flushPromises()
    expect(view.findAll('tbody td')[5].text()).toBe('')
  })

  it('opens the page list of a work read page by page, and shows its states', async () => {
    vi.mocked(getWorks).mockResolvedValue([
      aWork({ readings: { pages: 15, states: [{ value: 'ok', count: 12 }, { value: 'blocked', count: 3 }], routes: [], people: [], reviews: [], categories: [] } }),
      aWork({ id: 'wikipedia_trading_set', title: 'Kelly criterion', year: null }),
    ])
    const view = mountView()
    await flushPromises()
    const [read, html] = view.findAll('tbody tr')
    expect(read.find('a').attributes('href')).toBe('#/free/sources/openstax_principles_of_finance_2e')
    expect(read.text()).toContain('15 pages')
    expect(read.find('[data-state="blocked"]').text()).toContain('3')
    expect(html.find('a').exists()).toBe(false)
  })

  it('marks every work with its knowledge base, and a licensed one opens within its own', async () => {
    // invented: no licensed title stands in a tracked file
    const licensed = aWork({
      knowledge_base: 'licensed',
      id: 'a_licensed_book',
      title: 'a_licensed_book',
      authors: null,
      publisher: null,
      year: null,
      licence: null,
      format: null,
      shelf: null,
      readings: { pages: 2, states: [{ value: 'ok', count: 2 }], routes: [], people: [], reviews: [], categories: [] },
    })
    vi.mocked(getWorks).mockResolvedValue([aWork(), licensed])
    const view = mountView()
    await flushPromises()
    const [free, own] = view.findAll('tbody tr')
    expect(free.find('[data-kb="free"]').text()).toBe('free')
    expect(own.find('[data-kb="licensed"]').text()).toBe('licensed')
    expect(own.find('a').attributes('href')).toBe('#/licensed/sources/a_licensed_book')
  })

  it('shows a licensed work as the local catalog lists it, its edition beside its year and a word on the copy (N1.a)', async () => {
    // invented: no licensed title stands in a test
    const licensed = aWork({ knowledge_base: 'licensed', id: 'a_licensed_book', title: 'An Invented Book', authors: 'A. Author',
      publisher: 'Invented Press', year: 2001, edition: '2nd', licence: 'private copy (licensed)', format: 'pdf',
      shelf: 'trading_finance', notes: 'stand-in file' })
    const undated = aWork({ knowledge_base: 'licensed', id: 'another_book', title: 'Another Book', year: null, edition: '3rd', notes: null })
    vi.mocked(getWorks).mockResolvedValue([licensed, undated])
    const view = mountView()
    await flushPromises()
    const [own, other] = view.findAll('tbody tr')
    expect(own.find('.work-title').text()).toBe('An Invented Book')
    expect(own.find('[data-part="work-notes"]').text()).toBe('stand-in file')
    expect(own.text()).toContain('Invented Press')
    expect(own.text()).toContain('2001 · 2nd edition')
    expect(own.text()).toContain('private copy (licensed)')
    // no year: the edition alone, without a parting dot; no notes: nothing in their place
    expect(other.find('[data-part="edition"]').text()).toBe('3rd edition')
    expect(other.find('[data-part="work-notes"]').exists()).toBe(false)
  })

  it('says so when the catalog lists nothing, rather than drawing an empty table', async () => {
    vi.mocked(getWorks).mockResolvedValue([])
    const view = mountView()
    await flushPromises()
    expect(view.find('table').exists()).toBe(false)
    expect(view.text()).toContain('The catalog lists no works.')
  })

  it('names the missing API process when no answer came, with a glyph beside the words', async () => {
    vi.mocked(getWorks).mockRejectedValue(new ApiError(null, 'Network Error'))
    const view = mountView()
    await flushPromises()
    const alert = view.find('[role="alert"]')
    expect(alert.text()).toContain('python -m backend.diagnostics')
    expect(alert.find('[data-icon="status-error"]').exists()).toBe(true)
  })

  it('asks again on Try again', async () => {
    vi.mocked(getWorks).mockRejectedValueOnce(new ApiError(500, 'Internal Server Error')).mockResolvedValueOnce([aWork()])
    const view = mountView()
    await flushPromises()
    await view.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(1)
  })
})
