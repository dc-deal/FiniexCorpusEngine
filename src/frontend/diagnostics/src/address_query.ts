import type { LocationQuery } from 'vue-router'

/**
 * The values one key of the address's query holds: none, one (`?state=issue`) or several (`?state=issue&state=blocked`),
 * empty ones dropped. A view whose filter a link may choose reads it with this, so a link and a toggle mean the same.
 */
export function queryValues(query: LocationQuery, key: string): string[] {
  const given = query[key]
  return (Array.isArray(given) ? given : [given]).filter((value): value is string => typeof value === 'string' && value !== '')
}
