import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Every version of the reader's and the judge's instructions (`GET /api/prompts`, 148.a). */
export type PromptList = Schemas['PromptList']
/** One version of a role's instructions, with its files. */
export type PromptVersion = Schemas['PromptVersion']
/** One file of a version: its part, text, hashes and change from the version before. */
export type PromptFile = Schemas['PromptFile']
