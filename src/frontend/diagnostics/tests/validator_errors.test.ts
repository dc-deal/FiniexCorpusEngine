import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPage } from '@/api/api_client'
import { router } from '@/router'
import ReadingBlocks from '@/components/reading/ReadingBlocks.vue'
import PageView from '@/views/PageView.vue'
import { lookedSaid } from '@/person_words'
import type { ReadingError } from '@/types/api/page_types'
import { aBlock, aPageDetail, KELLY } from './page_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPage: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented in the validator's wording (228.a, after accounting p. 398 and p. 338)
function anError(overrides: Partial<ReadingError>): ReadingError {
  return { said: 'block b01 (line 5): HTML in prose', message: 'HTML in prose', block: 'b01', line: 5, looked: null, looked_at: null,
    corrected: false, ...overrides }
}

const NOTED = anError({ looked: 'note', looked_at: 'block', corrected: true })
const LINE_ONLY = anError({ said: 'line 3: attributes not parseable', message: 'attributes not parseable', block: null, line: 3 })
const RAW = '---\nwork: kelly\n---\n::: {#b01 .paragraph}\n<b>The growth rate</b>\n:::'

describe('a validator\'s error, on its block and in the list (228.a)', () => {
  it('says who looked in a person\'s words, the block or the page', () => {
    expect(lookedSaid(NOTED)).toBe('a person noted and corrected b01')
    expect(lookedSaid(anError({ looked: 'accept', looked_at: 'page' }))).toBe('a person accepted the page')
    expect(lookedSaid(anError({}))).toBe('')
  })

  it('stands on the block it names in a finding\'s look, red until a person has looked, and asks for its raw line', async () => {
    const blocks = [aBlock({ id: 'b01' }), aBlock({ id: 'b02' })]
    const view = mount(ReadingBlocks, { props: { blocks, errors: [anError({ looked: null }), LINE_ONLY] } })
    const onBlock = view.find('[data-block="b01"] [data-part="block-errors"] li')
    expect(onBlock.find('.part-label').text()).toBe("The validator's error:")
    expect(onBlock.find('.error-message').text()).toBe('HTML in prose')
    expect(onBlock.classes()).not.toContain('looked')
    expect(onBlock.find('[data-part="error-looked"]').exists()).toBe(false)
    // an error that names no block stands on none
    expect(view.findAll('[data-part="block-errors"]')).toHaveLength(1)
    await onBlock.find('[data-part="show-raw"]').trigger('click')
    expect(view.emitted('raw')).toEqual([[5]])
    await view.setProps({ errors: [NOTED] })
    const muted = view.find('[data-block="b01"] [data-part="block-errors"] li')
    expect(muted.classes()).toContain('looked')
    expect(muted.find('[data-part="error-looked"]').text()).toBe('a person noted and corrected b01')
  })
})

describe('the page view\'s errors and its numbered raw text (228.a)', () => {
  beforeEach(async () => {
    vi.mocked(getPage).mockReset().mockResolvedValue(aPageDetail({
      raw: RAW,
      reading: { front: {}, blocks: [aBlock({ id: 'b01' })], warnings: [], errors: [NOTED.said, LINE_ONLY.said], error_places: [NOTED, LINE_ONLY] },
    }))
    localStorage.clear()
    await router.push({ name: 'page', params: { kb: 'free', work: KELLY, page: 4 } })
  })

  function mountView() {
    return mount(PageView, { props: { kb: 'free', work: KELLY, page: 4 }, global: { plugins: [createPinia(), router] } })
  }

  it('lists each error as the validator wrote it, with its block and its line, muted where a person looked', async () => {
    const view = mountView()
    await flushPromises()
    const [first, second] = view.findAll('[data-part="parse-errors"] li')
    expect(first.find('.error-said').text()).toBe(NOTED.said)
    expect(first.find('[data-part="error-block"]').text()).toBe('b01')
    expect(first.find('[data-part="error-looked"]').text()).toBe('· a person noted and corrected b01')
    expect(first.classes()).toContain('looked')
    expect(second.find('[data-part="error-block"]').exists()).toBe(false)
    expect(second.find('[data-part="show-raw"]').exists()).toBe(true)
    expect(second.classes()).not.toContain('looked')
  })

  it('opens the raw text at the line an error names, marked, its lines numbered beside a text left as stored', async () => {
    const view = mountView()
    await flushPromises()
    await view.findAll('[data-part="parse-errors"] li')[1].find('[data-part="show-raw"]').trigger('click')
    await flushPromises()
    const raw = view.find('pre.raw')
    expect(raw.element.textContent).toBe(RAW)
    expect(raw.findAll('.raw-line').map(line => line.attributes('data-line'))).toEqual(['1', '2', '3', '4', '5', '6'])
    expect(raw.find('.raw-line.marked').attributes('data-line')).toBe('3')
    expect(raw.find('.raw-line.marked').text()).toBe('---')
    // the mark goes when the text is chosen anew
    await view.findAll('.mode button').find(button => button.text() === 'readable')!.trigger('click')
    await view.findAll('.mode button').find(button => button.text() === 'raw')!.trigger('click')
    expect(view.find('pre.raw .raw-line.marked').exists()).toBe(false)
  })

  it('marks an error\'s block in the raw text as a compiler does, the named line strongest, a looked-at one quietly', async () => {
    const onBlock = anError({ said: 'block b01 (line 4): HTML in prose', line: 4, lines: [4, 6] })
    vi.mocked(getPage).mockReset().mockResolvedValue(aPageDetail({
      raw: RAW,
      reading: { front: {}, blocks: [aBlock({ id: 'b01' })], warnings: [], errors: [onBlock.said, LINE_ONLY.said],
        error_places: [onBlock, LINE_ONLY] },
    }))
    const view = mountView()
    await flushPromises()
    await view.findAll('.mode button').find(button => button.text() === 'raw')!.trigger('click')
    const marks = () => view.findAll('pre.raw .raw-line').map(line => line.attributes('data-error-line') ?? '')
    // line 3 named alone; the block b01 from its opening fence (4) to its closing one (6), the named line strongest
    expect(marks()).toEqual(['', '', 'error-named', 'error-named', 'error-block', 'error-block'])
    expect(view.find('pre.raw').element.textContent).toBe(RAW)
    // where a person has looked, the block keeps a quiet mark, never the error's colour
    vi.mocked(getPage).mockResolvedValue(aPageDetail({
      raw: RAW,
      reading: { front: {}, blocks: [aBlock({ id: 'b01' })], warnings: [], errors: [NOTED.said],
        error_places: [{ ...NOTED, line: 4, lines: [4, 6] }] },
    }))
    const looked = mountView()
    await flushPromises()
    await looked.findAll('.mode button').find(button => button.text() === 'raw')!.trigger('click')
    expect(looked.findAll('pre.raw .raw-line').map(line => line.attributes('data-error-line') ?? ''))
      .toEqual(['', '', '', 'error-looked', 'error-looked', 'error-looked'])
  })
})
