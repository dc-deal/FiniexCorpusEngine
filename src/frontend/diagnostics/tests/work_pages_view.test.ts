import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getWorkPages } from '@/api/api_client'
import { router } from '@/router'
import WorkPagesView from '@/views/WorkPagesView.vue'
import type { KnowledgeBase } from '@/types/api/source_types'
import { aCheck, anOutlinedWork, aPageRow, aWorkPages, BLOCKED_ROUTE, CONTENT_FILTER, DECLINED_ROUTE, KELLY } from './page_fixture'
import { facetOption, pickFacet } from './facet_harness'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getWorkPages: vi.fn(),
}))

// attached, so the bar's panels, portalled to the document, can be opened; unmounted after each test, so none stays behind
enableAutoUnmount(afterEach)

function mountView(kb: KnowledgeBase = 'free', work = KELLY) {
  return mount(WorkPagesView, { props: { kb, work }, global: { plugins: [createPinia(), router] }, attachTo: document.body })
}

function cells(view: ReturnType<typeof mountView>): string[][] {
  return view.findAll('tbody tr').map(row => row.findAll('td').map(cell => cell.text()))
}

function isOpen(view: ReturnType<typeof mountView>, unit: string): boolean {
  return (view.find(`[data-unit="${unit}"]`).element as HTMLDetailsElement).open
}

