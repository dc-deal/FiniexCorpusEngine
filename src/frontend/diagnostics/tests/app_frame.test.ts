import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, ref } from 'vue'
import { ApiError } from '@/api/api_error'
import { getAppInfo } from '@/api/api_client'
import App from '@/App.vue'
import { router } from '@/router'
import { useFrameStore } from '@/stores/frame_store'
import { useViewName } from '@/view_name'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getAppInfo: vi.fn(),
}))

enableAutoUnmount(afterEach)

// the views themselves are not what is tested here, and each would ask the API for its own data
function mountFrame() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(App, { attachTo: document.body, global: { plugins: [pinia, router], stubs: { RouterView: true } } })
}

describe('the frame (decision 149.c, the operator 2026-11-10)', () => {
  beforeEach(async () => {
    vi.mocked(getAppInfo).mockReset()
    vi.mocked(getAppInfo).mockResolvedValue({ title: 'Capstone', subtitle: 'diagnostics' })
    await router.push('/sources')
  })

  it('takes its name from the API, and names the view on show in the header and the tab', async () => {
    const frame = mountFrame()
    await flushPromises()
    expect(frame.find('.frame-title').text()).toBe('Capstone diagnostics')
    expect(frame.find('.frame-subtitle').text()).toBe('diagnostics')
    expect(frame.find('.frame-overview').text()).toBe('Overview')
    expect(frame.find('.frame-view').text()).toBe('Sources')
    expect(document.title).toBe('Capstone · Sources')
    // on the overview its name stands once, as the link in the header
    await router.push('/overview')
    await flushPromises()
    expect(frame.find('.frame-view').exists()).toBe(false)
    expect(document.title).toBe('Capstone · Overview')
  })

  it('says once, in the head of every view, which clock the times are on: the reader\u2019s own zone (stage D11.a)', async () => {
    const frame = mountFrame()
    await flushPromises()
    expect(frame.find('[data-part="clock"]').text()).toBe(`times in ${Intl.DateTimeFormat().resolvedOptions().timeZone}`)
  })

  it('says a name that did not load, and still names the view', async () => {
    vi.mocked(getAppInfo).mockRejectedValue(new ApiError(500, 'the config is not readable'))
    const frame = mountFrame()
    await flushPromises()
    expect(frame.find('.frame-title').exists()).toBe(false)
    expect(frame.text()).toContain('name not loaded')
    expect(frame.find('[title="500: the config is not readable"]').exists()).toBe(true)
    expect(frame.find('.frame-view').text()).toBe('Sources')
  })

  it('opens a menu of every other view in four groups, and closes it on a choice', async () => {
    const frame = mountFrame()
    await flushPromises()
    const button = frame.find('button[aria-label="Menu"]')
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(frame.find('#frame-menu').exists()).toBe(false)
    await button.trigger('click')
    expect(button.attributes('aria-expanded')).toBe('true')
    const groups = frame.findAll('#frame-menu [data-group]')
    expect(groups.map(group => [group.find('h2').text(), group.findAll('a').map(link => link.text())])).toEqual([
      // the librarian's tools on one page, in place of the chat and the search (L1.a)
      ['Ask', ['Librarian']],
      ['Holding', ['Sources', 'Shelf']],
      ['Checks', ['Issues', 'Errors', 'Prompts']],
      ['Operations', ['Runs', 'Calls']],
    ])
    expect(frame.find('#frame-menu a[href="#/issues"]').exists()).toBe(true)
    await router.push('/issues')
    await flushPromises()
    expect(frame.find('#frame-menu').exists()).toBe(false)
  })

  it('closes the menu on Escape and on a click outside it', async () => {
    const frame = mountFrame()
    await flushPromises()
    const button = frame.find('button[aria-label="Menu"]')
    await button.trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(frame.find('#frame-menu').exists()).toBe(false)
    expect(document.activeElement).toBe(button.element)
    await button.trigger('click')
    // a click inside the panel leaves it open; one on the view closes it
    frame.find('#frame-menu').element.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(frame.find('#frame-menu').exists()).toBe(true)
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(frame.find('#frame-menu').exists()).toBe(false)
  })

  it('shows the name a view gave itself at this address, and never at the next', async () => {
    const name = ref<string | null>(null)
    const NamingView = defineComponent({ setup() { useViewName(() => name.value) }, render: () => h('p') })
    const frame = mountFrame()
    mount(NamingView, { global: { plugins: [router] } })
    await flushPromises()
    // until its data says what it is, the route's label stands
    expect(frame.find('.frame-view').text()).toBe('Sources')
    name.value = 'Finance 2e p. 5'
    await flushPromises()
    expect(frame.find('.frame-view').text()).toBe('Finance 2e p. 5')
    expect(document.title).toBe('Capstone · Finance 2e p. 5')
    // the view on its way out gives no new name, so the next view keeps its own label
    await router.push('/calls')
    await flushPromises()
    expect(useFrameStore().named).toEqual({ path: '/sources', name: 'Finance 2e p. 5' })
    expect(frame.find('.frame-view').text()).toBe('Calls')
  })
})
