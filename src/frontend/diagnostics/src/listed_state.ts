/**
 * The lists' own bucket (decision 211.a): a page the check lists as one to look at, on which a person's verdict stands. The
 * API decides it (`listed_state`), the view only asks: such a page leaves the open Issues for a fold of its own, counts in
 * its own state, and keeps its check's state in its row and record, receding.
 */
export const DECIDED = 'decided_by_a_person'
/**
 * The same where an automated review's verdict stands (Q.a, 18 Nov, on the operator's 2.a: "a person is always manual"): the
 * core serves the page by it, so it leaves the open Issues too, for a fold of its own; it is never counted as a person's.
 */
export const DECIDED_BY_REVIEW = 'decided_by_an_automated_review'

/** Whether a list counts the page as settled, by a person or by an automated review, as the API's `listed_state` says. */
export function isDecided(state: string | null | undefined): boolean {
  return state === DECIDED || state === DECIDED_BY_REVIEW
}

/**
 * A page's standing verdict as one facet counts it: a person's on the facet "A person", an automated review's on the facet
 * "Automated review", '' where the page has none of that voice. The API says whose it is (`by_a_person`).
 */
export function standingOf(mark: { standing: string, by_a_person?: boolean } | null | undefined, byAPerson: boolean): string {
  return mark && (mark.by_a_person !== false) === byAPerson ? mark.standing : ''
}
