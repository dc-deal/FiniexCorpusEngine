import axios from 'axios'
import { ApiError } from '@/api/api_error'
import type { AppInfo } from '@/types/api/app_types'
import type { CallList } from '@/types/api/calls_types'
import type { CodePage, CodeWork } from '@/types/api/code_types'
import type { ErrorClassList } from '@/types/api/errors_types'
import type { EpubSection, EpubWork } from '@/types/api/epub_types'
import type { HtmlArticle, HtmlWork } from '@/types/api/html_types'
import type { LibrarianCall, LibrarianInfo } from '@/types/api/librarian_types'
import type { Overview, PageList } from '@/types/api/overview_types'
import type { PromptList } from '@/types/api/prompts_types'
import type { IssueList, PageChunks, PageDetail, Recalled, WorkPages } from '@/types/api/page_types'
import type { RunDetail, RunList } from '@/types/api/runs_types'
import type { Shelf } from '@/types/api/shelf_types'
import type { KnowledgeBase, Work } from '@/types/api/source_types'
import type { PromoteGiven, PromoteRequest, Proposal, ProposalRequest, TablePreview, VerdictForm, VerdictGiven,
  VerdictRequest } from '@/types/api/verdict_types'

/** Same origin in the build; in development Vite forwards /api to the API process. */
const http = axios.create({ baseURL: '/api' })

http.interceptors.response.use(response => response, (error: unknown) => Promise.reject(typedError(error)))

/** A failed request as an `ApiError`; anything that is not a failed request passes unchanged. */
export function typedError(error: unknown): unknown {
  if (!axios.isAxiosError(error)) return error
  if (!error.response) return new ApiError(null, error.message)
  // FastAPI answers {"detail": "..."}; a validation error carries a list there instead
  const detail = (error.response.data as { detail?: unknown } | undefined)?.detail
  return new ApiError(error.response.status, typeof detail === 'string' ? detail : error.message)
}

/** A work within its knowledge base: an id alone is not a key (decision 80.a). */
function workPath(knowledgeBase: KnowledgeBase, sourceId: string): string {
  return `/${knowledgeBase}/works/${encodeURIComponent(sourceId)}`
}

/** The view's name for its header and its browser tab, as the app config holds it (149.c). */
export async function getAppInfo(): Promise<AppInfo> {
  const response = await http.get<AppInfo>('/app')
  return response.data
}

export async function getWorks(): Promise<Work[]> {
  const response = await http.get<Work[]>('/works')
  return response.data
}

export async function getWorkPages(knowledgeBase: KnowledgeBase, sourceId: string): Promise<WorkPages> {
  const response = await http.get<WorkPages>(`${workPath(knowledgeBase, sourceId)}/pages`)
  return response.data
}

