/**
 * A person's verdict as a person says it, one wording wherever a verdict stands (the operator, 11 Nov: one representation for one
 * kind of thing): the core's word is the verb, said as what the person did.
 */
export const STANDING: Record<string, string> = { accept: 'accepted', reject: 'rejected', note: 'noted' }

/**
 * Who has looked at a validator's error (228.a): "a person noted and corrected b04", "a person accepted the page". The API
 * says which verdict, whether it names the block or the page, and whether a correction stands; this says it in words.
 */
export function lookedSaid(error: { looked?: string | null, looked_at?: string | null, looked_by_a_person?: boolean | null,
  corrected?: boolean, block?: string | null }): string {
  if (!error.looked) return ''
  const did = STANDING[error.looked] ?? error.looked
  const who = error.looked_by_a_person === false ? 'an automated review' : 'a person'
  return `${who} ${did}${error.corrected ? ' and corrected' : ''} ${error.looked_at === 'block' && error.block ? error.block : 'the page'}`
}

/**
 * Whose verdict it is, named the same wherever it stands (the operator's 2.a, 18 Nov: "a person is always manual"): a person's
 * own, or an automated review a Claude Code session gave on the operator's delegation. The API says which (`by_a_person`); a
 * record without it is a person's, as the core reads it. Each returns the label without its colon.
 */
interface Voiced { by_a_person?: boolean | null }

function reviewed(one: Voiced | null | undefined): boolean {
  return one?.by_a_person === false
}

export function verdictBy(one: Voiced | null | undefined): string {
  return reviewed(one) ? 'Automated review' : 'A person'
}

export function verdictLabel(one: Voiced, onThePage = false): string {
  return `${reviewed(one) ? 'Automated review' : "A person's verdict"}${onThePage ? ' on the page' : ''}`
}

export function correctionLabel(one: Voiced, earlier = false): string {
  if (reviewed(one)) return earlier ? 'An earlier correction by an automated review' : 'Correction by an automated review'
  return earlier ? 'An earlier manual correction by a person' : 'Manual correction by a person'
}

export function assessmentLabel(one: Voiced, judge?: string | null): string {
  return `${reviewed(one) ? "An automated review's" : "A person's"} assessment of ${judge ?? 'the judge'}`
}
