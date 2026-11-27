import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPage, getRecall } from '@/api/api_client'
import { router } from '@/router'
import PageView from '@/views/PageView.vue'
import type { Judgement, PageDetail, Recalled } from '@/types/api/page_types'
import { KELLY, aBlock, aFormReading, aFormVerdict, aPageDetail, aPageForm } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getRecall: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented over a free paper: one reading, judged by judge/1, which counts, and by a prototype that found a void finding
const KEY = '2b2d48e77b246c95'
const PROTOTYPE = `${KEY}:judge/3:0`
const VOID = { kind: 'wrong_word', block: 'b01', severity: 'major', evidence: "'a' is 'a'", void: true, block_class: 'paragraph' }

function aJudgement(overrides: Partial<Judgement>): Judgement {
  return { version: 'judge/1', version_state: 'active', again: 0, verdict: 'ok', outcome: 'ok', findings: [], counts: true,
    recall: `${KEY}:judge/1:0`, ...overrides }
}

function aPage(): PageDetail {
  return aPageDetail({
    attempts: [{ reading_key: KEY, number: 1, model: 'claude-sonnet-5-5', mode: 'batch', attempt: 0, class_now: 'ok', format_errors: [],
      stored_at: '2026-11-09T09:21:55+00:00', deviation: null, shown: true, judgements: [
        aJudgement({}),
        aJudgement({ version: 'judge/3', version_state: 'prototype', counts: false, verdict: 'bad', findings: [VOID], recall: PROTOTYPE }),
      ] }],
    // the same in the API's form (#18): judge/1 found nothing, so its show is greyed (decision 25); judge/3's shows its finding
    form: aPageForm({ readings: [aFormReading({ key: KEY, verdicts: [
      aFormVerdict({ recall: `${KEY}:judge/1:0` }),
      aFormVerdict({ version: 'judge/3', version_said: 'prototype', verdict_said: 'bad · 1 finding: void', state: 'issue', standing: false,
        recall: PROTOTYPE, show_why_not: null }),
    ] })] }),
  })
}

function aRecall(): Recalled {
  return { recall: PROTOTYPE, reading_key: KEY, reading_number: 1, version: 'judge/3', version_state: 'prototype', again: 0,
    counts: false, said: 'judge/3 (prototype) on reading 1, never served', raw: 'the reading as stored', image_size: [1000, 1400],
    reading: { front: {}, errors: [], warnings: [], error_places: [], blocks: [aBlock({ id: 'b01', findings: [VOID] })] }, page_findings: [] }
}

function mountView() {
  return mount(PageView, { props: { kb: 'free', work: KELLY, page: 4 }, global: { plugins: [createPinia(), router] } })
}

describe('PageView, a judgement recalled on the page (181.a)', () => {
  beforeEach(async () => {
    vi.mocked(getPage).mockReset().mockResolvedValue(aPage())
    vi.mocked(getRecall).mockReset().mockResolvedValue(aRecall())
    localStorage.clear()
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 } })
  })

  it('shows a judgement on the page from its row, marked as not the standing view, and goes back', async () => {
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="recall-chip"]').exists()).toBe(false)
    expect(view.find('[data-part="analysis"]').classes()).not.toContain('overlay')
    // a judgement row whose findings change what the page shows offers it; one that found nothing is greyed, saying why
    expect(view.findAll('[data-part="page-form"] [data-part="recall"]')).toHaveLength(1)
    expect(view.findAll('[data-part="page-form"] [data-part="show-off"]')).toHaveLength(1)
    await view.find('[data-part="page-form"] [data-part="recall"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.judgement).toBe(PROTOTYPE)
    expect(getRecall).toHaveBeenCalledWith('free', KELLY, 4, PROTOTYPE)
    // the top row's chip, the analysis framed and saying so, the row it came from marked, its findings on the blocks
    expect(view.find('[data-part="recall-chip"]').text()).toContain('Recalled: judge/3 (prototype) on reading 1, never served')
    expect(view.find('[data-part="analysis"]').classes()).toContain('overlay')
    expect(view.find('[data-part="analysis-recalled"]').text()).toContain('recalled, not the standing view')
    expect(view.find('[data-part="page-form"] [data-part="recalled-here"]').exists()).toBe(true)
    expect(view.find('[data-block="b01"] [data-voice="code"]').exists()).toBe(true)
    // the quoted text is the standing view's: no choice of it while a judgement is recalled
    expect(view.findAll('.mode button').map(button => button.text())).toEqual(['readable', 'raw'])
    await view.find('[data-part="show-standing"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.judgement).toBeUndefined()
    expect(view.find('[data-part="recall-chip"]').exists()).toBe(false)
    expect(view.find('[data-part="analysis"]').classes()).not.toContain('overlay')
  })

  it('says so where the recalled reading\'s text is not on this machine', async () => {
    vi.mocked(getRecall).mockResolvedValue({ ...aRecall(), reading: null, raw: null,
      why_not: "reading 1's text is not on this machine: only the reading a page shows is exported" })
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 }, query: { judgement: PROTOTYPE } })
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="recall-missing"]').text()).toContain('not on this machine')
    expect(view.find('[data-part="recall-chip"]').exists()).toBe(true)
  })
})
