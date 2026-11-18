import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getHtmlArticle, getHtmlWork } from '@/api/api_client'
import { router } from '@/router'
import HtmlArticleView from '@/views/HtmlArticleView.vue'
import HtmlWorkView from '@/views/HtmlWorkView.vue'
import type { HtmlArticle, HtmlSection, HtmlWork } from '@/types/api/html_types'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getHtmlWork: vi.fn(),
  getHtmlArticle: vi.fn(),
}))

enableAutoUnmount(afterEach)

const WIKIPEDIA = 'wikipedia_trading_set'

/** An HTML work as the API serves it: invented counts over a free work's headings. */
function aWork(overrides: Partial<HtmlWork> = {}): HtmlWork {
  return {
    knowledge_base: 'free', source_id: WIKIPEDIA, title: 'Wikipedia articles on trading and risk', authors: 'Wikipedia contributors',
    licence: 'CC BY-SA 4.0', licence_url: null, route: 'html, parsed by section', why_not: null, sections: 3, chunks: 5,
    outline: [
      { id: 'h1', title: 'Algorithmic trading', parent: null, level: 1, label: 's1', first: 's1', last: 's3', sections: 3, chunks: 5 },
      { id: 'h2', title: 'History', parent: 'h1', level: 2, label: null, first: 's2', last: 's3', sections: 2, chunks: 4 },
      { id: 'h3', title: 'Early developments', parent: 'h2', level: 3, label: 's2', first: 's2', last: 's2', sections: 1, chunks: 2 },
      { id: 'h4', title: 'Recent developments', parent: 'h2', level: 3, label: 's3', first: 's3', last: 's3', sections: 1, chunks: 2 },
    ],
    rows: [
      { label: 's1', heading_path: 'Algorithmic trading', chunks: 1, characters: 400 },
      { label: 's2', heading_path: 'Algorithmic trading > History > Early developments', chunks: 2, characters: 900 },
      { label: 's3', heading_path: 'Algorithmic trading > History > Recent developments', chunks: 2, characters: 700 },
    ],
    ...overrides,
  }
}

function aSection(overrides: Partial<HtmlSection> = {}): HtmlSection {
  return {
    knowledge_base: 'free', source_id: WIKIPEDIA, work_title: 'Wikipedia articles on trading and risk', authors: 'Wikipedia contributors',
    licence: 'CC BY-SA 4.0', licence_url: 'https://example.org/licence', label: 's2',
    heading_path: 'Algorithmic trading > History > Early developments', url: 'https://example.org/wiki#Early', text: 'w0 w1 w2 w3 w4',
    chunks: [
      { id: `${WIKIPEDIA}:0001:000`, number: 1, text: 'w0 w1 w2', start: 0, end: 8, overlap: 0, tokens: 3 },
      { id: `${WIKIPEDIA}:0001:001`, number: 2, text: 'w2 w3 w4', start: 6, end: 14, overlap: 2, tokens: 3 },
    ],
    not_found: 0, previous: 's1', next: 's3', original: '<h3 id="Early">Early developments</h3><p>w0 w1 <span data-image="A chart"></span></p>',
    original_why_not: null, dropped: false,
    splitter: { splitter: 'RecursiveCharacterTextSplitter', chunk_size: 1000, chunk_overlap: 200 }, ...overrides,
  }
}

function mountWork() {
  return mount(HtmlWorkView, { props: { kb: 'free', work: WIKIPEDIA }, global: { plugins: [createPinia(), router] } })
}

/** An article as the API serves it: its sections, a heading with no text of its own before them, and its neighbours. */
function anArticle(sections: HtmlSection[] = [aSection()], overrides: Partial<HtmlArticle> = {}): HtmlArticle {
  return {
    knowledge_base: 'free', source_id: WIKIPEDIA, work_title: 'Wikipedia articles on trading and risk', title: 'Algorithmic trading',
    label: 's2', previous: 's1', previous_title: 'Kelly criterion', next: 's9', next_title: 'Sharpe ratio',
    authors: 'Wikipedia contributors', licence: 'CC BY-SA 4.0', licence_url: 'https://example.org/licence',
    splitter: { splitter: 'RecursiveCharacterTextSplitter', chunk_size: 1000, chunk_overlap: 200 },
    entries: [{ label: null, title: 'History', level: 2, section: null },
      ...sections.map(section => ({ label: section.label, title: section.heading_path.split(' > ').at(-1)!, level: 3, section }))],
    ...overrides,
  }
}

function mountSection(section = 's2') {
  return mount(HtmlArticleView, { props: { kb: 'free', work: WIKIPEDIA, section }, global: { plugins: [createPinia(), router] } })
}

