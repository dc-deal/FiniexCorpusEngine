import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LabelledLine from '@/components/base/LabelledLine.vue'
import DetailList from '@/components/base/DetailList.vue'

describe('the library\'s labelled line and detail list (179, 184)', () => {
  it('names a value by a bold label, the value its slot', () => {
    const line = mount(LabelledLine, { props: { label: 'Route' }, slots: { default: 'noted · vision reading' } })
    expect(line.find('.line-label').text()).toBe('Route:')
    expect(line.find('.line-value').text()).toBe('noted · vision reading')
    expect(line.attributes('data-label')).toBe('Route')
  })

  it('holds its pairs in one list the view gives', () => {
    const list = mount(DetailList, { slots: { default: '<dt>Model</dt><dd>claude-sonnet-5-5</dd>' } })
    expect(list.element.tagName).toBe('DL')
    expect(list.find('dt').text()).toBe('Model')
  })
})
