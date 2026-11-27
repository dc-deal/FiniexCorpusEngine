import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getPrompts } from '@/api/api_client'
import { router } from '@/router'
import PromptsView from '@/views/PromptsView.vue'
import type { PromptList } from '@/types/api/prompts_types'
import { sayDate } from '@/human_time'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getPrompts: vi.fn(),
}))

enableAutoUnmount(afterEach)

/**
 * The registry as the API serves it, in invented words: a reader of two files, its rules and its format, a judge, and a
 * judge prototype one sentence apart.
 */
function aList(): PromptList {
  const file = (path: string, part: string, text: string, frozen: string | null = 'aa11') =>
    ({ path, part, text, sha256: 'aa11', frozen_sha256: frozen, diff: null })
  const version = { title: null, model: 'claude-sonnet-5-5', state: 'active', frozen_on: '2026-10-30', why: 'the pilot', previous: null }
  return {
    about: 'Every version of the instructions.',
    parts: [
      { key: 'rules', label: 'Reader', about: 'what to transcribe' },
      { key: 'format', label: 'Format', about: 'the page file the reader writes' },
      { key: 'judge', label: 'Judge', about: 'how a model compares a reading with the page image' },
    ],
    versions: [
      { ...version, role: 'reader', version: 'page/1', title: 'Markdown blocks',
        files: [file('prompts/rules.txt', 'rules', 'Read the page.'), file('prompts/format.txt', 'format', 'Write blocks.')] },
      { ...version, role: 'judge', version: 'judge/1', title: 'The judge as measured', files: [file('prompts/judge1.txt', 'judge', 'Check every word.')] },
      { ...version, role: 'judge', version: 'judge/2', title: 'judge/1 + proper names', state: 'prototype', frozen_on: '2026-11-09',
        why: 'a proper name was called wrong', previous: 'judge/1',
        files: [{ ...file('prompts/judge2.txt', 'judge', 'Check every word. A name is right.', 'bb22'), diff: [
          { kind: 'removed', text: 'Check every word.', parts: [{ text: 'Check every word.', changed: false }] },
          { kind: 'added', text: 'Check every word. A name is right.', parts: [{ text: 'Check every word.', changed: false }, { text: ' A name is right.', changed: true }] },
        ] }] },
    ],
  }
}

function mountView() {
  return mount(PromptsView, { global: { plugins: [createPinia(), router] } })
}

describe('PromptsView', () => {
  beforeEach(async () => {
    vi.mocked(getPrompts).mockReset()
    await router.push('/prompts')
  })

  it('says what the view holds on demand, the core\u2019s words in the hint, never as a paragraph on every visit (stage D6)', async () => {
    vi.mocked(getPrompts).mockResolvedValue(aList())
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-part="about"]').exists()).toBe(false)
    await view.find('[data-part="prompts-hint-button"]').trigger('click')
    expect(view.find('[data-part="about"]').text()).toBe('Every version of the instructions.')
  })

  it('gives each part of the registry a tab, and a version of two files stands in two of them', async () => {
    vi.mocked(getPrompts).mockResolvedValue(aList())
    const view = mountView()
    await flushPromises()
    expect(view.findAll('[data-tab]').map(tab => tab.text())).toEqual(['Reader 1', 'Format 1', 'Judge 2'])
    expect(view.find('[data-tab="rules"]').attributes('aria-selected')).toBe('true')
    expect(view.find('[data-part="part-about"]').text()).toBe('what to transcribe')
    expect(view.findAll('tbody.version').map(row => row.attributes('data-version'))).toEqual(['page/1'])
    await view.find('[data-tab="format"]').trigger('click')
    expect(view.findAll('tbody.version').map(row => row.attributes('data-version'))).toEqual(['page/1'])
    await view.find('tbody.version .version-row').trigger('click')
    expect(view.find('[data-part="text"]').text()).toBe('Write blocks.')
  })

  it('lists one folded row per version, its title, state, model, freezing and hash, and opens it to its change', async () => {
    vi.mocked(getPrompts).mockResolvedValue(aList())
    const view = mountView()
    await flushPromises()
    await view.find('[data-tab="judge"]').trigger('click')
    const prototype = view.find('tbody[data-version="judge/2"]')
    const cells = prototype.findAll('.version-row td').map(cell => cell.text())
    // who wrote it beside the model (#18): an invented list names no origin, so "not known"
    expect(cells.slice(0, 7)).toEqual(['judge/2', 'judge/1 + proper names', 'prototype', 'claude-sonnet-5-5', 'not known',
      sayDate('2026-11-09').text, 'differs'])
    expect(prototype.find('.version-detail').exists()).toBe(false)
    await prototype.find('.version-row').trigger('click')
    expect(prototype.find('.changed').text()).toBe('A name is right.')
    expect(prototype.find('.switch').text()).toContain('change from judge/1')
    expect(prototype.find('[data-part="why"]').text()).toBe('a proper name was called wrong')
    // a first version has no change to show: opened, its text stands
    await view.find('tbody[data-version="judge/1"] .version-row').trigger('click')
    expect(view.find('tbody[data-version="judge/1"] [data-part="text"]').text()).toBe('Check every word.')
    // and a row folds again
    await prototype.find('.version-row').trigger('click')
    expect(prototype.find('.version-detail').exists()).toBe(false)
  })

  it('opens the tab and the row of the version a page\'s link asks for, and marks it', async () => {
    vi.mocked(getPrompts).mockResolvedValue(aList())
    await router.push({ name: 'prompts', query: { version: 'judge/2' } })
    const view = mountView()
    await flushPromises()
    expect(view.find('[data-tab="judge"]').attributes('aria-selected')).toBe('true')
    expect(view.find('tbody[data-version="judge/2"]').classes()).toEqual(expect.arrayContaining(['chosen', 'open']))
    expect(view.find('tbody[data-version="judge/1"]').classes()).not.toContain('chosen')
    expect(view.find('tbody[data-version="judge/1"] .version-detail').exists()).toBe(false)
  })

  it('stands a version nobody holds the text of, saying "no text", and names each version\'s origin (#18)', async () => {
    const list = aList()
    list.versions.push({ role: 'reader', version: 'an-invented/two-step', title: null, model: null, state: 'prototype', frozen_on: null,
      why: null, previous: null, files: [], origin: { author_kind: 'vendor', author: 'an invented vendor', written_on: '2026-11-20',
        source: 'https://example.org/an-invented-card', evidence: 'an invented model card names the package' } })
    vi.mocked(getPrompts).mockResolvedValue(list)
    const view = mountView()
    await flushPromises()
    await view.find('[data-tab="other"]').trigger('click')
    const row = view.find('tbody[data-version="an-invented/two-step"]')
    expect(row.find('[data-part="written-by"]').text()).toBe('an invented vendor')
    expect(row.find('[data-part="no-text"]').text()).toBe('no text')
    await row.find('.version-row').trigger('click')
    expect(row.find('[data-part="no-text-said"]').text()).toBe("no text: nobody holds this version's prompt")
    expect(row.find('[data-part="origin"]').text()).toContain('vendor · an invented vendor')
    expect(row.find('[data-part="origin"] a').attributes('href')).toBe('https://example.org/an-invented-card')
  })
})
