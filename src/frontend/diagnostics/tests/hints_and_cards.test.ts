import { afterEach, describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import HintPanel from '@/components/base/HintPanel.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import { HINTS } from '@/hints'
import { HOVER_DELAY } from '@/hover_delay'

describe('the library\'s one hint and one hover card (179)', () => {
  it('opens a registered hint from its mark, says its lead, and closes', async () => {
    const toggle = mount(HintToggle, { props: { id: 'routes', open: false } })
    expect(toggle.attributes('aria-label')).toBe(HINTS.routes.label)
    await toggle.trigger('click')
    expect(toggle.emitted('update:open')).toEqual([[true]])
    const panel = mount(HintPanel, { props: { id: 'routes' }, slots: { default: '<p class="figures">the levels</p>' } })
    expect(panel.find('.hint-lead').text()).toBe(HINTS.routes.lead)
    expect(panel.find('.figures').exists()).toBe(true)
    await panel.find('[data-part="routes-hint-close"]').trigger('click')
    expect(panel.emitted('close')).toHaveLength(1)
  })

  it('shows data under the pointer and the keyboard\'s focus, a row only where it has a value, and never a tooltip', async () => {
    const card = mount(HoverCard, {
      props: { title: 'Route', rows: [{ label: 'level', value: 'noted' }, { label: 'why', value: null }] },
      slots: { default: '<span class="route">noted · vision reading</span>' },
    })
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
    await card.trigger('mouseenter')
    expect(card.find('.card-title').text()).toBe('Route')
    expect(card.findAll('.card-row').map(row => row.attributes('data-row'))).toEqual(['level'])
    expect(card.attributes('title')).toBeUndefined()
    await card.trigger('mouseleave')
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
    await card.trigger('focusin')
    expect(card.find('[data-part="hover-card"]').exists()).toBe(true)
  })

  describe('waits for the pointer, never for the keyboard (C1.b)', () => {
    afterEach(() => {
      vi.useRealTimers()
      HOVER_DELAY.pointerMs = 0
    })

    it('opens on a pointer that rests 500 ms, not on one passing over, and at once on the keyboard\'s focus', async () => {
      HOVER_DELAY.pointerMs = 500  // the app's own value, which the suite's setup sets to 0 for every other test
      vi.useFakeTimers()
      const card = mount(HoverCard, { props: { title: 'Route', rows: [{ label: 'level', value: 'checked' }] }, slots: { default: 'p. 4' } })
      const opened = () => card.find('[data-part="hover-card"]').exists()
      await card.find('.hover-card-host').trigger('mouseenter')
      await vi.advanceTimersByTimeAsync(499)
      expect(opened()).toBe(false)
      await vi.advanceTimersByTimeAsync(1)
      expect(opened()).toBe(true)
      await card.find('.hover-card-host').trigger('mouseleave')
      expect(opened()).toBe(false)
      // a pointer that leaves before the wait is over opens nothing
      await card.find('.hover-card-host').trigger('mouseenter')
      await vi.advanceTimersByTimeAsync(300)
      await card.find('.hover-card-host').trigger('mouseleave')
      await vi.advanceTimersByTimeAsync(500)
      expect(opened()).toBe(false)
      await card.find('.hover-card-host').trigger('focusin')
      expect(opened()).toBe(true)
    })
  })

  it('opens beneath its host, and above it where the window\'s foot would cut it (SR 11-7 p. 5, 11 Nov)', async () => {
    // jsdom draws nothing: the host's and the card's boxes are given, a card 120 px tall, the window 768 px
    const boxOf = (hostTop: number, element: Element) => element.classList.contains('hover-card')
      ? new DOMRect(0, 0, 300, 120) : new DOMRect(40, hostTop, 60, 20)
    const placedAt = async (hostTop: number) => {
      const card = mount(HoverCard, { props: { title: 'Note 4', rows: [{ label: 'note', value: 'Smaller banks …' }] }, slots: { default: '<sup>4</sup>' } })
      const original = Element.prototype.getBoundingClientRect
      Element.prototype.getBoundingClientRect = function (this: Element) { return boxOf(hostTop, this) }
      await card.trigger('mouseenter')
      await new Promise(resolve => setTimeout(resolve))
      Element.prototype.getBoundingClientRect = original
      return (card.find('[data-part="hover-card"]').element as HTMLElement).style.top
    }
    expect(window.innerHeight).toBe(768)
    expect(await placedAt(100)).toBe('124px')  // room beneath: under the host, 4 px apart
    expect(await placedAt(720)).toBe('596px')  // the foot would cut it: above the host, 4 px apart
  })
})
