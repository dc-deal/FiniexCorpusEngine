import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** A work's pages as `GET /api/{knowledge_base}/works/{source_id}/pages` serves them. */
export type WorkPages = Schemas['WorkPages']
export type PageRow = Schemas['PageRow']
/** One route a work's pages are served by: its level, source, reader, why and pages (the operator, 10 Nov). */
export type RouteRow = Schemas['RouteRow']
/** A route level and what it means, in the core's words: the legend of the routes. */
export type RouteLevel = Schemas['RouteLevel']
/** One unit of a work's own order, with its whole subtree's pages in figures (decision 84.a). */
export type OutlineUnit = Schemas['OutlineUnit']
/** The pages behind one count of a unit, which the count opens (225.a). */
export type StatePages = Schemas['StatePages']
/** One page with its reading, trace, check and original (`GET /api/{knowledge_base}/works/{source_id}/pages/{pdf_page}`). */
export type PageDetail = Schemas['PageDetail']
/** The text the search and the chat quote for a page (`GET .../pages/{pdf_page}/quoted`). */
export type QuotedText = Schemas['QuotedText']
export type ReadingBlock = Schemas['Block']
export type Finding = Schemas['Finding']
/** A person's verdict on a page or a block of it (146.a). */
export type PersonVerdict = Schemas['PersonVerdict']
/** A person's standing verdict on the reading a page shows, beside its state (166.a). */
export type PersonMark = Schemas['PersonMark']
/** One judgement shown on the page as it judged (181.a). */
export type Recalled = Schemas['Recalled']
/** One judge's judgement of one reading, by the version of its prompt (147.a). */
export type Judgement = Schemas['Judgement']
/** One reading bought for a page, the pipeline's or a reader prototype's (210.a), with its judgements. */
export type Attempt = Schemas['Attempt']
/** A rule a judge proposed for the reader, never applied (202.a). */
export type ReaderRule = Schemas['ReaderRule']
export type Segment = Schemas['Segment']
/** One cell of a table as the core's table parser gives it: a reading's, or a person's correction of one (204.a). */
export type Cell = Schemas['Cell']
/** The correction that stands for a block (229.a): a person's latest that applies, drawn first, never served. */
export type StandingCorrection = Schemas['StandingCorrection']
/** A validator error parted into the block and the line it names, and whether a person has looked (228.a). */
export type ReadingError = Schemas['ReadingError']
export type Check = Schemas['Check']
export type Count = Schemas['Count']
/** The pages a person should look at, over every work of every knowledge base served (`GET /api/issues`). */
export type IssueList = Schemas['IssueList']
/** A page as a list across works shows it, in the issues and behind a figure of the overview. */
export type IssueRow = Schemas['IssueRow']
