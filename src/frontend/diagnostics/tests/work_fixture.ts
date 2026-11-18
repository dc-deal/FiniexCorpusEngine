import type { Work } from '@/types/api/source_types'

/** A work as the API serves it; a free source, so it may stand in a tracked file. */
export function aWork(overrides: Partial<Work> = {}): Work {
  return {
    knowledge_base: 'free',
    id: 'openstax_principles_of_finance_2e',
    title: 'Principles of Finance 2e',
    authors: 'Julie Dahlquist, Rainford Knight',
    publisher: 'OpenStax',
    year: 2026,
    licence: 'CC BY-NC-SA 4.0',
    format: 'pdf',
    shelf: 'trading_finance',
    ...overrides,
  }
}
