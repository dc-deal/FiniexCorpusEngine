import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPage, getQuoted } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import PageView from '@/views/PageView.vue'
import type { KnowledgeBase } from '@/types/api/source_types'
import { aBlock, aCheck, aPageDetail, aPageLadder, JUDGED_BAD_ROUTE, CONTENT_FILTER, KELLY } from './page_fixture'
import { sayTime } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getQuoted: vi.fn(),
}))

function mountView(page = 4, kb: KnowledgeBase = 'free', work = KELLY) {
  return mount(PageView, { props: { kb, work, page }, global: { plugins: [createPinia(), router] } })
}

// invented text, in the form the core quotes it: a formula as LaTeX, a table as rows
const QUOTED = 'The Kelly criterion sizes a bet: \\( f^* = p - q/b \\).\n| p | b | f* |\n| 0.6 | 1 | 0.2 |'

function modeButton(view: ReturnType<typeof mountView>, label: string) {
  return view.findAll('.mode button').find(button => button.text() === label)
}

const WRONG_VALUE = { kind: 'wrong_value', block: 'b02', severity: 'major', evidence: '1.034 read as 1.043', void: false }

describe('PageView', () => {
  beforeEach(() => {
    vi.mocked(getPage).mockReset()
    vi.mocked(getQuoted).mockReset()
    vi.mocked(getQuoted).mockImplementation(async (knowledgeBase, sourceId, pdfPage) => ({
      knowledge_base: knowledgeBase, source_id: sourceId, pdf_page: pdfPage, text: QUOTED }))
    localStorage.clear()
  })

  it('opens a page no reader has read: its state, what serves it, its own ladder, the text served and its own image (V2.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      read: false, trace: null, reading: null, raw: null, integrity: 'no reading', attempts: null, printed_label: null,
      route_why: "served from the PDF's text layer", said: "Not read: served from the PDF's text layer.",
      check: aCheck({ state: 'not_read', judged: false, why_judged: 'not read', verdict: null }),
      image: { available: true, why_not: null, width: 1275, height: 1650, same_as_read: null, kind: 'rendered', format: 'png',
        said: 'a render at 150 dpi: the page holds no image of its own' },
      ladder: aPageLadder(),
    }))
    const view = mountView()
    await flushPromises()
    const unread = view.find('[data-part="unread-page"]')
    expect(unread.find('.state-mark').attributes('data-state')).toBe('not_read')
    expect(unread.find('.route').text()).toBe("served from the PDF's text layer")
    expect(unread.findAll('.rung-level').map(level => level.text())).toEqual(['text layer', 'text served', 'keyword search',
      'semantic chunks', 'reading and check'])
    expect(unread.find('[data-said="reading and check"]').text()).toBe('no reading; planned')
    // reached, not reached and not known here as three forms, never colour alone
    expect(unread.findAll('.rung-mark').map(mark => mark.attributes('data-reached'))).toEqual(['true', 'true', 'true', 'unknown', 'false'])
    // the image is the PDF's own, said what it is; nothing of a reading stands, which it has not
    expect(unread.find('.own-image img').attributes('src')).toBe(`/api/free/works/${KELLY}/pages/4/image.png`)
    expect(unread.find('.own-image figcaption').text()).toBe('a render at 150 dpi: the page holds no image of its own')
    expect(view.find('.side-by-side').exists()).toBe(false)
    expect(view.find('[data-part="reading-cost"]').exists()).toBe(false)
    // the text served, folded until asked for
    const served = unread.find('[data-part="served-text"]')
    expect((served.element as HTMLDetailsElement).open).toBe(false)
    expect(served.find('.served-body').text()).toBe('The Kelly criterion sizes a bet.')
  })

  it('stands a read page\'s own ladder in its record, and says a file held back from providers is shown here alone (V2.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder({ held: 'held back by the provenance list (send: false)',
      served_text: null, served_why_not: 'not known yet: the search is built when the app starts and on a first search' }) }))
    const view = mountView()
    await flushPromises()
    const coverage = view.find('[data-part="page-coverage"]')
    expect(coverage.findAll('.rung-level')).toHaveLength(5)
    expect(coverage.find('[data-part="held"]').text()).toBe('held back by the provenance list (send: false); shown here, on this machine only')
    expect(coverage.find('.served-none').text()).toBe('not known yet: the search is built when the app starts and on a first search')
  })

  it('shows the original the reader received beside its reading', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail())
    const view = mountView()
    await flushPromises()
    expect(view.find('.original img').attributes('src')).toBe(`/api/free/works/${KELLY}/pages/4/image.png`)
    expect(view.find('.summary .image-mark.same').text()).toBe('image as read')
    expect(view.find('[data-block="b01"]').exists()).toBe(true)
  })

  it('says it when the original differs from what the reader received', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      image: { available: true, why_not: null, width: 1680, height: 2200, same_as_read: false, kind: 'reading', format: 'png' },
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('.summary .image-mark.differs').text()).toBe('image differs from the one read')
    expect(view.find('.summary .image-mark.differs [data-icon="status-error"]').exists()).toBe(true)
    expect(view.find('.summary .image-mark.same').exists()).toBe(false)
  })

  it('names the page by its PDF number and the number printed on it, and its knowledge base', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ printed_label: 'iv' }))
    const view = mountView()
    await flushPromises()
    expect(view.find('.view-title').text()).toBe('PDF page 4 · printed iv')
    expect(view.find('.trail [data-kb="free"]').text()).toBe('free')
  })

  it('puts what matters most in one line, and says no more where all is fine', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail())
    const view = mountView()
    await flushPromises()
    const summary = view.find('.summary')
    expect(summary.find('[data-state="ok"]').exists()).toBe(true)
    expect(summary.find('.cost').text()).toBe('0.016 USD')
    expect(summary.find('.class-move').exists()).toBe(false)
    expect(summary.find('.retry').exists()).toBe(false)
    expect(summary.find('.error-message').exists()).toBe(false)
  })

  it('names a bad verdict once, through the reasons', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      check: aCheck({
        state: 'issue',
        reasons: [{ value: 'judge: bad', count: 1 }, { value: 'omission', count: 1 }],
        verdict: { verdict: 'bad', outcome: 'issue', findings: [], void: 0 },
      }),
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('.summary').text().match(/judge: bad/g)).toHaveLength(1)
  })

  it('names a class that moved and a retry in the line', async () => {
    const detail = aPageDetail()
    vi.mocked(getPage).mockResolvedValue({
      ...detail,
      trace: { ...detail.trace!, class_when_collected: 'malformed', class_now: 'ok', attempt: 1 },
    })
    const view = mountView()
    await flushPromises()
    expect(view.find('.summary .class-move').text()).toBe('malformed → ok')
    expect(view.find('.summary .retry').text()).toBe('retry 1')
  })

  it('folds the details until they are asked for, and remembers the choice', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail())
    const view = mountView()
    await flushPromises()
    const details = view.find('details.details')
    const element = details.element as HTMLDetailsElement
    expect(element.open).toBe(false)
    element.open = true
    await details.trigger('toggle')
    expect(JSON.parse(localStorage.getItem('settings.v1') ?? 'null')).toMatchObject({ pageDetailsOpen: true })

    const again = mountView()
    await flushPromises()
    expect((again.find('details.details').element as HTMLDetailsElement).open).toBe(true)
  })

  it('shows the raw reading as escaped text on request', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ raw: '<table><tr><td>1</td></tr></table>' }))
    const view = mountView()
    await flushPromises()
    await view.findAll('.mode button')[1].trigger('click')
    expect(view.find('pre.raw').text()).toBe('<table><tr><td>1</td></tr></table>')
    expect(view.find('pre.raw table').exists()).toBe(false)
  })

  it('puts a finding beneath the block it names, and points to that block from the top', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      check: aCheck({ state: 'issue', verdict: { verdict: 'bad', outcome: 'issue', findings: [WRONG_VALUE], void: 0 } }), findings_at: [{ block: 'b02', said: 'stands' }],
      reading: { front: {}, blocks: [aBlock({ id: 'b01' }), aBlock({ id: 'b02', findings: [WRONG_VALUE] })], errors: [], warnings: [], error_places: [] },
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-block="b02"] [data-finding="0"]').text()).toContain('1.034 read as 1.043')
    expect(view.find('[data-block="b01"] [data-finding]').exists()).toBe(false)
    expect(view.find('.page-findings').exists()).toBe(false)
    // from the raw text, the pointer brings the readable view back with the block marked
    await view.findAll('.mode button')[1].trigger('click')
    await view.find('.found-at button').trigger('click')
    expect(view.find('[data-block="b02"]').classes()).toContain('highlighted')
  })

  it('brings the block into view on every click of the pointer, from the raw text as well', async () => {
    // jsdom lays nothing out and scrolls nothing: record which element is asked to come into view
    const scrolled: string[] = []
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value(this: Element) {
        scrolled.push(this.id)
      },
    })
    try {
      vi.mocked(getPage).mockResolvedValue(aPageDetail({
        check: aCheck({ state: 'issue', verdict: { verdict: 'bad', outcome: 'issue', findings: [WRONG_VALUE], void: 0 } }), findings_at: [{ block: 'b02', said: 'stands' }],
        reading: { front: {}, blocks: [aBlock({ id: 'b01' }), aBlock({ id: 'b02', findings: [WRONG_VALUE] })], errors: [], warnings: [], error_places: [] },
      }))
      const view = mountView()
      await flushPromises()
      await view.findAll('.mode button')[1].trigger('click')
      await view.find('.found-at button').trigger('click')
      await flushPromises()
      await view.find('.found-at button').trigger('click')
      await flushPromises()
      expect(scrolled).toEqual(['block-b02', 'block-b02'])
    } finally {
      Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
    }
  })

  it('keeps a finding about the page as a whole above the original, naming a block the reading lacks', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      page_findings: [{ kind: 'omission', block: 'b17', severity: 'minor', evidence: 'a footnote is missing', void: false }],
    }))
    const view = mountView()
    await flushPromises()
    const finding = view.find('.page-findings [data-finding="0"]')
    expect(finding.text()).toContain('omission')
    expect(finding.text()).toContain('b17, not in the reading')
    expect(view.find('.found-at').exists()).toBe(false)
  })

  it('frames the block under the pointer where the reader placed it, in percent of the image', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      reading: { front: {}, blocks: [aBlock({ id: 'b01', bbox: [168, 220, 840, 440] })], errors: [], warnings: [], error_places: [] },
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('.block-box').exists()).toBe(false)
    await view.find('[data-block="b01"]').trigger('mouseenter')
    const box = view.find('.block-box')
    expect(box.attributes('data-box')).toBe('b01')
    expect(box.attributes('style')).toContain('left: 10%')
    expect(box.attributes('style')).toContain('top: 10%')
    expect(box.attributes('style')).toContain('width: 40%')
    expect(box.attributes('style')).toContain('height: 10%')
    await view.find('[data-block="b01"]').trigger('mouseleave')
    expect(view.find('.block-box').exists()).toBe(false)
  })

  it('keeps the frame of the block chosen from the top once the pointer leaves', async () => {
    const omission = { kind: 'omission', block: 'b02', severity: 'major', evidence: null, void: false }
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      check: aCheck({ state: 'issue', verdict: { verdict: 'bad', outcome: 'issue', findings: [omission], void: 0 } }), findings_at: [{ block: 'b02', said: 'stands' }],
      reading: {
        front: {},
        blocks: [aBlock({ id: 'b01', bbox: [0, 0, 840, 220] }), aBlock({ id: 'b02', bbox: [0, 1100, 1680, 2200], findings: [omission] })],
        errors: [],
        warnings: [],
        error_places: [],
      },
    }))
    const view = mountView()
    await flushPromises()
    await view.find('.found-at button').trigger('click')
    expect(view.find('.block-box').attributes('data-box')).toBe('b02')
    await view.find('[data-block="b01"]').trigger('mouseenter')
    expect(view.find('.block-box').attributes('data-box')).toBe('b01')
    await view.find('[data-block="b01"]').trigger('mouseleave')
    expect(view.find('.block-box').attributes('data-box')).toBe('b02')
  })

  it('draws no frame for a block the reader gave no box and that names no block it is about', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      reading: { front: {}, blocks: [aBlock({ id: 'b01', block_class: 'description', content: 'D', bbox: null })], errors: [], warnings: [], error_places: [] },
    }))
    const view = mountView()
    await flushPromises()
    await view.find('[data-block="b01"]').trigger('mouseenter')
    expect(view.find('.block-box').exists()).toBe(false)
  })

  it('frames the figure a description is about, dashed, where the description has no box of its own', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      reading: { front: {}, blocks: [
        aBlock({ id: 'b03', block_class: 'figure', bbox: [168, 220, 840, 440] }),
        aBlock({ id: 'b05', block_class: 'description', content: 'D', bbox: null, attrs: { of: 'b03', form: 'prose' } }),
      ], errors: [], warnings: [], error_places: [] },
    }))
    const view = mountView()
    await flushPromises()
    await view.find('[data-block="b05"]').trigger('mouseenter')
    const box = view.find('.block-box')
    expect(box.classes()).toContain('described')
    expect(box.find('.block-box-label').text()).toBe('b05 describes b03')
    expect(box.attributes('style')).toContain('left: 10%')
    // the figure itself is framed as its own, solid
    await view.find('[data-block="b03"]').trigger('mouseenter')
    expect(view.find('.block-box').classes()).not.toContain('described')
    expect(view.find('.block-box-label').text()).toBe('b03')
  })

  it('says why a blocked page has no reading, in the provider\'s own words, and still shows its original', async () => {
    const detail = aPageDetail()
    vi.mocked(getPage).mockResolvedValue({
      ...detail,
      pdf_page: 2,
      route: 'text layer: the provider blocked the reading',
      check: aCheck({ state: 'blocked', verdict: null, judged: false }),
      trace: { ...detail.trace!, error_type: 'invalid_request_error', error_message: CONTENT_FILTER },
      reading: null,
      raw: null,
    })
    const view = mountView(2)
    await flushPromises()
    expect(view.find('.no-reading').exists()).toBe(true)
    expect(view.find('.route').text()).toBe('text layer: the provider blocked the reading')
    expect(view.find('.summary .error-message').text()).toBe(CONTENT_FILTER)
    expect(view.find('.original img').exists()).toBe(true)
    // with no reading, the text the search and the chat quote is all there is to show, and the one switch
    expect(view.findAll('.mode button').map(button => button.text())).toEqual(['quoted'])
    expect(view.find('.quoted-text').text()).toBe(QUOTED)
  })

  it('opens a page quoted from its text layer on its reading, as every page, the quoted text one click away (227.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      route: JUDGED_BAD_ROUTE,
      from_fallback: true,
      check: aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }], verdict: { verdict: 'bad', outcome: 'issue', findings: [], void: 0 } }),
    }))
    const view = mountView()
    await flushPromises()
    // the switch stands as on every page, on the reading, and the quoted text is not asked for until chosen
    expect(view.findAll('.mode button').map(button => button.text())).toEqual(['readable', 'raw', 'quoted'])
    expect(modeButton(view, 'readable')?.attributes('aria-pressed')).toBe('true')
    expect(view.find('[data-block="b01"]').exists()).toBe(true)
    expect(vi.mocked(getQuoted)).not.toHaveBeenCalled()
    await modeButton(view, 'quoted')!.trigger('click')
    await flushPromises()
    expect(vi.mocked(getQuoted)).toHaveBeenCalledWith('free', KELLY, 4)
    expect(view.find('.quoted-from').text()).toContain(JUDGED_BAD_ROUTE)
    // shown exactly as quoted: the formula's LaTeX and the table's rows, never rendered
    expect(view.find('.quoted-text').text()).toBe(QUOTED)
    expect(view.find('[data-block]').exists()).toBe(false)
  })

  it('opens a page quoted from its reading on the reading, and asks for the quoted text only when it is chosen', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail())
    const view = mountView()
    await flushPromises()
    expect(modeButton(view, 'readable')?.attributes('aria-pressed')).toBe('true')
    expect(vi.mocked(getQuoted)).not.toHaveBeenCalled()
    await modeButton(view, 'quoted')!.trigger('click')
    await flushPromises()
    expect(vi.mocked(getQuoted)).toHaveBeenCalledTimes(1)
    expect(view.find('.quoted-text').text()).toBe(QUOTED)
    // back and forth asks no second time
    await modeButton(view, 'raw')!.trigger('click')
    await modeButton(view, 'quoted')!.trigger('click')
    await flushPromises()
    expect(vi.mocked(getQuoted)).toHaveBeenCalledTimes(1)
  })

  it('says so where the core holds no quoted text for a page', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ route: JUDGED_BAD_ROUTE, from_fallback: true }))
    vi.mocked(getQuoted).mockResolvedValue({ knowledge_base: 'free', source_id: KELLY, pdf_page: 4, text: null })
    const view = mountView()
    await flushPromises()
    await modeButton(view, 'quoted')!.trigger('click')
    await flushPromises()
    expect(view.find('.no-quote').text()).toBe('The core holds no quoted text for this page.')
  })

  it('lists a page\'s readings over time where it has more than one, the one shown here marked and why it was chosen', async () => {
    const first = { reading_key: 'aaaa1111', number: 1, purpose: 'first reading', cell: 'FREE-SM', model: 'claude-sonnet-5-5',
      mode: 'batch', attempt: 0, class_now: 'malformed', stored_at: '2026-11-02T14:48:03+00:00', deviation: null, judgements: [],
      format_errors: [], cost_usd: 0.0157879, shown: false }
    const second = { ...first, reading_key: '2b2d48e77b246c95', number: 2, purpose: 'read again by a replay', mode: 'standard',
      attempt: 1, class_now: 'ok', stored_at: '2026-11-04T09:12:00+00:00', shown: true }
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({
        attempts: [first, second],
        chosen: { why: 're-read after the format retry', run_id: '7', chosen_at: '2026-11-04T09:13:00+00:00' },
      }))
      .mockResolvedValueOnce(aPageDetail({ attempts: [second] }))
    const healed = mountView()
    await flushPromises()
    // the reading shown first and open, the earlier one below it, folded (the operator, 2026-11-10)
    const rows = healed.findAll('.history [data-reading]')
    expect(rows.map(row => row.attributes('data-reading'))).toEqual(['2b2d48e77b246c95', 'aaaa1111'])
    expect(rows[0].classes()).toContain('current')
    expect(rows[0].text()).toContain('shown here')
    expect((rows[0].element as HTMLDetailsElement).open).toBe(true)
    expect((rows[1].element as HTMLDetailsElement).open).toBe(false)
    // each numbered across the page's readers and said in the core's words; the reader's own count in the fold (the operator, p. 524)
    expect(rows.map(row => row.find('.reading-number').text())).toEqual(['reading 2', 'reading 1'])
    expect(rows.map(row => row.find('[data-part="purpose"]').text())).toEqual(['read again by a replay', 'first reading'])
    expect(rows[0].find('[data-part="reader-attempt"]').text()).toBe("the reader's attempt 1 · cell FREE-SM · 0.016 USD")
    expect(healed.find('.history .chosen').text())
      .toBe(`Chosen ${sayTime('2026-11-04T09:13:00+00:00').text} by run 7: re-read after the format retry`)
    expect(healed.find('.history .chosen time').attributes('datetime')).toBe('2026-11-04T09:13:00+00:00')
    // one reading and no choice: nothing to tell, so nothing is printed
    const single = mountView()
    await flushPromises()
    expect(single.find('.history').exists()).toBe(false)
  })

  it('says a page that is not plainly ok in the API\'s one sentence first, its chips after it, and nothing for an ok page', async () => {
    const said = 'Not served: 4 readings failed the format check, the one shown here with 2 blocks left empty (b12, b15); '
      + "the PDF's text layer is served instead."
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({ said }))
      .mockResolvedValueOnce(aPageDetail())
    const notServed = mountView()
    await flushPromises()
    const sentence = notServed.find('[data-part="said"]')
    expect(sentence.text()).toBe(said)
    expect(sentence.element.nextElementSibling?.classList.contains('summary')).toBe(true)
    const ok = mountView()
    await flushPromises()
    expect(ok.find('[data-part="said"]').exists()).toBe(false)
  })

  it('says each block of the head\'s findings in a finding\'s own look: the flag and its gravest severity, a void one receding', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ findings_at: [
      { block: 'b11', said: 'stands', severity: 'major' }, { block: 'b13', said: 'stands', severity: 'minor' },
      { block: 'b16', said: 'void by code', severity: null }] }))
    const view = mountView()
    await flushPromises()
    const at = (block: string) => view.find(`[data-label="Findings"] [data-finding-at="${block}"]`)
    // form before colour: the flag on every one, the severity's word where findings stand, the ruling where code voided them
    expect(['b11', 'b13', 'b16'].map(block => at(block).find('[data-icon="finding"]').exists())).toEqual([true, true, true])
    expect([at('b11').classes(), at('b13').classes(), at('b16').classes()].map(classes => classes.find(name => ['major', 'minor', 'void'].includes(name))))
      .toEqual(['major', 'minor', 'void'])
    expect([at('b11').find('[data-severity]').text(), at('b13').find('[data-severity]').text()]).toEqual(['major', 'minor'])
    expect(at('b16').find('[data-said]').text()).toBe('void by code')
    expect(at('b16').find('[data-severity]').exists()).toBe(false)
    // each still a jump to its block
    expect(at('b11').find('button[data-jump="b11"]').exists()).toBe(true)
  })

  it('brings a note into view and marks it when its marker in the prose is clicked (206.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ reading: { front: {}, errors: [], warnings: [], error_places: [], blocks: [
      aBlock({ id: 'b02', segments: [{ kind: 'text', content: 'processes.' }, { kind: 'fn', content: '4', note: 'b09', note_text: 'The source.' }] }),
      aBlock({ id: 'b09', block_class: 'footnote', attrs: { marker: '4' }, segments: [{ kind: 'text', content: 'The source.' }] }),
    ] } }))
    const view = mountView()
    await flushPromises()
    await view.findAll('.mode button').find(button => button.text() === 'readable')!.trigger('click')
    expect(view.find('[data-block="b09"]').classes()).not.toContain('highlighted')
    await view.find('[data-block="b02"] [data-note="b09"]').trigger('click')
    await flushPromises()
    expect(view.find('[data-block="b09"]').classes()).toContain('highlighted')
  })

  it('puts a person who settled the page before the check, which recedes, and says the why only where the API gives it', async () => {
    const person = { standing: 'accepted' as const, by_a_person: true, reason: 'every value checked', note: 'every value checked by hand',
      given_by: 'maintainer', given_at: '2026-11-10T20:00:00+00:00' }
    const issue = aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }] })
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({ check: issue, person, listed_state: 'decided_by_a_person',
        route_why: 'a person accepted the reading: every value checked by hand', why_line: null }))
      .mockResolvedValueOnce(aPageDetail({ check: issue, person: { ...person, standing: 'noted' }, listed_state: 'decided_by_a_person' }))
      .mockResolvedValueOnce(aPageDetail({ check: aCheck({ state: 'ok' }), person: { ...person, standing: 'noted' }, listed_state: 'ok' }))
      .mockResolvedValueOnce(aPageDetail({ check: issue, listed_state: 'issue', why_line: 'anthropic blocked the page (content filter)' }))
    const labelsOf = (view: ReturnType<typeof mountView>) => view.findAll('[data-part="page-facts"] .line-label').map(label => label.text())
    const accepted = mountView()
    await flushPromises()
    expect(labelsOf(accepted).slice(0, 2)).toEqual(['A person:', 'Check:'])
    expect(accepted.find('[data-label="Check"] .state-mark').classes()).toContain('quiet')
    // the person's reason and note are in their card, not in the line; the route's whole why in the route's card
    expect(accepted.find('[data-label="A person"]').text()).not.toContain('every value checked')
    expect(labelsOf(accepted)).not.toContain('Why:')
    // a note settles a page the check listed to look at (211.a): the person first, the check's state kept, receding
    const settled = mountView()
    await flushPromises()
    expect(labelsOf(settled).slice(0, 2)).toEqual(['A person:', 'Check:'])
    expect(settled.find('[data-label="Check"] .state-mark').attributes('data-state')).toBe('issue')
    // a note on a page the check passed changes nothing: the check keeps its place
    const passed = mountView()
    await flushPromises()
    expect(labelsOf(passed).slice(0, 2)).toEqual(['Check:', 'A person:'])
    // a page no person settled: the check first, in its role, and the why the API gives a line for
    const open = mountView()
    await flushPromises()
    expect(labelsOf(open)[0]).toBe('Check:')
    expect(open.find('[data-label="Check"] .state-mark').classes()).toContain('error')
    expect(open.find('[data-label="Why"] .route-why').text()).toBe('anthropic blocked the page (content filter)')
  })

  it('says beside each reading what its check made of it, the verdict only where the state does not say it', async () => {
    const reading = { model: 'claude-sonnet-5-5', mode: 'batch', class_now: 'ok', stored_at: '2026-11-02T14:48:03+00:00',
      deviation: null, judgements: [], format_errors: [] }
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      attempts: [
        { ...reading, reading_key: 'aaaa1111', number: 1, attempt: 0, check: { state: 'issue', verdict: 'bad', outcome: 'issue', reasons: ['judge: bad'] }, shown: false },
        { ...reading, reading_key: 'bbbb2222', number: 2, attempt: 1, check: null, shown: false },
        { ...reading, reading_key: '2b2d48e77b246c95', number: 3, attempt: 2, check: { state: 'ok', verdict: 'ok', outcome: 'ok', reasons: [] }, shown: true },
      ],
    }))
    const view = mountView()
    await flushPromises()
    // the reading shown first, then the earlier ones, newest first
    const checks = view.findAll('.history .attempt-check').map(cell => cell.text())
    expect(checks).toEqual(['ok', 'not checked', 'issue · judged bad'])
  })

  it('says why each reading stands as it does, and a session reading\'s cost as not measurable, never 0', async () => {
    // invented after licensed pages line 1 named (the operator, 18 Nov: "reading 2 · malformed · issue" said what, not why)
    const malformed = ['block b04 (line 26): LaTeX command outside math: \\HL']
    const reading = { model: 'claude-sonnet-5-5', mode: 'batch', class_now: 'malformed', stored_at: '2026-11-02T14:48:03+00:00',
      deviation: null, judgements: [], cost_usd: 0.0094749 }
    const page = aPageDetail()
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      trace: { ...page.trace!, cost_usd: null },
      attempts: [
        { ...reading, reading_key: 'aaaa1111', number: 1, attempt: 0, check: null, format_errors: malformed, shown: false },
        { ...reading, reading_key: 'bbbb2222', number: 2, attempt: 1, format_errors: malformed, shown: false,
          check: { state: 'issue', verdict: null, outcome: null, reasons: ['format: malformed'] } },
        { ...reading, reading_key: '2b2d48e77b246c95', number: 3, attempt: 0, model: 'claude-opus-5-5', mode: 'session',
          class_now: 'ok', cost_usd: null, format_errors: [], shown: true,
          check: { state: 'ok', verdict: 'ok', outcome: 'ok', reasons: [] } },
      ],
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="reading-cost"]').text()).toBe('external cost, not measurable')
    const rows = view.findAll('.history [data-reading]')
    expect(rows.map(row => row.attributes('data-reading'))).toEqual(['2b2d48e77b246c95', 'bbbb2222', 'aaaa1111'])
    // the session reading: nothing wrong, so no why; its cost said, never 0
    expect(rows[0].find('[data-part="attempt-why"]').exists()).toBe(false)
    expect(rows[0].find('[data-part="reader-attempt"]').text()).toBe("the reader's attempt 0 · external cost, not measurable")
    // the checked retry: the check's reason and the validator's message, as written
    expect(rows[1].find('[data-part="attempt-reasons"]').text()).toBe('format: malformed')
    expect(rows[1].findAll('[data-part="format-error"]').map(error => error.text())).toEqual(malformed)
    expect(rows[1].find('[data-part="reader-attempt"]').text()).toBe("the reader's attempt 1 · 0.0095 USD")
    // the first reading, which no check reached: the validator's message says why it is malformed all the same
    expect(rows[2].find('[data-part="attempt-reasons"]').exists()).toBe(false)
    expect(rows[2].findAll('[data-part="format-error"]').map(error => error.text())).toEqual(malformed)
  })

  it('names an automated review\'s verdict so in the head, and says protected only where the export does (18 Nov)', async () => {
    const review = { standing: 'accepted' as const, by_a_person: false, reason: 'the judge\'s finding contradicts its own evidence',
      note: null, given_by: 'claude-opus-5-5 session, delegated by the operator (17 Nov)', given_at: '2026-11-17T20:00:00+00:00' }
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ check: aCheck({ state: 'issue' }), person: review, protected: false,
      listed_state: 'decided_by_an_automated_review' }))
    const view = mountView()
    await flushPromises()
    const labels = view.findAll('[data-part="page-facts"] .line-label').map(label => label.text())
    expect(labels).toContain('Automated review:')
    expect(labels).not.toContain('A person:')
    expect(view.find('[data-label="Automated review"] [data-icon="review"]').exists()).toBe(true)
    expect(view.find('[data-part="protected"]').exists()).toBe(false)
  })

  it('says in the line when the reading file is no longer what was checked, and nothing while it is', async () => {
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({ integrity: 'tampered' }))
      .mockResolvedValueOnce(aPageDetail({ integrity: 'missing', reading: null, raw: null }))
      .mockResolvedValueOnce(aPageDetail())
    const tampered = mountView()
    await flushPromises()
    const mark = tampered.find('.summary .reading-changed')
    expect(mark.text()).toBe('tampered: the reading file differs from the text that was checked')
    expect(mark.find('[data-integrity="tampered"] [data-icon="status-error"]').exists()).toBe(true)
    // the tampered text is still shown, as it now reads
    expect(tampered.find('[data-block="b01"]').exists()).toBe(true)
    const gone = mountView()
    await flushPromises()
    expect(gone.find('.summary .reading-changed').text()).toBe('missing: the reading file is gone')
    expect(gone.find('.no-reading').text()).toBe('The reading file is gone: there is no reading to show.')
    const whole = mountView()
    await flushPromises()
    expect(whole.find('.reading-changed').exists()).toBe(false)
  })

  it('says how to get an original that is not downloaded', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      image: { available: false, why_not: 'corpus/raw/x.pdf is not downloaded: run python -m backend.ingestion.acquire', width: null, height: null, same_as_read: null,
        kind: 'reading', format: 'png' },
    }))
    const view = mountView()
    await flushPromises()
    expect(view.find('.image-missing').text()).toContain('python -m backend.ingestion.acquire')
  })

  it('offers the neighbouring pages within the same knowledge base, a missing one keeping its place', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ previous_page: null, next_page: 5 }))
    const view = mountView()
    await flushPromises()
    const links = view.findAll('.pager a')
    expect(links.map(link => link.attributes('href'))).toEqual([`#/free/sources/${KELLY}/page/5`])
    expect(view.find('.pager [data-part="next"] .pager-label').text()).toBe('p. 5')
    // the first page has no previous one, and its box stays as an empty place, so next does not slide into it
    expect(view.findAll('.pager > .pager-link').map(box => box.classes().includes('empty'))).toEqual([true, false])
  })

  it('keeps a licensed page\'s neighbours and its work in the licensed knowledge base', async () => {
    // invented: no licensed title or text stands in a tracked file
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      knowledge_base: 'licensed', source_id: 'a_licensed_book', title: 'a_licensed_book', previous_page: 3, next_page: 5,
    }))
    const view = mountView(4, 'licensed', 'a_licensed_book')
    await flushPromises()
    expect(view.findAll('.pager a').map(link => link.attributes('href'))).toEqual([
      '#/licensed/sources/a_licensed_book/page/3',
      '#/licensed/sources/a_licensed_book/page/5',
    ])
    expect(view.findAll('.trail a')[1].attributes('href')).toBe('#/licensed/sources/a_licensed_book')
    expect(view.find('.original img').attributes('src')).toBe('/api/licensed/works/a_licensed_book/pages/4/image.png')
    expect(view.find('.trail [data-kb="licensed"]').exists()).toBe(true)
  })

  it('names a refused page instead of loading forever', async () => {
    vi.mocked(getPage).mockRejectedValue(new ApiError(404, 'no reading of PDF page 99'))
    const view = mountView(99)
    await flushPromises()
    expect(view.find('[role="alert"]').text()).toContain('no reading of PDF page 99')
  })
})
