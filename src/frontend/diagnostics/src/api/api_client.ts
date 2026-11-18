import axios from 'axios'
import { ApiError } from '@/api/api_error'
import type { AppInfo } from '@/types/api/app_types'
import type { CallList } from '@/types/api/calls_types'
import type { ChatInfo, ChatResult } from '@/types/api/chat_types'
import type { ErrorClassList } from '@/types/api/errors_types'
import type { HtmlArticle, HtmlWork } from '@/types/api/html_types'
import type { Overview, PageList } from '@/types/api/overview_types'
import type { PromptList } from '@/types/api/prompts_types'
import type { IssueList, PageDetail, QuotedText, Recalled, WorkPages } from '@/types/api/page_types'
import type { RunDetail, RunList } from '@/types/api/runs_types'
import type { Shelf } from '@/types/api/shelf_types'
import type { Corpus, SearchAnswer } from '@/types/api/search_types'
import type { KnowledgeBase, Work } from '@/types/api/source_types'
import type { TablePreview, VerdictForm, VerdictGiven, VerdictRequest } from '@/types/api/verdict_types'

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

/** The text the search and the chat quote for a page; the first call for a book the export has not cut may take a minute. */
export async function getQuoted(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): Promise<QuotedText> {
  const response = await http.get<QuotedText>(`${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}/quoted`)
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

export async function getChatInfo(): Promise<ChatInfo> {
  const response = await http.get<ChatInfo>('/chat')
  return response.data
}

/** One turn of the chat: the one request here that spends money. A turn takes seconds, the first after a start longer. */
export async function askChat(message: string, threadId: string): Promise<ChatResult> {
  const response = await http.post<ChatResult>('/chat', { message, thread_id: threadId })
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

/** The search the MCP server answers with; the first one after a start may wait for the index: 20 s free, 50 s with both. */
export async function searchPages(query: string, corpus: Corpus): Promise<SearchAnswer> {
  const response = await http.get<SearchAnswer>('/search', { params: { q: query, corpus } })
  return response.data
}

/** Whether a person's verdict is taken here, the dialog's lists, and each knowledge base's background export (213.b). */
export async function getVerdictForm(): Promise<VerdictForm> {
  const response = await http.get<VerdictForm>('/verdict')
  return response.data
}

/** A person's verdict on the reading a page shows: the one request here that writes, taken only from this machine. */
export async function giveVerdict(verdict: VerdictRequest): Promise<VerdictGiven> {
  const response = await http.post<VerdictGiven>('/verdict', verdict)
  return response.data
}

/** A correction's text as the table it would be, before it is sent; writes nothing. */
export async function previewTable(text: string): Promise<TablePreview> {
  const response = await http.post<TablePreview>('/verdict/preview', { text })
  return response.data
}

/** Where the original of a page is served, for an `<img>`: the image the reader received, rendered again. */
export function pageImageUrl(knowledgeBase: KnowledgeBase, sourceId: string, pdfPage: number): string {
  return `/api${workPath(knowledgeBase, sourceId)}/pages/${pdfPage}/image.png`
}
