import type { Ladder } from '@/types/api/ladder_types'
import type { Work } from '@/types/api/source_types'

/** A PDF work's coverage ladder as the API serves it (U1.a): the free finance book's figures, which may stand in a tracked file. */
export function aLadder(overrides: Partial<Ladder> = {}): Ladder {
  // its number and its share are the API's (L1.a), written here as it serves them
  const rung = (number: number, level: Ladder['rungs'][number]['level'], count: number | null, share: number | null, said: string) => ({
    level, number, count, of: 629, share, said, means: `what ${level} counts`, by_base: {}, pages_filter: null, warn: false })
  return {
    unit: 'PDF pages',
    whole: 629,
    rungs: [rung(1, 'text served', 612, 97, '612 of 629 PDF pages'), rung(2, 'keyword search', 539, 86, '539 of 629 PDF pages'),
      rung(3, 'semantic chunks', 592, 94, '2,396 chunks over 592 of 629 PDF pages'),
      rung(4, 'read', 629, 100, '629 of 629 PDF pages, 629 passed'), rung(5, 'checked', 407, 65, '407 of 629 PDF pages')],
    by_route: { 'vision reading': 612 },
    held: null,
    not_served: null,
    unplaced: {},
    states: [{ value: 'ok', count: 400 }, { value: 'issue', count: 9, served: 9 }, { value: 'blocked', count: 3, served: null }],
    planned: 629,
    passed: 629,
    built_at: null,
    ...overrides,
  }
}

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
    // a work read page by page opens its page list, as the API says of it (U1.a)
    page_list: Boolean(overrides.readings),
    ...overrides,
  }
}
