/**
 * Whether a page list's Why column shows the page's route (the operator's 25.a). Where the text comes from a fallback, the
 * text layer or a licensed work's legacy Markdown (H2.a), the route says why. Where the judge found the reading bad and the search serves that reading all the same, the route says
 * why too ("the judge's findings lie on blocks never quoted"). A page read and served as it should be says nothing.
 */
export function routeSaysWhy(row: { from_fallback: boolean, check: { state: string } }): boolean {
  return row.from_fallback || row.check.state === 'issue'
}
