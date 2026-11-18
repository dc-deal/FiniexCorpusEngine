/** One value of a facet with how often it occurs, as the API counted it. */
export interface FacetValue {
  value: string
  count: number
}

/** A facet of a flat list: what the bar shows for one field. */
export interface Facet {
  key: string
  label: string
  values: FacetValue[]
}

/** The chosen values per facet key; no value chosen means no filter on that facet. */
export type FacetSelection = Record<string, string[]>
