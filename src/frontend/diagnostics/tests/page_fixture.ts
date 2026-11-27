import type { Check, FormReading, IssueList, OutlineUnit, PageDetail, PageForm, PageRow, ReadingBlock, ShownVerdicts, WorkPages } from '@/types/api/page_types'
import type { PageLadder } from '@/types/api/ladder_types'

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

/** A page's own ladder as the API serves it (V2.a): a page served from its text layer, not read yet, planned. */
export function aPageLadder(overrides: Partial<PageLadder> = {}): PageLadder {
  return {
    rungs: [
      { level: 'text layer', reached: true, said: '4,074 characters', short: 'text layer' },
      { level: 'text served', reached: true, said: "served from the PDF's text layer", short: 'text layer' },
      { level: 'keyword search', reached: true, said: 'in search (BM25)', short: 'in BM25' },
      { level: 'semantic search', reached: null, said: 'not in the vector index on this machine', short: 'not in the index' },
      { level: 'reading and check', reached: false, said: 'no reading; planned', short: 'planned' },
    ],
    served_text: 'The Kelly criterion sizes a bet.',
    // the text layer serves it in its reading's place: the served text stands apart, named (21 Nov)
    served_by: "the PDF's text layer",
    served_why_not: null,
    held: null,
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
    image: { available: true, why_not: null, width: 1680, height: 2200, same_as_read: true, kind: 'reading', format: 'png' },
    read: true,
    attempts: null,
    chosen: null,
    human: [],
    waiting: [],
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

type FormVerdict = FormReading['verdicts'][number]
type VerdictRow = ShownVerdicts['rows'][number]

/** A verdict on a reading as the form's row says it (#18): a judge's that counts and found nothing, unless told otherwise. */
export function aFormVerdict(overrides: Partial<FormVerdict> = {}): FormVerdict {
  return { kind: 'judge', kind_said: 'judge', time: '2026-11-05T08:29:30+00:00', model: 'an-invented-judge', cost_usd: 0.0075,
    version: 'judge/1', version_said: 'counts', verdict_said: 'ok', state: 'ok', standing: true, recall: 'k1:judge/1:0',
    show_why_not: 'no difference: this judgement found nothing; use show on its reading', block: null, rules: [], hover: [], ...overrides }
}

/** A reading as the form's row says it (#18): the one shown, read and judged ok, unless told otherwise. */
export function aFormReading(overrides: Partial<FormReading> = {}): FormReading {
  return { kind_said: 'reading', key: 'k1', time: '2026-11-02T14:46:20+00:00', model: 'an-invented-reader', cost_usd: 0.016,
    version: 'page/1', result_state: 'ok', result_said: 'ok', shown: true, test_reading: false, promoted_said: null,
    promotable: false, recall: null, verdicts: [aFormVerdict()], hover: [{ label: 'reading key', value: 'k1' }], ...overrides }
}

/** A verdict as the Verdicts tab shows it (#18, decision 26): the served reading's standing judgement, unless told otherwise. */
export function aVerdictRow(overrides: Partial<VerdictRow> = {}): VerdictRow {
  return { kind: 'judge', kind_said: 'judge', standing: true, standing_said: 'standing', time: '2026-11-05T08:29:30+00:00',
    verdict: 'ok', state: 'ok', reason: null, about: 'the page', recall: 'k1:judge/1:0', answered: null, who: 'machine',
    who_said: 'judge/1 · an-invented-judge', hover: [], ...overrides }
}

/** The verdicts as shown (decision 26): on the served reading, unless told otherwise; the count is the rows'. */
export function shownVerdicts(rows: VerdictRow[] = [aVerdictRow()], overrides: Partial<ShownVerdicts> = {}): ShownVerdicts {
  return { said: 'as shown: the verdicts on the served reading', recalled: false, count: rows.length, rows, ...overrides }
}

/** A page's form (#18): one reading shown with its judge's verdict, no Lab, the verdict in the Verdicts tab. */
export function aPageForm(overrides: Partial<PageForm> = {}): PageForm {
  const readings = overrides.readings ?? [aFormReading()]
  const lab = overrides.lab ?? []
  const verdicts = overrides.verdicts ?? shownVerdicts()
  return { shown_judgement: 'j1', readings_count: readings.length, lab_count: lab.length, ...overrides, readings, lab, verdicts }
}
