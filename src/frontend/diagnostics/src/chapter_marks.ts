import type { InjectionKey, Ref } from 'vue'
import type { OutlineUnit } from '@/types/api/page_types'

/**
 * A chapter's count as a way to its pages (decision 225.a, the operator: chapter 6's red "1" should lead to "Multiple Choice" and
 * p. 398): the work's view opens the units that hold the pages behind a count and marks those pages, the first in view.
 * Which pages stand behind a count is the API's (`OutlineUnit.state_pages`); the view only opens and marks.
 */
export interface ChapterMarks {
  // the pages marked by the count last chosen
  marked: Ref<Set<number>>
  show: (pages: number[]) => void
}

export const CHAPTER_MARKS: InjectionKey<ChapterMarks> = Symbol('chapterMarks')

/** A unit known by its first page and title, which stay when the core renumbers the outline's ids (2026-11-10). */
export function unitKey(unit: Pick<OutlineUnit, 'first_page' | 'title'>): string {
  return `${unit.first_page}:${unit.title}`
}
