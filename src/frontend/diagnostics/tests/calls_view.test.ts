import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getCalls } from '@/api/api_client'
import { router } from '@/router'
import CallsView from '@/views/CallsView.vue'
import type { Call, CallList } from '@/types/api/calls_types'
import { pickFacet } from './facet_harness'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getCalls: vi.fn(),
}))

enableAutoUnmount(afterEach)

const KELLY = 'carta_conversano_kelly_criterion_2020'

/** A call as the API serves it; invented, over a free work. */
function aCall(overrides: Partial<Call> = {}): Call {
  return { at: '2026-11-06T11:00:02+00:00', tool: 'semantic_search', state: 'found', ms: 9880, client: 'chat', client_version: '0.1.0',
    query: 'What is the Kelly criterion?', corpus: null, hits: 10, work: null, page: null,
    answered: [{ knowledge_base: 'free', work: KELLY, title: 'Kelly criterion paper', label: '3', pdf: '3',
      view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } }],
    answered_works: [],
    filtered_by: { tool: ['semantic_search'], state: ['found'], client: ['chat'], kb: ['free'] },
    ...overrides }
}

function aList(): CallList {
  const search = aCall({ at: '2026-11-05T09:00:00+00:00', tool: 'search', ms: 3.2, client: 'claude-code', query: 'drawdown',
    answered: Array.from({ length: 5 }, (_, at) => ({ knowledge_base: 'free', work: KELLY, title: 'Kelly criterion paper', label: String(at + 1),
      pdf: String(at + 1), view: null })),
    filtered_by: { tool: ['search'], state: ['found'], client: ['claude-code'], kb: ['free'] } })
  return { why_not: null, hidden: 15, older: 0,
    tools: [{ tool: 'semantic_search', calls: 1, median_ms: 9880, states: [{ value: 'found', count: 1 }] },
      { tool: 'search', calls: 1, median_ms: 3.2, states: [{ value: 'found', count: 1 }] }],
    states: [{ value: 'found', count: 2 }], clients: [{ value: 'chat', count: 1 }, { value: 'claude-code', count: 1 }],
    knowledge_bases: [{ value: 'free', count: 2 }], calls: [aCall(), search] }
}

// attached, so the bar's panels, portalled to the document, can be opened
function mountCalls() {
  return mount(CallsView, { global: { plugins: [createPinia(), router] }, attachTo: document.body })
}

describe('CallsView', () => {
  beforeEach(() => {
    vi.mocked(getCalls).mockReset()
    localStorage.clear()
  })

  it('heads the log with each tool\'s figures and says how many calls public-only left out', async () => {
    vi.mocked(getCalls).mockResolvedValue(aList())
    const view = mountCalls()
    await flushPromises()
    expect(view.find('[data-tool="semantic_search"].tool').text()).toContain('9.9 s median')
    expect(view.find('[data-tool="search"].tool').text()).toContain('3.2 ms median')
    expect(view.find('[data-note="hidden"]').text()).toContain('15 calls not shown')
  })

  it('lists the calls by day, newest first, each with who asked what, and its pages opening their views', async () => {
    vi.mocked(getCalls).mockResolvedValue(aList())
    const view = mountCalls()
    await flushPromises()
    expect(view.findAll('.day').map(day => day.attributes('data-day'))).toEqual(['2026-11-06', '2026-11-05'])
    const newest = view.find('.day tbody tr')
    expect(newest.find('.client').text()).toBe('chat')
    expect(newest.find('.question').text()).toBe('"What is the Kelly criterion?"')
    expect(newest.find('.answered a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/3`)
    // a call answered by many pages lists them on request, one page a line, so long titles never run into each other
    const folded = view.find('[data-day="2026-11-05"] details.answered')
    expect(folded.find('summary').text()).toBe('5 pages answered')
    const lines = folded.findAll('.answered-pages li')
    expect(lines.map(line => line.text())).toEqual(['1', '2', '3', '4', '5'].map(label => `Kelly criterion paper p. ${label}`))
  })

  it('narrows the calls to a caller', async () => {
    vi.mocked(getCalls).mockResolvedValue(aList())
    const view = mountCalls()
    await flushPromises()
    await pickFacet(view, 'client', 'claude-code')
    expect(view.findAll('tbody tr').map(row => row.attributes('data-client'))).toEqual(['claude-code'])
    expect(view.find('.facet-count-label').text()).toBe('1 of 2')
    // and keeps the choice across a reload (F5, stage C), as the sources list does
    view.unmount()
    const again = mountCalls()
    await flushPromises()
    expect(again.findAll('tbody tr').map(row => row.attributes('data-client'))).toEqual(['claude-code'])
  })

  it('names the works a search over works answered with, each opening its pages where this app holds them', async () => {
    const list = aList()
    list.calls = [aCall({ tool: 'search_works', answered: [], answered_works: [
      { knowledge_base: 'free', work: 'carta-conversano-kelly-2020', source_id: KELLY, title: 'Kelly criterion paper' },
      { knowledge_base: 'free', work: 'wikipedia_trading_set', source_id: null, title: null },
    ] })]
    vi.mocked(getCalls).mockResolvedValue(list)
    const view = mountCalls()
    await flushPromises()
    const works = view.find('[data-answered="works"]')
    expect(works.text()).toContain('2 works answered:')
    expect(works.find('a').attributes('href')).toBe(`#/free/sources/${KELLY}`)
    expect(works.findAll('a')).toHaveLength(1)
  })

  it('says so where this machine keeps no call log', async () => {
    vi.mocked(getCalls).mockResolvedValue({ ...aList(), why_not: 'No call log on this machine.', calls: [] })
    const view = mountCalls()
    await flushPromises()
    expect(view.find('.note').text()).toBe('No call log on this machine.')
  })
})
