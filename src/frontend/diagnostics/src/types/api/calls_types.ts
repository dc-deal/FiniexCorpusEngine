import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The search server's call log, newest first, with its figures and filters (`GET /api/calls`). */
export type CallList = Schemas['CallList']
export type Call = Schemas['Call']
export type AnsweredPage = Schemas['AnsweredPage']
