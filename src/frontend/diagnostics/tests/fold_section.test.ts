import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FoldSection from '@/components/base/FoldSection.vue'
import { useSettingsStore } from '@/stores/settings_store'

describe('FoldSection, the one fold of every view (179)', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('sets a count apart from the name, so it never reads as a numbering', () => {
    const fold = mount(FoldSection, { props: { title: 'Lab', count: '3 judgements tried beside the pipeline' }, slots: { default: 'inside' } })
    expect(fold.find('summary').text()).toBe('Lab · 3 judgements tried beside the pipeline')
    expect(fold.find('.fold-body').text()).toBe('inside')
    expect(fold.find('details').attributes('open')).toBeUndefined()
  })

  it('stands open where its view opens it, and needs no store where nothing is kept', () => {
    setActivePinia(undefined as never)
    const fold = mount(FoldSection, { props: { title: 'Sources', open: true } })
    expect(fold.find('details').attributes('open')).toBeDefined()
  })

  it('keeps a remembered fold as the reader left it, and says each toggle', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const fold = mount(FoldSection, { props: { title: 'Reading History', remember: 'page.history' }, global: { plugins: [pinia] } })
    const details = fold.find('details').element as HTMLDetailsElement
    details.open = true
    await fold.find('details').trigger('toggle')
    expect(useSettingsStore().settings.foldsOpen['page.history']).toBe(true)
    expect(fold.emitted('toggle')).toEqual([[true]])
    const again = mount(FoldSection, { props: { title: 'Reading History', remember: 'page.history' }, global: { plugins: [pinia] } })
    expect(again.find('details').attributes('open')).toBeDefined()
  })

  it('stands as a record\'s row with a label, and as a plain row where it has nothing to fold open (H1.a)', () => {
    const row = mount(FoldSection, { props: { label: 'Route', title: 'noted · vision reading' }, slots: { default: 'its parts' } })
    expect(row.find('details').attributes('data-label')).toBe('Route')
    expect(row.find('details').classes()).toContain('labelled')
    expect([row.find('summary .fold-label').text(), row.find('summary .fold-title').text()]).toEqual(['Route:', 'noted · vision reading'])
    expect(row.find('.fold-body').text()).toBe('its parts')
    // nothing to fold open: the same row, its mark's place kept and empty, no body and nothing to click
    const plain = mount(FoldSection, { props: { label: 'Lab', plain: true }, slots: { title: 'none', default: 'never shown' } })
    expect(plain.find('details').exists()).toBe(false)
    expect([plain.find('.fold-label').text(), plain.find('.fold-mark').exists(), plain.find('.fold-title').text()]).toEqual(['Lab:', true, 'none'])
    expect(plain.text()).not.toContain('never shown')
  })

  it('lets a grid row hold its mark in its title cell, and its rows their own indent', () => {
    const fold = mount(FoldSection, { props: { markInTitle: true, flat: true }, slots: { title: '<span class="fold-inline-mark" />Chapter 1' } })
    expect(fold.find('.fold-mark').exists()).toBe(false)
    expect(fold.find('details').classes()).toEqual(expect.arrayContaining(['flat', 'mark-in-title']))
  })
})
