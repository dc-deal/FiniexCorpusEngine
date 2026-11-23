import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { callLibrarian, getLibrarian } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import LibrarianAnswer from '@/components/librarian/LibrarianAnswer.vue'
import SchemaForm from '@/components/librarian/SchemaForm.vue'
import { argumentsFromQuery, argumentsOf, queryOf, valuesOf } from '@/librarian_form'
import { router } from '@/router'
import LibrarianView from '@/views/LibrarianView.vue'
import type { LibrarianCall, LibrarianField, LibrarianInfo, LibrarianTool } from '@/types/api/librarian_types'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getLibrarian: vi.fn(),
  callLibrarian: vi.fn(),
}))

// a view of an earlier test, left mounted, would answer the shared router's next address with a call of its own
enableAutoUnmount(afterEach)

// invented fields of every kind a form draws, as the API parts a tool's input schema
function aField(overrides: Partial<LibrarianField> & Pick<LibrarianField, 'name' | 'kind'>): LibrarianField {
  return { required: false, default: null, server_default: null, choices: [], minimum: null, maximum: null, description: null,
    folded: false, ...overrides }
}

const FIELDS: LibrarianField[] = [
  aField({ name: 'question', kind: 'text', required: true }),
  aField({ name: 'hits', kind: 'integer', default: 10, server_default: 10, minimum: 1, maximum: 50 }),
  aField({ name: 'keywords', kind: 'list', folded: true }),
  aField({ name: 'router', kind: 'boolean', default: false, server_default: true }),
  aField({ name: 'corpus', kind: 'choice', default: 'all', server_default: 'all', choices: ['all', 'free', 'licensed'] }),
]

function aTool(name: string, fields: LibrarianField[] = [], overrides: Partial<LibrarianTool> = {}): LibrarianTool {
  return { name, label: { search: 'search (BM25)', semantic_search: 'semantic (hybrid)' }[name] ?? name, description: `Invented: what ${name} does. Local, no model, milliseconds, free.`, cost_said: 'local · no model · milliseconds · free',
    fields, folded_title: null, input_schema: {}, ...overrides }
}

const INFO: LibrarianInfo = { enabled: true, url: 'http://librarian:8765/mcp', why_not: null, tools: [
  aTool('works'), aTool('search', [aField({ name: 'query', kind: 'text', required: true }), FIELDS[1]]),
  aTool('semantic_search', FIELDS, { folded_title: 'your own translation, which spares the router',
    cost_said: 'about two seconds · a paid API · a fraction of a cent' }),
] }

function aCall(overrides: Partial<LibrarianCall> = {}): LibrarianCall {
  return { tool: 'search', arguments: {}, head: { state: 'found', seconds: 0.012, model_ran: false, model_said: 'no model' },
    answer: { state: 'found', hits: [] }, ...overrides }
}

