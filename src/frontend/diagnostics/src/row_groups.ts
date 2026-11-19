/**
 * A list's rows partitioned into groups, as the FiniexViewer's list does it (Y1.a): groups appear in the order their first
 * row does, so the reader's sort decides their order too, and a group's rows stand together in the order `within` gives
 * them (a series by its parts). It only arranges the rows the view already holds: it adds none, drops none and counts
 * nothing a heading would show beyond how many rows it holds.
 */
export interface RowGroup<T> {
  /** What the rows have in common: a series' id, or a row's own key where it belongs to none. */
  key: string
  rows: T[]
}

/** First-appearance buckets, each ordered by `within` where given; the sort of everything else is the caller's. */
export function groupRows<T>(rows: T[], keyOf: (row: T) => string, within?: (a: T, b: T) => number): RowGroup<T>[] {
  const buckets = new Map<string, T[]>()
  for (const row of rows) {
    const key = keyOf(row)
    const held = buckets.get(key)
    if (held) held.push(row)
    else buckets.set(key, [row])
  }
  return [...buckets].map(([key, held]) => ({ key, rows: within ? [...held].sort(within) : held }))
}

/** Which groups a list holds open, kept for the tab's session (Y1.a): every group starts closed, as the viewer's do. */
const OPEN_KEY = 'open_groups.v1'

function readOpen(): Record<string, unknown> {
  try {
    const raw = sessionStorage.getItem(OPEN_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    // an unreadable entry is the same as none: every group closed
    return {}
  }
}

/** The groups a list held open in this tab, the keys alone. */
export function openGroups(list: string): string[] {
  const keys = readOpen()[list]
  return Array.isArray(keys) ? keys.filter((key): key is string => typeof key === 'string') : []
}

/** Writes a list's open groups for the tab's session; a full or blocked storage keeps them for this page only. */
export function keepOpenGroups(list: string, keys: string[]): void {
  try {
    sessionStorage.setItem(OPEN_KEY, JSON.stringify({ ...readOpen(), [list]: keys }))
  } catch {
    // the groups simply open closed again after a reload
  }
}
