/**
 * A cost in USD as a person reads it (the operator, 18 Nov: many zeros are no help). Nothing paid says 0, never 0.0000;
 * an amount of a dollar or more keeps its cents (37.77); a smaller one its first two significant digits (0.014 for
 * 0.0136, 0.0083), so a page's reading and a run's sum read alike without a column of zeros. Every view that shows a
 * cost asks here, so no two of them write one differently.
 *
 * A reading read in a Claude Code session (280.a) has no cost an API ledger holds: the API serves None for it, and the
 * view says so in the operator's words rather than 0.
 */
export const NOT_MEASURABLE = 'external cost, not measurable'

export function usd(amount: number): string {
  if (amount === 0) return '0'
  if (Math.abs(amount) >= 1) return amount.toFixed(2)
  if (Math.abs(amount) < 0.0001) return '< 0.0001'
  return String(Number(amount.toPrecision(2)))
}

/** A reading's cost with its unit, or why it has none. */
export function readingCost(amount: number | null): string {
  return amount === null ? NOT_MEASURABLE : `${usd(amount)} USD`
}
