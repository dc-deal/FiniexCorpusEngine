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
export type PageChunks = Schemas['PageChunks']
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
export type StateCount = Schemas['StateCount']
/** The pages a person should look at, over every work of every knowledge base served (`GET /api/issues`). */
export type IssueList = Schemas['IssueList']
/** A page as a list across works shows it, in the issues and behind a figure of the overview. */
export type IssueRow = Schemas['IssueRow']
/** A page's readings and verdicts in one form (#18): Readings, Lab and Verdicts, every word and count served. */
export type PageForm = Schemas['PageForm']
export type ShownVerdicts = Schemas['ShownVerdicts']
/** One reading in the form's Readings or Lab tab. */
export type FormReading = Schemas['FormReading']
