import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { getPage, getRecall, getVerdictForm, giveVerdict, previewTable, promoteReading, proposeCorrection } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import VerdictPanel from '@/components/VerdictPanel.vue'
import PageView from '@/views/PageView.vue'
import { useToastStore } from '@/stores/toast_store'
import { canSend, correctionOffered, needsNote, payloadOf, prefillOf, type VerdictDraft } from '@/verdict_rules'
import type { PersonVerdict } from '@/types/api/page_types'
import type { Proposal, VerdictForm } from '@/types/api/verdict_types'
import { aBlock, aFormReading, aPageDetail, KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getRecall: vi.fn(),
  getVerdictForm: vi.fn(),
  giveVerdict: vi.fn(),
  previewTable: vi.fn(),
  promoteReading: vi.fn(),
  proposeCorrection: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented over a free paper: the panel's lists as the core words them, one export idle after three, a proposal possible
function aForm(overrides: Partial<VerdictForm> = {}): VerdictForm {
  return {
    enabled: true,
    why_not: null,
    verdicts: [{ value: 'accept', label: 'accept' }, { value: 'reject', label: 'reject' }, { value: 'note', label: 'note' }],
    reasons: [{ value: 'reading_wrong', label: 'the reading does not say what the page prints' },
      { value: 'other', label: 'another reason, said in the note' }],
    assessments: [{ value: 'right', label: 'the judge was right' }, { value: 'false_alarm', label: 'a false alarm' }],
    exports: [{ knowledge_base: 'free', running: false, pending: false, finished: 3, last_error: null, last_finished_at: null, waiting: [] }],
    propose: { available: true, why_not: null },
    ...overrides,
  }
}

const GRID = '<table><tr><th>p</th><td>0.6</td></tr></table>'
const CELLS = [[{ segments: [{ kind: 'text' as const, content: 'p' }], header: true, rowspan: 1, colspan: 1 },
  { segments: [{ kind: 'text' as const, content: '0.6' }], header: false, rowspan: 1, colspan: 1 }]]
const FINDING = { kind: 'wrong_value', block: 'b02', severity: 'major', evidence: '0.6 read as 0.9', void: false }
// invented: a proposal that reads 0.65 where the reading wrote 0.6, and the verdict the core's rules fill from it (F1.a)
const A_CORRECTION = '<table><tr><th>p</th><td>0.65</td></tr></table>'
const A_PROPOSAL: Proposal = { state: 'proposed', agrees_with_judge: 'partly', agrees_said: 'partly agrees with the judge',
  image_shows: 'the table prints 0.65', correction: A_CORRECTION, flags: [], why: null, cost_usd: 0.0312, version: 'correction/2',
  model: 'an-invented-model', diff: [],
  prefill: { verdict: 'reject', reason: 'reading_wrong', block: 'b02', judge_assessment: 'right', note: 'the table prints 0.65',
    correction: A_CORRECTION, said: 'filled by an invented model; nothing is recorded until a person records it' } }

function aPersonVerdict(overrides: Partial<PersonVerdict>): PersonVerdict {
  return { reading_key: 'r1', applies: true, block: 'b02', verdict: 'reject', reason: 'reading_wrong', reason_text: 'the reading does not say what the page prints',
    note: null, given_by: 'maintainer', given_at: '2026-11-10T22:03:55+00:00', by_a_person: true, ...overrides }
}

function aDraft(overrides: Partial<VerdictDraft> = {}): VerdictDraft {
  return { verdict: 'reject', reason: 'reading_wrong', block: 'b02', note: '', judgeAssessment: '', correction: '', ...overrides }
}

// a page of two blocks, a paragraph and a table, the table the one a finding names
function aPage(findings = true) {
  return aPageDetail({
    focus: 'b02',
    findings_at: findings ? [{ block: 'b02', said: 'stands', severity: 'major' }] : [],
    reading: { front: {}, errors: [], warnings: [], error_places: [], blocks: [
      aBlock({ id: 'b01', body: 'The growth rate of the bankroll.' }),
      aBlock({ id: 'b02', block_class: 'table', body: GRID, segments: [], rows: CELLS, findings: findings ? [FINDING] : [] }),
    ] },
  })
}

describe('the verdict\'s rules (213.b, 224.b)', () => {
  it('asks a note where the reason is said in it, and sends only a verdict with a reason', () => {
    expect(needsNote('other')).toBe(true)
    expect(needsNote('reading_wrong')).toBe(false)
    expect(canSend(aDraft())).toBe(true)
    expect(canSend(aDraft({ verdict: '' }))).toBe(false)
    expect(canSend(aDraft({ reason: '' }))).toBe(false)
    expect(canSend(aDraft({ reason: 'other', note: '  ' }))).toBe(false)
    expect(canSend(aDraft({ reason: 'other', note: 'the lines cross about 2012' }))).toBe(true)
  })

  it('offers a correction only for one block, started from the correction that stands for it, else the block\'s body', () => {
    expect(correctionOffered('')).toBe(false)
    expect(correctionOffered('b02')).toBe(true)
    expect(prefillOf(undefined)).toBe('')
    expect(prefillOf(aBlock({ body: GRID }))).toBe(GRID)
    // the API says which correction stands (229.a); a person's verdicts on the block do not decide it here
    const people = [aPersonVerdict({ correction: '<table><tr><td>first</td></tr></table>' })]
    const standing = { text: '<table><tr><td>latest</td></tr></table>', rows: null, given_by: 'maintainer', given_at: '2026-11-12T18:10:20+00:00', by_a_person: true }
    expect(prefillOf(aBlock({ body: GRID, people, correction: standing }))).toBe('<table><tr><td>latest</td></tr></table>')
  })

  it('sends a correction only with a block and only where it was changed; empty fields as none', () => {
    const sent = (draft: VerdictDraft) => payloadOf(draft, GRID, 'free', KELLY, 4)
    expect(sent(aDraft({ correction: GRID }))).toEqual({ knowledge_base: 'free', work: KELLY, pdf_page: 4, verdict: 'reject',
      reason: 'reading_wrong', block: 'b02', note: null, correction: null, judge_assessment: null, answers_judgement: null })
    // the judgement the page showed the person goes with the verdict, which answers it (#17)
    expect(payloadOf(aDraft({ correction: GRID }), GRID, 'free', KELLY, 4, 'an-invented-judgement-key').answers_judgement)
      .toBe('an-invented-judgement-key')
    const changed = '<table><tr><th>p</th><td>0.65</td></tr></table>'
    expect(sent(aDraft({ correction: changed, note: ' read 0.65 ', judgeAssessment: 'right' }))).toMatchObject({
      correction: changed, note: 'read 0.65', judge_assessment: 'right' })
    // the page as a whole: no block, so no correction, whatever the field still holds
    expect(sent(aDraft({ block: '', correction: changed }))).toMatchObject({ block: null, correction: null })
    expect(sent(aDraft({ correction: '   ' })).correction).toBeNull()
  })
})

describe('the verdict panel (213.b, V1.a)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(previewTable).mockReset().mockResolvedValue({ rows: CELLS })
    vi.mocked(giveVerdict).mockReset()
    vi.mocked(getVerdictForm).mockReset()
    vi.mocked(proposeCorrection).mockReset()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountPanel(target = 'b02', page = aPage(), form = aForm()) {
    return mount(VerdictPanel, { props: { page, knowledgeBase: 'free', work: KELLY, form, target }, attachTo: document.body })
  }

  it('opens on the block it is given, its text now above the correction started from it, previewed as the table it would be', async () => {
    const panel = mountPanel()
    expect((panel.find('[data-part="block"]').element as HTMLSelectElement).value).toBe('b02')
    expect(panel.find('[data-part="current-text"]').text()).toBe(GRID)
    expect((panel.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe(GRID)
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(previewTable).toHaveBeenCalledWith(GRID)
    expect(panel.findAll('[data-part="correction-preview"] th, [data-part="correction-preview"] td').map(cell => cell.text())).toEqual(['p', '0.6'])
  })

  it('opens on the page as a whole with no correction, and turns to a block chosen in it', async () => {
    const panel = mountPanel('')
    expect(panel.find('[data-part="correction-field"]').exists()).toBe(false)
    await panel.find('[data-part="block"]').setValue('b01')
    expect((panel.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe('The growth rate of the bankroll.')
    expect(panel.emitted('target')!.at(-1)).toEqual(['b01'])
    await vi.advanceTimersByTimeAsync(400)
    expect(previewTable).not.toHaveBeenCalled()
  })

  it('asks the judge\'s assessment where the block, or for the whole page the page, has a finding', () => {
    expect(mountPanel('b02').find('[data-part="assessment"]').exists()).toBe(true)
    expect(mountPanel('b01').find('[data-part="assessment"]').exists()).toBe(false)
    expect(mountPanel('').find('[data-part="assessment"]').exists()).toBe(true)
    expect(mountPanel('', aPage(false)).find('[data-part="assessment"]').exists()).toBe(false)
  })

  it('asks before a change is lost, turning to another block or closing, and turns or closes at once where nothing changed', async () => {
    const panel = mountPanel('b01')
    const exposed = panel.vm as unknown as { retarget: (block: string) => void }
    // nothing changed: it turns at once
    exposed.retarget('b02')
    await flushPromises()
    expect((panel.find('[data-part="block"]').element as HTMLSelectElement).value).toBe('b02')
    // a note written: it asks, keeps on Keep, turns on Turn with the note gone
    await panel.find('[data-part="note"]').setValue('read 0.65 from the image')
    exposed.retarget('b01')
    await flushPromises()
    expect(panel.find('[data-part="panel-ask"]').text()).toContain('Turn to b01 and lose what you changed?')
    await panel.find('[data-part="keep"]').trigger('click')
    expect((panel.find('[data-part="block"]').element as HTMLSelectElement).value).toBe('b02')
    exposed.retarget('b01')
    await flushPromises()
    await panel.find('[data-part="discard"]').trigger('click')
    expect((panel.find('[data-part="block"]').element as HTMLSelectElement).value).toBe('b01')
    expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('')
    // Esc with a change asks; Close then closes
    await panel.find('[data-part="note"]').setValue('again')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(panel.emitted('close')).toBeUndefined()
    expect(panel.find('[data-part="panel-ask"]').text()).toContain('Close and lose what you changed?')
    await panel.find('[data-part="discard"]').trigger('click')
    expect(panel.emitted('close')).toHaveLength(1)
  })

  it('closes on Esc at once where nothing changed', async () => {
    const panel = mountPanel('b02')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(panel.emitted('close')).toHaveLength(1)
  })

  it('holds the send until a verdict and a reason are chosen, and a note where the reason needs one', async () => {
    const panel = mountPanel()
    const send = () => panel.find('[data-part="send"]').attributes('disabled')
    expect(send()).toBeDefined()
    await panel.find('[data-verdict="reject"]').trigger('click')
    await panel.find('[data-part="reason"]').setValue('other')
    expect(panel.find('[data-part="note-needed"]').exists()).toBe(true)
    expect(send()).toBeDefined()
    await panel.find('[data-part="note"]').setValue('the lines cross about 2012')
    expect(send()).toBeUndefined()
  })

  it('hands its page what was recorded at once, asking nothing, so the page can close it (21 Nov)', async () => {
    const exported = { knowledge_base: 'free' as const, running: true, pending: false, finished: 3, last_error: null, last_finished_at: null, waiting: [] }
    vi.mocked(giveVerdict).mockResolvedValue({ verdict_id: 41, reading_key: 'k', route_before: 'vision reading', export: exported })
    const panel = mountPanel()
    await panel.find('[data-verdict="reject"]').trigger('click')
    await panel.find('[data-part="reason"]').setValue('reading_wrong')
    const changed = '<table><tr><th>p</th><td>0.65</td></tr></table>'
    await panel.find('[data-part="correction-field"]').setValue(changed)
    await panel.find('[data-part="send"]').trigger('click')
    await flushPromises()
    expect(giveVerdict).toHaveBeenCalledWith({ knowledge_base: 'free', work: KELLY, pdf_page: 4, verdict: 'reject', reason: 'reading_wrong',
      block: 'b02', note: null, correction: changed, judge_assessment: null, answers_judgement: null })
    expect(panel.emitted('recorded')).toEqual([[{ block: 'b02', verdict: 'reject', export: exported }]])
    // nothing lost, so nothing asked; the panel's own line says nothing, the page's toast does
    expect(panel.find('[data-part="panel-ask"]').exists()).toBe(false)
    expect(panel.find('[data-part="verdict-said"]').exists()).toBe(false)
    expect(getVerdictForm).not.toHaveBeenCalled()
  })

  it('says what the core refused, in its words', async () => {
    vi.mocked(giveVerdict).mockRejectedValue(new Error('the reason other needs a note'))
    const panel = mountPanel()
    await panel.find('[data-verdict="note"]').trigger('click')
    await panel.find('[data-part="reason"]').setValue('reading_wrong')
    await panel.find('[data-part="send"]').trigger('click')
    await flushPromises()
    const said = panel.find('[data-part="verdict-said"]')
    expect(said.text()).toBe('the reason other needs a note')
    expect(said.classes()).toContain('failed')
    expect(panel.emitted('recorded')).toBeUndefined()
  })

  it('promotes a Lab reading in its own mode: one the core promotes, a reason of its list, a note where the reason asks one (#18)', async () => {
    const exported = { knowledge_base: 'free' as const, running: true, pending: false, finished: 3, last_error: null, last_finished_at: null, waiting: [] }
    vi.mocked(promoteReading).mockResolvedValue({ reading_key: 'k3', export: exported })
    const form = aForm({ promote_reasons: [{ value: 'better', label: 'it reads the page better', short: 'better' },
      { value: 'other', label: 'another reason, said in the note', short: 'other' }] })
    const lab = [aFormReading({ key: 'k3', shown: false, model: 'an-invented-reader', version: 'page/1', result_said: 'no judge', promotable: true })]
    const panel = mount(VerdictPanel, { props: { page: aPage(), knowledgeBase: 'free', work: KELLY, form, target: '', mode: 'promote', labReadings: lab },
      attachTo: document.body })
    // the promotion's own body, not a verdict's
    expect(panel.find('[data-part="promote-body"]').exists()).toBe(true)
    expect(panel.find('[data-part="send"]').exists()).toBe(false)
    expect(panel.findAll('[data-part="promote-reading"] option').map(option => option.text()))
      .toEqual(['choose a Lab reading', 'an-invented-reader · page/1 · no judge'])
    expect(panel.findAll('[data-part="promote-reason"] option').map(option => option.text()))
      .toEqual(['choose a reason', 'better — it reads the page better', 'other — another reason, said in the note'])
    const held = () => panel.find('[data-part="send-promotion"]').attributes('disabled')
    expect(held()).toBeDefined()
    await panel.find('[data-part="promote-reading"]').setValue('k3')
    await panel.find('[data-part="promote-reason"]').setValue('other')
    expect(panel.find('[data-part="promote-note-needed"]').exists()).toBe(true)
    expect(held()).toBeDefined()
    await panel.find('[data-part="promote-note"]').setValue('  its tables hold  ')
    expect(held()).toBeUndefined()
    await panel.find('[data-part="send-promotion"]').trigger('click')
    await flushPromises()
    expect(promoteReading).toHaveBeenCalledWith({ knowledge_base: 'free', work: KELLY, pdf_page: 4, reading_key: 'k3', reason: 'other',
      note: 'its tables hold' })
    expect(panel.emitted('recorded')).toEqual([[{ block: '', verdict: 'promote', export: exported }]])
  })

  it('fills the whole verdict with AI, every field still the person\'s, beside what the image shows and the words changed; records nothing', async () => {
    // invented: a proposal that reads 0.65 where the reading wrote 0.6, and the verdict the core's rules fill from it (F1.a)
    const correction = '<table><tr><th>p</th><td>0.65</td></tr></table>'
    const proposal: Proposal = { state: 'proposed', agrees_with_judge: 'partly', agrees_said: 'partly agrees with the judge',
      image_shows: 'the table prints 0.65', correction, flags: ['large change', 'the image shows no such error'], why: null,
      cost_usd: 0.0123, version: 'correction/2', model: 'an-invented-model',
      diff: [{ kind: 'same', text: '<table><tr><th>p</th><td>' }, { kind: 'removed', text: '0.6' }, { kind: 'added', text: '0.65' },
        { kind: 'same', text: '</td></tr></table>' }],
      prefill: { verdict: 'reject', reason: 'reading_wrong', block: 'b02', judge_assessment: 'right', note: 'the table prints 0.65',
        correction, said: 'filled by an invented model; nothing is recorded until a person records it' } }
    vi.mocked(proposeCorrection).mockResolvedValue(proposal)
    const panel = mountPanel()
    expect(panel.find('[data-part="propose"]').text()).toBe('✦ fill with AI')
    await panel.find('[data-part="propose"]').trigger('click')
    await flushPromises()
    expect(proposeCorrection).toHaveBeenCalledWith({ knowledge_base: 'free', work: KELLY, pdf_page: 4, block: 'b02' })
    // every field filled, each still to be changed
    expect(panel.find('[data-verdict="reject"]').attributes('aria-pressed')).toBe('true')
    expect((panel.find('[data-part="reason"]').element as HTMLSelectElement).value).toBe('reading_wrong')
    expect((panel.find('[data-part="assessment"]').element as HTMLSelectElement).value).toBe('right')
    expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('the table prints 0.65')
    expect((panel.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe(correction)
    await panel.find('[data-part="note"]').setValue('read 0.65 in the second column')
    expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('read 0.65 in the second column')
    // beside it: what the image shows, the judge, the flags, the words changed, the cost, and that nothing is recorded yet
    expect(panel.find('[data-part="image-shows"]').text()).toBe('the image shows: the table prints 0.65')
    expect(panel.find('[data-part="agrees"]').text()).toBe('partly agrees with the judge')
    expect(panel.find('[data-flag="the image shows no such error"]').classes()).toContain('weigh')
    expect(panel.find('[data-flag="large change"]').classes()).not.toContain('weigh')
    expect(panel.findAll('[data-part="proposal-diff"] [data-diff]').map(part => `${part.attributes('data-diff')}:${part.text()}`)).toEqual([
      'same:<table><tr><th>p</th><td>', 'removed:0.6', 'added:0.65', 'same:</td></tr></table>'])
    expect(panel.find('[data-part="proposal-cost"]').text()).toBe('0.012 USD')
    expect(panel.find('[data-part="filled-said"]').text()).toBe('filled by an invented model; nothing is recorded until a person records it')
    expect(panel.find('[data-part="use-proposal"]').exists()).toBe(false)
    expect(giveVerdict).not.toHaveBeenCalled()
  })

  it('turns and counts while the model is asked, the button held and the panel busy, and fills once it came (21 Nov)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    let answer: (proposal: Proposal) => void = () => undefined
    vi.mocked(proposeCorrection).mockReturnValue(new Promise(resolve => { answer = resolve }))
    const panel = mountPanel()
    const button = () => panel.find('[data-part="propose"]')
    await button().trigger('click')
    expect(button().attributes('disabled')).toBeDefined()
    expect(button().find('[data-part="running"] .running-mark').exists()).toBe(true)
    expect(button().find('[data-part="running-words"]').text()).toBe('asking the model … 0 s')
    expect(panel.find('[data-part="verdict-panel"]').attributes('aria-busy')).toBe('true')
    await vi.advanceTimersByTimeAsync(12_000)
    expect(button().find('[data-part="running-words"]').text()).toBe('asking the model … 12 s')
    answer(A_PROPOSAL)
    await flushPromises()
    expect(button().text()).toBe('✦ fill with AI')
    expect(panel.find('[data-part="verdict-panel"]').attributes('aria-busy')).toBe('false')
    expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('the table prints 0.65')
    expect(proposeCorrection).toHaveBeenCalledTimes(1)
  })

  it('asks before the proposal replaces what the person typed while it was asked: Keep mine keeps it, Fill fills', async () => {
    for (const choice of ['keep-mine', 'fill-anyway']) {
      let answer: (proposal: Proposal) => void = () => undefined
      vi.mocked(proposeCorrection).mockReturnValueOnce(new Promise(resolve => { answer = resolve }))
      setActivePinia(createPinia())
      const panel = mountPanel()
      await panel.find('[data-part="propose"]').trigger('click')
      await panel.find('[data-part="note"]').setValue('my own note')
      answer(A_PROPOSAL)
      await flushPromises()
      expect(panel.find('[data-part="fill-ask"]').text()).toContain('The proposal came: fill the fields and replace what you typed?')
      expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('my own note')
      await panel.find(`[data-part="${choice}"]`).trigger('click')
      expect(panel.find('[data-part="fill-ask"]').exists()).toBe(false)
      expect((panel.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe(
        choice === 'keep-mine' ? 'my own note' : 'the table prints 0.65')
    }
  })

  it('keeps the model\'s call when the panel closes while it runs, and the panel opened again waits on it, asking nothing again', async () => {
    let answer: (proposal: Proposal) => void = () => undefined
    vi.mocked(proposeCorrection).mockReturnValue(new Promise(resolve => { answer = resolve }))
    const first = mountPanel()
    await first.find('[data-part="propose"]').trigger('click')
    first.unmount()
    const again = mountPanel()
    await flushPromises()
    expect(again.find('[data-part="propose"] [data-part="running"]').exists()).toBe(true)
    await again.find('[data-part="propose"]').trigger('click')
    answer(A_PROPOSAL)
    await flushPromises()
    expect(proposeCorrection).toHaveBeenCalledTimes(1)
    expect((again.find('[data-part="note"]').element as HTMLTextAreaElement).value).toBe('the table prints 0.65')
  })

  it('keeps the form as it was and says why where the model gave no proposal', async () => {
    vi.mocked(proposeCorrection).mockResolvedValueOnce({ state: 'no proposal', why: 'the answer was not a proposal (stop: max_tokens)',
      agrees_with_judge: null, agrees_said: null, image_shows: null, correction: null, flags: [], diff: [], cost_usd: 0.01,
      version: 'correction/2', model: 'an-invented-model', prefill: null })
    const panel = mountPanel()
    await panel.find('[data-part="propose"]').trigger('click')
    await flushPromises()
    expect(panel.find('[data-part="propose"]').attributes('disabled')).toBeDefined()
    expect(panel.find('[data-part="propose-why-not"]').text()).toBe('no proposal: the answer was not a proposal (stop: max_tokens)')
    expect((panel.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe(GRID)
    expect(panel.find('[data-verdict="reject"]').attributes('aria-pressed')).not.toBe('true')
  })

  it('says why no proposal can be made: from the form before any ask, or the core\'s reason after one, the button held', async () => {
    const closed = mountPanel('b02', aPage(), aForm({ propose: { available: false, why_not: 'no active correction version' } }))
    expect(closed.find('[data-part="propose"]').attributes('disabled')).toBeDefined()
    expect(closed.find('[data-part="propose-why-not"]').text()).toBe('no active correction version')
    vi.mocked(proposeCorrection).mockRejectedValue(new ApiError(409, 'held back by the provenance list (send: false)'))
    const panel = mountPanel()
    await panel.find('[data-part="propose"]').trigger('click')
    await flushPromises()
    expect(panel.find('[data-part="propose"]').attributes('disabled')).toBeDefined()
    expect(panel.find('[data-part="propose-why-not"]').text()).toBe('held back by the provenance list (send: false)')
    expect(proposeCorrection).toHaveBeenCalledTimes(1)
  })
})

describe('the page view opens the verdict panel only where the app takes one (213.b, 223.a, V1.a)', () => {
  beforeEach(async () => {
    vi.mocked(getPage).mockReset().mockResolvedValue(aPage())
    vi.mocked(getRecall).mockReset().mockRejectedValue(new Error('not asked here'))
    vi.mocked(getVerdictForm).mockReset()
    localStorage.clear()
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 } })
  })

  function mountView() {
    return mount(PageView, { props: { kb: 'free', work: KELLY, page: 4 }, global: { plugins: [createPinia(), router] }, attachTo: document.body })
  }

  it('shows no control when the app was started without --allow-verdicts', async () => {
    vi.mocked(getVerdictForm).mockResolvedValue(aForm({ enabled: false, why_not: 'read-only', exports: [] }))
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="give-verdict"]').exists()).toBe(false)
    expect(view.find('[data-part="verdict-mark"]').exists()).toBe(false)
  })

  it('opens the panel on the whole page from the head, on a block from its ⚖, the block outlined; none on a recalled judgement', async () => {
    vi.mocked(getVerdictForm).mockResolvedValue(aForm())
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="verdict-panel"]').exists()).toBe(false)
    // the ⚖ always shown on the block with a finding, on the pointer and focus on the other
    expect(view.find('[data-block="b02"] [data-part="verdict-mark"]').classes()).toContain('always')
    expect(view.find('[data-block="b01"] [data-part="verdict-mark"]').classes()).not.toContain('always')
    await view.find('[data-part="give-verdict"]').trigger('click')
    expect((view.find('[data-part="verdict-panel"] [data-part="block"]').element as HTMLSelectElement).value).toBe('')
    await view.find('[data-part="verdict-panel"] [data-part="close"]').trigger('click')
    expect(view.find('[data-part="verdict-panel"]').exists()).toBe(false)
    await view.find('[data-block="b02"] [data-part="verdict-mark"]').trigger('click')
    await flushPromises()
    expect((view.find('[data-part="verdict-panel"] [data-part="block"]').element as HTMLSelectElement).value).toBe('b02')
    expect(view.find('[data-block="b02"]').classes()).toContain('verdict-about')
    // another block's ⚖ while it is open turns it there, nothing changed in it
    await view.find('[data-block="b01"] [data-part="verdict-mark"]').trigger('click')
    await flushPromises()
    expect((view.find('[data-part="verdict-panel"] [data-part="block"]').element as HTMLSelectElement).value).toBe('b01')
    expect(view.find('[data-block="b01"]').classes()).toContain('verdict-about')
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 }, query: { judgement: 'k:judge/3:0' } })
    await flushPromises()
    expect(view.find('[data-part="give-verdict"]').exists()).toBe(false)
    expect(view.find('[data-part="verdict-panel"]').exists()).toBe(false)
  })

  it('closes the panel on a recorded verdict, says it in a toast that follows the export, and loads the page again after it', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const running = { knowledge_base: 'free' as const, running: true, pending: false, finished: 3, last_error: null, last_finished_at: null, waiting: [] }
      vi.mocked(getVerdictForm)
        .mockResolvedValueOnce(aForm())
        .mockResolvedValueOnce(aForm({ exports: [running] }))
        .mockResolvedValue(aForm({ exports: [{ ...running, running: false, finished: 4 }] }))
      vi.mocked(giveVerdict).mockResolvedValue({ verdict_id: 41, reading_key: 'k', route_before: 'vision reading', export: running })
      const view = mountView()
      await flushPromises()
      await view.find('[data-block="b02"] [data-part="verdict-mark"]').trigger('click')
      const panel = view.find('[data-part="verdict-panel"]')
      await panel.find('[data-verdict="accept"]').trigger('click')
      await panel.find('[data-part="reason"]').setValue('reading_wrong')
      await panel.find('[data-part="send"]').trigger('click')
      await flushPromises()
      // the panel gone at once, nothing asked; the toast says what was recorded and that its export runs
      expect(view.find('[data-part="verdict-panel"]').exists()).toBe(false)
      const toasts = useToastStore()
      // how long the export may take, in words, and where to follow it (E1.a); no export of the fixture's base finished to tell
      expect(toasts.toasts.map(toast => [toast.text, toast.detail])).toEqual([['Verdict recorded · b02 · accept — the index rebuild may take '
        + 'a few minutes', 'the free export runs in the background: follow it at the hourglass in the header']])
      toasts.hold(toasts.toasts[0].id)  // a person points at it: it stands while the export runs
      // the page asked again at once, so the verdict stands in its Check row as waiting for the export
      const asked = vi.mocked(getPage).mock.calls.length
      expect(asked).toBe(2)
      await vi.advanceTimersByTimeAsync(2000)
      expect(toasts.toasts[0].detail).toBe('the free export runs in the background: follow it at the hourglass in the header')
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(toasts.toasts[0].detail).toBe('served from now on')
      // the page's own data asked again, so its verdict, the person's mark and its route show without F5
      expect(vi.mocked(getPage).mock.calls.length).toBe(asked + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows a verdict recorded and not yet exported in its Check row, waiting, and loads the page again when an export ends', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ waiting: [{ knowledge_base: 'free', source_id: KELLY, pdf_page: 4, block: 'b05',
      verdict: 'accept', given_at: '2026-11-21T17:02:00+00:00', by_a_person: true }] }))
    vi.mocked(getVerdictForm).mockResolvedValue(aForm())
    const view = mountView()
    await flushPromises()
    const waiting = view.find('[data-label="Check"] [data-part="waiting-verdict"]')
    expect(waiting.text()).toContain('your verdict: accept · b05 · recorded')
    expect(waiting.text()).toContain('served once the export is done')
    expect(waiting.find('[data-icon="hourglass"]').exists()).toBe(true)
    // an export of the base ends, this view's or another's: the page's own data asked again
    const asked = vi.mocked(getPage).mock.calls.length
    const { useVerdictStore } = await import('@/stores/verdict_store')
    const store = useVerdictStore()
    store.form = aForm({ exports: [{ ...store.form!.exports[0], finished: 4 }] })
    await flushPromises()
    expect(vi.mocked(getPage).mock.calls.length).toBe(asked + 1)
  })

  it('keeps the panel open with the core\'s words where recording failed, and says nothing in a toast', async () => {
    vi.mocked(getVerdictForm).mockResolvedValue(aForm())
    vi.mocked(giveVerdict).mockRejectedValue(new Error('the reason other needs a note'))
    const view = mountView()
    await flushPromises()
    await view.find('[data-block="b02"] [data-part="verdict-mark"]').trigger('click')
    await view.find('[data-part="verdict-panel"] [data-verdict="note"]').trigger('click')
    await view.find('[data-part="verdict-panel"] [data-part="reason"]').setValue('reading_wrong')
    await view.find('[data-part="verdict-panel"] [data-part="send"]').trigger('click')
    await flushPromises()
    expect(view.find('[data-part="verdict-panel"] [data-part="verdict-said"]').text()).toBe('the reason other needs a note')
    expect(useToastStore().toasts).toEqual([])
  })
})
