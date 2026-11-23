import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getCodePage, getCodeWork } from '@/api/api_client'
import LibrarianAnswer from '@/components/librarian/LibrarianAnswer.vue'
import NumberedText from '@/components/base/NumberedText.vue'
import { router } from '@/router'
import CodePageView from '@/views/CodePageView.vue'
import CodeWorkView from '@/views/CodeWorkView.vue'
import type { CodePage, CodeUnit, CodeWork } from '@/types/api/code_types'
import type { LibrarianCall } from '@/types/api/librarian_types'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getCodeWork: vi.fn(),
  getCodePage: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented throughout (#12): no licensed code, title or name stands in a test
const KEY = 'an_invented_code'
const BAND = 'Indicators/Invented Band (I).txt'
const TEXT = 'inputs: Length(20);\nvars: Middle(0);\nMiddle = InventedAverage(Close, Length);\nPlot1(Middle, "Middle");'

function aUnit(overrides: Partial<CodeUnit> = {}): CodeUnit {
  return { name: 'Invented Band', unit: 'indicator', category: 'volatility', aliases: ['an invented envelope'],
    inputs: [{ name: 'Length', default: '20' }], source_named: 'from an invented book',
    summary: 'An invented sentence about a band.', summary_is: 'derived (an invented model)', ...overrides }
}

function aWork(overrides: Partial<CodeWork> = {}): CodeWork {
  return {
    knowledge_base: 'licensed', work: KEY, title: 'An Invented Code', code_language: 'EasyLanguage', licence: 'an invented licence',
    route: 'source code, as the publisher gave it', files: 3, units: 2,
    companion: { key: 'an_invented_book', title: 'An Invented Book', view: 'pages', id: 'an_invented_book_src' },
    categories: [{ category: 'trend', units: 1 }, { category: 'volatility', units: 1 }], catalog_said: null,
    folders: [
      { title: 'Functions', count: 1, files: [{ label: 'Functions/Invented Average.txt', name: 'Invented Average',
        unit: aUnit({ name: 'Invented Average', unit: 'function', category: 'trend' }) }] },
      { title: 'Indicators', count: 1, files: [{ label: BAND, name: 'Invented Band (I)', unit: aUnit() }] },
      { title: 'Strategies', count: 1, files: [{ label: 'Strategies/Invented Cross (S).txt', name: 'Invented Cross (S)', unit: null }] },
    ],
    ...overrides,
  }
}

function aPage(overrides: Partial<CodePage> = {}): CodePage {
  return {
    knowledge_base: 'licensed', work: KEY, title: 'An Invented Code', code_language: 'EasyLanguage', licence: 'an invented licence',
    route: 'source code, as the publisher gave it', label: BAND, folder: 'Indicators', name: 'Invented Band (I)', text: TEXT,
    lines: { first: 1, last: 4 }, unit: aUnit(), previous: 'Functions/Invented Average.txt', next: 'Strategies/Invented Cross (S).txt',
    previous_name: 'Invented Average', next_name: 'Invented Cross (S)', position: 2, files: 3,
    companion: { key: 'an_invented_book', title: 'An Invented Book', view: 'pages', id: 'an_invented_book_src' },
    ...overrides,
  }
}

describe('a book\'s companion code (#12)', () => {
  beforeEach(() => {
    vi.mocked(getCodeWork).mockReset().mockResolvedValue(aWork())
    vi.mocked(getCodePage).mockReset().mockResolvedValue(aPage())
  })

  it('addresses a file by its label as one encoded segment, as the librarian links it, and takes the lines a hit names', () => {
    const resolved = router.resolve(`/licensed/code/${KEY}/Indicators%2FInvented%20Band%20(I).txt?lines=2-3`)
    expect(resolved.name).toBe('code-page')
    expect(resolved.params.label).toBe(BAND)
    expect(resolved.query.lines).toBe('2-3')
    expect(router.resolve({ name: 'code-page', params: { kb: 'licensed', work: KEY, label: BAND } }).href)
      .toBe(`#/licensed/code/${KEY}/Indicators%2FInvented%20Band%20(I).txt`)
    // only the licensed knowledge base has code works
    expect(router.resolve(`/free/code/${KEY}`).matched).toEqual([])
  })

  it('lists a work\'s folders and files, each with its catalog entry, the core\'s count by category once in its head', async () => {
    const view = mount(CodeWorkView, { props: { kb: 'licensed', work: KEY }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(view.find('.view-title').text()).toBe('An Invented Code')
    expect(view.find('[data-part="summary"]').text()).toContain('3 files of EasyLanguage')
    expect(view.find('[data-part="categories"] span').text()).toBe('2 units in the catalog:')
    expect(view.findAll('[data-part="categories"] [data-category]').map(one => one.text())).toEqual(['trend 1', 'volatility 1'])
    expect(view.findAll('[data-folder]').map(fold => fold.attributes('data-folder'))).toEqual(['Functions', 'Indicators', 'Strategies'])
    const band = view.find(`tr[data-file="${BAND}"]`)
    expect(band.find('a').attributes('href')).toBe(`#/licensed/code/${KEY}/Indicators%2FInvented%20Band%20(I).txt`)
    expect(band.find('[data-cell="inputs"]').text()).toBe('Length = 20')
    // the sentence a model's: said as derived, never as a quote
    expect(band.find('[data-cell="summary"] .summary').text()).toBe('An invented sentence about a band.')
    expect(band.find('[data-cell="summary"] [data-part="derived"]').text()).toBe('derived (an invented model), never quoted')
    expect(band.find('[data-cell="summary"]').text()).not.toMatch(/[“"]/)
    expect(view.find('tr[data-file="Strategies/Invented Cross (S).txt"] [data-cell="none"]').text()).toBe('not in the catalog')
    // the way back names the book it accompanies, its record a link
    expect(view.find('[data-part="trail-book"]').attributes('href')).toBe('#/licensed/sources/an_invented_book_src')
  })

  it('says why where the catalog holds none of its units', async () => {
    vi.mocked(getCodeWork).mockResolvedValue(aWork({ units: 0, categories: [], catalog_said: 'an invented why' }))
    const view = mount(CodeWorkView, { props: { kb: 'licensed', work: KEY }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(view.find('[data-part="categories"]').exists()).toBe(false)
    expect(view.find('[data-part="catalog-said"]').text()).toBe('an invented why')
  })

  it('shows a file numbered as its text, the lines asked for marked and scrolled to, its neighbours in the pager', async () => {
    const scrolled: string[] = []
    const scrollIntoView = vi.fn(function (this: Element) { scrolled.push(this.getAttribute('data-line') ?? '') })
    Element.prototype.scrollIntoView = scrollIntoView
    const view = mount(CodePageView, { props: { kb: 'licensed', work: KEY, label: BAND, lines: '2-3' },
      global: { plugins: [createPinia(), router] } })
    await flushPromises()
    const code = view.find('pre.numbered-text[data-part="code"]')
    // the text as given, the numbers beside it and never in it
    expect(code.element.textContent).toBe(TEXT)
    expect(code.findAll('.numbered-line').map(line => line.attributes('data-line'))).toEqual(['1', '2', '3', '4'])
    expect(code.findAll('.numbered-line.marked').map(line => line.attributes('data-line'))).toEqual(['2', '3'])
    expect(scrolled).toEqual(['2'])
    expect(view.find('[data-label="Lines"]').text()).toContain('1–4 · 2–3 asked for')
    expect(view.find('[data-part="derived"]').text()).toBe('derived (an invented model), never quoted')
    expect(view.find('[data-part="previous"]').attributes('href')).toBe(`#/licensed/code/${KEY}/Functions%2FInvented%20Average.txt`)
    expect(view.find('[data-part="next"]').text()).toContain('Invented Cross (S)')
    expect(view.find('[data-part="position"]').text()).toBe('file 2 of 3')
    // no image and no reading, which a file has not
    expect(view.find('img').exists()).toBe(false)
    expect(view.find('[data-part="trail-work"]').attributes('href')).toBe(`#/licensed/code/${KEY}`)
  })

  it('says a file the catalog holds nothing of, and marks nothing without lines asked for', async () => {
    vi.mocked(getCodePage).mockResolvedValue(aPage({ unit: null }))
    const view = mount(CodePageView, { props: { kb: 'licensed', work: KEY, label: BAND }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(view.find('[data-label="Unit"]').text()).toContain('not in the catalog')
    expect(view.findAll('.numbered-line.marked')).toHaveLength(0)
  })
})

describe('the one numbered look (221.a)', () => {
  it('keeps the text as stored, numbers each line, and marks a range and a line of its own', () => {
    const view = mount(NumberedText, { props: { text: 'a\nb\nc', marked: { first: 2, last: 3 }, marks: new Map([[1, 'error-named']]) } })
    expect(view.element.textContent).toBe('a\nb\nc')
    expect(view.findAll('.numbered-line.marked').map(line => line.attributes('data-line'))).toEqual(['2', '3'])
    expect(view.find('[data-line="1"]').attributes('data-mark')).toBe('error-named')
    expect(view.find('[data-line="1"]').classes()).toContain('error-named')
  })
})

describe('the Librarian page\'s code answers (#12)', () => {
  function aCall(overrides: Partial<LibrarianCall>): LibrarianCall {
    return { tool: 'code_catalog', arguments: {}, head: { state: 'found', seconds: 0.012, model_ran: false, model_said: 'no model' },
      answer: { state: 'found' }, ...overrides }
  }

  it('draws the catalog\'s units in the code work page\'s rows, each opening its file here', async () => {
    await router.push('/librarian')
    const view = mount(LibrarianAnswer, { props: { call: aCall({ catalog: { total: 1, categories: [{ category: 'volatility', units: 1 }],
      units: [{ work: KEY, page: BAND, code_language: 'EasyLanguage', companion_of: 'an_invented_book',
        view: `/licensed/code/${KEY}/Indicators%2FInvented%20Band%20(I).txt?lines=1-4`, unit: aUnit() }] } }) },
    global: { plugins: [createPinia(), router] } })
    expect(view.find('[data-part="catalog-categories"]').text()).toBe('volatility 1')
    const row = view.find(`[data-part="catalog"] tr[data-file="${KEY}|${BAND}"]`)
    expect(row.find('a').attributes('href')).toBe(`#/licensed/code/${KEY}/Indicators%2FInvented%20Band%20(I).txt?lines=1-4`)
    expect(row.find('[data-part="derived"]').text()).toBe('derived (an invented model), never quoted')
  })

  it('shows a code file a client opened numbered, a page of text as before', () => {
    const page = { work: KEY, title: 'An Invented Code', page: BAND, page_said: BAND, text: 'a\nb', kind: 'code' }
    const code = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'open_page', page }) }, global: { plugins: [createPinia(), router] } })
    expect(code.findAll('[data-part="page-text"] .numbered-line')).toHaveLength(2)
    const text = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'open_page', page: { ...page, kind: 'text' } }) },
      global: { plugins: [createPinia(), router] } })
    expect(text.find('pre[data-part="page-text"]').text()).toBe('a\nb')
    expect(text.find('.numbered-line').exists()).toBe(false)
  })
})
