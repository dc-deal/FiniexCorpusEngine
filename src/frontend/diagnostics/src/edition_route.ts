import type { RouteLocationRaw } from 'vue-router'
import type { Edition, KnowledgeBase } from '@/types/api/source_types'

/**
 * Where a work's own record opens here, by the view and the id the API gives: an EPUB in the EPUB view, a PDF in its page
 * list; null where it has no record here. An edition's (the operator's E1.a, 20 Nov: a kept edition keeps all it has, its
 * record among it) and the book a code work accompanies (#12) alike.
 */
export function recordRoute(target: { view?: 'pages' | 'epub' | null, id?: string | null }, kb: KnowledgeBase): RouteLocationRaw | null {
  if (!target.id || !target.view) return null
  return { name: target.view === 'epub' ? 'epub-work' : 'work', params: { kb, work: target.id } }
}

/** Where an edition's own record opens. */
export function editionRoute(edition: Edition, kb: KnowledgeBase): RouteLocationRaw | null {
  return recordRoute(edition, kb)
}
