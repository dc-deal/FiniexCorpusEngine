<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import ChatTurn from '@/components/ChatTurn.vue'
import { useChatStore } from '@/stores/chat_store'

/**
 * The chat, compact (decision 100.a): one conversation per tab, the example questions on its first screen, then question
 * and turn after turn. Enter sends, Shift+Enter breaks the line, and a key that confirms a composing input method sends
 * nothing. While a turn runs the line says how long it has taken, in seconds, rather than a progress nothing measures; a
 * failed turn gives its question back to the input and is never sent again by itself, since every turn costs.
 */
const store = useChatStore()
const { info, infoError, entries, sending, pending, failure } = storeToRefs(store)
const draft = ref('')
const input = ref<HTMLTextAreaElement | null>(null)
const thread = ref<HTMLElement | null>(null)
const elapsed = ref(0)
let ticking: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  void store.loadInfo()
})

onUnmounted(() => clearInterval(ticking))

watch(sending, now => {
  clearInterval(ticking)
  elapsed.value = 0
  if (now) {
    const started = Date.now()
    ticking = setInterval(() => {
      elapsed.value = Math.floor((Date.now() - started) / 1000)
    }, 1000)
  }
})

// the newest turn into view as it arrives; only the thread scrolls
watch(() => entries.value.length, async () => {
  await nextTick()
  thread.value?.lastElementChild?.scrollIntoView?.({ block: 'start' })
})

function useExample(example: string): void {
  draft.value = example
  input.value?.focus()
}

async function send(): Promise<void> {
  const message = draft.value.trim()
  if (!message || sending.value) return
  draft.value = ''
  if (!await store.send(message)) draft.value = message
}

function onKeydown(event: KeyboardEvent): void {
  // a key that confirms a composing input method's text is no request to send it
  if (event.isComposing || event.keyCode === 229) return
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}
</script>

<template>
  <section class="chat-view">
    <header class="chat-head">
      <h1 class="view-title">Chat</h1>
      <AppButton v-if="entries.length" size="compact" :disabled="sending" @click="store.newConversation()">New conversation</AppButton>
    </header>

    <ApiFailure v-if="infoError" :error="infoError" @retry="store.loadInfo()" />
    <LoadingLine v-else-if="!info" />
    <p v-else-if="!info.enabled" class="switched-off">{{ info.why_not }}</p>
    <template v-else>
      <div v-if="!entries.length && !pending" class="start">
        <p class="start-title">Ask the knowledge base: every answer with a verbatim quote and its page.</p>
        <!-- which search answers here (the operator, 16 Nov), as the keyword search says it is the other one -->
        <p class="start-how" data-part="chat-how">
          Answers come through the librarian's semantic (hybrid) search: a router, vectors and BM25 fused, a relevance
          floor. Every quote is checked word for word against its page.
        </p>
        <p class="start-label">Try one of these</p>
        <ul class="examples">
          <li v-for="example in info.examples" :key="example">
            <AppButton variant="quiet" class="example" @click="useExample(example)">{{ example }}</AppButton>
          </li>
        </ul>
      </div>

      <ol ref="thread" class="thread">
        <li v-for="(entry, at) in entries" :key="`${at}/${entry.result.turn_id}`" class="exchange">
          <p class="question">{{ entry.question }}</p>
          <ChatTurn :result="entry.result" />
        </li>
        <li v-if="pending" class="exchange">
          <p class="question">{{ pending }}</p>
          <div class="waiting">
            <LoadingLine />
            <span class="waiting-label">searching and writing · {{ elapsed }} s</span>
          </div>
        </li>
      </ol>

      <p v-if="failure" class="failure" role="alert">{{ failure.message }} Your question is back in the box; nothing was sent again.</p>

      <form class="ask" @submit.prevent="send">
        <textarea
          ref="input"
          v-model="draft"
          class="draft"
          rows="2"
          :disabled="sending"
          placeholder="Ask about trading, finance, accounting or running software reliably"
          aria-label="Your question"
          @keydown="onKeydown"
        />
        <AppButton type="submit" :disabled="sending || !draft.trim()">Send</AppButton>
      </form>
    </template>
  </section>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  max-width: 60rem;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.switched-off,
.start-how,
.start-label,
.waiting-label {
  color: var(--color-text-secondary);
}

.start {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.examples {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.example {
  text-align: left;
}

.thread {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.exchange {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* the question as it was typed: text, its line breaks kept */
.question {
  align-self: flex-end;
  max-width: 80%;
  white-space: pre-wrap;
  padding: var(--space-sm) var(--space-md);
  border-radius: 6px;
  background-color: var(--color-bg-elevated);
}

.waiting {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.failure {
  color: var(--color-error);
}

.ask {
  display: flex;
  gap: var(--space-sm);
  align-items: flex-end;
}

.draft {
  flex: 1;
  resize: vertical;
  min-height: 3rem;
  padding: var(--space-sm);
  font: inherit;
  color: var(--color-text-primary);
  background-color: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
}
</style>
