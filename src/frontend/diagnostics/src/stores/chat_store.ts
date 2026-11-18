import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { askChat, getChatInfo } from '@/api/api_client'
import type { ChatInfo, ChatResult } from '@/types/api/chat_types'

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught))
}

/** One question and the turn that answered it. */
export interface ChatEntry {
  question: string
  result: ChatResult
}

interface KeptConversation {
  threadId: string
  entries: ChatEntry[]
}

// The conversation is kept for this tab, so a reload shows what the agent still remembers of it; a new tab starts afresh.
const KEPT = 'chat.conversation.v1'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function kept(): KeptConversation | null {
  try {
    const conversation = JSON.parse(sessionStorage.getItem(KEPT) ?? 'null') as KeptConversation | null
    return conversation && UUID.test(conversation.threadId) && Array.isArray(conversation.entries) ? conversation : null
  } catch {
    return null
  }
}

/**
 * The one conversation of this tab (decision 100.a): its id, the turns so far, and whether one is under way. A failed turn
 * leaves the list, so its question can be given back to the input; nothing is sent twice by itself, since every turn costs.
 */
export const useChatStore = defineStore('chat', () => {
  const info = ref<ChatInfo | null>(null)
  const infoError = ref<Error | null>(null)
  const start = kept()
  const threadId = ref(start?.threadId ?? crypto.randomUUID())
  const entries = ref<ChatEntry[]>(start?.entries ?? [])
  const sending = ref(false)
  const pending = ref<string | null>(null)  // the question under way, shown until its turn arrives or fails
  const failure = ref<Error | null>(null)

  watch([threadId, entries], () => {
    try {
      sessionStorage.setItem(KEPT, JSON.stringify({ threadId: threadId.value, entries: entries.value }))
    } catch {
      // a full or blocked storage keeps nothing: the conversation then lasts as long as the page
    }
  }, { deep: true })

  async function loadInfo(): Promise<void> {
    infoError.value = null
    try {
      info.value = await getChatInfo()
    } catch (caught) {
      infoError.value = asError(caught)
    }
  }

  /** Sends one message; false where the turn failed, so the view can give the question back to the input. */
  async function send(message: string): Promise<boolean> {
    if (sending.value) return false
    sending.value = true
    pending.value = message
    failure.value = null
    try {
      entries.value.push({ question: message, result: await askChat(message, threadId.value) })
      return true
    } catch (caught) {
      failure.value = asError(caught)
      return false
    } finally {
      sending.value = false
      pending.value = null
    }
  }

  function newConversation(): void {
    threadId.value = crypto.randomUUID()
    entries.value = []
    failure.value = null
  }

  return { info, infoError, threadId, entries, sending, pending, failure, loadInfo, send, newConversation }
})
