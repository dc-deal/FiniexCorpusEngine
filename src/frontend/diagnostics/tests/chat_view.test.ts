import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { askChat, getChatInfo } from '@/api/api_client'
import { ApiError } from '@/api/api_error'
import { router } from '@/router'
import ChatView from '@/views/ChatView.vue'
import { aKnowledgeResult } from './chat_fixture'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getChatInfo: vi.fn(),
  askChat: vi.fn(),
}))

enableAutoUnmount(afterEach)

const EXAMPLES = ['Explain the Sharpe ratio to me', 'What is a maximum drawdown?']

function mountChat() {
  return mount(ChatView, { global: { plugins: [createPinia(), router] } })
}

describe('ChatView', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(askChat).mockReset()
    vi.mocked(getChatInfo).mockReset()
    vi.mocked(getChatInfo).mockResolvedValue({ enabled: true, why_not: null, examples: EXAMPLES })
  })

  it('offers the example questions first, and a click fills the input without sending it', async () => {
    const view = mountChat()
    await flushPromises()
    const examples = view.findAll('.examples button')
    expect(examples.map(example => example.text())).toEqual(EXAMPLES)
    await examples[1].trigger('click')
    expect((view.find('textarea').element as HTMLTextAreaElement).value).toBe('What is a maximum drawdown?')
    expect(vi.mocked(askChat)).not.toHaveBeenCalled()
  })

  it('says on its first screen which search answers: the hybrid one, every quote checked (the operator, 16 Nov)', async () => {
    const view = mountChat()
    await flushPromises()
    const how = view.find('[data-part="chat-how"]').text()
    expect(how).toContain("the librarian's semantic (hybrid) search")
    expect(how).toContain('vectors and BM25 fused')
    expect(how).toContain('checked word for word')
  })

  it('sends on Enter, keeps Shift+Enter for a new line, and sends nothing while an input method composes', async () => {
    vi.mocked(askChat).mockResolvedValue(aKnowledgeResult())
    const view = mountChat()
    await flushPromises()
    const box = view.find('textarea')
    await box.setValue('What is the Kelly criterion?')
    await box.trigger('keydown', { key: 'Enter', shiftKey: true })
    await box.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(vi.mocked(askChat)).not.toHaveBeenCalled()
    await box.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    const [message, threadId] = vi.mocked(askChat).mock.calls[0]
    expect(message).toBe('What is the Kelly criterion?')
    expect(threadId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
    expect(view.find('.exchange .question').text()).toBe('What is the Kelly criterion?')
    expect(view.find('.chat-turn').exists()).toBe(true)
    expect((box.element as HTMLTextAreaElement).value).toBe('')
  })

  it('shows the question under way and how long it has taken, the input closed until the turn arrives', async () => {
    let answer: (result: ReturnType<typeof aKnowledgeResult>) => void = () => {}
    vi.mocked(askChat).mockImplementation(() => new Promise(resolve => { answer = resolve }))
    const view = mountChat()
    await flushPromises()
    await view.find('textarea').setValue('Kelly?')
    await view.find('form').trigger('submit')
    expect(view.find('.exchange .question').text()).toBe('Kelly?')
    expect(view.find('.waiting-label').text()).toBe('searching and writing · 0 s')
    expect(view.find('textarea').attributes('disabled')).toBeDefined()
    answer(aKnowledgeResult())
    await flushPromises()
    expect(view.find('.waiting').exists()).toBe(false)
  })

  it('gives a failed turn\'s question back to the input and sends nothing again by itself', async () => {
    vi.mocked(askChat).mockRejectedValue(new ApiError(502, 'The turn failed: TimeoutError: no answer in 120 s'))
    const view = mountChat()
    await flushPromises()
    await view.find('textarea').setValue('Kelly?')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect((view.find('textarea').element as HTMLTextAreaElement).value).toBe('Kelly?')
    expect(view.find('.failure').text()).toContain('The turn failed: TimeoutError: no answer in 120 s')
    expect(view.findAll('.exchange')).toHaveLength(0)
    expect(vi.mocked(askChat)).toHaveBeenCalledTimes(1)
  })

  it('keeps the conversation for the tab, and a new one starts with a new id', async () => {
    vi.mocked(askChat).mockResolvedValue(aKnowledgeResult())
    const view = mountChat()
    await flushPromises()
    await view.find('textarea').setValue('Kelly?')
    await view.find('form').trigger('submit')
    await flushPromises()
    const first = vi.mocked(askChat).mock.calls[0][1]
    const reloaded = mountChat()
    await flushPromises()
    expect(reloaded.findAll('.exchange')).toHaveLength(1)
    await reloaded.find('.chat-head button').trigger('click')
    expect(reloaded.findAll('.exchange')).toHaveLength(0)
    await reloaded.find('textarea').setValue('Again?')
    await reloaded.find('form').trigger('submit')
    await flushPromises()
    expect(vi.mocked(askChat).mock.calls[1][1]).not.toBe(first)
  })

  it('says why the chat is switched off, and offers no input', async () => {
    vi.mocked(getChatInfo).mockResolvedValue({ enabled: false, why_not: 'The chat is switched off in this app.', examples: EXAMPLES })
    const view = mountChat()
    await flushPromises()
    expect(view.find('.switched-off').text()).toBe('The chat is switched off in this app.')
    expect(view.find('textarea').exists()).toBe(false)
  })
})
