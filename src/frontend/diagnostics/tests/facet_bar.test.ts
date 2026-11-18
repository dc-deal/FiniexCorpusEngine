import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FacetBar from '@/components/base/FacetBar.vue'
import type { FacetSelection } from '@/types/facet_types'

const FACETS = [{ key: 'state', label: 'State', values: [{ value: 'ok', count: 1200 }, { value: 'issue', count: 40 }] }]

function mountBar(selection: FacetSelection) {
  return mount(FacetBar, { props: { facets: FACETS, modelValue: selection } })
}

describe('FacetBar', () => {
  it('shows each value with how often the API counted it', () => {
    const bar = mountBar({})
    expect(bar.find('[data-value="ok"]').text()).toContain('1,200')
  })

  it('chooses a value on a click and lets go of it on the next', async () => {
    const bar = mountBar({})
    await bar.find('[data-value="issue"]').trigger('click')
    expect(bar.emitted('update:modelValue')?.[0]).toEqual([{ state: ['issue'] }])
    await bar.setProps({ modelValue: { state: ['issue'] } })
    expect(bar.find('[data-value="issue"]').attributes('aria-pressed')).toBe('true')
    await bar.find('[data-value="issue"]').trigger('click')
    expect(bar.emitted('update:modelValue')?.[1]).toEqual([{ state: [] }])
  })
})
