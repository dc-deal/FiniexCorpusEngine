import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getOverview, getPages } from '@/api/api_client'
import { router } from '@/router'
import OverviewView from '@/views/OverviewView.vue'
import PagesView from '@/views/PagesView.vue'
import type { Headline, Milestone, Overview, PageList } from '@/types/api/overview_types'
import { anIssueList, KELLY } from './page_fixture'
import { aLadder } from './work_fixture'
import { facetOption, pickFacet } from './facet_harness'
import { sayTime } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getOverview: vi.fn(),
  getPages: vi.fn(),
}))

enableAutoUnmount(afterEach)

const NO_SHELF = 'no shelf built on this machine: python -m backend.search.shelf builds it'
const NO_END_WHY = 'the command stopped before it could record an end, or it is still running'

/** The corpus' headline as the API sums it (O3.a); invented numbers, so they may stand in a tracked file. */
function aHeadline(overrides: Partial<Headline> = {}): Headline {
  return {
    bases: ['free', 'licensed'], left_out: [], shelf_left_out: [],
    works: { total: 19, by_base: { free: 15, licensed: 4 } },
    planned: { total: 2222, by_base: { free: 1822, licensed: 400 } },
    read: { total: 2212, by_base: { free: 1822, licensed: 390 } },
    share_read: 2212 / 2222,
    passed: { total: 2195, by_base: { free: 1815, licensed: 380 } },
    share_passed: 2195 / 2222,
    served: { total: 3454, by_base: { free: 2554, licensed: 900 } },
    to_look_at: { total: 40, by_base: { free: 7, licensed: 33 } },
    cost_usd: { total: 37.77, by_base: { free: 0.1956, licensed: 37.5744 }, by_provider: { anthropic: 37.0, openrouter: 0.77 } },
    ...overrides,
  }
}

function anOverview(overrides: Partial<Overview> = {}): Overview {
  return { headline: aHeadline(), history: [], runs: null, runs_why_not: 'No runs recorded on this machine: the pipeline database is local and not tracked.',
    ...overrides }
}

function mountOverview() {
  return mount(OverviewView, { global: { plugins: [createPinia(), router] } })
}