describe('HtmlWorkView', () => {
  beforeEach(() => {
    vi.mocked(getHtmlWork).mockReset()
    localStorage.clear()
  })

  it('stands the outline by heading, a heading with its own section opening it, one without text naming its range only', async () => {
    vi.mocked(getHtmlWork).mockResolvedValue(aWork())
    const view = mountWork()
    await flushPromises()
    expect(view.find('.summary').text()).toContain('3 sections by heading · 5 chunks')
    const root = view.find('[data-node="h1"]')
    expect(root.find('a.unit-title').attributes('href')).toBe(`#/free/html/${WIKIPEDIA}/s1`)
    expect(root.find('.unit-range').text()).toBe('s1–s3')
    // its own line, not its children's
    const history = view.find('[data-node="h2"] > summary')
    expect(history.find('a.unit-title').exists()).toBe(false)
    expect(history.find('.unit-title').text()).toBe('History')
    expect(history.find('.unit-count').text()).toBe('2 sections · 4 chunks')
    // a heading with nothing beneath it is a row with nothing to unfold
    expect(view.find('[data-node="h3"]').element.tagName).toBe('DIV')
  })

  it('greys a heading dropped as noise at its place, opening its original', async () => {
    const work = aWork()
    work.outline.push({ id: 'x1', title: 'See also', parent: 'h1', level: 2, label: null, first: null, last: null, sections: 0, chunks: 0, dropped: 'd1' })
    vi.mocked(getHtmlWork).mockResolvedValue(work)
    const view = mountWork()
    await flushPromises()
    const dropped = view.find('[data-node="x1"]')
    expect(dropped.attributes('data-part')).toBe('dropped')
    expect(dropped.find('a').attributes('href')).toBe(`#/free/html/${WIKIPEDIA}/d1`)
    expect(dropped.text()).toContain('dropped as noise: not indexed')
  })

  it('lists every section flat in the table, each opening its chunks', async () => {
    vi.mocked(getHtmlWork).mockResolvedValue(aWork())
    const view = mountWork()
    await flushPromises()
    await view.findAll('.view-switch button')[1].trigger('click')
    const rows = view.findAll('tbody tr[data-section]')
    expect(rows.map(row => row.attributes('data-section'))).toEqual(['s1', 's2', 's3'])
    expect(rows[1].find('a').attributes('href')).toBe(`#/free/html/${WIKIPEDIA}/s2`)
    expect(rows[1].text()).toContain('Algorithmic trading > History > Early developments')
  })

  it('says how to build the index where it is not built', async () => {
    vi.mocked(getHtmlWork).mockResolvedValue(aWork({ why_not: 'No search index on this machine yet: `python -m backend.ingestion.build`', outline: [], rows: [] }))
    const view = mountWork()
    await flushPromises()
    expect(view.find('.why-not').text()).toContain('backend.ingestion.build')
    expect(view.find('.outline').exists()).toBe(false)
  })
})

