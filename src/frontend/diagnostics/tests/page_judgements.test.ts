import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPage } from '@/api/api_client'
import { router } from '@/router'
import PageView from '@/views/PageView.vue'
import type { Judgement, PageDetail } from '@/types/api/page_types'
import { aBlock, aCheck, aPageDetail, KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented over a free paper: a finding the core found void, naming no difference
const VOID_FINDING = { kind: 'wrong_word', block: 'b01', severity: 'major', evidence: "'a' is 'a'", void: true, block_class: 'paragraph' }

function aJudgement(overrides: Partial<Judgement> = {}): Judgement {
  return { version: 'judge/1', version_state: 'active', model: 'claude-sonnet-5-5', mode: 'batch', again: 0,
    stored_at: '2026-11-09T10:56:48+00:00', verdict: 'bad', outcome: 'ok', judge_outcome: 'issue', findings: [VOID_FINDING],
    cost_usd: 0.0069, counts: true, ...overrides }
}

/** The review's showcase in invented words: one reading, judged by judge/1, asked again, and by two prototypes. */
function aJudgedPage(overrides: Partial<PageDetail> = {}): PageDetail {
  const reading = { model: 'claude-sonnet-5-5', mode: 'batch', class_now: 'ok', stored_at: '2026-11-09T09:21:55+00:00', deviation: null,
    format_errors: [] }
  return aPageDetail({
    check: aCheck({
      why_judged: 'a block stage 2 cannot check',
      verdict: { verdict: 'bad', outcome: 'ok', judge_outcome: 'issue', void: 1, findings: [VOID_FINDING] },
      stage2: { suspicious: false, has_layer: true, recall: 1, precision: 0.9964, findings: [{ kind: 'text_drawn', block: 'b02', detail: '5 reader words', severity: 'note' }],
        unverifiable: [{ why: 'figure_text', block: 'b05', cls: 'figure' }] },
      judge: { model: 'claude-sonnet-5-5', provider: 'anthropic', mode: 'batch', cost_usd: 0.0069, version: 'judge/1' },
    }),
    reading: { front: {}, blocks: [aBlock({ id: 'b01', findings: [VOID_FINDING],
      people: [{ reading_key: 'r1', applies: true, block: 'b01', verdict: 'accept', reason_text: 'the judge quotes the same word twice', by_a_person: true }] })],
    errors: [], warnings: [], error_places: [] },
    attempts: [
      { ...reading, reading_key: 'r0', number: 1, attempt: 0, check: { state: 'ok', verdict: 'bad', outcome: 'ok', reasons: [], came_from: 'an earlier check' },
        judgements: [aJudgement({ judge_outcome: 'bin' })], shown: false },
      { ...reading, reading_key: 'r1', number: 2, attempt: 1, check: { state: 'ok', verdict: 'bad', outcome: 'ok', reasons: [] }, shown: true, judgements: [
        aJudgement(),
        aJudgement({ again: 1, counts: false, mode: 'standard' }),
        aJudgement({ version: 'judge/2', version_state: 'prototype', counts: false }),
        aJudgement({ version: 'judge/3', version_state: 'prototype', counts: false, verdict: 'ok', outcome: 'ok', judge_outcome: 'ok', findings: [] }),
      ] },
    ],
    human: [{ reading_key: 'r1', applies: true, block: 'b01', verdict: 'accept', reason_text: 'the judge quotes the same word twice', by_a_person: true },
      { reading_key: 'r0', applies: false, block: null, verdict: 'note', reason_text: 'looked at the first reading', by_a_person: true }],
    ...overrides,
  })
}

function mountView() {
  return mount(PageView, { props: { kb: 'free', work: KELLY, page: 4 }, global: { plugins: [createPinia(), router] } })
}

describe('PageView, the check in stages and its judges (146.a, 147.a)', () => {
  beforeEach(() => {
    vi.mocked(getPage).mockReset()
    localStorage.clear()
  })

  it('shows the three stages one by one in the details, then a person', async () => {
    vi.mocked(getPage).mockResolvedValue(aJudgedPage())
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-stage="1"]').text()).toContain('validator page/1.1')
    const stage2 = view.find('[data-stage="2"]')
    expect(stage2.text()).toContain('recall 1.000 · precision 0.996')
    expect(stage2.find('[data-part="stage2-finding"]').text()).toBe('text_drawn · b02 · 5 reader words · note')
    expect(stage2.find('[data-part="unverifiable"]').text()).toBe('cannot check b05 (figure): figure_text')
    // stage 3 one fact a line, each named (the operator, 16 Nov)
    const stage3 = view.find('[data-stage="3"]')
    expect(stage3.findAll('.line-label').map(label => label.text())).toEqual(['Why:', 'Verdict:', 'Judge:'])
    expect(stage3.find('[data-part="stage3-why"] .line-value').text()).toBe('a block stage 2 cannot check')
    expect(stage3.find('[data-part="stage3-verdict"] .line-value').text()).toContain('bad, counts as ok')
    expect(stage3.find('[data-part="stage3-verdict"] .line-value').text()).toContain("(the judge's own outcome: issue)")
    expect(stage3.find('[data-part="stage3-judge"] [data-part="judge-version"]').text()).toBe('judge/1')
    expect(stage3.find('[data-part="stage3-judge"] .line-value').text()).toContain('· claude-sonnet-5-5')
    const people = view.findAll('[data-stage="person"] [data-person]')
    expect(people[0].text()).toContain('accept')
    expect(people[0].text()).toContain('b01')
    expect(people[1].classes()).toContain('earlier')
    expect(people[1].text()).toContain('does not apply')
  })

  it('says where no stage 2 report holds the reading and no person has judged the page', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail())
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-stage="2"]').text()).toBe('no stage 2 report holds this reading')
    expect(view.find('[data-stage="person"]').text()).toBe('no person has judged this page')
  })

  it('says only why a page the judge did not judge was left out, on its one line', async () => {
    const outside = 'not judged: passed stages 1 and 2, outside the sample'
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ check: aCheck({ judged: false, why_judged: outside, verdict: null }) }))
    const view = mountView()
    await flushPromises()
    const stage3 = view.find('[data-stage="3"]')
    expect(stage3.findAll('.line-label').map(label => label.text())).toEqual(['Why:'])
    expect(stage3.find('[data-part="stage3-why"] .line-value').text()).toBe(outside)
  })

  it('marks a void finding beneath its block, never hiding it, one labelled line per voice, a person\'s verdict the last (178.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aJudgedPage())
    const view = mountView()
    await flushPromises()
    await view.findAll('.mode button').find(button => button.text() === 'readable')!.trigger('click')
    const block = view.find('[data-block="b01"]')
    const finding = block.find('[data-finding="0"]')
    expect(finding.classes()).toContain('void')
    // the judge's finding, the code's ruling with its rule in the hover, the judge's evidence on a line of its own and
    // beneath it, then a person's verdict on the block: four voices, each its own labelled line, in this order
    const voices = block.findAll('.block-findings [data-voice]')
    expect(voices.map(voice => voice.attributes('data-voice'))).toEqual(['judge', 'code', 'evidence', 'person'])
    expect(voices.map(voice => voice.find('.part-label').text()))
      .toEqual(["The judge's finding:", "The code's ruling:", "The judge's evidence:", "A person's verdict:"])
    expect(finding.find('[data-part="void"]').text()).toBe("void: the judge's evidence names no difference")
    // the rule in the library's card, no browser tooltip (203.a)
    expect(finding.find('[data-part="void"]').attributes('title')).toBeUndefined()
    await finding.find('[data-voice="code"] .hover-card-host').trigger('mouseenter')
    expect(finding.find('[data-part="hover-card"] .card-title').text()).toBe("The code's ruling")
    expect(finding.find('[data-part="hover-card"] [data-row="rule"] .card-value').text())
      .toBe('the finding quotes no difference between print and reading: the strings it quotes stand in the block and in the PDF\'s text layer')
    expect(finding.find('[data-voice="evidence"]').text()).toBe("The judge's evidence:")
    expect(finding.find('.evidence').text()).toBe("'a' is 'a'")
    const person = block.find('[data-voice="person"]')
    expect([person.find('.person-standing').text(), person.find('.person-part').text()])
      .toEqual(['accepted', '· the judge quotes the same word twice'])
  })

  it('shows a person\'s correction first, the reading muted beneath it, and their assessment of the judge as manual (229.a, 188.a)', async () => {
    const page = aJudgedPage()
    const block = page.reading!.blocks[0]
    block.segments = null
    block.text = 'the crossing in 2000'
    const given = { given_by: 'maintainer', given_at: '2026-11-10T19:58:18+00:00' }
    block.people = [{ ...block.people[0], ...given, verdict: 'note', note: 'read from the chart', correction: 'the crossing around 2012',
      judge_assessment: 'right_for_a_wrong_reason', judge_assessment_text: "the judge's verdict is right, but its own evidence is not" }]
    // the correction that stands, as the API chooses it
    block.correction = { text: 'the crossing around 2012', rows: null, by_a_person: true, ...given }
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    const shown = view.find('[data-block="b01"]')
    // first the correction as the block's content, saying whose it is and that the search does not quote it yet
    const standing = shown.find('[data-part="standing-correction"]')
    expect(standing.find('.part-label').text()).toBe('Manual correction by a person')
    expect(standing.find('[data-part="correction-given"]').text()).toMatch(/^· not served yet · maintainer · /)
    expect(standing.find('[data-part="correction-content"]').text()).toBe('the crossing around 2012')
    expect(standing.find('[data-part="correction-content"]').classes()).toContain('person-correction')
    // then the reading as it stands, labelled and muted, before the findings
    expect(standing.find('[data-part="as-read-said"]').text()).toBe('The reading, as the reader wrote it:')
    expect(shown.find('[data-part="as-read"] .block-body').text()).toBe('the crossing in 2000')
    const order = shown.findAll('[data-part="standing-correction"], [data-part="as-read"], .block-findings').map(part => part.attributes('data-part') ?? 'findings')
    expect(order).toEqual(['standing-correction', 'as-read', 'findings'])
    // the correction is drawn once: beneath the findings the verdict, its note and the assessment, not the correction again
    expect(shown.findAll('.block-findings [data-voice]').map(voice => voice.attributes('data-voice')))
      .toEqual(['judge', 'code', 'evidence', 'person', 'assessment'])
    expect(shown.find('.block-findings [data-part="correction"]').exists()).toBe(false)
    const assessment = shown.find('[data-voice="assessment"]')
    expect(assessment.find('.part-label').text()).toBe("A person's assessment of the judge:")
    expect(assessment.find('.assessment').text()).toBe("the judge's verdict is right, but its own evidence is not")
    // the note stands once, beneath the verdict, never again in a tooltip of the assessment (203.a)
    expect(assessment.attributes('title')).toBeUndefined()
  })

  it('keeps an earlier correction beneath the findings, said as earlier, and a block without one as it was (229.a)', async () => {
    const page = aJudgedPage()
    const block = page.reading!.blocks[0]
    const earlier = { ...block.people[0], verdict: 'note', correction: 'the crossing about 2010', given_at: '2026-11-09T10:00:00+00:00' }
    const latest = { ...block.people[0], verdict: 'note', correction: 'the crossing around 2012', given_at: '2026-11-10T19:58:18+00:00' }
    block.people = [earlier, latest]
    block.correction = { text: latest.correction, rows: null, given_by: null, given_at: latest.given_at, by_a_person: true }
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    const shown = view.find('[data-block="b01"]')
    expect(shown.find('[data-part="correction-given"]').text()).toMatch(/^· not served yet · /)
    expect(shown.find('[data-part="correction-content"]').text()).toBe('the crossing around 2012')
    expect(shown.find('.block-findings [data-voice="correction"]').text()).toBe('An earlier manual correction by a person:')
    expect(shown.find('.block-findings [data-part="correction"]').text()).toBe('the crossing about 2010')
    // the same page without a correction: no line of one, the reading not muted
    block.people = []
    block.correction = null
    vi.mocked(getPage).mockResolvedValue(page)
    const plain = mountView()
    await flushPromises()
    expect(plain.find('[data-part="standing-correction"]').exists()).toBe(false)
    expect(plain.find('[data-part="as-read"]').exists()).toBe(false)
    expect(plain.find('[data-block="b01"] .block-content').classes()).not.toContain('as-read')
  })

  it('names the judge a person rated where the API knows it, so it reads apart from another judge\'s finding', async () => {
    const page = aJudgedPage()
    const block = page.reading!.blocks[0]
    block.people = [{ ...block.people[0], judge_assessment: 'false_alarm', judge_assessment_text: 'the judge reported an error that is not there',
      assessed: 'judge/1' }]
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    await view.findAll('.mode button').find(button => button.text() === 'readable')!.trigger('click')
    expect(view.find('[data-block="b01"] [data-voice="assessment"] .part-label').text()).toBe("A person's assessment of judge/1:")
  })
})
