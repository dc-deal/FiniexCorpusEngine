import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AppToasts from '@/components/base/AppToasts.vue'
import { TOAST_MS, useToastStore } from '@/stores/toast_store'

enableAutoUnmount(afterEach)

describe('the app\'s toasts (21 Nov)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stands about 4 s, held while pointed at or focused, its time running on from where it stood', async () => {
    const store = useToastStore()
    const id = store.show({ text: 'Verdict recorded · b05 · accept', detail: 'the licensed export runs in the background' })
    await vi.advanceTimersByTimeAsync(1000)
    store.hold(id)
    await vi.advanceTimersByTimeAsync(10 * TOAST_MS)
    expect(store.toasts.map(toast => toast.text)).toEqual(['Verdict recorded · b05 · accept'])
    // its line follows what it set going while it stands
    expect(store.update(id, { detail: 'served from now on' })).toBe(true)
    store.release(id)
    await vi.advanceTimersByTimeAsync(TOAST_MS - 1000 - 1)
    expect(store.toasts).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(store.toasts).toEqual([])
    // a toast gone is left gone
    expect(store.update(id, { detail: 'late' })).toBe(false)
  })

  it('says each in a polite status, holds it while hovered, and closes it on its ×', async () => {
    const store = useToastStore()
    const toasts = mount(AppToasts, { attachTo: document.body })
    store.show({ text: 'Verdict recorded · b05 · accept', detail: 'the licensed export runs in the background' })
    await toasts.vm.$nextTick()
    const region = toasts.find('[data-part="toasts"]')
    expect([region.attributes('role'), region.attributes('aria-live')]).toEqual(['status', 'polite'])
    expect(toasts.find('[data-part="toast-text"]').text()).toBe('Verdict recorded · b05 · accept')
    expect(toasts.find('[data-part="toast-detail"]').text()).toBe('the licensed export runs in the background')
    await toasts.find('[data-toast]').trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(2 * TOAST_MS)
    expect(toasts.find('[data-toast]').exists()).toBe(true)
    await toasts.find('[data-part="toast-close"]').trigger('click')
    expect(toasts.find('[data-toast]').exists()).toBe(false)
  })
})
