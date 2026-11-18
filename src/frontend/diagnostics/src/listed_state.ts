/**
 * The lists' own bucket (decision 211.a): a page the check lists as one to look at, on which a person's verdict stands. The
 * API decides it (`listed_state`), the view only asks: such a page leaves the open Issues for a fold of its own, counts in
 * its own state, and keeps its check's state in its row and record, receding.
 */
export const DECIDED = 'decided_by_a_person'