export async function getPage(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<PageDetail> {
  const response = await http.get<PageDetail>(`${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}`)
  return response.data
}

/** A read page's chunks in semantic search's index, placed in its quoted blocks (W4): asked when "as served" is switched on. */
export async function getPageChunks(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<PageChunks> {
  const response = await http.get<PageChunks>(`${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}/chunks`)
  return response.data
}

/** One judgement of a page shown as it judged (181.a), by the id the page's judgement carries. */
export async function getRecall(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number, judgement: string): Promise<Recalled> {
  const response = await http.get<Recalled>(`${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}/recall`, { params: { judgement } })
  return response.data
}

/** An HTML work's outline and sections, from the search index (the operator's 6.a). */
export async function getHtmlWork(knowledgeBase: KnowledgeBase, sourceId: string): Promise<HtmlWork> {
  const response = await http.get<HtmlWork>(`/${knowledgeBase}/html/${encodeURIComponent(sourceId)}`)
  return response.data
}

/** A licensed EPUB work's outline and sections (123.a), as the librarian serves them. */
export async function getEpubWork(knowledgeBase: KnowledgeBase, sourceId: string): Promise<EpubWork> {
  const response = await http.get<EpubWork>(`/${knowledgeBase}/epub/${encodeURIComponent(sourceId)}`)
  return response.data
}

/** One section of a licensed EPUB work: its text in runs, each image where its mark stands. */
export async function getEpubSection(knowledgeBase: KnowledgeBase, sourceId: string, label: string): Promise<EpubSection> {
  const response = await http.get<EpubSection>(`/${knowledgeBase}/epub/${encodeURIComponent(sourceId)}/sections/${encodeURIComponent(label)}`)
  return response.data
}

/** A book's companion code (#12): its folders and files, each with the core's catalog entry. */
export async function getCodeWork(knowledgeBase: KnowledgeBase, work: string): Promise<CodeWork> {
  const response = await http.get<CodeWork>(`/${knowledgeBase}/code/${encodeURIComponent(work)}`)
  return response.data
}

/** One file of a code work by its label, its path in the work sent as one encoded segment. */
export async function getCodePage(knowledgeBase: KnowledgeBase, work: string, label: string): Promise<CodePage> {
  const response = await http.get<CodePage>(`/${knowledgeBase}/code/${encodeURIComponent(work)}/files/${encodeURIComponent(label)}`)
  return response.data
}

/** Where an EPUB's image is read from: its path inside the EPUB, served from the zip by the API. */
export function epubImageUrl(knowledgeBase: KnowledgeBase, sourceId: string, href: string): string {
  return `/api/${knowledgeBase}/epub/${encodeURIComponent(sourceId)}/image?href=${encodeURIComponent(href)}`
}

/** The article, chapter or other top unit holding a section, whole: every section with its original and chunks. */
export async function getHtmlArticle(knowledgeBase: KnowledgeBase, sourceId: string, label: string): Promise<HtmlArticle> {
  const response = await http.get<HtmlArticle>(`/${knowledgeBase}/html/${encodeURIComponent(sourceId)}/articles/${encodeURIComponent(label)}`)
  return response.data
}

/** The judge's and stage 2's findings grouped by kind, block class and work, with their pages. */
export async function getErrorClasses(): Promise<ErrorClassList> {
  const response = await http.get<ErrorClassList>('/error-classes')
  return response.data
}

/** Every version of the reader's and the judge's instructions, with its change from the one before (148.a). */
export async function getPrompts(): Promise<PromptList> {
  const response = await http.get<PromptList>('/prompts')
  return response.data
}

export async function getShelf(): Promise<Shelf> {
  const response = await http.get<Shelf>('/shelf')
  return response.data
}

export async function getCalls(): Promise<CallList> {
  const response = await http.get<CallList>('/calls')
  return response.data
}

/** The librarian's tools as the running server lists them (L1.a); the page's first call opens its one session with it. */
export async function getLibrarian(): Promise<LibrarianInfo> {
  const response = await http.get<LibrarianInfo>('/librarian')
  return response.data
}

/** One tool call over MCP to the running librarian, as an IDE session makes it: `semantic_search` spends a fraction of a
 * cent, and a model call with the router on. */
export async function callLibrarian(tool: string, args: Record<string, unknown>): Promise<LibrarianCall> {
  const response = await http.post<LibrarianCall>('/librarian/call', { tool, arguments: args })
  return response.data
}

export async function getRuns(): Promise<RunList> {
  const response = await http.get<RunList>('/runs')
  return response.data
}

export async function getRun(knowledgeBase: KnowledgeBase, runId: number): Promise<RunDetail> {
  const response = await http.get<RunDetail>(`/${knowledgeBase}/runs/${runId}`)
  return response.data
}

export async function getIssues(): Promise<IssueList> {
  const response = await http.get<IssueList>('/issues')
  return response.data
}

export async function getOverview(): Promise<Overview> {
  const response = await http.get<Overview>('/overview')
  return response.data
}

/** The pages behind a figure of the overview: every page served that matches every filter given. */
export async function getPages(filters: Record<string, string>): Promise<PageList> {
  const response = await http.get<PageList>('/pages', { params: filters })
  return response.data
}

/** Whether a person's verdict is taken here, the dialog's lists, and each knowledge base's background export (213.b). */
export async function getVerdictForm(): Promise<VerdictForm> {
  const response = await http.get<VerdictForm>('/verdict')
  return response.data
}

/** A person's verdict on the reading a page shows: the one request here that writes, taken only from this machine. */
/** A person's promotion of a Lab reading (#18), behind the same switch and guard as a verdict. */
export async function promoteReading(asked: PromoteRequest): Promise<PromoteGiven> {
  const response = await http.post<PromoteGiven>('/verdict/promote', asked)
  return response.data
}

export async function giveVerdict(verdict: VerdictRequest): Promise<VerdictGiven> {
  const response = await http.post<VerdictGiven>('/verdict', verdict)
  return response.data
}

/** A correction's text as the table it would be, before it is sent; writes nothing. */
export async function previewTable(text: string): Promise<TablePreview> {
  const response = await http.post<TablePreview>('/verdict/preview', { text })
  return response.data
}

/** ✦ propose (W2.a): a model's correction of one block; a 409 carries the core's reason where it sends nothing. */
export async function proposeCorrection(asked: ProposalRequest): Promise<Proposal> {
  const response = await http.post<Proposal>('/verdict/propose', asked)
  return response.data
}

/** Where the original of a page is served, for an `<img>`: the image the reader received, rendered again. */
export function pageImageUrl(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): string {
  return `/api${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}/image.png`
}
