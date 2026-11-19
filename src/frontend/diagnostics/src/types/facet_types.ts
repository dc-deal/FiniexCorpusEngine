/**
 * What a facet IS, for any list that can be narrowed (Y1.a: ported from the FiniexViewer, whose rules the frontend follows,
 * 260.a).
 *
 * The definition is the only place that knows what a row looks like; everything else in the facet machinery works on these
 * functions, which is what lets one bar serve the sources list, the issues and a work's pages without learning any of them.
 */
export interface FacetDefinition<T> {
  id: string
  label: string
  /**
   * The values this row holds for the facet. An empty array means the row STATES NONE, and such a row is matched only while
   * the facet has nothing selected: a row with no value cannot honestly answer a question about that value.
   */
  valuesOf: (row: T) => string[]
}

/** One way to order the list. `compare` is a plain comparator, so a caller can sort by anything. */
export interface SortDefinition<T> {
  id: string
  label: string
  compare: (a: T, b: T) => number
}

/** Which values are picked per facet id. Absent or empty means the facet is not narrowing. */
export type FacetSelection = Record<string, string[]>

/**
 * One choosable value with the number of rows behind it.
 *
 * The count is what would REMAIN if this value were picked, with every OTHER facet's selection still applied, so a count of
 * 0 means picking it leads nowhere, and the reader can see that before clicking rather than after.
 */
export interface FacetOption {
  value: string
  count: number
  active: boolean
}

/** One value of a facet with how often it occurs, as the API counted it: the chip bar's, until its views move (Y1.a, C). */
export interface FacetValue {
  value: string
  count: number
}

/** A facet of a flat list as the chip bar draws it: what it shows for one field, with the API's counts. */
export interface Facet {
  key: string
  label: string
  values: FacetValue[]
}
