import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPage, getPageChunks } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import PageView from '@/views/PageView.vue'
import type { KnowledgeBase } from '@/types/api/source_types'
import { aBlock, aCheck, aPageDetail, aPageLadder, JUDGED_BAD_ROUTE, CONTENT_FILTER, KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
  getPageChunks: vi.fn(),
}))

function mountView(page = 4, kb: KnowledgeBase = 'free', work = KELLY) {
  return mount(PageView, { props: { kb, work, page }, global: { plugins: [createPinia(), router] } })
}

// an invented page of the three kinds the operator looked at (21 Nov, finance p. 469): a formula, its description, a definition;
// each quoted block with the form the search and the chat quote, the description never quoted
const SERVED_BLOCKS = [
  aBlock({ id: 'b01', block_class: 'formula', segments: null, latex: 'f^* = p - q/b', served: '\\[ f^* = p - q/b \\]' }),
  aBlock({ id: 'b02', block_class: 'description', content: 'D', segments: null, text: 'A formula giving the bet\'s size.', served: null }),
  aBlock({ id: 'b03', block_class: 'glossary_entry', attrs: { term: 'Kelly fraction' }, served: 'Kelly fraction: the share of the bankroll bet.' }),
]

const WRONG_VALUE = { kind: 'wrong_value', block: 'b02', severity: 'major', evidence: '1.034 read as 1.043', void: false }

// the record's rows, always these in this order (H1.a)
const RECORD_ROWS = ['Check:', 'Route:', 'Reading:', 'Findings:', 'Coverage:', 'Details:']
const ONE_READING = { reading_key: '2b2d48e77b246c95', number: 1, purpose: 'first reading', cell: 'FREE-SM', model: 'claude-sonnet-5-5',
  mode: 'batch', attempt: 0, class_now: 'ok', stored_at: '2026-11-02T14:48:03+00:00', deviation: null, judgements: [], format_errors: [],
  cost_usd: 0.0157879, shown: true }