describe('WorkPagesView', () => {
  beforeEach(async () => {
    vi.mocked(getWorkPages).mockReset()
    localStorage.clear()
    // the router is shared: no test inherits the filter another one put in the address
    await router.push('/')
  })

  it('opens with the filter its address chose, so a count on the shelf lands on exactly its pages', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow({ pdf_page: 1 }),
      aPageRow({ pdf_page: 2, route: DECLINED_ROUTE, check: aCheck({ state: 'blocked' }) })]))
    await router.push({ name: 'work', params: { kb: 'free', work: KELLY }, query: { route: DECLINED_ROUTE } })
    const view = mountView()
    await flushPromises()
    expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['2'])
    // another count of the same work changes only the address, and the filter follows it
    await router.push({ name: 'work', params: { kb: 'free', work: KELLY }, query: { state: 'ok' } })
    await flushPromises()
    expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['1'])
  })

  it('gives each route a row with its level, source, reader, why and pages, and a row chosen narrows the list', async () => {
    const READ = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)'
    vi.mocked(getWorkPages).mockResolvedValue({
      ...aWorkPages([aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 2, route: BLOCKED_ROUTE, check: aCheck({ state: 'blocked' }) }),
        aPageRow({ pdf_page: 3 })]),
      routes: [
        { route: READ, level: 'checked', source: 'vision reading', reader: 'claude-sonnet-5-5, page/1, validator page/1.1', why: null, pages: 2 },
        { route: BLOCKED_ROUTE, level: 'fallback', source: 'text layer', reader: null, why: 'the provider blocked the reading', pages: 1 },
      ],
      route_levels: [{ level: 'checked', says: 'the checked reading of the page image', pages: 2 },
        { level: 'noted', says: 'the checked reading, with a note', pages: 0 },
        { level: 'fallback', says: 'the PDF\'s own text layer', pages: 1 }],
    })
    const view = mountView()
    await flushPromises()
    // folded by default to one line, each level that serves a page with its count, the fallback in its warning role
    expect(view.find('#routes-table').exists()).toBe(false)
    const counts = view.findAll('.routes-line .level-count')
    expect(counts.map(count => count.text())).toEqual(['2 checked', '1 fallback'])
    expect(counts[1].classes()).toContain('warn')
    expect(counts[1].find('[data-icon="route-fallback"]').exists()).toBe(true)
    // the levels' meaning is a hint on demand
    expect(view.find('[data-part="routes-legend"]').exists()).toBe(false)
    await view.find('[data-part="routes-hint-button"]').trigger('click')
    expect(view.findAll('.route-legend dt').map(term => term.text())).toEqual(['checked', 'noted', 'fallback'])
    // opened, the table; the choice is kept with the other settings
    await view.find('[data-part="routes-toggle"]').trigger('click')
    expect(JSON.parse(localStorage.getItem('settings.v1') ?? '{}').routesOpen).toBe(true)
    const rows = view.findAll('.route-table tbody tr')
    expect(rows.map(row => row.findAll('td').map(cell => cell.text()))).toEqual([
      ['checked', 'vision reading', 'claude-sonnet-5-5, page/1, validator page/1.1', '', '2'],
      ['fallback', 'text layer', '', 'the provider blocked the reading', '1'],
    ])
    // the fallback stands out by its glyph as well as its word, and every level says what it means in its hover
    expect(rows[1].find('[data-icon="route-fallback"]').exists()).toBe(true)
    expect(rows[0].find('.level').attributes('title')).toBe('the checked reading of the page image')
    // the states stay a facet; the routes have no chips of their own any more
    expect(view.find('[data-facet="route"]').exists()).toBe(false)
    const pages = () => view.findAll('tr[data-page]').map(row => row.attributes('data-page'))
    await rows[1].trigger('click')
    await flushPromises()
    expect(pages()).toEqual(['2'])
    expect(router.currentRoute.value.query.route).toEqual([BLOCKED_ROUTE])
    const chosen = view.findAll('.route-table tbody tr')[1]!
    expect(chosen.classes()).toContain('chosen')
    expect(chosen.find('button').attributes('aria-pressed')).toBe('true')
    await chosen.find('button').trigger('click')
    await flushPromises()
    expect(pages()).toEqual(['1', '2', '3'])
  })

  it('says a route chosen while the routes are folded, and lets it go there', async () => {
    vi.mocked(getWorkPages).mockResolvedValue({
      ...aWorkPages([aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 2, route: DECLINED_ROUTE, check: aCheck({ state: 'blocked' }) })]),
      routes: [{ route: DECLINED_ROUTE, level: 'fallback', source: 'text layer', reader: null, why: 'the reader declined the page', pages: 1 }],
      route_levels: [{ level: 'fallback', says: 'the PDF\'s own text layer', pages: 1 }],
    })
    await router.push({ name: 'work', params: { kb: 'free', work: KELLY }, query: { route: DECLINED_ROUTE } })
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="route-filter"]').text()).toContain('one route chosen')
    await view.find('[data-part="route-filter-clear"]').trigger('click')
    await flushPromises()
    expect(view.findAll('tr[data-page]').map(row => row.attributes('data-page'))).toEqual(['1', '2'])
  })

  it('counts the work\'s pages once and its states in one line of the API\'s totals, the bar narrowing below (SC1.a)', async () => {
    const pages = [aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 4, check: aCheck({ state: 'issue' }) })]
    vi.mocked(getWorkPages).mockResolvedValue({ ...aWorkPages(pages), summary: { pages: 2, routes: [], people: [], reviews: [],
      categories: [], states: [{ value: 'ok', count: 1 }, { value: 'issue', count: 1, served: 1 }] } })
    const view = mountView()
    await flushPromises()
    const head = view.find('.summary')
    expect(head.find('.page-total').text()).toBe('2 pages')
    // the head's line of totals, the API's over every page of the work, the served tally kept beside its state
    const totals = () => head.find('[data-part="totals"]')
    expect(totals().findAll('.state-count').map(count => count.attributes('data-state'))).toEqual(['ok', 'issue'])
    expect(totals().find('.state-count[data-state="issue"] [data-part="served"]').text()).toContain('1 served')
    // whatever the bar narrows, the totals stand
    await pickFacet(view, 'state', 'issue')
    expect(view.find('.facet-count-label').text()).toBe('1 of 2')
    expect(totals().find('.state-count[data-state="ok"] .count').text()).toBe('1')
  })

  it('lists every read page, each opening its page view within the knowledge base', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 4 })]))
    const view = mountView()
    await flushPromises()
    expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['1', '4'])
    expect(view.find('[data-page="4"] a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/4`)
  })

  it('opens a licensed work\'s pages within the licensed knowledge base, and jumps there', async () => {
    // invented: no licensed title or text stands in a tracked file
    vi.mocked(getWorkPages).mockResolvedValue({
      ...aWorkPages([aPageRow({ pdf_page: 3 })]), knowledge_base: 'licensed', source_id: 'a_licensed_book', title: 'a_licensed_book',
    })
    const view = mountView('licensed', 'a_licensed_book')
    await flushPromises()
    expect(view.find('[data-page="3"] a').attributes('href')).toBe('#/licensed/sources/a_licensed_book/page/3')
    expect(view.find('.work-id [data-kb="licensed"]').exists()).toBe(true)
    expect(vi.mocked(getWorkPages)).toHaveBeenCalledWith('licensed', 'a_licensed_book')
  })

  it('names the work\'s knowledge base once, above its pages', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow()]))
    const view = mountView()
    await flushPromises()
    expect(view.find('.work-id [data-kb="free"]').exists()).toBe(true)
    expect(view.find('tbody [data-kb]').exists()).toBe(false)
  })

  it('prints nothing more for a page that is fine, and the change of class where there is one', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([
      aPageRow({ pdf_page: 1 }),
      aPageRow({ pdf_page: 2, class_when_collected: 'malformed', class_now: 'ok', attempt: 1 }),
    ]))
    const view = mountView()
    await flushPromises()
    const [fine, moved] = cells(view)
    // printed, reasons, why, class and retry empty
    expect([fine[1], ...fine.slice(3, 7)]).toEqual(['', '', '', '', ''])
    expect(moved[5]).toBe('malformed → ok')
    expect(moved[6]).toBe('1')
  })

  it('gives the judge no column of its own: the state and the reasons already say it', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow()]))
    const view = mountView()
    await flushPromises()
    expect(view.findAll('thead th').map(head => head.text())).not.toContain('Judge')
  })

  it('shows the number printed on a page and, for a blocked one, the provider\'s own sentence', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([
      aPageRow({ pdf_page: 1, printed_label: 'ii' }),
      aPageRow({
        pdf_page: 2,
        check: aCheck({ state: 'blocked', verdict: null, judged: false, reasons: [{ value: 'errored', count: 1 }] }),
        class_now: 'errored',
        error_message: CONTENT_FILTER,
      }),
    ]))
    const view = mountView()
    await flushPromises()
    const [printed, blocked] = cells(view)
    expect(printed[1]).toBe('ii')
    expect(blocked[3]).toBe('errored')
    expect(blocked[4]).toBe(CONTENT_FILTER)
  })

  it('gives a declined page\'s route where the provider gave no sentence, and nothing for a page read as it should be', async () => {
    // invented over a free work: a reading the judge found bad that the search serves all the same (25.a)
    const servedDespite = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2): the judge\'s findings lie on blocks never quoted'
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([
      aPageRow({ pdf_page: 1 }),
      aPageRow({
        pdf_page: 747,
        route: DECLINED_ROUTE,
        check: aCheck({ state: 'blocked', verdict: null, judged: false, reasons: [{ value: 'refused', count: 1 }] }),
        class_now: 'refused',
        from_fallback: true,
      }),
      aPageRow({ pdf_page: 750, route: servedDespite, check: aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }] }) }),
    ]))
    const view = mountView()
    await flushPromises()
    expect(view.findAll('thead th').map(cell => cell.text())).toContain('Why')
    const [read, declined, served] = cells(view)
    expect(read[4]).toBe('')
    expect(declined[4]).toBe(DECLINED_ROUTE)
    expect(served[4]).toBe(servedDespite)
  })

  it('narrows the list to the chosen state', async () => {
    const pages = [aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 9, check: aCheck({ state: 'issue' }) })]
    vi.mocked(getWorkPages).mockResolvedValue({
      ...aWorkPages(pages),
      summary: { pages: 2, states: [{ value: 'ok', count: 1 }, { value: 'issue', count: 1 }], routes: [], people: [], reviews: [], categories: [] },
    })
    const view = mountView()
    await flushPromises()
    // in the core's order, ok before issue, each with how many of the work's pages carry it
    const states = await facetOption(view, 'state', 'ok')
    expect([...states.parentElement!.querySelectorAll('.facet-option')].map(option => option.getAttribute('data-value'))).toEqual(['ok', 'issue'])
    await pickFacet(view, 'state', 'issue')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['9'])
    // the choice stands in the address, so a reload (F5) or the browser's back finds the list as it was left
    expect(router.currentRoute.value.query.state).toEqual(['issue'])
  })

  it('offers a jump straight to a PDF page by its number', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow()]))
    const view = mountView()
    await flushPromises()
    expect(view.find('.summary .page-jump input').exists()).toBe(true)
  })

  it('says its record in labelled lines as a page does, the jump named by its line (219.a)', async () => {
    vi.mocked(getWorkPages).mockResolvedValue(aWorkPages([aPageRow({ pdf_page: 1 }), aPageRow({ pdf_page: 4 })]))
    const view = mountView()
    await flushPromises()
    const labels = view.findAll('[data-part="work-facts"] .line-label').map(label => label.text())
    expect(labels).toEqual(['Work:', 'Pages:', 'States:', 'PDF page:'])
    // the jump's field named for a reader that cannot see the line's label
    expect(view.find('[data-label="PDF page"] .page-jump-label').exists()).toBe(false)
    expect(view.find('[data-label="PDF page"] input').attributes('aria-label')).toBe('PDF page')
    // the head's grid holds its label column to the page head's ten characters
    const widths = view.findAll('[data-part="work-facts"] .labelled-lines').map(grid => grid.attributes('style'))
    expect(widths.length).toBe(1)
    expect(widths.every(style => style?.includes('--label-width: 10ch'))).toBe(true)
  })

  it('says so when a work has no page readings', async () => {
    vi.mocked(getWorkPages).mockResolvedValue({ ...aWorkPages([]), summary: null })
    const view = mountView()
    await flushPromises()
    expect(view.text()).toContain('This work has no page readings.')
  })

  describe('by the work\'s own order', () => {
    it('stands the pages under their chapters, folded, each chapter counting every page beneath it', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      expect(view.find('.outline').exists()).toBe(true)
      expect(['u001', 'u002', 'u004', 'u005'].map(unit => isOpen(view, unit))).toEqual([false, false, false, false])
      // a table (159.a): a head naming each column, one per state the work has, and each unit's figures in them
      expect(view.findAll('[data-part="chapter-head"] > span').map(cell => cell.text()))
        .toEqual(['Chapter', 'PDF pages', 'Pages', 'ok', 'issue', 'Note'])
      const growth = view.find('[data-unit="u002"] > summary .unit-head')
      expect(growth.findAll(':scope > span').map(cell => cell.text())).toEqual(['2 The growth rate', 'p. 3–6', '3', '2', '1', ''])
      expect(growth.find('[data-state="issue"]').text()).toBe('1')
      // a sub-unit sits inside its chapter, its title indented, its figures in the same columns
      expect(view.find('[data-unit="u002"] [data-unit="u003"] [data-page="5"]').exists()).toBe(true)
      expect(view.find('[data-unit="u003"] .unit-title').attributes('style')).toContain('var(--indent-step)')
      expect(view.find('[data-unit="u002"] > .fold-body > .unit-body table [data-page="3"]').exists()).toBe(true)
    })

    it('stands a unit\'s own pages in a block one step deeper than its title, at every depth, its caption the API\'s count (161.a)', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      const chapter = view.find('[data-unit="u002"] > .fold-body > .unit-body > [data-part="own-pages"]')
      expect(chapter.find('.own-caption').text()).toBe('1 page of 2 The growth rate itself, outside its sections')
      expect(chapter.attributes('style')).toContain('margin-left: 1.25rem')
      const section = view.find('[data-unit="u003"] > .fold-body > .unit-body > [data-part="own-pages"]')
      expect(section.find('.own-caption').text()).toBe('2 pages of 2.1 One asset itself')
      expect(section.attributes('style')).toContain('margin-left: 2.5rem')
      // the block's first column gives up the indent, so every other column keeps its place
      expect(section.find('col').attributes('style')).toContain('width: 7.5rem')
      expect(view.find('[data-unit="outside"] .own-caption').text()).toBe('1 page outside every chapter')
    })

    it('makes a count to look at a way to its pages: it opens the units holding them and marks them, a fine count a figure (225.a)', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      const growth = view.find('[data-unit="u002"] > summary .unit-head')
      // the ok count stays a figure; the issue count is a button that names what it opens
      expect(growth.find('[data-state="ok"] button').exists()).toBe(false)
      const count = growth.find('[data-state="issue"] [data-show-state="issue"]')
      expect(count.text()).toBe('1')
      expect(count.attributes('aria-label')).toBe('show the page of 2 The growth rate in issue')
      expect(view.find('[data-unit="u001"] summary button').exists()).toBe(false)
      await count.trigger('click')
      await flushPromises()
      // the chapter and its section that hold page 5 stand open, and page 5 is marked, nothing else
      expect(['u002', 'u003', 'u001', 'u004'].map(unit => isOpen(view, unit))).toEqual([true, true, false, false])
      expect(view.findAll('tr.marked').map(row => row.attributes('data-page'))).toEqual(['5'])
    })

    it('keeps a chapter the reader opened open on coming back from a page, and not one a filter opened (the operator, 2026-11-10)', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      const growth = view.find('[data-unit="u002"]')
      ;(growth.element as HTMLDetailsElement).open = true
      await growth.trigger('toggle')
      view.unmount()
      // back from a page: the view is mounted anew, and the chapter stands open as the reader left it
      const back = mountView()
      await flushPromises()
      expect(isOpen(back, 'u002')).toBe(true)
      expect(isOpen(back, 'u001')).toBe(false)
    })

    it('lists a page shared by two units under both, and marks a unit the chat\'s index leaves out', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      expect(view.find('[data-unit="u003"] [data-page="6"]').exists()).toBe(true)
      expect(view.find('[data-unit="u004"] [data-page="6"]').exists()).toBe(true)
      expect(view.find('[data-unit="u005"] .note').text()).toBe('not in the chat\'s index')
    })

    it('keeps the pages outside every unit apart, before the first chapter', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      const outside = view.find('[data-unit="outside"]')
      expect(outside.find('[data-page="1"]').exists()).toBe(true)
      expect(outside.find('.unit-head .unit-title').text()).toBe('Outside the outline')
      expect(outside.find('.unit-head .unit-pages').text()).toBe('1')
      expect(view.findAll('.outline > details').map(unit => unit.attributes('data-unit'))[0]).toBe('outside')
    })

    it('shows, with a filter chosen, only the chapters holding a matching page, open down to the page', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      await pickFacet(view, 'state', 'issue')
      expect(view.findAll('[data-unit]').map(unit => unit.attributes('data-unit'))).toEqual(['u002', 'u003'])
      expect([isOpen(view, 'u002'), isOpen(view, 'u003')]).toEqual([true, true])
      expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['5'])
    })

    it('offers the flat table, and remembers the choice', async () => {
      vi.mocked(getWorkPages).mockResolvedValue(anOutlinedWork())
      const view = mountView()
      await flushPromises()
      await view.findAll('.view-switch button')[1].trigger('click')
      expect(view.find('.outline').exists()).toBe(false)
      expect(view.findAll('tbody tr').map(row => row.attributes('data-page'))).toEqual(['1', '2', '3', '5', '6', '9'])
      expect(JSON.parse(localStorage.getItem('settings.v1') ?? 'null')).toMatchObject({ workPagesView: 'table' })

      const again = mountView()
      await flushPromises()
      expect(again.find('.outline').exists()).toBe(false)
    })

    it('says why a work stands flat: a PDF without bookmarks, or no outline exported yet', async () => {
      vi.mocked(getWorkPages)
        .mockResolvedValueOnce({ ...aWorkPages([aPageRow()]), outline: [] })
        .mockResolvedValueOnce(aWorkPages([aPageRow()]))
      const bare = mountView()
      await flushPromises()
      expect(bare.find('.no-outline').text()).toContain('no bookmarks')
      expect(bare.find('.view-switch').exists()).toBe(false)

      const unexported = mountView()
      await flushPromises()
      expect(unexported.find('.no-outline').text()).toContain('no outline for this work yet')
    })
  })
})
