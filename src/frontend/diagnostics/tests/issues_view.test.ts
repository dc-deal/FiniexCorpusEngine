import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getIssues } from '@/api/api_client'
import { router } from '@/router'
import IssuesView from '@/views/IssuesView.vue'
import type { IssueList } from '@/types/api/page_types'
import { aCheck, anIssueList, JUDGED_BAD_ROUTE, CONTENT_FILTER, DECLINED_ROUTE, KELLY } from './page_fixture'
import { facetOption, pickFacet } from './facet_harness'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getIssues: vi.fn(),
}))

// attached, so the bar's panels, portalled to the document, can be opened; unmounted after each test, so none stays behind
enableAutoUnmount(afterEach)

function mountView() {
  return mount(IssuesView, { global: { plugins: [createPinia(), router] }, attachTo: document.body })
}

function listed(view: ReturnType<typeof mountView>): (string | undefined)[] {
  return view.findAll('tbody tr[data-page]').map(row => row.attributes('data-page'))
}

// invented over a free work: a page the judge found bad whose reading the search serves all the same
const SERVED_DESPITE = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2): the judge\'s findings lie on blocks never quoted'

// a second knowledge base, its work invented: no licensed title or text stands in a tracked file
function withALicensedWork(): IssueList {
  const free = anIssueList()
  return {
    knowledge_bases: [{ value: 'free', count: 2 }, { value: 'licensed', count: 1 }],
    states: [{ value: 'issue', count: 1 }, { value: 'blocked', count: 2 }],
    people: [],
    reviews: [],
    categories: [],
    rows: [...free.rows, {
      knowledge_base: 'licensed',
      source_id: 'a_licensed_book',
      title: 'a_licensed_book',
      pdf_page: 5,
      route: DECLINED_ROUTE,
      check: aCheck({ state: 'blocked', judged: false, verdict: null, reasons: [{ value: 'refused', count: 1 }] }),
      error_message: null,
      from_text_layer: true,
      apart: false,
    }],
  }
}

