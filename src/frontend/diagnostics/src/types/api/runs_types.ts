import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Every run of the pipeline, newest first, both knowledge bases together (`GET /api/runs`). */
export type RunList = Schemas['RunList']
export type RunLine = Schemas['RunLine']
/** One run whole, with the pages it chose a reading for (`GET /api/{knowledge_base}/runs/{run_id}`). */
export type RunDetail = Schemas['RunDetail']
