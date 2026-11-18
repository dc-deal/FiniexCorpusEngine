import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getRun, getRuns } from '@/api/api_client'
import { router } from '@/router'
import RunsView from '@/views/RunsView.vue'
import RunView from '@/views/RunView.vue'
import type { RunDetail, RunLine } from '@/types/api/runs_types'
import { sayTime } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getRuns: vi.fn(),
  getRun: vi.fn(),
}))

enableAutoUnmount(afterEach)

const KELLY = 'carta_conversano_kelly_criterion_2020'

/** Runs as the API serves them; invented, so they may stand in a tracked file. */
function aRun(overrides: Partial<RunLine> = {}): RunLine {
  return { knowledge_base: 'free', run_id: 17, command: 'python -m backend.conversion.replay reread --work kelly --page 3 --cap 75',
    started_at: '2026-11-05T08:52:35+00:00', ended_at: '2026-11-05T08:55:06+00:00', outcome: 'ok', cost_usd: 0.166,
    batch_ids: [], note: null, ...overrides }
}

function aRunDetail(overrides: Partial<RunDetail> = {}): RunDetail {
  return { ...aRun(), code_commit: '15e96738fe352316b160e80f59d86cb37d4c1ea9', code_clean: false, code_sha256: 'a32247a0f81dc15b',
    cost_by_provider: { anthropic: 0.058, openrouter: 0.108 },
    chose: [{ file: 'kelly.pdf', pdf_page: 3, source_id: KELLY, title: 'Kelly criterion paper', reading_key: 'a29eea63',
      why: 'replay --reread: judged ok', chosen_at: '2026-11-05T08:53:03+00:00' }],
    ...overrides }
}

function mountRun(run = 17) {
  return mount(RunView, { props: { kb: 'free', run }, global: { plugins: [createPinia(), router] } })
}

describe('RunsView', () => {
  beforeEach(() => {
    vi.mocked(getRuns).mockReset()
  })

  it('lists every run newest first, each opening its own page, and says why a base is not listed', async () => {
    vi.mocked(getRuns).mockResolvedValue({
      bases: [{ knowledge_base: 'free', why_not: null }, { knowledge_base: 'licensed', why_not: 'not read: the app was started with --public-only' }],
      runs: [aRun({ run_id: 18, command: 'python -m backend.conversion.integrity', batch_ids: ['msgbatch_01', 'msgbatch_02'] }), aRun()],
    })
    const view = mount(RunsView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    const rows = view.findAll('tbody tr')
    expect(rows.map(row => row.attributes('data-run'))).toEqual(['free/18', 'free/17'])
    expect(rows[1].find('.run-id a').attributes('href')).toBe('#/free/runs/17')
    expect(rows[1].find('.command').text()).toBe('replay reread --work kelly --page 3 --cap 75')
    expect(rows[0].find('.batches').text()).toBe('2 batches')
    expect(view.find('.not-listed[data-kb="licensed"]').text()).toContain('--public-only')
    expect(view.find('.not-listed[data-kb="free"]').exists()).toBe(false)
  })
})

describe('RunView', () => {
  beforeEach(() => {
    vi.mocked(getRun).mockReset()
  })

  it('shows a run whole: its command, its code, its cost by provider, and the pages it chose, each opening its view', async () => {
    vi.mocked(getRun).mockResolvedValue(aRunDetail({
      chose: [...aRunDetail().chose, { file: 'unexported.pdf', pdf_page: 7, source_id: null, title: 'unexported.pdf',
        reading_key: 'b1', why: 'second reader chosen', chosen_at: '2026-11-05T09:00:00+00:00' }],
    }))
    const view = mountRun()
    await flushPromises()
    expect(vi.mocked(getRun)).toHaveBeenCalledWith('free', 17)
    expect(view.find('.command').text()).toBe('python -m backend.conversion.replay reread --work kelly --page 3 --cap 75')
    expect(view.find('[data-fact="code"]').text()).toContain('15e96738fe35 · with uncommitted changes')
    expect(view.findAll('[data-fact="cost"] .provider').map(provider => provider.text())).toEqual(['· anthropic 0.0580', '· openrouter 0.1080'])
    const [exported, unexported] = view.findAll('.chose-rows tbody tr')
    expect(exported.find('a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/3`)
    expect(exported.find('.when time').attributes('datetime')).toBe('2026-11-05T08:53:03+00:00')
    expect(exported.find('.when').text()).toBe(sayTime('2026-11-05T08:53:03+00:00').text)
    // a page the export does not hold has no view to open
    expect(unexported.find('a').exists()).toBe(false)
  })

  it('names a work once where its pages begin, not on every page of it', async () => {
    const page = aRunDetail().chose[0]
    vi.mocked(getRun).mockResolvedValue(aRunDetail({
      chose: [page, { ...page, pdf_page: 4 }, { ...page, file: 'other.pdf', source_id: 'other', title: 'Another work', pdf_page: 1 }],
    }))
    const view = mountRun()
    await flushPromises()
    expect(view.findAll('.chose-rows .work').map(cell => cell.text())).toEqual(['Kelly criterion paper', '', 'Another work'])
  })

  it('says a run that chose no reading did so', async () => {
    vi.mocked(getRun).mockResolvedValue(aRunDetail({ chose: [], code_clean: true }))
    const view = mountRun()
    await flushPromises()
    expect(view.find('.none').text()).toBe('This run chose no reading.')
    expect(view.find('[data-fact="code"]').text()).toContain('· clean')
  })

  it('never shows an answer for another run as this one', async () => {
    let answerFor17: (detail: RunDetail) => void = () => {}
    vi.mocked(getRun)
      .mockImplementationOnce(() => new Promise(resolve => { answerFor17 = resolve }))
      .mockResolvedValueOnce(aRunDetail({ run_id: 18 }))
    const view = mountRun(17)
    await view.setProps({ run: 18 })
    await flushPromises()
    answerFor17(aRunDetail({ run_id: 17 }))
    await flushPromises()
    expect(view.find('.view-title').text()).toContain('Run #18')
  })
})
