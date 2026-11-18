import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { getPage, getRecall, getVerdictForm, giveVerdict, previewTable } from '@/api/api_client'
import { router } from '@/router'
import VerdictDialog from '@/components/VerdictDialog.vue'
import PageView from '@/views/PageView.vue'
import { canSend, correctionOffered, needsNote, payloadOf, prefillOf, type VerdictDraft } from '@/verdict_rules'
import type { PersonVerdict } from '@/types/api/page_types'
import type { VerdictForm } from '@/types/api/verdict_types'
import { aBlock, aPageDetail, KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getRecall: vi.fn(),
  getVerdictForm: vi.fn(),
  giveVerdict: vi.fn(),
  previewTable: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented over a free paper: the dialog's lists as the core words them, one export idle after three
function aForm(overrides: Partial<VerdictForm> = {}): VerdictForm {
  return {
    enabled: true,
    why_not: null,
    verdicts: [{ value: 'accept', label: 'accept' }, { value: 'reject', label: 'reject' }, { value: 'note', label: 'note' }],
    reasons: [{ value: 'reading_wrong', label: 'the reading does not say what the page prints' },
      { value: 'other', label: 'another reason, said in the note' }],
    assessments: [{ value: 'right', label: 'the judge was right' }, { value: 'false_alarm', label: 'a false alarm' }],
    exports: [{ knowledge_base: 'free', running: false, pending: false, finished: 3, last_error: null, last_finished_at: null }],
    ...overrides,
  }
}

const GRID = '<table><tr><th>p</th><td>0.6</td></tr></table>'
const CELLS = [[{ segments: [{ kind: 'text' as const, content: 'p' }], header: true, rowspan: 1, colspan: 1 },
  { segments: [{ kind: 'text' as const, content: '0.6' }], header: false, rowspan: 1, colspan: 1 }]]

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
      aBlock({ id: 'b02', block_class: 'table', body: GRID, segments: [], rows: CELLS }),
    ] },
  })
}

describe('the verdict dialog\'s rules (213.b, 224.b)', () => {
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
      reason: 'reading_wrong', block: 'b02', note: null, correction: null, judge_assessment: null })
    const changed = '<table><tr><th>p</th><td>0.65</td></tr></table>'
    expect(sent(aDraft({ correction: changed, note: ' read 0.65 ', judgeAssessment: 'right' }))).toMatchObject({
      correction: changed, note: 'read 0.65', judge_assessment: 'right' })
    // the page as a whole: no block, so no correction, whatever the field still holds
    expect(sent(aDraft({ block: '', correction: changed }))).toMatchObject({ block: null, correction: null })
    expect(sent(aDraft({ correction: '   ' })).correction).toBeNull()
  })
})