describe('the Librarian\'s form and address (L1.a)', () => {
  it('opens a form on its defaults, the view\'s own where it has one, and sends what was set in each field\'s type', () => {
    const values = valuesOf(FIELDS)
    expect(values).toEqual({ question: '', hits: '10', keywords: '', router: false, corpus: 'all' })
    const args = argumentsOf(FIELDS, { ...values, question: ' what is a bond discount? ', keywords: 'bond, discount' })
    // the server's defaults left out; the router's off sent, since the view's form starts other than the server would
    expect(args).toEqual({ question: 'what is a bond discount?', keywords: ['bond', 'discount'], router: false })
    expect(argumentsOf(FIELDS, { ...values, question: 'q', router: true, hits: '3' })).toEqual({ question: 'q', hits: 3, router: true })
    // a number the field cannot read goes as written: the server says what is wrong with it, as it would tell a client
    expect(argumentsOf(FIELDS, { ...values, question: 'q', hits: 'ten' })).toEqual({ question: 'q', hits: 'ten', router: false })
  })

  it('puts a call in the address and reads it back the same, and a tab alone calls nothing that requires an argument', () => {
    const args = { question: 'what is a bond discount?', keywords: ['bond', 'discount'], hits: 3, router: false }
    const query = queryOf('semantic_search', args)
    expect(query).toEqual({ tool: 'semantic_search', question: 'what is a bond discount?', keywords: ['bond', 'discount'], hits: '3', router: 'false' })
    expect(argumentsFromQuery(FIELDS, query as Record<string, string | string[]>)).toEqual(args)
    expect(argumentsFromQuery(FIELDS, { tool: 'semantic_search' })).toBeNull()
    expect(argumentsFromQuery([], { tool: 'works' })).toEqual({})
  })

  it('draws a control per argument by its kind, the folded ones in a fold beneath, and says each change', async () => {
    const form = mount(SchemaForm, { props: { fields: FIELDS, values: valuesOf(FIELDS), foldedTitle: 'your own translation' } })
    expect(form.find('[data-field="router"] input').attributes('type')).toBe('checkbox')
    expect((form.find('[data-field="router"] input').element as HTMLInputElement).checked).toBe(false)
    const hits = form.find('[data-field="hits"] input')
    expect([hits.attributes('type'), hits.attributes('min'), hits.attributes('max')]).toEqual(['number', '1', '50'])
    expect(form.find('[data-field="hits"] [data-part="field-default"]').text()).toBe('default 10')
    expect(form.findAll('[data-field="corpus"] option').map(option => option.text())).toEqual(['all', 'free', 'licensed'])
    expect(form.find('[data-field="question"] input').attributes('required')).toBeDefined()
    const folded = form.find('[data-part="folded-fields"]')
    expect([folded.find('summary').text(), folded.find('[data-field="keywords"]').exists()]).toEqual(['your own translation', true])
    await form.find('[data-field="question"] input').setValue('a question')
    expect(form.emitted('update:values')!.at(-1)![0]).toMatchObject({ question: 'a question' })
    await form.find('form').trigger('submit')
    expect(form.emitted('submit')).toHaveLength(1)
  })
})

