import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getOverview, getPages } from '@/api/api_client'
import { router } from '@/router'
import OverviewView from '@/views/OverviewView.vue'
import PagesView from '@/views/PagesView.vue'
import type { Headline, Overview } from '@/types/api/overview_types'
import { anIssueList } from './page_fixture'
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
    passed: { total: 2195, by_base: { free: 1815, licensed: 380 } },
    share_passed: 2195 / 2222,
    served: { total: 3454, by_base: { free: 2554, licensed: 900 } },
    to_look_at: { total: 40, by_base: { free: 7, licensed: 33 } },
    cost_usd: { total: 37.77, by_base: { free: 0.1956, licensed: 37.5744 }, by_provider: { anthropic: 37.0, openrouter: 0.77 } },
    ...overrides,
  }
}

function anOverview(overrides: Partial<Overview> = {}): Overview {
  return { headline: aHeadline(), runs: null, runs_why_not: 'No runs recorded on this machine: the pipeline database is local and not tracked.',
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
    expect(tiles.map(tile => tile.attributes('data-tile'))).toEqual(['works', 'planned', 'passed', 'served', 'to_look_at', 'cost'])
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

  it('says which base the sums leave out and why, and which has no shelf built', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview({ headline: aHeadline({
      bases: ['free'], left_out: [{ knowledge_base: 'licensed', why: 'not read: the app was started with --public-only' }],
      works: null, planned: null, passed: null, served: null, share_passed: null,
      shelf_left_out: [{ knowledge_base: 'free', why: NO_SHELF }],
      to_look_at: { total: 7, by_base: { free: 7 } }, cost_usd: { total: 0.1956, by_base: { free: 0.1956 }, by_provider: { anthropic: 0.1956 } },
    }) }))
    const view = mountOverview()
    await flushPromises()
    expect(view.find('[data-part="left-out"][data-kb="licensed"]').text()).toContain('--public-only')
    expect(view.find('[data-part="shelf-left-out"][data-kb="free"]').text()).toContain('no shelf built')
    expect(view.findAll('[data-tile]').map(tile => tile.attributes('data-tile'))).toEqual(['to_look_at', 'cost'])
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
  beforeEach(() => {
    vi.mocked(getPages).mockReset()
  })

  it('lists the pages the address filters for, each filter standing above, removable', async () => {
    vi.mocked(getPages).mockResolvedValue({ filters: { knowledge_base: 'free', state: 'blocked' }, rows: anIssueList().rows.slice(0, 1) })
    await router.push('/pages?knowledge_base=free&state=blocked')
    const view = mount(PagesView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(vi.mocked(getPages)).toHaveBeenCalledWith({ knowledge_base: 'free', state: 'blocked' })
    expect(view.findAll('.filter').map(filter => filter.attributes('data-filter'))).toEqual(['knowledge_base', 'state'])
    expect(view.find('[data-filter="state"] .remove').attributes('href')).toBe('#/pages?knowledge_base=free')
    expect(view.findAll('tbody tr[data-page]')).toHaveLength(1)
  })

  it('says so when no page matches', async () => {
    vi.mocked(getPages).mockResolvedValue({ filters: { reason: 'nothing like it' }, rows: [] })
    await router.push('/pages?reason=nothing%20like%20it')
    const view = mount(PagesView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(view.text()).toContain('No page matches these filters.')
  })
})
