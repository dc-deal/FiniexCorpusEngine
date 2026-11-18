import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StateMark from '@/components/StateMark.vue'

describe('StateMark', () => {
  it('says every state in a word beside its glyph, never in colour alone', () => {
    for (const state of ['ok', 'ok_unjudged', 'issue', 'blocked', 'stopped']) {
      const mark = mount(StateMark, { props: { state } })
      expect(mark.find('[data-icon]').exists()).toBe(true)
      expect(mark.text()).toBe(state.replace('_', ' '))
    }
  })

  it('keeps a page that is fine quiet and makes an issue stand out', () => {
    expect(mount(StateMark, { props: { state: 'ok' } }).classes()).toContain('quiet')
    const issue = mount(StateMark, { props: { state: 'issue' } })
    expect(issue.classes()).toContain('error')
    expect(issue.find('[data-icon="status-issue"]').exists()).toBe(true)
    expect(mount(StateMark, { props: { state: 'blocked' } }).classes()).toContain('warning')
  })

  it('says a page no check has reached yet is not yet checked, a thing to weigh and not a fine page', () => {
    const mark = mount(StateMark, { props: { state: 'not_yet_checked' } })
    expect(mark.text()).toBe('not yet checked')
    expect(mark.classes()).toContain('warning')
  })

  it('shows a state it does not know as unfamiliar, in the core\'s own word', () => {
    const mark = mount(StateMark, { props: { state: 'quarantined' } })
    expect(mark.text()).toBe('quarantined')
    expect(mark.find('[data-icon="status-unknown"]').exists()).toBe(true)
  })
})