describe('the Librarian\'s answers, each tool\'s own parts (L1.a)', () => {
  it('draws hits as cards with their page in this view, the whole chunk folded, and the head\'s floor in the warning role', () => {
    const view = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'semantic_search',
      head: { state: 'found', count: '1 hit', seconds: 2.04, model_ran: true, model_said: 'a model ran: an-invented-model',
        relevance: 0.41, relevance_floor: 0.45, below_floor: true,
        floor_said: 'below the floor (0.410 < 0.450): the books likely say nothing on this' },
      plan: { search_query: 'bond discount', concept_query: 'bond pricing', keywords: ['bond'], behaviour: 'answer', fell_back: false },
      hits: [{ rank: 1, knowledge_base: 'free', work: 'a-work', title: 'An Invented Book', edition_said: '2nd edition, 2001', page: '44',
        page_said: 'p. 27 (PDF p. 44)', section: '4 Bonds', score: 0.41, snippet: 'a discount', text: 'the whole chunk of the page',
        route: 'vision reading', licence: 'CC BY', terms_missing: [], view: '/free/sources/a_work/page/44' }],
      answer: { state: 'found', hits: [{ title: 'An Invented Book' }] } }) }, global: { plugins: [router] } })
    const head = view.find('[data-part="call-head"]')
    expect(head.find('[data-part="floor"]').classes()).toContain('warning')
    expect([head.find('[data-part="took"]').text(), head.find('[data-part="model"]').text()]).toEqual(['2.0 s', 'a model ran: an-invented-model'])
    expect(view.find('[data-part="plan"]').text()).toContain('bond discount')
    const card = view.find('[data-hit="1"]')
    expect(card.find('[data-part="hit-page"]').attributes('href')).toBe('#/free/sources/a_work/page/44')
    expect(card.find('[data-part="hit-page"]').text()).toBe('p. 27 (PDF p. 44)')
    expect(card.find('[data-part="whole-chunk"] .chunk-text').text()).toBe('the whole chunk of the page')
    // the answer as it came, one click away
    expect(view.find('[data-part="raw-json"] summary').text()).toBe('raw JSON')
    expect(JSON.parse(view.find('[data-part="raw-json"] pre').text())).toEqual({ state: 'found', hits: [{ title: 'An Invented Book' }] })
  })

  it('draws the works as a table, a subject\'s works with each best section a call of open_page, and contents as a tree', () => {
    const works = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'works', works: [{ work: 'a-work', title: 'An Invented Book',
      edition_said: '2nd edition, 2001', knowledge_base: 'free', pages: 12, route: 'vision reading', kept_editions: ['a-work-1st'] }] }) },
    global: { plugins: [router] } })
    expect(works.find('[data-part="works-table"] tr[data-work="a-work"]').text()).toContain('An Invented Book')
    expect(works.find('[data-part="kept-editions"]').text()).toBe('kept beside it: a-work-1st')
    // a kept edition says the edition searched and its own pages, which open by its key (#14)
    const kept = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'works', works: [{ work: 'a-work-1st', title: 'An Invented Book',
      kept_for: 'a-work', pages_kept: 312, kept_editions: [] }] }) }, global: { plugins: [router] } })
    expect(kept.find('[data-part="kept-for"]').text().replace(/\s+/g, ' ')).toBe('kept: a-work is searched; its own 312 pages open by its key')
    const found = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'search_works', found_works: [{ rank: 1, work: 'a-work',
      title: 'An Invented Book', pages_matching: 9, pages_with_every_term: 2, best_sections: [{ section: '4 Bonds', page: '88',
        page_said: 'p. 80 (PDF p. 88)', score: 4 }] }] }) }, global: { plugins: [router] } })
    expect(found.find('[data-part="pages-matching"]').text()).toBe('9 pages hold a word, 2 every one')
    expect(found.find('[data-part="open-page"]').attributes('href')).toBe('#/librarian?tool=open_page&work=a-work&page=88')
    const toc = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'toc', contents: { work: 'a-work', title: 'An Invented Book',
      source: 'pdf bookmarks', left_out: 3, entries: [{ level: 1, title: 'One', page: '5' }, { level: 2, title: 'One point one', page: '6' }] } }) },
    global: { plugins: [router] } })
    const entries = toc.findAll('[data-part="contents-tree"] .entry')
    expect(entries.map(entry => entry.attributes('data-level'))).toEqual(['1', '2'])
    expect(entries[1].attributes('style')).toContain('calc(1 * var(--indent-step))')
    expect(toc.find('[data-part="contents-tree"]').text()).toContain('3 deeper entries left out')
  })

  it('draws an opened page as its text and an image with what it is', () => {
    const page = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'open_page', page: { work: 'a-work', title: 'An Invented Book',
      page: '5', page_said: 'PDF p. 5', route: 'text layer', text: 'The page, <b>word</b> for word.', view: '/free/sources/a_work/page/5' } }) },
    global: { plugins: [router] } })
    expect(page.find('[data-part="page-text"]').text()).toBe('The page, <b>word</b> for word.')
    expect(page.find('[data-part="page-text"] b').exists()).toBe(false)
    expect(page.find('[data-part="page-view"]').attributes('href')).toBe('#/free/sources/a_work/page/5')
    const image = mount(LibrarianAnswer, { props: { call: aCall({ tool: 'page_image', image: { src: 'data:image/png;base64,iVBORw0KGgo=',
      page_said: 'PDF p. 5', described: [['what', 'a render at 150 dpi'], ['pixels', '1275 × 1650']] } }) }, global: { plugins: [router] } })
    expect(image.find('[data-part="sent-image"] img').attributes('src')).toBe('data:image/png;base64,iVBORw0KGgo=')
    expect(image.findAll('[data-part="sent-image"] .line-label').map(label => label.text())).toEqual(['what:', 'pixels:'])
  })
})