describe('PageView', () => {
  beforeEach(() => {
    vi.mocked(getPage).mockReset()
    vi.mocked(getPageChunks).mockReset()
    localStorage.clear()
  })

  it('stands the record\'s rows on a page no reader has read, each that has nothing saying none, then its own image (V2.a, H1.a)', async () => {
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
    const rows = view.find('[data-part="page-facts"]')
    expect(rows.findAll('.fold-label').map(label => label.text())).toEqual(RECORD_ROWS)
    expect(rows.find('[data-label="Check"] .state-mark').attributes('data-state')).toBe('not_read')
    expect(rows.find('[data-label="Route"] .route').text()).toBe("served from the PDF's text layer")
    // a row that has nothing says so in one word and folds nothing open, so the layout never moves from page to page
    for (const label of ['Reading', 'Findings', 'Details']) {
      const row = rows.find(`[data-label="${label}"]`)
      expect([label, row.find('.fold-title').text(), row.element.tagName]).toEqual([label, 'none', 'DIV'])
    }
    // no sentence of its own above the rows: the state and the route say it
    expect(view.find('[data-part="said"]').exists()).toBe(false)
    const coverage = rows.find('[data-label="Coverage"]')
    expect(coverage.findAll('.rung-level').map(level => level.text())).toEqual(['text layer', 'text served', 'keyword search',
      'semantic search', 'reading and check'])
    expect(coverage.find('[data-said="reading and check"]').text()).toBe('no reading; planned')
    // reached, not reached and not known here as three forms, never colour alone
    expect(coverage.findAll('.rung-mark').map(mark => mark.attributes('data-reached'))).toEqual(['true', 'true', 'true', 'unknown', 'false'])
    // the image is the PDF's own, said what it is; nothing of a reading stands, which it has not
    expect(view.find('.own-image img').attributes('src')).toBe(`/api/free/works/${KELLY}/pages/4/image.png`)
    expect(view.find('.own-image figcaption').text()).toBe('a render at 150 dpi: the page holds no image of its own')
    expect(view.find('.side-by-side').exists()).toBe(false)
    expect(view.find('[data-part="reading-cost"]').exists()).toBe(false)
    // the text served, folded until asked for
    const served = view.find('[data-part="served-text"]')
    expect((served.element as HTMLDetailsElement).open).toBe(false)
    expect(served.find('.served-body').text()).toBe('The Kelly criterion sizes a bet.')
  })

  it('stands the same rows on a read page in the same order, the page\'s sentence in the Check line\'s words (H1.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder(), attempts: [ONE_READING],
      check: aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }, { value: 'other', count: 1 }] }),
      said: "Served despite the judge's findings: the judge's findings lie on blocks never quoted.",
      check_said: "served all the same: the judge's findings lie on blocks never quoted" }))
    const view = mountView()
    await flushPromises()
    const rows = view.find('[data-part="page-facts"]')
    expect(rows.findAll('.fold-label').map(label => label.text())).toEqual(RECORD_ROWS)
    const check = rows.find('[data-label="Check"]')
    expect(check.find('[data-part="check-said"]').text()).toBe("· served all the same: the judge's findings lie on blocks never quoted")
    expect(check.find('.state-mark').attributes('data-state')).toBe('issue')
    expect(view.find('[data-part="said"]').exists()).toBe(false)
    // each row one line that folds open for more: the check its three stages, the route its parts; the reading folds nothing
    expect([check.element.tagName, (check.element as HTMLDetailsElement).open]).toEqual(['DETAILS', false])
    expect(check.find('[data-stage="3"]').exists()).toBe(true)
    expect(rows.find('[data-label="Route"] [data-part="route-parts"]').exists()).toBe(true)
    expect(rows.find('[data-label="Reading"]').element.tagName).toBe('DIV')
    // nothing found says none; the page's readings stand in the form beneath the record (#18)
    expect(rows.find('[data-label="Findings"] .fold-title').text()).toBe('none')
    expect(rows.find('[data-label="Details"]').element.tagName).toBe('DETAILS')
  })

  it('stands a read page\'s own ladder in its record, and says a file held back from providers is shown here alone (V2.a)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder({ held: 'held back by the provenance list (send: false)',
      served_text: null, served_why_not: 'not known yet: the search is built when the app starts and on a first search' }) }))
    const view = mountView()
    await flushPromises()
    const coverage = view.find('[data-label="Coverage"]')
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

  it('brings the analysis and the block into view on every click of the pointer, from the raw text as well, the block flashing (43.a)', async () => {
    // jsdom lays nothing out and scrolls nothing: record which element is asked to come into view
    const scrolled: string[] = []
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value(this: Element) {
        scrolled.push(this.id || this.getAttribute('data-part') || '')
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
      // the block's frame in the reading answers the click (43.a), and does again on the second
      expect(view.find('[data-block="b02"]').attributes('data-flash')).toBe('yes')
      await view.find('.found-at button').trigger('click')
      await flushPromises()
      expect(view.find('[data-block="b02"]').attributes('data-flash')).toBe('yes')
      // each click: the window to the analysis, as show does, then the block in its column
      expect(scrolled).toEqual(['analysis', 'block-b02', 'analysis', 'block-b02'])
    } finally {
      Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
    }
  })

  it('keeps a finding about the page as a whole in the Findings row\'s fold, counted in its line, naming a block the reading lacks', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      page_findings: [{ kind: 'omission', block: 'b17', severity: 'minor', evidence: 'a footnote is missing', void: false }],
    }))
    const view = mountView()
    await flushPromises()
    const row = view.find('[data-label="Findings"]')
    expect(row.find('[data-part="page-findings-said"]').text()).toBe('· 1 finding on the page as a whole')
    const finding = row.find('.page-findings [data-finding="0"]')
    expect(finding.text()).toContain('omission')
    expect(finding.text()).toContain('b17, not in the reading')
    // no block of the reading has a finding: no block to jump to
    expect(row.find('[data-finding-at]').exists()).toBe(false)
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

  it('says why a blocked page has no reading, and holds the text served in its place in its coverage, named (21 Nov)', async () => {
    const detail = aPageDetail()
    vi.mocked(getPage).mockResolvedValue({
      ...detail,
      pdf_page: 2,
      route: 'text layer: the provider blocked the reading',
      check: aCheck({ state: 'blocked', verdict: null, judged: false }),
      trace: { ...detail.trace!, error_type: 'invalid_request_error', error_message: CONTENT_FILTER },
      reading: null,
      raw: null,
      ladder: aPageLadder(),
    })
    const view = mountView(2)
    await flushPromises()
    expect(view.find('.no-reading').exists()).toBe(true)
    expect(view.find('.route').text()).toBe('text layer: the provider blocked the reading')
    expect(view.find('.summary .error-message').text()).toBe(CONTENT_FILTER)
    expect(view.find('.original img').exists()).toBe(true)
    // no tab to choose: the quoted tab is gone (21 Nov); what serves the page in its reading's place stands in its coverage
    expect(view.findAll('.mode button')).toHaveLength(0)
    const served = view.find('[data-part="served-text"]')
    expect(served.find('.fold-title').text()).toBe("text served: the PDF's text layer")
    expect(served.find('.served-body').text()).toBe('The Kelly criterion sizes a bet.')
  })

  it('folds a page\'s coverage to one line of marks and words, open or closed as the reader last left it (21 Nov)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder() }))
    const view = mountView()
    await flushPromises()
    const fold = view.find('[data-part="page-ladder-fold"]')
    expect((fold.element as HTMLDetailsElement).open).toBe(false)
    expect(fold.findAll('.line-mark').map(mark => mark.attributes('data-reached'))).toEqual(['true', 'true', 'true', 'unknown', 'false'])
    expect(fold.find('.line-words').text()).toBe('text layer · text layer · in BM25 · not in the index · planned')
    // opened, it is kept with the reader's other folds: the next page opens it as left
    ;(fold.element as HTMLDetailsElement).open = true
    await fold.trigger('toggle')
    const next = mountView(5)
    await flushPromises()
    expect((next.find('[data-part="page-ladder-fold"]').element as HTMLDetailsElement).open).toBe(true)
    // a page whose reading is served has no "text served" fold: its reading panel shows what is served
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder({ served_by: null }) }))
    const reading = mountView(6)
    await flushPromises()
    expect(reading.find('[data-part="served-text"]').exists()).toBe(false)
  })

  it('shows a page as served chunk first: each chunk a group of its quoted blocks, a split one in both, none never quoted (21 Nov)', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ ladder: aPageLadder({ served_by: null }),
      reading: { front: { printed_label: '4' }, blocks: SERVED_BLOCKS, errors: [], warnings: [], error_places: [] } }))
    const formula = { block: 'b01', block_class: 'formula', part: false, runs: [{ text: '\\[ f^* = p - q/b \\]', shared: false }] }
    vi.mocked(getPageChunks).mockResolvedValue({ knowledge_base: 'free', source_id: KELLY, pdf_page: 4, said: null, held_back: null,
      head_said: 'this page lies in 2 chunks: A runs in from p. 3; B begins here',
      not_placed: '1 chunk of this page could not be placed in its quoted text', outside: [],
      splitter: { splitter: 'recursive character', chunk_size: 1000, chunk_overlap: 150 },
      groups: [
        { letter: 'A', id: 'c1', characters: 912, pages: 'pp. 3–4', shares: 0, runs_in_from: 3,
          head: ['runs in from p. 3', '912 characters', 'pp. 3–4'],
          blocks: [formula, { block: 'b03', block_class: 'glossary_entry', part: true,
            runs: [{ text: 'Kelly fraction: ', shared: false }, { text: 'the share', shared: true }] }] },
        { letter: 'B', id: 'c2', characters: 522, pages: 'pp. 4–5', shares: 9, shares_with: 'A', runs_on_to: 5,
          head: ['522 characters', 'pp. 4–5', 'shares 9 characters with A', 'runs on to p. 5'],
          blocks: [{ block: 'b03', block_class: 'glossary_entry', part: true,
            runs: [{ text: 'the share', shared: true }, { text: ' of the bankroll bet.', shared: false }] }] }] })
    const view = mountView()
    await flushPromises()
    // off by default: the readable view as it was, the chunks not asked for
    expect(view.find('[data-part="chunk-groups"]').exists()).toBe(false)
    expect(vi.mocked(getPageChunks)).not.toHaveBeenCalled()
    await view.find('[data-part="as-served"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(getPageChunks)).toHaveBeenCalledWith('free', KELLY, 4)
    // the page as its chunks: each a group with its one-line head, the API's words in order; the reading's own blocks gone
    expect(view.find('[data-part="chunks-said"]').text()).toBe('this page lies in 2 chunks: A runs in from p. 3; B begins here')
    expect(view.findAll('[data-part="chunk-head"]').map(head => head.text())).toEqual([
      'chunk A · runs in from p. 3 · 912 characters · pp. 3–4', 'chunk B · 522 characters · pp. 4–5 · shares 9 characters with A · runs on to p. 5'])
    expect(view.find('ol.blocks').exists()).toBe(false)
    // the block the border cuts stands in both chunks with its part, marked; the text they share dashed in both
    const split = view.findAll('[data-block="b03"]')
    expect(split.map(block => [block.find('[data-part="block-part"]').text(), block.find('[data-part="served-form"]').text()])).toEqual([
      ['(part)', 'Kelly fraction: the share'], ['(part)', 'the share of the bankroll bet.']])
    expect(view.findAll('[data-part="chunk-groups"] .overlap').map(run => run.text())).toEqual(['the share', 'the share'])
    expect(view.find('[data-chunk="A"] [data-block="b01"] [data-part="served-form"]').text()).toBe('\\[ f^* = p - q/b \\]')
    // the description never quoted is in no chunk and stands nowhere in the mode; one chunk not placed, said
    expect(view.find('[data-block="b02"]').exists()).toBe(false)
    expect(view.find('[data-part="not-placed"]').text()).toBe('1 chunk of this page could not be placed in its quoted text')
    // off again: as it was, the never-quoted block back, and asked no second time
    await view.find('[data-part="as-served"]').trigger('click')
    expect(view.find('[data-part="chunk-groups"]').exists()).toBe(false)
    expect(view.find('[data-block="b02"]').text()).toContain("A formula giving the bet's size.")
    expect(view.find('pre.raw').exists()).toBe(false)
    await view.find('[data-part="as-served"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(getPageChunks)).toHaveBeenCalledTimes(1)
  })

  it('says a page serving another text in its reading\'s place serves nothing of its reading, and offers no "as served"', async () => {
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ route: JUDGED_BAD_ROUTE, from_fallback: true, ladder: aPageLadder() }))
    const view = mountView()
    await flushPromises()
    expect(view.findAll('.mode button').map(button => button.text())).toEqual(['readable', 'raw'])
    expect(view.find('[data-part="as-served"]').exists()).toBe(false)
    expect(view.find('[data-part="as-served-off"]').text()).toBe(
      "as served: the PDF's text layer serves this page in its reading's place, so nothing of the reading is served")
    expect(vi.mocked(getPageChunks)).not.toHaveBeenCalled()
  })

  it('says a page that is not plainly ok in the Check line\'s words, no sentence above the record, and nothing for an ok page', async () => {
    const said = 'Not served: 4 readings failed the format check, the one shown here with 2 blocks left empty (b12, b15); '
      + "the PDF's text layer is served instead."
    const words = 'not served: 4 readings failed the format check, the one shown here with 2 blocks left empty (b12, b15); '
      + "the PDF's text layer is served instead"
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({ said, check_said: words }))
      .mockResolvedValueOnce(aPageDetail())
    const notServed = mountView()
    await flushPromises()
    expect(notServed.find('[data-label="Check"] [data-part="check-said"]').text()).toBe(`· ${words}`)
    expect(notServed.find('[data-part="said"]').exists()).toBe(false)
    const ok = mountView()
    await flushPromises()
    expect(ok.find('[data-part="check-said"]').exists()).toBe(false)
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

  it('puts a person who settled the page before the check in its line, which recedes, and says the why only where the API gives it', async () => {
    const person = { standing: 'accepted' as const, by_a_person: true, reason: 'every value checked', note: 'every value checked by hand',
      given_by: 'maintainer', given_at: '2026-11-10T20:00:00+00:00' }
    const issue = aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }] })
    vi.mocked(getPage)
      .mockResolvedValueOnce(aPageDetail({ check: issue, person, listed_state: 'decided_by_a_person',
        route_why: 'a person accepted the reading: every value checked by hand', why_line: null }))
      .mockResolvedValueOnce(aPageDetail({ check: issue, person: { ...person, standing: 'noted' }, listed_state: 'decided_by_a_person' }))
      .mockResolvedValueOnce(aPageDetail({ check: aCheck({ state: 'ok' }), person: { ...person, standing: 'noted' }, listed_state: 'ok' }))
      .mockResolvedValueOnce(aPageDetail({ check: issue, listed_state: 'issue', why_line: 'anthropic blocked the page (content filter)' }))
    // within the Check line (H1.a): whether the person's verdict stands before the check's state
    const personFirst = (view: ReturnType<typeof mountView>) => Boolean(view.find('[data-part="person-verdict"]').element
      .compareDocumentPosition(view.find('[data-label="Check"] .state-mark').element) & Node.DOCUMENT_POSITION_FOLLOWING)
    const accepted = mountView()
    await flushPromises()
    expect(personFirst(accepted)).toBe(true)
    expect(accepted.find('[data-part="person-verdict"] .person-by').text()).toBe('A person')
    expect(accepted.find('[data-label="Check"] .state-mark').classes()).toContain('quiet')
    // the person's reason and note are in their card, not in the line; no why of the route's where the API gives none
    expect(accepted.find('[data-part="check-line"]').text()).not.toContain('every value checked')
    expect(accepted.find('[data-label="Route"] .route-why').exists()).toBe(false)
    // a note settles a page the check listed to look at (211.a): the person first, the check's state kept, receding
    const settled = mountView()
    await flushPromises()
    expect(personFirst(settled)).toBe(true)
    expect(settled.find('[data-label="Check"] .state-mark').attributes('data-state')).toBe('issue')
    // a note on a page the check passed changes nothing: the check keeps its place
    const passed = mountView()
    await flushPromises()
    expect(personFirst(passed)).toBe(false)
    // a page no person settled: the check in its role, and the why the API gives in the route's line
    const open = mountView()
    await flushPromises()
    expect(open.find('[data-part="person-verdict"]').exists()).toBe(false)
    expect(open.find('[data-label="Check"] .state-mark').classes()).toContain('error')
    expect(open.find('[data-label="Route"] .route-why').text()).toBe('anthropic blocked the page (content filter)')
  })

  it('names an automated review\'s verdict so in the head, and says protected only where the export does (18 Nov)', async () => {
    const review = { standing: 'accepted' as const, by_a_person: false, reason: 'the judge\'s finding contradicts its own evidence',
      note: null, given_by: 'claude-opus-5-5 session, delegated by the operator (17 Nov)', given_at: '2026-11-17T20:00:00+00:00' }
    vi.mocked(getPage).mockResolvedValue(aPageDetail({ check: aCheck({ state: 'issue' }), person: review, protected: false,
      listed_state: 'decided_by_an_automated_review' }))
    const view = mountView()
    await flushPromises()
    const verdict = view.find('[data-label="Check"] [data-part="person-verdict"]')
    expect([verdict.attributes('data-by'), verdict.find('.person-by').text()]).toEqual(['Automated review', 'Automated review'])
    expect(verdict.find('[data-icon="review"]').exists()).toBe(true)
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
