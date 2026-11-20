import type { RouteLocationRaw } from 'vue-router'
import type { Edition, KnowledgeBase } from '@/types/api/source_types'

/**
 * Where an edition's own record opens (the operator's E1.a, 20 Nov: a kept edition keeps all it has, its record among it): an
 * EPUB in the EPUB view, a PDF in its page list, by the id the API gives; null where it has no record here.
 */
export function editionRoute(edition: Edition, kb: KnowledgeBase): RouteLocationRaw | null {
  if (!edition.id || !edition.view) return null
  return { name: edition.view === 'epub' ? 'epub-work' : 'work', params: { kb, work: edition.id } }
}
