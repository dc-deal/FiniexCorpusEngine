import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppButton from '@/components/base/AppButton.vue'

describe('AppButton', () => {
  it('renders what it was given', () => {
    expect(mount(AppButton, { slots: { default: 'Try again' } }).text()).toBe('Try again')
  })

  it('is solid unless asked to be quiet or a link', () => {
    expect(mount(AppButton).classes()).toContain('solid')
    expect(mount(AppButton, { props: { variant: 'quiet' } }).classes()).toContain('quiet')
    expect(mount(AppButton, { props: { variant: 'link' } }).classes()).not.toContain('solid')
  })

  it('wears the overlay\'s role as the way back from a view that is not the standing one (30.a)', () => {
    const back = mount(AppButton, { props: { variant: 'overlay', size: 'compact' }, slots: { default: 'Show standing' } })
    expect([back.element.tagName, back.classes()]).toEqual(['BUTTON', expect.arrayContaining(['overlay', 'compact'])])
    expect(back.classes()).not.toContain('solid')
  })

  /** `aria-pressed` makes a button a toggle for a screen reader, so only a toggle carries it. */
  it('announces a toggle only where it is one', () => {
    expect(mount(AppButton).attributes('aria-pressed')).toBeUndefined()
    expect(mount(AppButton, { props: { marked: true } }).attributes('aria-pressed')).toBeUndefined()
    expect(mount(AppButton, { props: { active: true } }).attributes('aria-pressed')).toBe('true')
  })

  it('is a plain button, so it never submits a form, unless it is the one asked to', () => {
    expect(mount(AppButton).attributes('type')).toBe('button')
    expect(mount(AppButton, { props: { type: 'submit' } }).attributes('type')).toBe('submit')
  })
})