describe('LibrarianView (L1.a)', () => {
  beforeEach(async () => {
    vi.mocked(getLibrarian).mockReset().mockResolvedValue(INFO)
    vi.mocked(callLibrarian).mockReset().mockResolvedValue(aCall())
    localStorage.clear()
    await router.push({ name: 'librarian' })
  })

  function mountView() {
    return mount(LibrarianView, { global: { plugins: [createPinia(), router] } })
  }

  it('stands every tool as a tab in the API\'s order, each with its description and its line on cost', async () => {
    const view = mountView()
    await flushPromises()
    // the two search tools by the view's names, the code name in the tab's head (the standing rule)
    expect(view.findAll('[data-part="tabs"] button').map(tab => tab.text())).toEqual(['works', 'search (BM25)', 'semantic (hybrid)'])
    expect(view.find('[data-part="tool-name"]').text()).toBe('tool: works')
    // the first tab chosen
    expect(view.find('[data-tab="works"]').attributes('aria-pressed')).toBe('true')
    expect(view.find('[data-part="description"] .fold-count').text()).toBe('· local · no model · milliseconds · free')
    // works, which requires nothing, called on the page's own address, a client's first call; its tab names it, no second
    expect(vi.mocked(callLibrarian)).toHaveBeenCalledWith('works', {})
    await view.find('[data-tab="works"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(callLibrarian)).toHaveBeenCalledTimes(1)
  })

  it('keeps the router off by default and passes it through, and the address names the run', async () => {
    await router.push({ name: 'librarian', query: { tool: 'semantic_search' } })
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="tool-name"]').text()).toBe('tool: semantic_search')
    expect((view.find('[data-field="router"] input').element as HTMLInputElement).checked).toBe(false)
    expect(vi.mocked(callLibrarian)).not.toHaveBeenCalled()  // a tab alone calls nothing that requires an argument
    await view.find('[data-field="question"] input').setValue('what is a bond discount?')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect(vi.mocked(callLibrarian)).toHaveBeenCalledWith('semantic_search', { question: 'what is a bond discount?', router: false })
    expect(router.currentRoute.value.query).toEqual({ tool: 'semantic_search', question: 'what is a bond discount?', router: 'false' })
    expect(vi.mocked(callLibrarian)).toHaveBeenCalledTimes(1)  // the address read back makes no second call
  })

  it('turns and counts on Run while the call is out, and takes no second click (21 Nov)', async () => {
    let answer: (call: LibrarianCall) => void = () => undefined
    vi.mocked(callLibrarian).mockReturnValue(new Promise(resolve => { answer = resolve }))
    await router.push({ name: 'librarian', query: { tool: 'search', query: 'kelly' } })
    const view = mountView()
    await flushPromises()
    const run = view.find('[data-part="run"]')
    expect(run.attributes('disabled')).toBeDefined()
    expect(run.find('[data-part="running-words"]').text()).toBe('calling the librarian … 0 s')
    answer(aCall())
    await flushPromises()
    expect(view.find('[data-part="run"]').text()).toBe('Run')
    expect(view.find('[data-part="run"]').attributes('disabled')).toBeUndefined()
  })

  it('makes the call a pasted address names, once, its arguments in its fields\' types', async () => {
    await router.push({ name: 'librarian', query: { tool: 'search', query: 'kelly fraction', hits: '3' } })
    const view = mountView()
    await flushPromises()
    expect(vi.mocked(callLibrarian)).toHaveBeenCalledWith('search', { query: 'kelly fraction', hits: 3 })
    expect((view.find('[data-field="query"] input').element as HTMLInputElement).value).toBe('kelly fraction')
    expect(view.find('[data-part="call-head"]').exists()).toBe(true)
    // the old search's and chat's addresses open their tabs
    await router.push('/search?q=kelly')
    expect(router.currentRoute.value.fullPath).toBe('/librarian?tool=search&query=kelly')
    await router.push('/chat')
    expect(router.currentRoute.value.fullPath).toBe('/librarian?tool=semantic_search')
  })

  it('says in words when the librarian does not answer, and a failed call where its answer would stand', async () => {
    vi.mocked(getLibrarian).mockResolvedValue({ enabled: true, url: 'http://librarian:8765/mcp', tools: [],
      why_not: 'The librarian does not answer at http://librarian:8765/mcp: ConnectError: connection refused' })
    const down = mountView()
    await flushPromises()
    expect(down.find('[data-part="why-not"]').text()).toContain('does not answer')
    expect(down.find('[data-part="tabs"]').exists()).toBe(false)
    vi.mocked(getLibrarian).mockResolvedValue(INFO)
    vi.mocked(callLibrarian).mockRejectedValue(new ApiError(502, 'The call failed on its way: TimeoutError'))
    await router.push({ name: 'librarian', query: { tool: 'search', query: 'kelly' } })
    const failed = mountView()
    await flushPromises()
    expect(failed.text()).toContain('The call failed on its way: TimeoutError')
  })
})
