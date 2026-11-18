import type { components, operations } from '@/types/api/diagnostics_api'

/** The search's answer as `GET /api/search` serves it: the core's hits, each with where the diagnostics shows its page. */
export type SearchAnswer = components['schemas']['SearchAnswer']
export type SearchHit = components['schemas']['SearchHit']
/** Which knowledge bases a search covers, as the API's query parameter names them. */
export type Corpus = NonNullable<NonNullable<operations['search_pages']['parameters']['query']>['corpus']>
