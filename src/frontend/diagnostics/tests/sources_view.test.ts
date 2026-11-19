import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getWorks } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import SourcesView from '@/views/SourcesView.vue'
import type { Work } from '@/types/api/source_types'
import { aWork } from './work_fixture'
import { searchFor, sortBy } from './facet_harness'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getWorks: vi.fn(),
}))

/** A part of an invented licensed series (invented throughout: no licensed title stands in a test). */
function INVENTED_PART(part: number, version: string | null = null): Work {
  const id = `an_invented_course_${part}${version ? '_earlier' : ''}`
  return aWork({ knowledge_base: 'licensed', id, title: `Lecture ${part}${version ? ' (earlier)' : ''}`, authors: 'A. Lecturer',
    format: 'pdf', shelf: 'trading_finance', year: 2010 + part, structure: 'read page by page',
    series: { id: 'an_invented_course', title: 'An Invented Course', part, of: 3, version } })
}

let mounted: VueWrapper | null = null

function mountView() {
  // attached, so the bar's menus and panels, portalled to the document, can be opened and read
  mounted = mount(SourcesView, { global: { plugins: [createPinia(), router] }, attachTo: document.body })
  return mounted
}

/** A work's row by its id, wherever the sort put it. */
function rowOf(view: VueWrapper, id: string) {
  return view.find(`tbody tr[data-work="${id}"]`)
}

