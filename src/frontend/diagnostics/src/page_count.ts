/** A count of pages the API served, said as words: "1 page", "1,234 pages". It counts nothing itself. */
export function pageCount(count: number): string {
  return `${count.toLocaleString('en')} ${count === 1 ? 'page' : 'pages'}`
}