describe('OverviewView', () => {
  beforeEach(() => {
    vi.mocked(getOverview).mockReset()
    vi.mocked(getPages).mockReset()
  })

  it('heads the corpus with one line of figures, each summed over the bases, its part per base in its card (O3.a)', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    const tiles = view.findAll('[data-tile]')
    expect(tiles.map(tile => tile.attributes('data-tile'))).toEqual(['works', 'planned', 'read', 'passed', 'served', 'to_look_at', 'cost'])
    expect(view.find('[data-part="share-read"]').text()).toBe('99.5 % of planned')
    expect(view.find('[data-tile="planned"] .tile-value').text()).toBe('2,222')
    expect(view.find('[data-part="share"]').text()).toBe('98.8 % of planned')
    expect(view.find('[data-tile="to_look_at"]').attributes('href')).toBe('#/issues')
    expect(view.find('[data-tile="cost"] .tile-value').text()).toBe('37.77')
    // the split per base is a detail: in the figure's card, never a column of its own
    expect(view.text()).not.toContain('1,822')
    await view.find('[data-tile="planned"]').element.parentElement!.dispatchEvent(new Event('mouseenter'))
    await flushPromises()
    const card = view.find('[data-part="hover-card"]')
    expect(card.find('.card-title').text()).toBe('Pages planned')
    expect(card.findAll('.card-row').map(row => row.text())).toEqual(['free1,822', 'licensed400'])
    // the cost's card: each base's part, then each provider's, where the per-model tables stood
    await view.find('[data-tile="cost"]').element.parentElement!.dispatchEvent(new Event('mouseenter'))
    await flushPromises()
    expect(view.findAll('[data-tile="cost"] ~ [data-part="hover-card"] .card-row').map(row => row.text()))
      .toEqual(['free0.2', 'licensed37.57', 'anthropic (provider)37.00', 'openrouter (provider)0.77'])
    // the tables of counts are gone from the overview, their counts in the Pages list's filters (O3.a)
    expect(view.find('[data-band="pipeline"]').exists()).toBe(false)
    expect(view.find('[data-band="cost"]').exists()).toBe(false)
  })

  it('says how far the corpus is refined, a level opening its pages where the Pages view lists them (U1.a)', async () => {
    const corpus = aLadder({ unit: 'pages and sections', rungs: aLadder().rungs.map(rung => ({ ...rung,
      by_base: { free: 600, licensed: (rung.count ?? 0) - 600 },
      pages_filter: (rung.level === 'read' ? {} : rung.level === 'checked' ? { state: ['ok', 'decided_by_a_person'] } : null) as
        Record<string, string[]> | null })) })
    vi.mocked(getOverview).mockResolvedValue(anOverview({ headline: aHeadline({ ladder: corpus }) }))
    const view = mountOverview()
    await flushPromises()
    const band = view.find('[data-band="coverage"]')
    // no Pages filter lists the text served: its figures stand, no link
    expect(band.find('[data-said="text served"] a').exists()).toBe(false)
    expect(band.find('[data-said="read"] a').attributes('href')).toBe('#/pages')
    expect(band.find('[data-said="checked"] a').attributes('href')).toBe('#/pages?state=ok&state=decided_by_a_person')
    // each base's part of a level in its card
    await band.find('[data-said="read"] .hover-card-host').trigger('mouseenter')
    expect(band.find('[data-said="read"] [data-row="licensed"] .card-value').text()).toBe('29')
  })

  it('says which base the sums leave out and why, and which has no shelf built', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview({ headline: aHeadline({
      bases: ['free'], left_out: [{ knowledge_base: 'licensed', why: 'not read: the app was started with --public-only' }],
      works: null, planned: null, read: null, share_read: null, passed: null, served: null, share_passed: null,
      shelf_left_out: [{ knowledge_base: 'free', why: NO_SHELF }],
      to_look_at: { total: 7, by_base: { free: 7 } }, cost_usd: { total: 0.1956, by_base: { free: 0.1956 }, by_provider: { anthropic: 0.1956 } },
    }) }))
    const view = mountOverview()
    await flushPromises()
    expect(view.find('[data-part="left-out"][data-kb="licensed"]').text()).toContain('--public-only')
    expect(view.find('[data-part="shelf-left-out"][data-kb="free"]').text()).toContain('no shelf built')
    expect(view.findAll('[data-tile]').map(tile => tile.attributes('data-tile'))).toEqual(['to_look_at', 'cost'])
  })

  it('lists the corpus\'s history a line per milestone, newest first, each base\'s part in the milestone\'s card (X1.a)', async () => {
    const both: Milestone = { at: '2026-11-19', milestone: 'both apart', planned: 2222, read: 2212, passed: 2195, share_passed: 0.9878,
      served: 3454, summed: false, parts: { free: { planned: 1822, read: 1822, passed: 1815, share_passed: 0.9962, served: 2554 },
        licensed: { planned: 400, read: 390, passed: 380, share_passed: 0.95, served: 900 } } }
    const taken: Milestone = { at: '2026-11-08', milestone: 'taken over', planned: 2000, read: null, passed: 1900, share_passed: 0.95,
      served: null, summed: true, parts: {} }
    vi.mocked(getOverview).mockResolvedValueOnce(anOverview()).mockResolvedValueOnce(anOverview({ history: [both, taken] }))
    const none = mountOverview()
    await flushPromises()
    expect(none.find('[data-band="history"] .note').text()).toBe('No milestone recorded on this machine yet.')

    const view = mountOverview()
    await flushPromises()
    const lines = view.findAll('[data-band="history"] tbody tr')
    expect(lines.map(line => line.attributes('data-milestone'))).toEqual(['both apart', 'taken over'])
    expect(lines[0].findAll('td').map(cell => cell.text()).slice(1)).toEqual(['both apart', '2,222', '2,212', '2,195', '98.8 %', '3,454'])
    // a line taken over summed keeps what it did not keep empty, and its card says so
    expect(lines[1].findAll('td').map(cell => cell.text()).slice(2)).toEqual(['2,000', '', '1,900', '95.0 %', ''])
    await lines[0].find('.milestone .hover-card-host').trigger('mouseenter')
    expect(lines[0].findAll('.card-row').map(row => row.text()).slice(1)).toEqual(['free1,815 of 1,822 passed', 'licensed380 of 400 passed'])
    await lines[1].find('.milestone .hover-card-host').trigger('mouseenter')
    expect(lines[1].find('[data-row="bases"] .card-value').text()).toBe('both summed, as taken over before 19 Nov')
  })

  it('withholds the name of a milestone where the API gives none, under --public-only (81.a)', async () => {
    const free: Milestone = { at: '2026-11-19', milestone: null, planned: 1822, read: 1822, passed: 1815, share_passed: 0.9962,
      served: 2554, summed: false, parts: { free: { planned: 1822, read: 1822, passed: 1815, share_passed: 0.9962, served: 2554 } } }
    vi.mocked(getOverview).mockResolvedValue(anOverview({ history: [free] }))
    const view = mountOverview()
    await flushPromises()
    expect(view.find('[data-band="history"] [data-part="withheld"]').text()).toBe('name withheld under --public-only')
  })

  it('lists the latest runs of both bases in one table, each with its base, and says a run that recorded no end', async () => {
    vi.mocked(getOverview)
      .mockResolvedValueOnce(anOverview())
      .mockResolvedValueOnce(anOverview({ runs_why_not: null, runs: [
        { knowledge_base: 'licensed', run_id: 374, command: 'python -m backend.conversion.reading.direct_reader prepare',
          started_at: '2026-11-18T21:10:00+00:00', ended_at: null, outcome: 'no end recorded', outcome_why: NO_END_WHY, cost_usd: null,
          batch_ids: [], note: null },
        { knowledge_base: 'free', run_id: 17, command: 'python -m backend.conversion.replay reread', started_at: '2026-11-05T08:52:00+00:00',
          ended_at: '2026-11-05T09:00:00+00:00', outcome: 'ok', outcome_why: null, cost_usd: 0.0416, batch_ids: ['msgbatch_01', 'msgbatch_02'],
          note: null },
      ] }))
    const none = mountOverview()
    await flushPromises()
    expect(none.find('[data-band="runs"] .note').text()).toContain('No runs recorded on this machine')

    const view = mountOverview()
    await flushPromises()
    expect(view.findAll('[data-run]').map(row => row.attributes('data-run'))).toEqual(['licensed/374', 'free/17'])
    expect(view.find('[data-run="licensed/374"] [data-kb="licensed"]').exists()).toBe(true)
    // a run that recorded no end, in the API's words, what that means in its card; never "failed"
    const outcome = view.find('[data-run="licensed/374"] .outcome')
    expect(outcome.text()).toBe('no end recorded')
    await outcome.find('.hover-card-host').trigger('mouseenter')
    expect(outcome.find('[data-row="means"] .card-value').text()).toBe(NO_END_WHY)
    // a run on one line: the time said as a person says it, the command short, the batches folded to a count
    const run = view.find('[data-run="free/17"]')
    expect(run.find('.when time').attributes('datetime')).toBe('2026-11-05T08:52:00+00:00')
    expect(run.find('.when').text()).toBe(sayTime('2026-11-05T08:52:00+00:00').text)
    expect(run.find('.command').text()).toBe('replay reread')
    expect(run.find('.batches summary').text()).toBe('2 batches')
    expect(run.find('.cost').text()).toBe('0.042')
    expect(run.find('.run-id a').attributes('href')).toBe('#/free/runs/17')
  })
})