describe('HtmlArticleView', () => {
  beforeEach(() => {
    vi.mocked(getHtmlArticle).mockReset()
  })

  it('shows the whole article on one scroll, the section asked for marked, and moves within it without asking again', async () => {
    const recent = aSection({ label: 's3', heading_path: 'Algorithmic trading > History > Recent developments', url: null,
      original: '<h3 id="Recent">Recent developments</h3><p>Later.</p>' })
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle([aSection(), recent]))
    const view = mountSection()
    await flushPromises()
    expect(view.find('.view-title').text()).toBe('Algorithmic trading')
    // every place of the article in the work's order: a heading without text of its own, then each section with its chunks
    expect(view.findAll('article.entry').map(entry => entry.attributes('data-entry') ?? entry.find('.entry-heading').text()))
      .toEqual(['History', 's2', 's3'])
    expect(view.find('[data-entry="s3"] [data-part="original"] h3').text()).toBe('Recent developments')
    expect(view.find('[data-entry="s2"]').classes()).toContain('chosen')
    // the contents lead to each section within the same scroll
    expect(view.findAll('.contents-list a').map(link => link.attributes('href')))
      .toEqual([`#/free/html/${WIKIPEDIA}/s2`, `#/free/html/${WIKIPEDIA}/s3`])
    await view.setProps({ section: 's3' })
    await flushPromises()
    expect(view.find('[data-entry="s3"]').classes()).toContain('chosen')
    expect(vi.mocked(getHtmlArticle)).toHaveBeenCalledTimes(1)
  })

  it('shows every chunk in its box with its place, the characters it shares with the one before marked', async () => {
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle())
    const view = mountSection()
    await flushPromises()
    const chunks = view.findAll('.chunk')
    expect(chunks).toHaveLength(2)
    expect(chunks[1].find('.chunk-head').text()).toContain('chunk 2 of 2')
    expect(chunks[1].find('.chunk-head').text()).toContain('characters 6–14')
    expect(chunks[1].find('.overlap').text()).toBe('w2')
    expect(chunks[1].find('.chunk-text').text()).toBe('w2 w3 w4')
    expect(chunks[0].find('.overlap').exists()).toBe(false)
    // what the dashed line is, with the splitter's own figures: a hint on demand, never a browser tooltip (203.a); how much
    // a chunk shares, and with which, in the card of its count
    expect(view.find('[data-part="overlap-legend"]').exists()).toBe(false)
    expect(chunks[1].find('.overlap').attributes('title')).toBeUndefined()
    await chunks[1].find('.chunk-head .hover-card-host').trigger('mouseenter')
    const card = chunks[1].find('[data-part="hover-card"]')
    expect(card.find('.card-title').text()).toBe('Shared with the chunk before')
    expect(card.find('[data-row="with"] .card-value').text()).toBe('chunk 1')
    await view.find('[data-part="overlap-hint-button"]').trigger('click')
    expect(view.find('[data-part="overlap-legend"]').text()).toContain('Formulas stand here as the LaTeX the index holds')
  })

  it('offers no hint on the dashed line where no chunk shares text with the one before', async () => {
    const section = aSection()
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle([{ ...section, chunks: [section.chunks[0]] }]))
    const view = mountSection()
    await flushPromises()
    expect(view.find('[data-part="overlap-hint-button"]').exists()).toBe(false)
    expect(view.find('[data-part="overlap-legend"]').exists()).toBe(false)
  })

  it('draws each line break of the indexed text as a paragraph, the shared characters marked across it', async () => {
    const text = 'w0 w1\nw2 w3\nw4'
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle([aSection({ text, chunks: [
      { id: `${WIKIPEDIA}:0001:000`, number: 1, text: 'w0', start: 0, end: 2, overlap: 0, tokens: 1 },
      // shares 'w0 w1\nw2' with the chunk before: the mark runs across the break, in both paragraphs
      { id: `${WIKIPEDIA}:0001:001`, number: 2, text, start: 0, end: text.length, overlap: 8, tokens: 4 },
    ] })]))
    const view = mountSection()
    await flushPromises()
    const paragraphs = view.findAll('.chunk')[1].findAll('.paragraph')
    expect(paragraphs.map(paragraph => paragraph.text())).toEqual(['w0 w1', 'w2 w3', 'w4'])
    expect(paragraphs.map(paragraph => paragraph.find('.overlap').exists() ? paragraph.find('.overlap').text() : '')).toEqual(['w0 w1', 'w2', ''])
  })

  it('names the work\'s licence and leads to each section\'s original and to the articles beside it', async () => {
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle())
    const view = mountSection()
    await flushPromises()
    expect(view.find('[data-part="attribution"]').text()).toContain('CC BY-SA 4.0')
    expect(view.find('[data-entry="s2"] [data-part="source"]').attributes('href')).toBe('https://example.org/wiki#Early')
    expect(view.find('[data-part="previous"] .pager-label').text()).toBe('Kelly criterion')
    expect(view.find('[data-part="previous"]').attributes('href')).toBe(`#/free/html/${WIKIPEDIA}/s1`)
    expect(view.find('[data-part="next"] .pager-label').text()).toBe('Sharpe ratio')
    // before the title, whose length varies, so the boxes never move with it
    const head = view.find('.article-head').element
    expect(head.firstElementChild?.classList.contains('pager')).toBe(true)
  })

  it('shows the section\'s stripped original on the left, sanitised, an image as its alt text', async () => {
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle())
    const view = mountSection()
    await flushPromises()
    const original = view.find('[data-part="original"]')
    expect(original.find('h3#Early').text()).toBe('Early developments')
    expect(original.find('span[data-image="A chart"]').exists()).toBe(true)
  })

  it('stands a heading dropped as noise greyed at its place, with its original and no chunks', async () => {
    const dropped = aSection({ label: 'd1', heading_path: 'See also', text: '', chunks: [], previous: null, url: null,
      next: 'd2', dropped: true, original: '<h2 id="See_also">See also</h2>' })
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle([aSection(), dropped]))
    const view = mountSection('d1')
    await flushPromises()
    const entry = view.find('[data-entry="d1"]')
    expect(entry.classes()).toEqual(expect.arrayContaining(['dropped', 'chosen']))
    expect(entry.find('[data-part="dropped"]').text()).toContain('not indexed, so no chunks')
    expect(entry.findAll('.chunk')).toHaveLength(0)
    expect(entry.find('[data-part="original"] h2').text()).toBe('See also')
  })

  it('says so where a chunk was not found in the section\'s text', async () => {
    const section = aSection()
    section.chunks[1] = { ...section.chunks[1], start: null, end: null, overlap: 0 }
    vi.mocked(getHtmlArticle).mockResolvedValue(anArticle([{ ...section, not_found: 1 }]))
    const view = mountSection()
    await flushPromises()
    expect(view.find('.not-found').text()).toContain('1 of these chunks were not found')
    expect(view.findAll('.chunk')[1].find('.missing').exists()).toBe(true)
  })
})
