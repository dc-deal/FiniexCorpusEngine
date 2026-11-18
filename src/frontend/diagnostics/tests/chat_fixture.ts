import type { ChatResult } from '@/types/api/chat_types'

export const KELLY = 'carta_conversano_kelly_criterion_2020'

const CITATION = { text: 'Practical Implementation of the Kelly Criterion · p. 3', link: null, licence: 'CC BY 4.0' }

const PASSED = [
  { check: 'input', name: 'Input check: not empty, not too long', status: 'passed', detail: '28 characters' },
  { check: 'quotes', name: 'Quotes appear word for word in their passage', status: 'warning', detail: '1 kept, 1 dropped' },
  { check: 'call_limit', name: 'Model and tool calls per message within the cap', status: 'passed', detail: '2 model and 1 tool calls' },
]

/** A knowledge turn as the API serves it; invented words over a free work, so it may stand in a tracked file. */
export function aKnowledgeResult(overrides: Partial<ChatResult> = {}): ChatResult {
  return {
    kind: 'knowledge',
    turn_id: 'a1b2c3d4',
    question: 'What is the Kelly criterion?',
    text: '',
    turn: {
      behaviour: 'answer',
      answer: 'The Kelly criterion sizes a bet as a **fraction** of wealth [1].',
      quotes: [{ passage: 1, text: 'the optimal strategy is to bet a *fraction* <b>of</b> wealth', citation: CITATION,
        view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } }],
      sources: [{ number: 1, work: KELLY, page: { label: '3', pdf: '3', printed: '2' }, citation: CITATION,
        view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } },
      { number: 2, work: 'wikipedia_trading_set', page: { label: 's9', pdf: null, printed: null },
        citation: { text: 'Kelly criterion, Wikipedia · s9', link: 'https://en.wikipedia.org/wiki/Kelly_criterion#Proof', licence: 'CC BY-SA 4.0' },
        view: null }],
      gaps: 'How to size a **portfolio** of bets.',
      follow_up: null,
      disclaimer: 'Not trading advice. For educational purposes only.',
    },
    server: null,
    usd: 0.0031,
    seconds: 11.24,
    model_calls: 2,
    call_limit_reached: null,
    security: PASSED,
    logged: true,
    ...overrides,
  }
}
