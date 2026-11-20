import { afterEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { autoUpdate, computePosition, flip, size, type ComputePositionReturn } from '@floating-ui/dom'
import HoverCard from '@/components/base/HoverCard.vue'
import { HOVER_DELAY } from '@/hover_delay'

// jsdom draws nothing, so where a card stands is the browser check's to see (`e2e/views.spec.ts`, 20 Nov); here Floating UI
// answers as told, and the test holds what the card asks of it and does with its answer
vi.mock('@floating-ui/dom', async original => {
  const real = await original<typeof import('@floating-ui/dom')>()
  return { ...real, autoUpdate: vi.fn(real.autoUpdate), computePosition: vi.fn(), flip: vi.fn(real.flip), size: vi.fn(real.size) }
})

const answer = (x: number, y: number, hidden = false) => ({ x, y, placement: 'bottom-start', strategy: 'fixed',
  middlewareData: { hide: { referenceHidden: hidden } } }) as unknown as ComputePositionReturn

const aCard = () => mount(HoverCard, { props: { title: 'Note 4', rows: [{ label: 'note', value: 'Smaller banks …' }] },
  slots: { default: '<sup>4</sup>' }, attachTo: document.body })

describe('a hover card stands wholly inside the window, placed by Floating UI (the operator, 20 Nov)', () => {
  afterEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('asks for the window\'s rule: fixed, beneath first, above where short, the side with more room where it fits neither', async () => {
    vi.mocked(computePosition).mockResolvedValue(answer(40, 596))
    const card = aCard()
    await card.trigger('focusin')
    await flushPromises()
    const [host, floating, options] = vi.mocked(computePosition).mock.calls[0]!
    expect(host).toBe(card.element)
    expect(floating).toBe(card.find('[data-part="hover-card"]').element)
    expect([options?.strategy, options?.placement]).toEqual(['fixed', 'bottom-start'])
    expect(vi.mocked(flip).mock.calls[0]![0]).toMatchObject({ padding: 8, fallbackStrategy: 'bestFit' })
    expect(vi.mocked(size).mock.calls[0]![0]).toMatchObject({ padding: 8 })
    // where Floating UI puts it, the card stands
    const style = (card.find('[data-part="hover-card"]').element as HTMLElement).style
    expect([style.top, style.left]).toEqual(['596px', '40px'])
  })

  it('is placed again while it stands open, and stops being placed once closed', async () => {
    const stop = vi.fn()
    vi.mocked(autoUpdate).mockImplementationOnce((_host, _floating, update) => {
      update()
      return stop
    })
    vi.mocked(computePosition).mockResolvedValue(answer(8, 124))
    const card = aCard()
    await card.trigger('focusin')
    await flushPromises()
    expect(autoUpdate).toHaveBeenCalledTimes(1)
    expect(stop).not.toHaveBeenCalled()
    await card.trigger('focusout')
    expect(stop).toHaveBeenCalledTimes(1)
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
  })

  it('closes when its host has left the window', async () => {
    vi.mocked(computePosition).mockResolvedValue(answer(8, 124, true))
    const card = aCard()
    // a host the window draws: jsdom gives it no box, so one is given
    vi.spyOn(card.element, 'getClientRects').mockReturnValue([new DOMRect(0, -40, 60, 20)] as unknown as DOMRectList)
    await card.trigger('focusin')
    await flushPromises()
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
  })

  it('scrolls where it is taller than its room, takes the pointer then, and waits for it to cross into it', async () => {
    vi.useFakeTimers()
    vi.mocked(computePosition).mockImplementation(async (_host, floating) => {
      Object.defineProperty(floating, 'scrollHeight', { value: 600, configurable: true })
      Object.defineProperty(floating, 'clientHeight', { value: 244, configurable: true })
      return answer(8, 8)
    })
    const card = aCard()
    await card.trigger('mouseenter')
    await flushPromises()
    const floating = card.find('[data-part="hover-card"]')
    expect(floating.classes()).toContain('scrolls')
    expect(floating.attributes('tabindex')).toBe('0')
    // the pointer leaves the host on its way into the card: the card waits, and stays once the pointer is in it
    await card.trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(HOVER_DELAY.crossMs - 1)
    await card.trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(HOVER_DELAY.crossMs)
    expect(card.find('[data-part="hover-card"]').exists()).toBe(true)
    // and it closes once the pointer has left it
    await card.trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(HOVER_DELAY.crossMs)
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
    vi.useRealTimers()
  })

  it('lets the pointer through and closes at once where it fits, as every card did before', async () => {
    vi.mocked(computePosition).mockResolvedValue(answer(8, 124))
    const card = aCard()
    await card.trigger('mouseenter')
    await flushPromises()
    expect(card.find('[data-part="hover-card"]').classes()).not.toContain('scrolls')
    expect(card.find('[data-part="hover-card"]').attributes('tabindex')).toBeUndefined()
    await card.trigger('mouseleave')
    expect(card.find('[data-part="hover-card"]').exists()).toBe(false)
  })
})
