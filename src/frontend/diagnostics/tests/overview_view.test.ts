import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getOverview, getPages } from '@/api/api_client'
import { router } from '@/router'
import OverviewView from '@/views/OverviewView.vue'
import PagesView from '@/views/PagesView.vue'
import type { BaseHeadline, ModelSection, Overview, Section } from '@/types/api/overview_types'
import { anIssueList } from './page_fixture'
import { sayTime } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getOverview: vi.fn(),
  getPages: vi.fn(),
}))

enableAutoUnmount(afterEach)

const VISION = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)'

/** The overview as the API serves it; invented numbers, so they may stand in a tracked file. */
function aFreeHeadline(overrides: Partial<BaseHeadline> = {}): BaseHeadline {
  return { knowledge_base: 'free', served: true, why_not: null, works: 4, pages: 12, served_works: 6, served_pages: 2315, judged: 7,
    to_look_at: 3, cost_usd: 0.1956, runs: null, ...overrides }
}

function sections(): Section[] {
  return [
    { title: 'How the text is made', field: 'route', linked: true, note: null, rows: [
      { value: VISION, free: 10, licensed: null },
      { value: 'text layer: the provider blocked the reading', free: 2, licensed: null },
    ] },
    { title: 'State', field: 'state', linked: true, note: null, rows: [
      { value: 'ok', free: 9, licensed: null }, { value: 'blocked', free: 2, licensed: null }, { value: 'issue', free: 1, licensed: null },
    ] },
    { title: 'Is the reading what was checked', field: 'integrity', linked: true, note: null, rows: [
      { value: 'whole', free: 11, licensed: null }, { value: 'tampered', free: 1, licensed: null },
    ] },
  ]
}

const SECOND_READER = 'mistralai/mistral-large-4-0 · Mistral'

function models(): ModelSection[] {
  return [
    { title: 'Readings by model', field: 'reader', linked: true, note: null, rows: [
      { value: 'claude-sonnet-5-5', free: 12, licensed: null, free_usd: 0.1956, licensed_usd: null },
      { value: SECOND_READER, free: 2, licensed: null, free_usd: null, licensed_usd: null },
    ] },
    { title: 'Judgements by model', field: 'judge', linked: true, note: null, rows: [
      { value: 'claude-sonnet-5-5', free: 7, licensed: null, free_usd: 0.0512, licensed_usd: null },
    ] },
  ]
}

function anOverview(free: BaseHeadline = aFreeHeadline(), searchSection: Partial<Section> = {}): Overview {
  return {
    bases: [free, { knowledge_base: 'licensed', served: false, why_not: 'not read: the app was started with --public-only',
      works: 0, pages: 0, judged: 0, to_look_at: 0, cost_usd: 0, runs: null }],
    models: models(),
    sections: sections(),
    search: { title: 'In the search, every medium', field: 'route', linked: false, note: null, rows: [], ...searchSection },
  }
}

function mountOverview() {
  return mount(OverviewView, { global: { plugins: [createPinia(), router] } })
}

