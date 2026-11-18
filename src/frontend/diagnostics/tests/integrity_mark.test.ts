import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import IntegrityMark from '@/components/IntegrityMark.vue'

describe('IntegrityMark', () => {
  it('says a reading file is whole, or that a page has none, quietly, in the core\'s word beside a glyph', () => {
    for (const state of ['whole', 'no reading']) {
      const mark = mount(IntegrityMark, { props: { state } })
      expect(mark.classes()).toContain('quiet')
      expect(mark.find('[data-icon]').exists()).toBe(true)
      expect(mark.text()).toBe(state)
    }
  })

  it('makes a tampered or missing reading file stand out', () => {
    for (const state of ['tampered', 'missing']) {
      const mark = mount(IntegrityMark, { props: { state } })
      expect(mark.classes()).toContain('error')
      expect(mark.find('[data-icon="status-error"]').exists()).toBe(true)
    }
  })

  it('shows a word it does not know as unfamiliar', () => {
    expect(mount(IntegrityMark, { props: { state: 'rewritten' } }).find('[data-icon="status-unknown"]').exists()).toBe(true)
  })
})
