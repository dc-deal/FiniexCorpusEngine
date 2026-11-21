import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** The librarian's tools as the running server lists them (L1.a), or why it does not answer. */
export type LibrarianInfo = Schemas['LibrarianInfo']
/** One tool: its description, a line on what it costs and takes, and its form's fields from its input schema. */
export type LibrarianTool = Schemas['LibrarianTool']
export type LibrarianField = Schemas['LibrarianField']
/** One call's answer: its head line, its tool's parts, and the answer as it came. */
export type LibrarianCall = Schemas['LibrarianCall']
export type HitCard = Schemas['HitCard']
export type WorkRow = Schemas['WorkRow']
export type FoundWork = Schemas['FoundWork']
export type Contents = Schemas['Contents']
