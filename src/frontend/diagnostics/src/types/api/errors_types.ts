import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The findings grouped by stage, kind, block class and work (`GET /api/error-classes`). */
export type ErrorClassList = Schemas['ErrorClassList']
export type ErrorClass = Schemas['ErrorClass']
