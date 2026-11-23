import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** A book's companion code whole: its folders and files, each with the core's catalog entry (`GET /api/{knowledge_base}/code/{work}`). */
export type CodeWork = Schemas['CodeWork']
/** One file of a code work, its text numbered (`GET /api/{knowledge_base}/code/{work}/files/{label}`). */
export type CodePage = Schemas['CodePage']
/** What the core's catalog says of one file's unit: its name, kind, category, inputs and a model's sentence. */
export type CodeUnit = Schemas['CodeUnit']
