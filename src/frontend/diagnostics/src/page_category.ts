/**
 * A page's category as the API counts it (decision 172.a): the core's word, or `not named` where no reading named the
 * page's kind (`readings.NOT_NAMED`), so a facet can choose those pages too.
 */
const NOT_NAMED = 'not named'

export function categoryOf(row: { category?: string | null }): string {
  return row.category ?? NOT_NAMED
}