describe('the verdict dialog (213.b)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(previewTable).mockReset().mockResolvedValue({ rows: CELLS })
    vi.mocked(giveVerdict).mockReset()
    vi.mocked(getVerdictForm).mockReset()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountDialog(page = aPage()) {
    return mount(VerdictDialog, { props: { page, knowledgeBase: 'free', work: KELLY, form: aForm() } })
  }

  it('starts on the block the finding names, its correction prefilled and previewed as the table it would be', async () => {
    const dialog = mountDialog()
    expect((dialog.find('[data-part="block"]').element as HTMLSelectElement).value).toBe('b02')
    expect((dialog.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe(GRID)
    expect(dialog.find('[data-part="correction-preview"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(previewTable).toHaveBeenCalledWith(GRID)
    expect(dialog.findAll('[data-part="correction-preview"] th, [data-part="correction-preview"] td').map(cell => cell.text())).toEqual(['p', '0.6'])
  })

  it('offers no correction for the page as a whole and previews no text that is not a table', async () => {
    const dialog = mountDialog()
    await dialog.find('[data-part="block"]').setValue('')
    expect(dialog.find('[data-part="correction-field"]').exists()).toBe(false)
    await dialog.find('[data-part="block"]').setValue('b01')
    expect((dialog.find('[data-part="correction-field"]').element as HTMLTextAreaElement).value).toBe('The growth rate of the bankroll.')
    await vi.advanceTimersByTimeAsync(400)
    expect(previewTable).not.toHaveBeenCalled()
  })

  it('asks the judge\'s assessment only where the page has a finding', () => {
    expect(mountDialog().find('[data-part="assessment"]').exists()).toBe(true)
    expect(mountDialog(aPage(false)).find('[data-part="assessment"]').exists()).toBe(false)
  })

  it('holds the send until a verdict and a reason are chosen, and a note where the reason needs one', async () => {
    const dialog = mountDialog()
    const send = () => dialog.find('[data-part="send"]').attributes('disabled')
    expect(send()).toBeDefined()
    await dialog.find('[data-verdict="reject"]').trigger('click')
    await dialog.find('[data-part="reason"]').setValue('other')
    expect(dialog.find('[data-part="note-needed"]').exists()).toBe(true)
    expect(send()).toBeDefined()
    await dialog.find('[data-part="note"]').setValue('the lines cross about 2012')
    expect(send()).toBeUndefined()
  })

  it('says the verdict is recorded, follows the export, and asks for the page again once it has finished', async () => {
    vi.mocked(giveVerdict).mockResolvedValue({ verdict_id: 41, reading_key: 'k', route_before: 'vision reading',
      export: { knowledge_base: 'free', running: true, pending: false, finished: 3, last_error: null, last_finished_at: null } })
    vi.mocked(getVerdictForm)
      .mockResolvedValueOnce(aForm({ exports: [{ knowledge_base: 'free', running: true, pending: false, finished: 3, last_error: null, last_finished_at: null }] }))
      .mockResolvedValue(aForm({ exports: [{ knowledge_base: 'free', running: false, pending: false, finished: 4, last_error: null, last_finished_at: null }] }))
    const dialog = mountDialog()
    await dialog.find('[data-verdict="reject"]').trigger('click')
    await dialog.find('[data-part="reason"]').setValue('reading_wrong')
    const changed = '<table><tr><th>p</th><td>0.65</td></tr></table>'
    await dialog.find('[data-part="correction-field"]').setValue(changed)
    await dialog.find('[data-part="send"]').trigger('click')
    await flushPromises()
    expect(giveVerdict).toHaveBeenCalledWith({ knowledge_base: 'free', work: KELLY, pdf_page: 4, verdict: 'reject', reason: 'reading_wrong',
      block: 'b02', note: null, correction: changed, judge_assessment: null })
    expect(dialog.find('[data-part="verdict-said"]').text()).toBe('Recorded · the view updates after the export (about a minute)')
    // the first ask finds the export still running; the second finds it finished
    await vi.advanceTimersByTimeAsync(2000)
    expect(dialog.emitted('recorded')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(dialog.emitted('recorded')).toHaveLength(1)
  })

  it('says what the core refused, in its words', async () => {
    vi.mocked(giveVerdict).mockRejectedValue(new Error('the reason other needs a note'))
    const dialog = mountDialog()
    await dialog.find('[data-verdict="note"]').trigger('click')
    await dialog.find('[data-part="reason"]').setValue('reading_wrong')
    await dialog.find('[data-part="send"]').trigger('click')
    await flushPromises()
    const said = dialog.find('[data-part="verdict-said"]')
    expect(said.text()).toBe('the reason other needs a note')
    expect(said.classes()).toContain('failed')
    expect(dialog.emitted('recorded')).toBeUndefined()
  })
})

describe('the page view offers a verdict only where the app takes one (213.b, 223.a)', () => {
  beforeEach(async () => {
    vi.mocked(getPage).mockReset().mockResolvedValue(aPage())
    vi.mocked(getRecall).mockReset().mockRejectedValue(new Error('not asked here'))
    vi.mocked(getVerdictForm).mockReset()
    localStorage.clear()
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 } })
  })

  function mountView() {
    return mount(PageView, { props: { kb: 'free', work: KELLY, page: 4 }, global: { plugins: [createPinia(), router] } })
  }

  it('shows no control when the app was started without --allow-verdicts', async () => {
    vi.mocked(getVerdictForm).mockResolvedValue(aForm({ enabled: false, why_not: 'read-only', exports: [] }))
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="give-verdict"]').exists()).toBe(false)
  })

  it('opens the dialog from the head on the standing reading, and offers none on a recalled judgement', async () => {
    vi.mocked(getVerdictForm).mockResolvedValue(aForm())
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="verdict-dialog"]').exists()).toBe(false)
    await view.find('[data-part="give-verdict"]').trigger('click')
    expect(view.find('[data-part="verdict-dialog"]').exists()).toBe(true)
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 }, query: { judgement: 'k:judge/3:0' } })
    await flushPromises()
    expect(view.find('[data-part="give-verdict"]').exists()).toBe(false)
    expect(view.find('[data-part="verdict-dialog"]').exists()).toBe(false)
  })
})
