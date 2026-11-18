/**
 * A person's verdict as a person says it, one wording wherever a verdict stands (the operator, 11 Nov: one representation for one
 * kind of thing): the core's word is the verb, said as what the person did.
 */
export const STANDING: Record<string, string> = { accept: 'accepted', reject: 'rejected', note: 'noted' }

/**
 * Who has looked at a validator's error (228.a): "a person noted and corrected b04", "a person accepted the page". The API
 * says which verdict, whether it names the block or the page, and whether a correction stands; this says it in words.
 */
export function lookedSaid(error: { looked?: string | null, looked_at?: string | null, corrected?: boolean, block?: string | null }): string {
  if (!error.looked) return ''
  const did = STANDING[error.looked] ?? error.looked
  return `a person ${did}${error.corrected ? ' and corrected' : ''} ${error.looked_at === 'block' && error.block ? error.block : 'the page'}`
}
