import type { Check, IssueList, OutlineUnit, PageDetail, PageRow, ReadingBlock, WorkPages } from '@/types/api/page_types'

/** Pages as the API serves them, from a free paper, so they may stand in a tracked file. */
export const KELLY = 'carta_conversano_kelly_criterion_2020'
const VISION_ROUTE = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)'
export const BLOCKED_ROUTE = 'text layer: the provider blocked the reading'
export const JUDGED_BAD_ROUTE = 'text layer: the judge found the reading bad, a person looks at it'
export const DECLINED_ROUTE = 'text layer: the reader declined the page'
export const CONTENT_FILTER = 'Output blocked by content filtering policy'

export function aCheck(overrides: Partial<Check> = {}): Check {
  return {
    state: 'ok',
    reasons: [],
    judged: true,
    why_judged: 'in the random sample',
    verdict: { verdict: 'ok', outcome: 'ok', findings: [], void: 0 },
    ...overrides,
  }
}

export function aPageRow(overrides: Partial<PageRow> = {}): PageRow {
  return {
    pdf_page: 1,
    printed_label: null,
    units: null,
    route: VISION_ROUTE,
    check: aCheck(),
    class_when_collected: 'ok',
    class_now: 'ok',
    attempt: 0,
    cost_usd: 0.0163,
    error_message: null,
    from_fallback: false,
    read: true,
    ...overrides,
  }
}

export function aWorkPages(pages: PageRow[]): WorkPages {
  return {
    knowledge_base: 'free',
    source_id: KELLY,
    title: 'Kelly criterion paper',
    summary: { pages: pages.length, states: [{ value: 'ok', count: pages.length }], routes: [{ value: VISION_ROUTE, count: pages.length }], people: [], reviews: [], categories: [] },
    // no route table unless a test asks for one, so a test of the page list counts its rows alone
    routes: [],
    route_levels: [],
    outline: null,
    outside_outline: null,
    pages,
  }
}

function aUnit(id: string, title: string, parent: string | null, first: number, last: number, pages: number,
  states: OutlineUnit['states'], ownPages: number, indexed = true): OutlineUnit {
  // the pages behind an issue count, as the API gives them (225.a): page 5 is the one issue
  const statePages = states.some(count => count.value === 'issue') ? [{ value: 'issue', pages: [5] }] : []
  return { id, level: parent ? 2 : 1, title, parent, first_page: first, last_page: last, indexed, pages, own_pages: ownPages, states,
    state_pages: statePages }
}

/**
 * The Kelly paper under an invented outline (the free export carries none yet), with the figures the API would count:
 * page 1 outside every unit, page 5 an issue, page 6 in two units, back matter at the end.
 */
export function anOutlinedWork(): WorkPages {
  const ok = (count: number) => ({ value: 'ok', count })
  return {
    ...aWorkPages([
      aPageRow({ pdf_page: 1, units: [] }),
      aPageRow({ pdf_page: 2, units: ['u001'] }),
      aPageRow({ pdf_page: 3, units: ['u002'] }),
      aPageRow({ pdf_page: 5, units: ['u003'], check: aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }] }) }),
      aPageRow({ pdf_page: 6, units: ['u003', 'u004'] }),
      aPageRow({ pdf_page: 9, units: ['u005'] }),
    ]),
    summary: { pages: 6, states: [ok(5), { value: 'issue', count: 1 }], routes: [{ value: VISION_ROUTE, count: 6 }], people: [], reviews: [], categories: [] },
    outline: [
      // the last figure each unit's own pages: those whose text is its own, outside every unit beneath it
      aUnit('u001', '1 Introduction', null, 2, 2, 1, [ok(1)], 1),
      aUnit('u002', '2 The growth rate', null, 3, 6, 3, [ok(2), { value: 'issue', count: 1 }], 1),
      aUnit('u003', '2.1 One asset', 'u002', 5, 6, 2, [{ value: 'issue', count: 1 }, ok(1)], 2),
      aUnit('u004', '3 Many assets', null, 6, 8, 1, [ok(1)], 1),
      aUnit('u005', 'References', null, 9, 9, 1, [ok(1)], 1, false),
    ],
    outside_outline: { pages: 1, states: [ok(1)], routes: [{ value: VISION_ROUTE, count: 1 }], people: [], reviews: [], categories: [] },
  }
}

export function aBlock(overrides: Partial<ReadingBlock> = {}): ReadingBlock {
  return {
    id: 'b01',
    block_class: 'paragraph',
    group: 'content',
    content: 'V',
    attrs: {},
    bbox: null,
    segments: [{ kind: 'text', content: 'The growth rate of the bankroll.' }],
    latex: null,
    rows: null,
    code: null,
    text: null,
    findings: [],
    people: [],
    ...overrides,
  }
}

export function aPageDetail(overrides: Partial<PageDetail> = {}): PageDetail {
  return {
    knowledge_base: 'free',
    source_id: KELLY,
    title: 'Kelly criterion paper',
    pdf_page: 4,
    printed_label: '4',
    previous_page: 3,
    next_page: 5,
    route: VISION_ROUTE,
    from_fallback: false,
    trace: {
      reading_key: '2b2d48e77b246c95',
      model: 'claude-sonnet-5-5',
      form: 'markdown',
      contract: 'page/1',
      validator: 'page/1.1',
      attempt: 0,
      cost_usd: 0.0163,
      stored_at: '2026-11-02T14:48:03+00:00',
      class_when_collected: 'ok',
      class_now: 'ok',
      error_type: null,
      error_message: null,
      text_sha256: '9e13150cbfdb262e',
      image_sha256: 'bb98ed7cdbd618ad',
      image_size: [1680, 2200],
      resolution: 'hi',
    },
    check: aCheck(),
    page_findings: [],
    reading: { front: { printed_label: '4' }, blocks: [aBlock()], errors: [], warnings: [], error_places: [] },
    raw: '::: {#b01 .paragraph}\nThe growth rate of the bankroll.\n:::\n',
    integrity: 'whole',
    image: { available: true, why_not: null, width: 1680, height: 2200, same_as_read: true },
    attempts: null,
    chosen: null,
    human: [],
    ...overrides,
  }
}

export function anIssueList(): IssueList {
  return {
    knowledge_bases: [{ value: 'free', count: 2 }],
    states: [{ value: 'issue', count: 1 }, { value: 'blocked', count: 1 }],
    people: [],
    reviews: [],
    categories: [],
    rows: [
      {
        knowledge_base: 'free',
        source_id: KELLY,
        title: 'Kelly criterion paper',
        pdf_page: 2,
        route: BLOCKED_ROUTE,
        check: aCheck({ state: 'blocked', judged: false, verdict: null, reasons: [{ value: 'errored', count: 1 }] }),
        error_message: CONTENT_FILTER,
        from_fallback: true,
        apart: false,
      },
      {
        knowledge_base: 'free',
        source_id: KELLY,
        title: 'Kelly criterion paper',
        pdf_page: 9,
        route: JUDGED_BAD_ROUTE,
        check: aCheck({ state: 'issue', reasons: [{ value: 'judge: bad', count: 1 }, { value: 'omission', count: 3 }] }),
        error_message: null,
        from_fallback: true,
        apart: false,
      },
    ],
  }
}
