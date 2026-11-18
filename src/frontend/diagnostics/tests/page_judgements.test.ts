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

  it('keeps the pipeline\'s judgements in the Reading History, the one that counts first, and a person\'s verdicts beneath', async () => {
    vi.mocked(getPage).mockResolvedValue(aJudgedPage())
    const view = mountView()
    await flushPromises()
    // a fold, folded on first load (decision 183), its title saying what it holds, the count set apart from the name
    expect(view.find('details.history').attributes('open')).toBeUndefined()
    expect(view.find('details.history > summary').text()).toBe('Reading History · 2 readings · shown: reading 2 · 2 judgements count')
    // the reading shown first, then the earlier one; a judge asked again and the prototypes are not the history's
    const lines = view.findAll('.history tr.judgement')
    expect(lines.map(line => line.attributes('data-judgement'))).toEqual(['2/0', '1/0'])
    const line = view.find('.history tr.judgement[data-judgement="2/0"]')
    expect(line.find('[data-part="counts"]').text()).toBe('counts')
    expect(line.text()).toContain('1 finding: void')
    expect(line.text()).toContain('issue')  // the judge's own outcome, in its column
    // folded, a reading sums its judgements up in one line, and says how many the Lab holds
    expect(view.find('[data-reading="r1"] [data-part="judgements"]').text()).toBe('1 judgement: judge/1 counts · 3 in the Lab')
    // a check carried over from before says where it comes from
    expect(view.find('[data-reading="r0"] .attempt-check').text()).toContain('an earlier check')
    // a person's verdict stands beneath the reading it judged, as its own line
    const person = view.find('[data-reading="r1"] .reading-people [data-person="0"]')
    // as a verdict reads beneath a block: one look wherever it stands (the operator, 11 Nov)
    expect(person.findAll('span').map(part => part.text())).toEqual(["A person's verdict:", 'accepted', '· the judge quotes the same word twice', '· b01'])
    expect(view.find('[data-reading="r0"] .reading-people').text()).toContain('does not apply to this one')
  })

  it('moves what was tried beside the pipeline into the Lab below, labelled and folded (150.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aJudgedPage())
    const view = mountView()
    await flushPromises()
    const lab = view.find('details.lab')
    expect(lab.attributes('open')).toBeUndefined()
    expect(lab.find('summary').text()).toBe('Lab · 3 judgements tried beside the pipeline, never served')
    const line = (name: string) => lab.find(`tr.judgement[data-judgement="${name}"]`)
    expect(lab.findAll('tr.judgement').map(row => row.attributes('data-judgement'))).toEqual(['2/1', '2/2', '2/3'])
    expect(line('2/1').find('[data-part="again"]').text()).toBe('asked again')
    expect(line('2/1').text()).toContain('reading 2, shown here')
    expect(line('2/3').find('[data-part="prototype"]').text()).toBe('prototype')
    expect(line('2/3').text()).toContain('judge/3')
    expect(line('2/3').text()).toContain('no findings')
    // a row says the severity of the findings that stand, and how many are void (line 1's check-along on finance p. 94)
    expect(line('2/2').text()).toContain('1 finding: void')
    // the history comes first on the page, the Lab after it
    const order = view.find('details.history').element.compareDocumentPosition(view.find('details.lab').element)
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('says a judgement\'s findings by their severity, so a minor finding under an ok verdict shows in its row', async () => {
    const minor = { ...VOID_FINDING, kind: 'other', severity: 'minor', void: false }
    const page = aJudgedPage()
    page.attempts![1].judgements = [
      aJudgement({ findings: [{ ...minor, severity: 'major' }, minor, VOID_FINDING] }),
      aJudgement({ version: 'judge/4', version_state: 'prototype', counts: false, verdict: 'ok', outcome: 'ok', judge_outcome: 'ok', findings: [minor] }),
    ]
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    expect(view.find('.history tr.judgement[data-judgement="2/0"] .judgement-findings').text()).toBe('3 findings: 1 major, 1 minor, 1 void')
    const lab = view.find('.lab tr.judgement[data-judgement="2/1"]')
    expect(lab.text()).toContain('ok → ok')
    expect(lab.text()).toContain('1 finding: minor')
  })

  it('keeps a reader prototype\'s reading out of the history and in the Lab, with its judgements, never served (210.a)', async () => {
    const page = aJudgedPage()
    const prototype = { ...page.attempts![1], reading_key: 'p2', number: 3, shown: false, cell: 'P2-WALK-SM', reader_version: 'page/2',
      prototype: true, purpose: 'a reader prototype (page/2), never served',
      judgements: [aJudgement({ version: 'judge/4', version_state: 'prototype', counts: false, verdict: 'ok', outcome: 'ok', judge_outcome: 'ok', findings: [] })] }
    const unjudged = { ...prototype, reading_key: 'p2b', number: 4, judgements: [] }
    page.attempts = [...page.attempts!, prototype, unjudged]
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    // the history holds the pipeline's two readings alone
    expect(view.find('details.history > summary').text()).toBe('Reading History · 2 readings · shown: reading 2 · 2 judgements count')
    expect(view.find('[data-reading="p2"]').exists()).toBe(false)
    // the Lab: the prototype's reading by its reader, its judge/4 judgement, and the reading no judge has judged
    const lab = view.find('details.lab')
    expect(lab.find('summary').text()).toBe('Lab · 2 readings and 4 judgements tried beside the pipeline, never served')
    const row = lab.find('tr.judgement[data-judgement="3/0"]')
    expect(row.find('[data-reader="page/2"]').text()).toBe('reading 3, page/2 (prototype), never served')
    expect(row.text()).toContain('judge/4')
    expect(lab.find('tr.lab-reading[data-reading="p2b"]').text()).toContain('no judge has judged this reading')
  })

  it('shows a judge\'s rules for the reader beneath its judgement in the Lab, read-only, never applied (202.a)', async () => {
    const page = aJudgedPage()
    page.attempts![1].judgements[2] = aJudgement({ version: 'judge/4', version_state: 'prototype', counts: false, reader_rules: [
      { kind: 'format_rule', block: 'b03', rule: 'Give each account header a colspan of two.', block_class: null, attribute: null, value: null },
      { kind: 'attribute', block: 'b09', rule: 'Invent no bullet marker.', block_class: 'list_item', attribute: 'marker', value: 'none' },
    ] })
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    const lab = view.find('details.lab')
    // right beneath the judgement that proposed them, and under no other
    const rows = lab.findAll('tbody tr').map(row => row.attributes('data-judgement') ?? row.attributes('data-rules'))
    expect(rows).toEqual(['2/1', '2/2', '2/2', '2/3'])
    const rules = lab.find('tr.lab-rules [data-part="reader-rules"]')
    expect(rules.find('.part-label').text()).toBe('Proposals for the reader, never applied:')
    // its parts as spans of one flex line, parted by the line's gap
    expect(rules.findAll('.rule').map(rule => rule.findAll('span').map(part => part.text()))).toEqual([
      ['format rule', 'b03', 'Give each account header a colspan of two.'],
      ['attribute', 'b09', 'class list_item · attribute marker = none', 'Invent no bullet marker.'],
    ])
  })

  it('shows no Lab where nothing was tried beside the pipeline', async () => {
    const page = aJudgedPage()
    page.attempts = page.attempts!.map(attempt => ({ ...attempt, judgements: attempt.judgements.filter(judgement => judgement.counts) }))
    vi.mocked(getPage).mockResolvedValue(page)
    const view = mountView()
    await flushPromises()
    expect(view.find('.lab').exists()).toBe(false)
    expect(view.find('[data-reading="r1"] [data-part="judgements"]').text()).toBe('1 judgement: judge/1 counts')
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
