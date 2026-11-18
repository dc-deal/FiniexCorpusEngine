import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getShelf } from '@/api/api_client'
import { router } from '@/router'
import ShelfView from '@/views/ShelfView.vue'
import type { Shelf, ShelfRow } from '@/types/api/shelf_types'
import { sayTime } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getShelf: vi.fn(),
}))

enableAutoUnmount(afterEach)

const KELLY = 'carta_conversano_kelly_criterion_2020'
const BLOCKED = 'text layer: the provider blocked the reading'

/** A shelf row as the API serves it; invented counts over a free work. */
function aRow(overrides: Partial<ShelfRow> = {}): ShelfRow {
  return { knowledge_base: 'free', work: 'carta-conversano-kelly-2020', title: 'Kelly criterion paper', source_id: KELLY,
    file: `${KELLY}.pdf`, format: 'pdf', pages: 15, planned: 97, read: 97, passed: 39, share_passed: 0.4021,
    not_passed: [{ reason: 'blocked', count: 39, route: BLOCKED }, { reason: 'no_page', count: 1, route: 'text layer: the reading found no page' }],
    served: { pages: 76, searchable: 76, from_readings: 39, by_route: {} }, unplaced: {}, unplaced_total: 0, held: null,
    not_served: null, has_pages: true, ...overrides }
}

function aShelf(rows: ShelfRow[] = [aRow()]): Shelf {
  return { bases: [
    { knowledge_base: 'free', why_not: null, built_at: '2026-11-08T17:56:17+00:00', in_step: true, totals: { works: rows.length, planned: 97 }, works: rows },
    { knowledge_base: 'licensed', why_not: 'not read: the app was started with --public-only', built_at: null, totals: {}, works: [] },
  ] }
}

function mountShelf() {
  return mount(ShelfView, { global: { plugins: [createPinia(), router] } })
}

describe('ShelfView', () => {
  beforeEach(() => {
    vi.mocked(getShelf).mockReset()
  })

  it('shows each work with the core\'s counts and share, and a reason\'s count opening exactly its pages', async () => {
    vi.mocked(getShelf).mockResolvedValue(aShelf())
    const view = mountShelf()
    await flushPromises()
    const row = view.find(`[data-work="${KELLY}"]`)
    expect(row.find('[data-cell="share"]').text()).toBe('40 %')
    const blocked = row.find('[data-reason="blocked"]')
    expect(blocked.text()).toBe('39 blocked')
    const target = router.resolve((blocked.attributes('href') ?? '').slice(1))
    expect(target.params).toEqual({ kb: 'free', work: KELLY })
    expect(target.query).toEqual({ route: BLOCKED })
    expect(row.find('[data-reason="no_page"]').text()).toBe('1 no page')
    expect(view.find('[data-kb="free"] .built').text()).toBe(`built ${sayTime('2026-11-08T17:56:17+00:00').text}`)
    expect(view.find('[data-kb="free"] .built time').attributes('datetime')).toBe('2026-11-08T17:56:17+00:00')
  })

  it('warns where the shelf was built from another export than the one served, and says nothing where it was not', async () => {
    const parted = aShelf()
    parted.bases[0].in_step = false
    vi.mocked(getShelf).mockResolvedValueOnce(parted).mockResolvedValueOnce(aShelf())
    const view = mountShelf()
    await flushPromises()
    expect(view.find('[data-kb="free"] [data-part="out-of-step"]').text()).toContain('built from another export')
    const inStep = mountShelf()
    await flushPromises()
    expect(inStep.find('[data-part="out-of-step"]').exists()).toBe(false)
  })

  it('opens nothing for a work this app holds no readings of, and says why a base is not shown', async () => {
    vi.mocked(getShelf).mockResolvedValue(aShelf([aRow({ has_pages: false, work: null })]))
    const view = mountShelf()
    await flushPromises()
    expect(view.find('[data-kb="free"] tbody a').exists()).toBe(false)
    expect(view.find('[data-kb="licensed"] .why-not').text()).toContain('--public-only')
  })

  it('says what passed but is not served, and an unexplained count in the open', async () => {
    vi.mocked(getShelf).mockResolvedValue(aShelf([aRow({
      unplaced: { 'nothing to quote on the page': 3, 'unexplained': 2 }, unplaced_total: 5 })]))
    const view = mountShelf()
    await flushPromises()
    expect(view.find('.unplaced summary').text()).toBe('5')
    expect(view.find('.unexplained-note').text()).toContain('2 passed but not served, unexplained')
  })
})
