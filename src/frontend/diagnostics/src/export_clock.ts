/**
 * How long an export runs and may take, in words a person reads (the operator's E1.a, 21 Nov: a verdict recorded was taken for
 * "nothing saved" while its export ran unseen for minutes). The figures are the API's: since when it runs and the median of
 * the last finished exports; only the words are the view's.
 */

/** The header's clock of a running export: "3 of about 5 min", "12 of about 45 s", or "running 3 min" without an estimate. */
export function exportClock(elapsed: number, expected: number | null | undefined): string {
  if (expected === null || expected === undefined) return `running ${elapsed < 60 ? `${elapsed} s` : `${Math.floor(elapsed / 60)} min`}`
  if (expected < 90) return `${elapsed} of about ${Math.round(expected)} s`
  // the minute it is in, from the first: a start a moment ago reads 1, not 0
  return `${Math.max(1, Math.ceil(elapsed / 60))} of about ${Math.round(expected / 60)} min`
}

/** How long an export may take, for the toast after a record: "a few seconds" under 20 s, "about 45 seconds" under 90 s, else
 * "about 5 minutes"; "a few minutes" where no export of the base has finished yet to tell. */
export function durationWords(expected: number | null | undefined): string {
  if (expected === null || expected === undefined) return 'a few minutes'
  if (expected < 20) return 'a few seconds'
  if (expected < 90) return `about ${Math.round(expected)} seconds`
  return `about ${Math.round(expected / 60)} minutes`
}
