import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The whole pipeline at a glance, the knowledge bases side by side (`GET /api/overview`). */
export type Overview = Schemas['Overview']
export type BaseHeadline = Schemas['BaseHeadline']
/** One box of the overview: each value of a field once, its count per knowledge base beside it. */
export type Section = Schemas['Section']
/** A box of which model did what: the pages each one worked on, and what that work cost, per knowledge base. */
export type ModelSection = Schemas['ModelSection']
export type ModelRow = Schemas['ModelRow']
/** The pages behind a figure (`GET /api/pages`), with the filters they answer. */
export type PageList = Schemas['PageList']
