import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The corpus at a glance (`GET /api/overview`, O3.a): a headline summed over the knowledge bases served, and the latest runs. */
export type Overview = Schemas['Overview']
export type Headline = Schemas['Headline']
/** A headline figure: its sum, and each knowledge base's part of it, the detail. */
export type Figure = Schemas['Figure']
/** The pages behind a figure (`GET /api/pages`), with the filters they answer. */
export type PageList = Schemas['PageList']
