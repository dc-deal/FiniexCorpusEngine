import type { components } from '@/types/api/diagnostics_api'

/** A work as `GET /api/works` serves it (pydantic model `Work`), from the free catalog or a licensed export. */
export type Work = components['schemas']['Work']
/** The knowledge bases the core exports, by the name every row carries (decision 80.a). */
export type KnowledgeBase = Work['knowledge_base']
/** A work held in more than one edition (E1.a): one served, the others kept, each edition's own record marked on it. */
export type Editions = components['schemas']['Editions']
export type Edition = components['schemas']['Edition']