describe('PagesView', () => {
  const ORDER = ['ok', 'ok_unjudged', 'not_yet_checked', 'decided_by_a_person', 'decided_by_an_automated_review', 'blocked', 'issue', 'stopped']

  /** The page list as the API serves it (P1.a): each page with its words in every field; invented over a free work. */
  function aPageList(states: string[]): PageList {
    const template = anIssueList().rows[0]!
    return {
      filters: {}, state_order: ORDER,
      rows: states.map((state, at) => ({ ...template, pdf_page: at + 1, listed_state: state,
        filtered_by: { state: [state], route: [template.route], verdict: state === 'issue' ? ['bad'] : [], reason: [], reader: [],
          judge: [], provider: [], category: ['content'], why_judged: [], person: [], review: [] } })),
    }
  }

  function mountPages() {
    return mount(PagesView, { global: { plugins: [createPinia(), router] }, attachTo: document.body })
  }

  beforeEach(() => {
    vi.mocked(getPages).mockReset()
  })

  it('loads every page once and narrows them in the browser by the choice in the address (P1.a)', async () => {
    vi.mocked(getPages).mockResolvedValue(aPageList(['ok', 'blocked', 'issue', 'blocked']))
    await router.push('/pages?knowledge_base=free&state=blocked')
    const view = mountPages()
    await flushPromises()
    // the API is asked for every page, never for a field the bar can narrow by
    expect(vi.mocked(getPages)).toHaveBeenCalledWith({})
    expect(view.findAll('tbody tr[data-page]')).toHaveLength(2)
    expect(view.find('.facet-count-label').text()).toBe('2 of 4')
    expect(view.find('.facet-trigger[data-facet="state"] .facet-badge').text()).toBe('1')
    // the states in the core's order, as the API gives it, each with how many pages carry it
    const options = [...(await facetOption(view, 'state', 'ok')).parentElement!.querySelectorAll('.facet-option')]
    expect(options.map(option => option.getAttribute('data-value'))).toEqual(['ok', 'blocked', 'issue'])
  })

  it('writes a pick to the address, so a link or the browser\'s back opens the same pages (P1.a)', async () => {
    vi.mocked(getPages).mockResolvedValue(aPageList(['ok', 'blocked', 'issue']))
    await router.push('/pages')
    const view = mountPages()
    await flushPromises()
    await pickFacet(view, 'verdict', 'bad')
    expect(router.currentRoute.value.fullPath).toBe('/pages?verdict=bad')
    expect(view.findAll('tbody tr[data-page]').map(row => row.attributes('data-page'))).toEqual([`free/${KELLY}/3`])
    expect(vi.mocked(getPages)).toHaveBeenCalledTimes(1)
  })

  it('asks the API for a reading file\'s state only when the address names it, and lets it be dropped', async () => {
    vi.mocked(getPages).mockResolvedValue(aPageList(['ok']))
    await router.push('/pages?integrity=tampered&state=ok')
    const view = mountPages()
    await flushPromises()
    expect(vi.mocked(getPages)).toHaveBeenCalledWith({ integrity: 'tampered' })
    const filter = view.find('[data-filter="integrity"]')
    expect(filter.text()).toContain('reading file: tampered')
    expect(filter.find('.remove').attributes('href')).toBe('#/pages?state=ok')
  })

  it('draws the first 500 pages of a long list, says how many there are, and draws every page on request', async () => {
    vi.mocked(getPages).mockResolvedValue(aPageList(Array.from({ length: 620 }, () => 'ok')))
    await router.push('/pages')
    const view = mountPages()
    await flushPromises()
    expect(view.findAll('tbody tr[data-page]')).toHaveLength(500)
    expect(view.find('[data-part="more"]').text()).toContain('the first 500 of 620 pages')
    await view.find('[data-part="show-every-page"]').trigger('click')
    expect(view.findAll('tbody tr[data-page]')).toHaveLength(620)
    expect(view.find('[data-part="more"]').exists()).toBe(false)
  })

  it('says so when no page matches', async () => {
    vi.mocked(getPages).mockResolvedValue(aPageList(['ok']))
    await router.push('/pages?state=blocked')
    const view = mountPages()
    await flushPromises()
    expect(view.text()).toContain('No page matches these filters.')
  })
})