describe('SourcesView', () => {
  beforeEach(() => {
    vi.mocked(getWorks).mockReset()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    mounted?.unmount()
    mounted = null
    vi.restoreAllMocks()
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

  it('shows one row per work by its title, with the id a ticket would name, and states the sort in force (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork(), aWork({ id: 'wikipedia_kelly_criterion', title: 'Kelly criterion' })])
    const view = mountView()
    await flushPromises()
    const rows = view.findAll('tbody tr')
    expect(rows.map(row => row.attributes('data-work'))).toEqual(['wikipedia_kelly_criterion', 'openstax_principles_of_finance_2e'])
    expect(rows[1].text()).toContain('openstax_principles_of_finance_2e')
    expect(view.find('.facet-sort-trigger').text()).toContain('Sort: title')
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
    expect(view.findAll('thead th').map(cell => cell.text())).toContain('Pages')
    const [pdf, html, unbuilt] = ['openstax_principles_of_finance_2e', 'wikipedia_trading_set',
      'kleppmann_accounting_for_computer_scientists'].map(id => rowOf(view, id))
    // a work read page by page: its pages, a figure (B3.a); any other: how it is cut, in the API's words, in the same column
    expect(pdf.find('[data-cell="structure"] [data-part="pages"]').text()).toBe('629')
    expect(html.find('[data-cell="structure"]').text()).toBe('130 sections by heading · 263 chunks')
    expect(html.find('a.work-title').attributes('href')).toBe('#/free/html/wikipedia_trading_set')
    expect(unbuilt.find('[data-cell="structure"]').text()).toBe('sections by heading · search index not built')
    // why, in the API's words, in the row's card where a browser tooltip stood (decision 179)
    expect(unbuilt.find('[data-cell="structure"] [title]').exists()).toBe(false)
    await unbuilt.find('.work-card').trigger('mouseenter')
    expect(unbuilt.find('[data-row="structure"] .card-value').text()).toBe('No search index on this machine yet')
  })

  it('leaves the year empty for a work without one, such as a set of living articles', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork({ id: 'wikipedia_trading_set', year: null })])
    const view = mountView()
    await flushPromises()
    const headings = view.findAll('thead th').map(cell => cell.text())
    expect(view.findAll('tbody td')[headings.indexOf('Year')].text()).toBe('')
  })

  it('opens the page list of a work read page by page, and shows its states', async () => {
    vi.mocked(getWorks).mockResolvedValue([
      aWork({ readings: { pages: 15, states: [{ value: 'ok', count: 12 }, { value: 'blocked', count: 3 }], routes: [], people: [], reviews: [], categories: [] } }),
      aWork({ id: 'wikipedia_trading_set', title: 'Kelly criterion', year: null }),
    ])
    const view = mountView()
    await flushPromises()
    const [read, html] = ['openstax_principles_of_finance_2e', 'wikipedia_trading_set'].map(id => rowOf(view, id))
    expect(read.find('a').attributes('href')).toBe('#/free/sources/openstax_principles_of_finance_2e')
    expect(read.find('[data-part="pages"]').text()).toBe('15')
    expect(read.find('td[data-state="blocked"]').text()).toBe('3')
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
    const [free, own] = ['openstax_principles_of_finance_2e', 'a_licensed_book'].map(id => rowOf(view, id))
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
    const [own, other] = ['a_licensed_book', 'another_book'].map(id => rowOf(view, id))
    expect(own.find('.work-title').text()).toBe('An Invented Book')
    // the title and the id a line each (B4.a); the notes, the publisher and the licence stand in the row's card only (B2)
    expect(own.find('[data-part="work-notes"]').exists()).toBe(false)
    expect(own.text()).not.toContain('Invented Press')
    await own.find('.work-card').trigger('mouseenter')
    const card = own.find('[data-part="hover-card"]')
    expect(card.find('.card-title').text()).toBe('An Invented Book')
    expect(card.find('[data-row="publisher"] .card-value').text()).toBe('Invented Press')
    expect(card.find('[data-row="licence"] .card-value').text()).toBe('private copy (licensed)')
    expect(card.find('[data-row="id"] .card-value').text()).toBe('a_licensed_book')
    expect(card.find('[data-row="series"]').exists()).toBe(false)
    expect(card.find('[data-row="notes"] .card-value').text()).toBe('stand-in file')
    expect(own.text()).toContain('2001 · 2nd edition')
    // no year: the edition alone, without a parting dot
    expect(other.find('[data-part="edition"]').text()).toBe('3rd edition')
  })

  it('lists a catalog entry not read yet with its columns and the API\'s words in place of page counts, no link (O1.a)', async () => {
    // invented: an EPUB the licensed catalog lists and the export holds no pages of
    const unread = aWork({ knowledge_base: 'licensed', id: 'an_unread_book', title: 'An Unread Book', format: 'epub', readings: null,
      not_read: 'not read page by page' })
    vi.mocked(getWorks).mockResolvedValue([unread])
    const view = mountView()
    await flushPromises()
    const row = view.find('tbody tr')
    expect(row.find('[data-part="not-read"]').text()).toBe('not read page by page')
    expect(row.find('.work-title').text()).toBe('An Unread Book')
    expect(row.find('a').exists()).toBe(false)
    expect(row.text()).toContain('epub')
  })

  it('opens a licensed EPUB the librarian serves on its own view and counts its sections, or says they are being counted (123.a)', async () => {
    // invented: the catalog's id and the librarian's key differ, as for a legacy work
    const counted = aWork({ knowledge_base: 'licensed', id: 'an_invented_book_file', title: 'An Invented Book', format: 'epub',
      readings: null, epub_key: 'invented', sections: 268 })
    const counting = aWork({ knowledge_base: 'licensed', id: 'another_file', title: 'Another Book', format: 'epub', readings: null,
      epub_key: 'another', sections: null, structure_why_not: 'sections by heading · being counted, here in a moment' })
    vi.mocked(getWorks).mockResolvedValue([counted, counting])
    const view = mountView()
    await flushPromises()
    const [first, second] = ['an_invented_book_file', 'another_file'].map(id => rowOf(view, id))
    expect(first.find('a.work-title').attributes('href')).toBe('#/licensed/epub/invented')
    expect(first.find('[data-part="epub-sections"]').text()).toBe('268 sections by heading')
    expect(second.find('[data-part="epub-sections"]').text()).toBe('sections by heading · being counted, here in a moment')
    expect(second.find('a.work-title').attributes('href')).toBe('#/licensed/epub/another')
  })

  it('says beside a state to look at how many of its pages the core serves all the same (18 Nov)', async () => {
    // invented: nine issues whose findings lie on blocks never quoted, all served; three blocked, none
    const work = aWork({ readings: { pages: 20, states: [{ value: 'ok', count: 8 }, { value: 'issue', count: 9, served: 9 },
      { value: 'blocked', count: 3, served: null }], routes: [], people: [], reviews: [], categories: [] } })
    vi.mocked(getWorks).mockResolvedValue([work])
    const view = mountView()
    await flushPromises()
    // beneath the issue's figure, on a line of its own, without the dot that joins it to a count elsewhere (B3.a)
    const issue = view.find('td[data-state="issue"]')
    expect(issue.find('.count').text()).toBe('9')
    expect(issue.find('[data-part="served"]').text()).toBe('9 served')
    expect(issue.find('[data-part="served"] [data-icon="quoted"]').exists()).toBe(true)
    expect(view.find('td[data-state="blocked"] [data-part="served"]').exists()).toBe(false)
    expect(view.find('td[data-state="ok"] [data-part="served"]').exists()).toBe(false)
  })

  it('stands five states as figure columns under their glyph and word, the rarer states in the card (B3.a)', async () => {
    const work = aWork({ readings: { pages: 40, routes: [], people: [], reviews: [], categories: [], states: [
      { value: 'ok', count: 20 }, { value: 'ok_unjudged', count: 9 }, { value: 'issue', count: 2 }, { value: 'blocked', count: 1 },
      { value: 'stopped', count: 4 }, { value: 'decided_by_a_person', count: 3 }, { value: 'decided_by_an_automated_review', count: 1 },
    ] } })
    vi.mocked(getWorks).mockResolvedValue([work, aWork({ id: 'wikipedia_trading_set', title: 'Kelly criterion', format: 'html',
      sections: 130, chunks: 263 })])
    const view = mountView()
    await flushPromises()
    const heads = view.findAll('thead th.state-head')
    expect(heads.map(head => head.find('.state-mark').attributes('data-state')))
      .toEqual(['ok', 'ok_unjudged', 'issue', 'blocked', 'decided_by_a_person'])
    const row = rowOf(view, 'openstax_principles_of_finance_2e')
    expect(row.findAll('td[data-state]').map(cell => cell.find('.count').text())).toEqual(['20', '9', '2', '1', '3'])
    // a work not read page by page leaves the figures empty and says its structure in the pages column
    const html = rowOf(view, 'wikipedia_trading_set')
    expect(html.findAll('td[data-state]').every(cell => cell.text() === '')).toBe(true)
    expect(html.find('[data-cell="structure"]').text()).toBe('130 sections by heading · 263 chunks')
    // the rarer states, which have no column, in the card with their counts
    await row.find('.work-card').trigger('mouseenter')
    expect(row.find('[data-row="stopped"] .card-value').text()).toBe('4')
    expect(row.find('[data-row="decided by an automated review"] .card-value').text()).toBe('1')
    expect(row.find('[data-row="ok"]').exists()).toBe(false)
  })

  it('sorts by blocked or by issue, most first, a work without pages read last (B3.a)', async () => {
    const states = (blocked: number, issue: number) => ({ pages: 10, routes: [], people: [], reviews: [], categories: [],
      states: [{ value: 'issue', count: issue }, { value: 'blocked', count: blocked }].filter(count => count.count > 0) })
    vi.mocked(getWorks).mockResolvedValue([
      aWork({ id: 'a', title: 'A', readings: states(1, 5) }), aWork({ id: 'b', title: 'B', readings: states(4, 0) }),
      aWork({ id: 'c', title: 'C', readings: null, format: 'html' }), aWork({ id: 'd', title: 'D', readings: states(0, 2) }),
    ])
    const view = mountView()
    await flushPromises()
    await sortBy(view, 'blocked, most first')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['b', 'a', 'd', 'c'])
    await sortBy(view, 'issue, most first')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['a', 'd', 'b', 'c'])
  })

  it('narrows by a facet in its panel, a knowledge base drawn with its glyph and word, and says how many of all it shows (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork(), INVENTED_PART(1), aWork({ id: 'wikipedia_trading_set', title: 'Kelly criterion' })])
    const view = mountView()
    await flushPromises()
    expect(view.findAll('.facet-trigger').map(chip => chip.attributes('data-facet')))
      .toEqual(['kb', 'format', 'shelf', 'structure', 'series'])
    await view.find('.facet-trigger[data-facet="kb"]').trigger('click')
    await flushPromises()
    const licensed = document.querySelector<HTMLElement>('.facet-option[data-value="licensed"]')!
    expect(licensed.querySelector('[data-kb="licensed"] [data-icon="kb-licensed"]')).not.toBeNull()
    expect(licensed.querySelector('.facet-count')!.textContent).toBe('1')
    licensed.click()
    await flushPromises()
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['an_invented_course_1'])
    expect(view.find('.facet-count-label').text()).toBe('1 of 3')
  })

  it('searches title, authors and id, and says so when nothing is left rather than drawing an empty table (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([
      aWork(),
      aWork({ id: 'wikipedia_kelly_criterion', title: 'Kelly criterion', authors: 'Wikipedia contributors' }),
    ])
    const view = mountView()
    await flushPromises()
    await searchFor(view, 'dahlquist')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['openstax_principles_of_finance_2e'])
    await searchFor(view, 'kelly_crit')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['wikipedia_kelly_criterion'])
    await searchFor(view, 'no such work')
    expect(view.find('table').exists()).toBe(false)
    expect(view.find('[data-part="none-match"]').text()).toBe('No work matches the search and the filters.')
  })

  it('sorts by year, newest first, a work without one last, and by author (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([
      aWork({ id: 'old', title: 'A', year: 1990, authors: 'Zed' }),
      aWork({ id: 'undated', title: 'B', year: null, authors: null }),
      aWork({ id: 'new', title: 'C', year: 2024, authors: 'Abel' }),
    ])
    const view = mountView()
    await flushPromises()
    await sortBy(view, 'year, newest first')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['new', 'old', 'undated'])
    await sortBy(view, 'author')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['new', 'old', 'undated'])
  })

  it('stands a series\' parts under one heading, closed, with its title and how many parts it holds (Y1.a)', async () => {
    // invented: a course in three parts, the third also as an earlier version, and a work of no series
    vi.mocked(getWorks).mockResolvedValue([
      INVENTED_PART(3), INVENTED_PART(1), INVENTED_PART(3, 'earlier version'), INVENTED_PART(2), aWork({ title: 'Z last' }),
    ])
    const view = mountView()
    await flushPromises()
    const head = view.find('tr.series-head')
    expect(head.find('.series-glyph').text()).toBe('▸')
    expect(head.find('.series-title').text()).toBe('An Invented Course')
    expect(head.find('.series-count').text()).toBe('4 works')
    expect(head.find('.series-toggle').attributes('aria-expanded')).toBe('false')
    expect(view.findAll('tbody tr[data-work]').map(row => row.attributes('data-work'))).toEqual(['openstax_principles_of_finance_2e'])

    await head.find('.series-toggle').trigger('click')
    // its parts in their order, a current part before its earlier version, each one step in under the heading
    const parts = view.findAll('tbody tr.in-series')
    expect(parts.map(row => row.attributes('data-work')))
      .toEqual(['an_invented_course_1', 'an_invented_course_2', 'an_invented_course_3', 'an_invented_course_3_earlier'])
    expect(view.find('tr.series-head .series-toggle').attributes('aria-expanded')).toBe('true')
    // an open group stays open on a reload in this tab
    mounted!.unmount()
    const again = mountView()
    await flushPromises()
    expect(again.findAll('tbody tr.in-series')).toHaveLength(4)
  })

  it('builds the groups from the rows the bar leaves: a series narrowed to one part loses its heading (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([INVENTED_PART(1), INVENTED_PART(2)])
    const view = mountView()
    await flushPromises()
    await searchFor(view, 'an_invented_course_2')
    expect(view.find('tr.series-head').exists()).toBe(false)
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['an_invented_course_2'])
    expect(view.find('tbody tr').classes()).not.toContain('in-series')
  })

  it('brings back the bar on a reload (F5): its picks, its search and its sort; a bar nobody touched stores nothing (Y1.a)', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork(), INVENTED_PART(1), aWork({ id: 'wikipedia_trading_set', title: 'Kelly', format: 'html' })])
    const untouched = mountView()
    await flushPromises()
    expect(localStorage.getItem('settings.v1')).toBeNull()
    untouched.unmount()

    localStorage.setItem('settings.v1', JSON.stringify({ version: 1, bars: {
      sources: { selection: { kb: ['free'] }, search: 'principles', sort: 'year' },
    } }))
    const view = mountView()
    await flushPromises()
    expect(view.findAll('tbody tr').map(row => row.attributes('data-work'))).toEqual(['openstax_principles_of_finance_2e'])
    expect((view.find('.facet-search').element as HTMLInputElement).value).toBe('principles')
    expect(view.find('.facet-sort-trigger').text()).toContain('year, newest first')
    expect(view.find('.facet-trigger[data-facet="kb"] .facet-badge').text()).toBe('1')
  })

  it('returns to where the reader stood once the works are drawn, not before (F5, Y1.a)', async () => {
    await router.push('/sources')
    sessionStorage.setItem('scroll.v1', JSON.stringify({ '/sources': 640 }))
    const scrolled = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    let answer: (works: Work[]) => void = () => {}
    vi.mocked(getWorks).mockReturnValue(new Promise(resolve => { answer = resolve }))
    mountView()
    await flushPromises()
    expect(scrolled).not.toHaveBeenCalled()
    answer([aWork()])
    await flushPromises()
    expect(scrolled).toHaveBeenCalledWith(0, 640)
  })

  it('opens at its top when the tab\'s storage is blocked, and still draws its works', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const scrolled = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    vi.mocked(getWorks).mockResolvedValue([aWork()])
    const view = mountView()
    await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(1)
    expect(scrolled).not.toHaveBeenCalled()
  })

  it('ranks its columns, each cell stating its column\'s rank, and Publisher and Licence stand in no column (B1.a, B2)', async () => {
    vi.mocked(getWorks).mockResolvedValue([aWork(), INVENTED_PART(1), INVENTED_PART(2)])
    const view = mountView()
    await flushPromises()
    expect(view.findAll('thead th').map(cell => cell.text())).toEqual(['Work', 'Knowledge base', 'Pages', 'ok', 'ok unjudged', 'issue',
      'blocked', 'decided by a person', 'Authors', 'Year', 'Format', 'Topic'])
    // the ladder taken again with the figures (B3.a): the work and its pages, then issue and blocked, then the knowledge base,
    // ok and the authors, then ok unjudged and decided by a person, the year, format and topic last
    const ranks = view.findAll('col').map(col => col.attributes('data-rank') ?? '1')
    expect(ranks).toEqual(['1', '3', '1', '3', '4', '2', '2', '4', '3', '5', '5', '5'])
    expect(view.findAll('thead th').map(cell => cell.attributes('data-rank') ?? '1')).toEqual(ranks)
    await view.find('tr.series-head .series-toggle').trigger('click')
    // every row, a series' heading too: a cell per column, never one spanning them, which a narrow table cannot hold
    for (const row of view.findAll('tbody tr')) {
      expect(row.findAll('td').map(cell => cell.attributes('data-rank') ?? '1'), row.attributes('data-work')).toEqual(ranks)
    }
    expect(view.find('tr.series-head td[colspan]').exists()).toBe(false)
  })

  it('names a part\'s series in its card, with its part and an earlier version\'s words', async () => {
    vi.mocked(getWorks).mockResolvedValue([INVENTED_PART(1), INVENTED_PART(1, 'earlier version')])
    const view = mountView()
    await flushPromises()
    await view.find('tr.series-head .series-toggle').trigger('click')
    const earlier = view.find('tr[data-work="an_invented_course_1_earlier"]')
    await earlier.find('.work-card').trigger('mouseenter')
    expect(earlier.find('[data-row="series"] .card-value').text()).toBe('An Invented Course, part 1 of 3 (earlier version)')
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
