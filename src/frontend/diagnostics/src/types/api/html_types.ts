import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** An HTML work whole: its outline by heading and its sections (`GET /api/{knowledge_base}/html/{source_id}`). */
export type HtmlWork = Schemas['HtmlWork']
export type HtmlNode = Schemas['HtmlNode']
/** One section as indexed, its chunks in order (`GET /api/{knowledge_base}/html/{source_id}/sections/{label}`). */
export type HtmlSection = Schemas['HtmlSection']
/** A top unit of the outline whole, on one scroll (`GET /api/{knowledge_base}/html/{source_id}/articles/{label}`). */
export type HtmlArticle = Schemas['HtmlArticle']
