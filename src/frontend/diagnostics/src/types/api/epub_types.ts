import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** A licensed EPUB work whole: its outline by heading and its sections (`GET /api/{knowledge_base}/epub/{source_id}`). */
export type EpubWork = Schemas['EpubWork']
/** One section: its text in runs, each image where its mark stands (`GET /api/{knowledge_base}/epub/{source_id}/sections/{label}`). */
export type EpubSection = Schemas['EpubSection']