describe('OverviewView', () => {
  beforeEach(() => {
    vi.mocked(getOverview).mockReset()
    vi.mocked(getPages).mockReset()
  })

  it('heads each knowledge base with its key figures, and says why one is not served', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    const free = view.find('.headline[data-kb="free"]')
    expect(free.find('[data-tile="pages"] .tile-value').text()).toBe('12')
    expect(free.find('[data-tile="judged"] .tile-value').text()).toBe('7')
    expect(free.find('[data-tile="to_look_at"]').attributes('href')).toBe('#/issues')
    expect(free.find('[data-tile="cost"] .tile-value').text()).toBe('0.2')
    expect(view.find('.headline[data-kb="licensed"] .not-served').text()).toContain('--public-only')
  })

  it('says what the works and pages tiles count, what was read with what the search serves beneath it (1.a)', async () => {
    vi.mocked(getOverview).mockResolvedValueOnce(anOverview())
      .mockResolvedValueOnce(anOverview(aFreeHeadline({ served_works: null, served_pages: null })))
    const view = mountOverview()
    await flushPromises()
    const works = view.find('.headline[data-kb="free"] [data-tile="works"]')
    expect(works.find('.tile-value').text()).toBe('4')
    expect(works.find('.tile-label').text()).toBe('works read page by page')
    expect(works.find('[data-part="served"]').text()).toBe('6 in the search')
    const pages = view.find('.headline[data-kb="free"] [data-tile="pages"]')
    expect(pages.find('.tile-label').text()).toBe('pages read')
    expect(pages.find('[data-part="served"]').text()).toBe('2,315 in the search')
    // while the search index is still being built its counts are not known, and the tile says so rather than guess
    const building = mountOverview()
    await flushPromises()
    expect(building.find('.headline[data-kb="free"] [data-tile="works"] [data-part="served"]').text()).toBe('search index building')
  })

  it('names each value once, its count per knowledge base beside it, and opens the pages behind a count', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    const states = view.find('[data-section="State"]')
    expect(states.findAll('thead th').map(head => head.text())).toEqual(['State', 'free', 'licensed'])
    expect(states.findAll('[data-value="issue"]')).toHaveLength(1)
    const issue = states.find('[data-value="issue"] [data-kb="free"] a')
    expect(issue.text()).toBe('1')
    expect(issue.attributes('href')).toBe('#/pages?knowledge_base=free&state=issue')
    // a base not served shows no count, and no link
    expect(states.find('[data-value="issue"] [data-kb="licensed"]').text()).toBe('—')
    expect(states.find('[data-value="issue"] [data-kb="licensed"] a').exists()).toBe(false)
    // a route with spaces, commas and slashes comes back whole from the address
    const vision = view.find('[data-field="route"] [data-value^="vision"] [data-kb="free"] a').attributes('href') ?? ''
    expect(router.resolve(vision.slice(1)).query).toEqual({ knowledge_base: 'free', route: VISION })
  })

  it('says which model did what: its pages, each opening them, and what its work cost beside them', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    const readers = view.find('[data-band="cost"] [data-section="Readings by model"]')
    expect(readers.findAll('thead th').map(head => head.text())).toEqual(['Readings by model', 'free', 'USD', 'licensed', 'USD'])
    const second = readers.find(`[data-value="${SECOND_READER}"]`)
    const href = second.find('[data-kb="free"] a').attributes('href') ?? ''
    expect(router.resolve(href.slice(1)).query).toEqual({ knowledge_base: 'free', reader: SECOND_READER })
    // a cost the export does not give is said unknown, never shown as nothing spent
    expect(second.find('[data-kb-usd="free"]').text()).toBe('—')
    expect(readers.find('[data-value="claude-sonnet-5-5"] [data-kb-usd="free"]').text()).toBe('0.2')
    expect(view.find('[data-section="Judgements by model"] [data-kb="free"] a').attributes('href'))
      .toBe('#/pages?knowledge_base=free&judge=claude-sonnet-5-5')
    // the boxes that count pages alone carry no cost column
    expect(view.find('[data-section="State"] [data-kb-usd]').exists()).toBe(false)
  })

  it('says whether each reading is what was checked, a tampered one marked and opening its pages', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    const box = view.find('[data-band="pipeline"] [data-section="Is the reading what was checked"]')
    const tampered = box.find('[data-value="tampered"]')
    expect(tampered.find('[data-integrity="tampered"] [data-icon="status-error"]').exists()).toBe(true)
    expect(tampered.find('[data-kb="free"] a').attributes('href')).toBe('#/pages?knowledge_base=free&integrity=tampered')
  })

  it('sets the boxes in bands, each under its heading', async () => {
    vi.mocked(getOverview).mockResolvedValue(anOverview())
    const view = mountOverview()
    await flushPromises()
    expect(view.findAll('.band').map(band => band.attributes('data-band'))).toEqual(['cost', 'pipeline', 'search', 'runs'])
    expect(view.find('[data-band="pipeline"] [data-section="State"]').exists()).toBe(true)
    expect(view.find('[data-band="search"] [data-section="In the search, every medium"]').exists()).toBe(true)
  })

  it('says the search is still being built, counts it without links once it stands, and shows recorded runs', async () => {
    vi.mocked(getOverview)
      .mockResolvedValueOnce(anOverview(aFreeHeadline(), { note: 'The search index is still being built; it counts here once it stands.' }))
      .mockResolvedValueOnce(anOverview(aFreeHeadline({
        runs: [{ knowledge_base: 'free', run_id: 17, command: 'python -m backend.conversion.replay reread', started_at: '2026-11-05T08:52:00+00:00',
          ended_at: null, outcome: 'ok', cost_usd: 0.0416, batch_ids: ['msgbatch_01', 'msgbatch_02'], note: null }],
      }), { rows: [{ value: 'html, parsed by section', free: 767, licensed: null }] }))
    const building = mountOverview()
    await flushPromises()
    expect(building.find('[data-section="In the search, every medium"] .box-note').text()).toContain('still being built')
    expect(building.find('.runs[data-kb="free"]').text()).toContain('No runs recorded on this machine')

    const built = mountOverview()
    await flushPromises()
    const html = built.find('[data-section="In the search, every medium"] [data-value="html, parsed by section"] [data-kb="free"]')
    expect(html.text()).toBe('767')
    expect(html.find('a').exists()).toBe(false)
    // a run on one line: the time short, the command without its shared module path, the batches folded to a count
    const run = built.find('.runs [data-run="17"]')
    // the API's ISO time stays in the element; the text is said as a person says it, against this machine's clock
    expect(run.find('.when time').attributes('datetime')).toBe('2026-11-05T08:52:00+00:00')
    expect(run.find('.when').text()).toBe(sayTime('2026-11-05T08:52:00+00:00').text)
    expect(run.find('.command').text()).toBe('replay reread')
    expect(run.find('.command').attributes('title')).toBe('python -m backend.conversion.replay reread')
    expect(run.find('.batches summary').text()).toBe('2 batches')
    expect(run.find('.cost').text()).toBe('0.042')
    // a run's number opens its own page
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