describe('IssuesView', () => {
  beforeEach(async () => {
    vi.mocked(getIssues).mockReset()
    // the router is shared: no test inherits the choice another one put in the address
    await router.push('/issues')
  })

  it('lists every page to look at, one click from its page view', async () => {
    vi.mocked(getIssues).mockResolvedValue(anIssueList())
    const view = mountView()
    await flushPromises()
    expect(view.find('.view-title').text()).toBe('Issues')
    const rows = view.findAll('tbody tr[data-page]')
    expect(rows).toHaveLength(2)
    expect(rows[1].find('a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/9`)
    expect(rows[1].text()).toContain('omission ×3')
  })

  it('names a work once above its pages, with its knowledge base', async () => {
    vi.mocked(getIssues).mockResolvedValue(anIssueList())
    const view = mountView()
    await flushPromises()
    expect(view.findAll('.work-row')).toHaveLength(1)
    expect(view.find('.work-row').text()).toContain('Kelly criterion paper')
    expect(view.find('.work-row [data-kb="free"]').exists()).toBe(true)
    expect(view.findAll('tbody tr[data-page]').every(row => !row.text().includes('Kelly criterion paper'))).toBe(true)
  })

  it('says why a page\'s text comes from its text layer: in the provider\'s words, else by its route', async () => {
    vi.mocked(getIssues).mockResolvedValue(withALicensedWork())
    const view = mountView()
    await flushPromises()
    expect(view.find(`[data-page="free/${KELLY}/2"] .why`).text()).toBe(CONTENT_FILTER)
    expect(view.find(`[data-page="free/${KELLY}/9"] .why`).text()).toBe(JUDGED_BAD_ROUTE)
    // a page the reader declined: no provider sentence, so its route says it
    expect(view.find('[data-page="licensed/a_licensed_book/5"] .why .route-why').text()).toBe(DECLINED_ROUTE)
  })

  it('says why a page the judge found bad is served all the same, by its route (25.a)', async () => {
    const list = anIssueList()
    list.rows.push({ ...list.rows[1], pdf_page: 11, route: SERVED_DESPITE, from_text_layer: false })
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    expect(view.find('thead').text()).toContain('Why')
    expect(view.find(`[data-page="free/${KELLY}/11"] .why .route-why`).text()).toBe(SERVED_DESPITE)
  })

  it('marks a page a person judged beside its state, and narrows to it in one click (166.a)', async () => {
    const list = anIssueList()
    const accepted = list.rows.find(row => row.check.state === 'issue')!
    accepted.person = { standing: 'accepted', reason: 'the judge miscounted', note: 'eleven T-accounts, as printed', by_a_person: true }
    list.states = list.states.map(count => (count.value === 'issue' ? { ...count, accepted: 1, rejected: 0 } : count))
    list.people = [{ value: 'accepted', count: 1 }]
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    const mark = view.find(`tr[data-page="free/${KELLY}/${accepted.pdf_page}"] [data-person="accepted"]`)
    expect(mark.text()).toBe('accepted')
    // under the pointer a card of data, no browser tooltip (179): the reason and the note
    await mark.element.parentElement!.dispatchEvent(new Event('mouseenter'))
    await flushPromises()
    const card = view.find('[data-part="hover-card"]')
    expect(card.find('[data-row="reason"] .card-value').text()).toBe('the judge miscounted')
    expect(card.find('[data-row="note"] .card-value').text()).toBe('eleven T-accounts, as printed')
    // the person's verdicts are counted once, in their own facet, never again beside a state (the viewer's tip 5, stage C)
    expect((await facetOption(view, 'state', 'issue')).textContent).not.toContain('accepted')
    expect((await facetOption(view, 'person', 'accepted')).querySelector('.facet-count')!.textContent).toBe('1')
    await pickFacet(view, 'person', 'accepted')
    expect(listed(view)).toEqual([`free/${KELLY}/${accepted.pdf_page}`])
  })

  it('lists a page that is not content after the rest, its category beside its state, and narrows by category (172.a)', async () => {
    const list = anIssueList()
    const exercise = list.rows.find(row => row.check.state === 'issue')!
    Object.assign(exercise, { category: 'exercise', page_kind: 'body', apart: true, category_said: 'questions and problems' })
    list.rows.find(row => row !== exercise)!.category = 'content'
    list.categories = [{ value: 'content', count: 1 }, { value: 'exercise', count: 1 }]
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    const apart = view.find('[data-part="apart"]')
    expect(apart.find('h2').text()).toContain('Not content: noted, not repaired')
    expect(apart.findAll('tbody tr[data-page]').map(row => row.attributes('data-page'))).toEqual([`free/${KELLY}/${exercise.pdf_page}`])
    const mark = apart.find('[data-category="exercise"]')
    expect(mark.text()).toBe('exercise')
    // what the category means, as the API says it (177.a), and what the reader called the page
    await mark.element.parentElement!.dispatchEvent(new Event('mouseenter'))
    await flushPromises()
    const card = view.find('[data-part="hover-card"]')
    expect(card.find('[data-row="means"] .card-value').text()).toBe('questions and problems')
    expect(card.find('[data-row="the reader called it"] .card-value').text()).toBe('body')
    // a content page says nothing of its category
    expect(view.findAll('[data-category="content"]')).toHaveLength(0)
    await pickFacet(view, 'category', 'content')
    expect(view.find('[data-part="apart"]').exists()).toBe(false)
    expect(listed(view)).toHaveLength(1)
  })

  it('heads the list with the totals of the API in one line, each state once, the served tally kept, whatever the bar narrows (SC1.a)', async () => {
    const list = anIssueList()
    list.states = [{ value: 'issue', count: 1, served: 1 }, { value: 'blocked', count: 1 }]
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    const totals = () => view.find('[data-part="totals"]')
    expect(totals().find('.line-label').text()).toBe('States:')
    expect(totals().findAll('.state-count').map(count => count.attributes('data-state'))).toEqual(['issue', 'blocked'])
    expect(totals().find('.state-count[data-state="issue"] [data-part="served"]').text()).toContain('1 served')
    await pickFacet(view, 'state', 'blocked')
    expect(listed(view)).toHaveLength(1)
    expect(totals().find('.state-count[data-state="issue"] .count').text()).toBe('1')
  })

  it('narrows the list to the chosen state', async () => {
    vi.mocked(getIssues).mockResolvedValue(anIssueList())
    const view = mountView()
    await flushPromises()
    await pickFacet(view, 'state', 'blocked')
    expect(listed(view)).toEqual([`free/${KELLY}/2`])
    // the bar says how many of all it shows, and the state's chip that it holds a pick
    expect(view.find('.facet-count-label').text()).toBe('1 of 2')
    expect(view.find('.facet-trigger[data-facet="state"] .facet-badge').text()).toBe('1')
  })

  it('keeps the choice in the address, so back from a page, or a link, opens the same narrowed list (24.a)', async () => {
    vi.mocked(getIssues).mockResolvedValue(anIssueList())
    const view = mountView()
    await flushPromises()
    await pickFacet(view, 'state', 'blocked')
    expect(router.currentRoute.value.fullPath).toBe('/issues?state=blocked')
    // the list opened afresh at that address, as the browser's back or a link would, is the same narrowed list
    const again = mountView()
    await flushPromises()
    expect(listed(again)).toEqual([`free/${KELLY}/2`])
    expect(again.find('.facet-trigger[data-facet="state"]').classes()).toContain('active')
    // choosing nothing leaves an address without a filter
    await pickFacet(view, 'state', 'blocked')
    expect(router.currentRoute.value.fullPath).toBe('/issues')
    expect(listed(view)).toHaveLength(2)
  })

  it('offers the knowledge base as a choice only where more than one is served', async () => {
    vi.mocked(getIssues).mockResolvedValueOnce(anIssueList()).mockResolvedValueOnce(withALicensedWork())
    const single = mountView()
    await flushPromises()
    expect(single.find('.facet-trigger[data-facet="kb"]').exists()).toBe(false)
    single.unmount()

    const both = mountView()
    await flushPromises()
    // a knowledge base keeps its glyph and its word in the panel, as in a row (Q3.a)
    expect((await facetOption(both, 'kb', 'licensed')).querySelector('[data-kb="licensed"] [data-icon="kb-licensed"]')).not.toBeNull()
    await pickFacet(both, 'kb', 'licensed')
    const rows = both.findAll('tbody tr[data-page]')
    expect(rows.map(row => row.attributes('data-page'))).toEqual(['licensed/a_licensed_book/5'])
    expect(rows[0].find('a').attributes('href')).toBe('#/licensed/sources/a_licensed_book/page/5')
  })

  it('says so when no page needs a look', async () => {
    vi.mocked(getIssues).mockResolvedValue({ knowledge_bases: [], states: [], people: [], reviews: [], categories: [], rows: [] })
    const view = mountView()
    await flushPromises()
    expect(view.text()).toContain('No page needs a look.')
  })

  it('folds a page a person settled apart from the open ones, its bucket counted with the verdicts (211.a)', async () => {
    const list = anIssueList()
    const [blocked, judged] = list.rows
    list.rows = [{ ...blocked, listed_state: 'blocked' },
      { ...judged, listed_state: 'decided_by_a_person', person: { standing: 'noted', reason: 'looked at by hand', by_a_person: true } }]
    list.states = [{ value: 'decided_by_a_person', count: 1, accepted: 0, rejected: 0, noted: 1 }, { value: 'blocked', count: 1 }]
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    // the open list keeps the blocked page; the settled one stands in the fold below, folded, its check's state receding
    expect(view.findAll('tbody tr[data-page]').filter(row => !row.element.closest('[data-part="decided"]'))
      .map(row => row.attributes('data-page'))).toEqual([`free/${KELLY}/2`])
    const fold = view.find('[data-part="decided"]')
    expect(fold.attributes('open')).toBeUndefined()
    expect(fold.find('summary').text()).toBe("Decided by a person · 1 page, the check's state kept in each")
    expect(fold.find(`tr[data-page="free/${KELLY}/9"] .state-mark`).classes()).toContain('quiet')
    expect(view.find('[data-part="none-open"]').exists()).toBe(false)
    // the bucket's value in the state's panel: its own glyph and word
    const value = await facetOption(view, 'state', 'decided_by_a_person')
    expect(value.querySelector('.state-word')!.textContent).toBe('decided by a person')
    expect(value.querySelector('.state-mark')!.classList).toContain('quiet')
    // narrowed to the bucket, the open list is empty and the fold holds the page
    await pickFacet(view, 'state', 'decided_by_a_person')
    expect(listed(view)).toEqual([`free/${KELLY}/9`])
  })

  it('folds a page an automated review settled apart from a person\'s, and never counts it as a person\'s (Q.a, 18 Nov)', async () => {
    // the operator's 2.a: "a person is always manual"; a session's verdict on the operator's delegation settles the page as the
    // core serves it, but in a bucket and a facet of its own
    const list = anIssueList()
    const [blocked, judged] = list.rows
    list.rows = [{ ...blocked, listed_state: 'blocked' },
      { ...judged, listed_state: 'decided_by_an_automated_review',
        person: { standing: 'accepted', reason: 'the judge\'s finding contradicts its own evidence', by_a_person: false,
          given_by: 'claude-opus-5-5 session, delegated by the operator (17 Nov)' } }]
    list.states = [{ value: 'decided_by_an_automated_review', count: 1, accepted: 0, rejected: 0, noted: 0 }, { value: 'blocked', count: 1 }]
    list.reviews = [{ value: 'accepted', count: 1 }]
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="decided"]').exists()).toBe(false)
    const fold = view.find('[data-part="reviewed"]')
    expect(fold.find('summary').text()).toBe("Decided by an automated review · 1 page, the check's state kept in each")
    expect(fold.find(`tr[data-page="free/${KELLY}/9"] .state-mark`).classes()).toContain('quiet')
    // the row's mark is a machine's, never a person's glyph, and its card says whose it is
    const mark = fold.find(`tr[data-page="free/${KELLY}/9"] .person-standing`)
    expect(mark.find('[data-icon="review"]').exists()).toBe(true)
    expect(mark.find('[data-icon="person-accepted"]').exists()).toBe(false)
    // the bucket's value, its own glyph and word; no "A person" facet, an "Automated review" one
    const value = await facetOption(view, 'state', 'decided_by_an_automated_review')
    expect(value.querySelector('.state-word')!.textContent).toBe('decided by an automated review')
    expect(value.querySelector('[data-icon="status-reviewed"]')).not.toBeNull()
    expect(view.find('.facet-trigger[data-facet="person"]').exists()).toBe(false)
    expect(view.find('.facet-trigger[data-facet="review"]').text()).toContain('Automated review')
    // narrowed to what the review accepted, only its page stands
    await pickFacet(view, 'review', 'accepted')
    expect(listed(view)).toEqual([`free/${KELLY}/9`])
  })

  it('says no page needs a look when every listed page is settled, and keeps them in the fold', async () => {
    const list = anIssueList()
    list.rows = list.rows.map(row => ({ ...row, listed_state: 'decided_by_a_person', person: { standing: 'accepted' as const, by_a_person: true } }))
    vi.mocked(getIssues).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="none-open"]').text()).toBe('No page needs a look.')
    expect(view.findAll('[data-part="decided"] tbody tr[data-page]')).toHaveLength(2)
  })
})
