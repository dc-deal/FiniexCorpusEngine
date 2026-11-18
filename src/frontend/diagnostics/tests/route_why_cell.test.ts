import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RouteWhy from '@/components/RouteWhy.vue'

// a page row's fields the Why needs, invented over the core's own route words
const TEXT_LAYER = 'text layer: the provider blocked the reading'
const READ = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2)'

function aRow(overrides: Record<string, unknown> = {}) {
  return { error_message: null, route: READ, route_level: 'checked', route_why: null, from_text_layer: false, check: { state: 'ok' }, ...overrides }
}

describe('RouteWhy (159.a)', () => {
  it('says nothing for a page served as checked, and has no card to open', () => {
    const cell = mount(RouteWhy, { props: { row: aRow() } })
    expect(cell.text()).toBe('')
    expect(cell.find('.hover-card-host').exists()).toBe(false)
  })

  it('says a fallback by its glyph and its why, the whole route in its card, never on the row', async () => {
    const cell = mount(RouteWhy, { props: { row: aRow({ route: TEXT_LAYER, route_level: 'fallback', route_why: 'the provider blocked the reading', from_text_layer: true }) } })
    expect(cell.text()).toBe('the provider blocked the reading')
    expect(cell.find('[data-icon="route-fallback"]').exists()).toBe(true)
    // the library's card, no browser tooltip (203.a)
    expect(cell.find('.route-why').attributes('title')).toBeUndefined()
    await cell.find('.hover-card-host').trigger('mouseenter')
    expect(cell.find('[data-part="hover-card"] [data-row="route"] .card-value').text()).toBe(TEXT_LAYER)
    expect(cell.find('[data-part="hover-card"] [data-row="level"] .card-value').text()).toBe('fallback')
  })

  it('puts the provider\'s own sentence first, where it gave one', () => {
    const cell = mount(RouteWhy, { props: { row: aRow({ route: TEXT_LAYER, route_level: 'fallback', route_why: 'the provider blocked the reading',
      error_message: 'Output blocked by content filtering policy' }) } })
    expect(cell.text()).toBe('Output blocked by content filtering policy')
  })

  it('says a noted route\'s why, and an export written before levels its whole route where it is worth saying', () => {
    const noted = mount(RouteWhy, { props: { row: aRow({ route: `${READ}: the judge's findings lie on blocks never quoted`, route_level: 'noted',
      route_why: 'the judge\'s findings lie on blocks never quoted', check: { state: 'issue' } }) } })
    expect(noted.text()).toBe('the judge\'s findings lie on blocks never quoted')
    const older = mount(RouteWhy, { props: { row: aRow({ route: TEXT_LAYER, route_level: null, from_text_layer: true }) } })
    expect(older.text()).toBe(TEXT_LAYER)
  })
})
