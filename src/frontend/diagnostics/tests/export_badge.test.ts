import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ExportBadge from '@/components/ExportBadge.vue'
import { durationWords, exportClock } from '@/export_clock'
import { useVerdictStore } from '@/stores/verdict_store'
import type { VerdictForm } from '@/types/api/verdict_types'

enableAutoUnmount(afterEach)

const NOW = Date.parse('2026-11-21T17:05:00+00:00')
type Status = VerdictForm['exports'][number]

function aStatus(overrides: Partial<Status> = {}): Status {
  return { knowledge_base: 'licensed', running: true, pending: false, finished: 3, last_error: null, last_finished_at: null,
    started_at: '2026-11-21T17:02:30+00:00', expected_seconds: 300, waiting: [], ...overrides }
}

function aForm(exports: Status[]): VerdictForm {
  return { enabled: true, why_not: null, verdicts: [], reasons: [], assessments: [], exports, propose: { available: false, why_not: 'none' } }
}

describe('an export\'s clock in words (E1.a)', () => {
  it('says how far a running export is, in the minute it is in, and without an estimate how long it has run', () => {
    expect(exportClock(150, 300)).toBe('3 of about 5 min')
    expect(exportClock(0, 300)).toBe('1 of about 5 min')
    expect(exportClock(12, 45)).toBe('12 of about 45 s')
    expect(exportClock(40, null)).toBe('running 40 s')
    expect(exportClock(185, null)).toBe('running 3 min')
  })

  it('says how long one may take at the toast\'s boundaries', () => {
    expect([null, 19, 20, 89, 90, 300].map(durationWords)).toEqual(['a few minutes', 'a few seconds', 'about 20 seconds',
      'about 89 seconds', 'about 2 minutes', 'about 5 minutes'])
  })
})

describe('the header\'s hourglass (E1.a)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountBadge(exports: Status[]) {
    useVerdictStore().form = aForm(exports)
    return mount(ExportBadge, { attachTo: document.body })
  }

  it('says nothing while no export runs', () => {
    expect(mountBadge([aStatus({ running: false, started_at: null, expected_seconds: null })]).find('[data-part="export-badge"]').exists()).toBe(false)
  })

  it('turns and counts while one runs, with an estimate and without, and opens a card of what it serves', async () => {
    const waiting = [{ knowledge_base: 'licensed' as const, source_id: 'a_book', pdf_page: 1161, block: 'b05', verdict: 'accept',
      given_at: '2026-11-21T17:02:00+00:00', by_a_person: true }]
    const badge = mountBadge([aStatus({ pending: true, waiting })])
    expect(badge.find('[data-part="export-clock"]').text()).toBe('licensed export · 3 of about 5 min')
    expect(badge.find('.hourglass').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(badge.find('[data-part="export-clock"]').text()).toBe('licensed export · 4 of about 5 min')
    await badge.find('[data-part="export-running"]').trigger('click')
    const card = badge.find('[data-part="export-card"]')
    expect(card.find('[data-part="export-next"]').text()).toContain('one more export waits after this one')
    expect(card.find('[data-waiting="0"]').text()).toContain('a_book · p. 1161 · b05 · accept · recorded')
    const unknown = mountBadge([aStatus({ expected_seconds: null })])
    expect(unknown.find('[data-part="export-clock"]').text()).toBe('licensed export · running 3 min')
  })

  it('says served for 4 s when it ends, and a failure until it is clicked away', async () => {
    const badge = mountBadge([aStatus()])
    const store = useVerdictStore()
    store.form = aForm([aStatus({ running: false, finished: 4, started_at: null })])
    await badge.vm.$nextTick()
    expect(badge.find('[data-part="export-served"]').text()).toBe('served')
    await vi.advanceTimersByTimeAsync(4000)
    expect(badge.find('[data-part="export-badge"]').exists()).toBe(false)
    store.form = aForm([aStatus({ finished: 4 })])
    await badge.vm.$nextTick()
    store.form = aForm([aStatus({ running: false, finished: 5, started_at: null, last_error: 'the export stopped: disk full' })])
    await badge.vm.$nextTick()
    const failed = badge.find('[data-part="export-failed"]')
    expect([failed.text(), failed.attributes('role')]).toEqual(['licensed export failed: the export stopped: disk full', 'alert'])
    await vi.advanceTimersByTimeAsync(60_000)
    expect(badge.find('[data-part="export-failed"]').exists()).toBe(true)
    await badge.find('[data-part="export-failed"]').trigger('click')
    expect(badge.find('[data-part="export-badge"]').exists()).toBe(false)
  })
})
