import { describe, it, expect, afterEach } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { router } from '@/router'
import ChatTurn from '@/components/ChatTurn.vue'
import type { ChatResult } from '@/types/api/chat_types'
import { aKnowledgeResult, KELLY } from './chat_fixture'

enableAutoUnmount(afterEach)

function mountTurn(result: ChatResult) {
  return mount(ChatTurn, { props: { result }, global: { plugins: [router] } })
}

describe('ChatTurn', () => {
  it('renders the answer as Markdown, and every quote word for word as text, with the page it comes from', () => {
    const view = mountTurn(aKnowledgeResult())
    expect(view.find('.answer strong').text()).toBe('fraction')
    // a quote is verbatim: Markdown and HTML characters in it stay characters
    const quote = view.find('.quote')
    expect(quote.find('.quote-text').text()).toBe('the optimal strategy is to bet a *fraction* <b>of</b> wealth')
    expect(quote.find('.quote-text b').exists()).toBe(false)
    expect(quote.find('.quote-source').text()).toContain('[1] Practical Implementation of the Kelly Criterion · p. 3 · CC BY 4.0')
    expect(quote.find('a.open').attributes('href')).toBe(`#/free/sources/${KELLY}/page/3`)
  })

  it('names what the sources do not cover, the disclaimer, and every passage with where it opens', () => {
    const view = mountTurn(aKnowledgeResult())
    expect(view.find('.gaps').text()).toContain('Not covered by the sources:')
    expect(view.find('.gaps strong').text()).toBe('portfolio')
    expect(view.find('.disclaimer').text()).toBe('Not trading advice. For educational purposes only.')
    const sources = view.findAll('.sources li')
    expect(sources[0].find('a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/3`)
    // an HTML section opens its source, out of this page's reach
    const wiki = sources[1].find('a')
    expect(wiki.attributes('href')).toBe('https://en.wikipedia.org/wiki/Kelly_criterion#Proof')
    expect(wiki.attributes('rel')).toBe('noopener noreferrer')
  })

  it('opens an HTML section in its article beside its source, for a passage and a quote from it (164.a)', () => {
    const base = aKnowledgeResult()
    const article = { knowledge_base: 'free' as const, source_id: 'wikipedia_trading_set', label: 's5' }
    const sources = base.turn!.sources.map((source, at) => (at === 1 ? { ...source, article } : source))
    const quote = { ...base.turn!.quotes[0], passage: 2, view: null, article,
      citation: { ...base.turn!.quotes[0].citation, link: 'https://en.wikipedia.org/wiki/Sharpe_ratio#History' } }
    const view = mountTurn({ ...base, turn: { ...base.turn!, sources, quotes: [quote] } })
    const href = '#/free/html/wikipedia_trading_set/s5'
    // beside the source's own page, never instead of it
    const links = view.find('.quote .quote-source').findAll('a.open')
    expect(links.map(link => link.text())).toEqual(['open the source', 'open in the article'])
    expect(links[1].attributes('href')).toBe(href)
    expect(view.findAll('.sources li')[1].find('[data-part="article"]').attributes('href')).toBe(href)
    // a PDF page's passage has its page view and no article
    expect(view.findAll('.sources li')[0].find('[data-part="article"]').exists()).toBe(false)
  })

  it('says whose words are whose: the answer the model\'s, the quotes the sources\' own, a question back as one', () => {
    const base = aKnowledgeResult()
    const view = mountTurn({ ...base, turn: { ...base.turn!, follow_up: 'Is the report for a customer or for the books?' } })
    expect(view.find('[data-part="answer"]').text()).toContain('in the model\'s words')
    expect(view.find('[data-part="quotes"]').text()).toBe('Quoted word for word, each checked against its passage')
    expect(view.find('.follow-up .label').text()).toBe('A question back:')
  })

  it('shows the best passage\'s relevance beside its floor, and marks a turn whose best passage lies below it', () => {
    const base = aKnowledgeResult()
    const hit = mountTurn({ ...base, turn: { ...base.turn!, relevance: 0.503, relevance_floor: 0.495, below_floor: false } })
    expect(hit.find('[data-part="relevance"]').text()).toBe('relevance 0.503, floor 0.495')
    expect(hit.find('[data-part="relevance"]').classes()).not.toContain('below')
    const miss = mountTurn({ ...base, turn: { ...base.turn!, relevance: 0.451, relevance_floor: 0.495, below_floor: true } })
    const line = miss.find('[data-part="relevance"]')
    expect(line.text()).toBe('relevance 0.451, floor 0.495: the best passage lies below the floor')
    expect(line.classes()).toContain('below')
    expect(line.find('[data-icon="status-unknown"]').exists()).toBe(true)
  })

  it('shows nothing found as a warning and a decline as a notice', () => {
    const base = aKnowledgeResult()
    const notFound = mountTurn({ ...base, turn: { ...base.turn!, behaviour: 'not_found', quotes: [], sources: [] } })
    expect(notFound.find('.answer').classes()).toContain('warning')
    const declined = mountTurn({ ...base, turn: { ...base.turn!, behaviour: 'decline_off_topic', quotes: [], sources: [] } })
    expect(declined.find('.answer').classes()).toContain('notice')
  })

  it('puts the turn id, its time and its cost beneath it, and the security checks folded away', () => {
    const view = mountTurn(aKnowledgeResult({ call_limit_reached: 'Model call limits exceeded: 5' }))
    expect(view.find('.turn-foot').text()).toContain('a1b2c3d4 · 11.2 s · ≈ 0.0031 USD')
    expect(view.find('.cap').text()).toContain('Model call limits exceeded: 5')
    const security = view.find('details.security')
    expect(security.attributes('open')).toBeUndefined()
    expect(security.find('[data-check="quotes"]').classes()).toContain('warning')
    expect(security.find('[data-check="input"]').classes()).toContain('quiet')
  })

  it('shows a calculation\'s text, written by code, and never the agent\'s own sentence', () => {
    const calculation = { ...aKnowledgeResult(), kind: 'calculation', turn: null, disclaimer: 'Not trading advice.',
      text: '| measure | value |\n|---|---|\n| Sharpe ratio | 0.41 |', agent_text: 'Here is your Sharpe ratio.' } as ChatResult
    const view = mountTurn(calculation)
    expect(view.find('.markdown table').exists()).toBe(true)
    expect(view.text()).not.toContain('Here is your Sharpe ratio.')
  })

  it('shows a refused question\'s text as text', () => {
    const view = mountTurn({ ...aKnowledgeResult(), kind: 'invalid', turn: null, text: 'Please type a question.' })
    expect(view.find('.notice').text()).toBe('Please type a question.')
  })

  it('shows what the search server answered: an opened page word for word, an image, hits, or why not', () => {
    const server = (tool: string, answer: Record<string, unknown>, image_src: string | null = null) => mountTurn(
      { ...aKnowledgeResult(), kind: 'server', turn: null, server: { tool, args: { work: KELLY, page: '3' }, answer, image_src } })
    const opened = server('open_page', { state: 'found', title: 'Kelly paper', page: { label: '3', pdf: '3', printed: '2' },
      text: 'A page, **word** for word.' })
    expect(opened.find('.page-text').text()).toBe('A page, **word** for word.')
    expect(opened.find('.page-head').text()).toContain('page 3 (printed 2)')
    const image = server('page_image', { state: 'found', page: { label: '3', pdf: '3', printed: null } }, 'data:image/png;base64,iVBORw0KGgo=')
    expect(image.find('img').attributes('src')).toBe('data:image/png;base64,iVBORw0KGgo=')
    const hits = server('search', { state: 'found', hits: [{ knowledge_base: 'free', work: KELLY, title: 'Kelly paper',
      page: { label: '3', pdf: '3', printed: null }, snippet: 'the bet', view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } }] })
    expect(hits.find('.hit a').attributes('href')).toBe(`#/free/sources/${KELLY}/page/3`)
    const missing = server('open_page', { state: 'nothing found', page: '999', why: 'no page 999 in this work' })
    expect(missing.find('.not-found').text()).toBe('nothing found: no page 999 in this work')
  })
})
