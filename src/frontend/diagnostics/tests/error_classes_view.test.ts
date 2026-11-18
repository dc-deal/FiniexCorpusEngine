import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getErrorClasses } from '@/api/api_client'
import { router } from '@/router'
import ErrorClassesView from '@/views/ErrorClassesView.vue'
import type { ErrorClass, ErrorClassList } from '@/types/api/errors_types'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getErrorClasses: vi.fn(),
}))

enableAutoUnmount(afterEach)

const KELLY = 'carta_conversano_kelly_criterion_2020'

function aClass(overrides: Partial<ErrorClass> = {}): ErrorClass {
  return { stage: 'judge', kind: 'wrong_value', block_class: 'table', void: false, knowledge_base: 'free', source_id: KELLY,
    title: 'Kelly criterion paper', findings: 3, pages: [4, 9], ...overrides }
}

function aList(): ErrorClassList {
  return { classes: [aClass(), aClass({ kind: 'wrong_word', block_class: 'list_item', void: true, findings: 1, pages: [5] }),
    aClass({ stage: 'stage 2', kind: 'text_drawn', block_class: null, findings: 20, pages: [1, 2, 3] })],
  stages: [], kinds: [], knowledge_bases: [] }
}

describe('ErrorClassesView', () => {
  beforeEach(() => {
    vi.mocked(getErrorClasses).mockReset()
  })

  it('splits the judge\'s counting findings, the void ones and stage 2\'s, each with its pages drawn when opened', async () => {
    vi.mocked(getErrorClasses).mockResolvedValue(aList())
    const view = mount(ErrorClassesView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    const judge = view.find('[data-table="judge"]')
    expect(judge.findAll('tbody tr')).toHaveLength(1)
    expect(judge.find('tbody tr').text()).toContain('wrong_value')
    expect(judge.find('tbody tr').text()).toContain('table')
    expect(view.find('[data-table="void"] tbody tr').text()).toContain('wrong_word')
    expect(view.find('[data-table="stage2"] thead').text()).not.toContain('Block class')
    // the pages stand only once opened, each opening its page
    const details = judge.find('details.pages')
    expect(details.find('a').exists()).toBe(false)
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')
    expect(details.findAll('a').map(link => link.attributes('href'))).toEqual([`#/free/sources/${KELLY}/page/4`, `#/free/sources/${KELLY}/page/9`])
  })
})
