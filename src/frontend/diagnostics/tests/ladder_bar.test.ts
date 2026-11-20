import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LadderBar from '@/components/LadderBar.vue'

describe('LadderBar', () => {
  it('stays quiet where nothing calls for a look: one neutral fill as long as its part', () => {
    const bar = mount(LadderBar, { props: { count: 300, of: 400 } })
    expect(bar.attributes('data-look')).toBe('quiet')
    expect(bar.find('.ladder-fill').attributes('style')).toContain('width: 75%')
    expect(bar.find('.ladder-issues').exists()).toBe(false)
  })

  it('stands the pages the judge found bad as a segment after the checked ones, apart by a gap (C1.b)', () => {
    const bar = mount(LadderBar, { props: { count: 300, of: 400, issues: 40 } })
    expect(bar.attributes('data-look')).toBe('issues')
    const issues = bar.find('.ladder-issues')
    expect(issues.attributes('data-issues')).toBe('0.100')
    expect(issues.attributes('style')).toContain('left: calc(75% + 2px)')
  })

  it('draws a level nothing reaches that should in the warning role, and one not measured here hatched (C1.b)', () => {
    expect(mount(LadderBar, { props: { count: 0, of: 310, warn: true } }).attributes('data-look')).toBe('warning')
    const unknown = mount(LadderBar, { props: { count: null, of: 310 } })
    expect(unknown.attributes('data-look')).toBe('not measured')
    expect(unknown.attributes('data-share')).toBe('unknown')
    expect(unknown.find('.ladder-fill').exists()).toBe(false)
  })
})
