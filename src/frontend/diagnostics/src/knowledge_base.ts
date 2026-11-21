import type { KnowledgeBase } from '@/types/api/source_types'

const BASES: readonly string[] = ['free', 'licensed'] satisfies KnowledgeBase[]

/** A knowledge base an answer names, where it is one this view knows; a word it does not know marks nothing. The
 * librarian's answers name it as a string (L1.a), so a base added there never breaks the page. */
export function knowledgeBaseOf(name: string | null | undefined): KnowledgeBase | null {
  return name && BASES.includes(name) ? name as KnowledgeBase : null
}
