/**
 * A count the API served, said as words with the noun that agrees with it: "1 page", "1,234 pages", "1 batch",
 * "2 batches". It counts nothing itself. One helper for every view (the viewer's tip 9, stage D: "1 sections by heading",
 * "toc 1 calls"), so no two views say a count differently; English only, as every label here is.
 */
export function counted(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString('en')} ${noun(count, one, many)}`
}

/** The noun alone that agrees with a count standing apart, a figure in a span of its own: "1,156 calls", "1 call". */
export function noun(count: number, one: string, many = `${one}s`): string {
  return count === 1 ? one : many
}

/** A count of pages, the count said most often. */
export function pageCount(count: number): string {
  return counted(count, 'page')
}
