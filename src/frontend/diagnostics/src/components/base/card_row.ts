/** One row of a hover card: a label and its value; a row without a value is left out. Rows of one `group` stand together,
 * and where the group changes the card draws a thin rule and the new group's `caption`, where it has one; an `indent`ed row
 * is a part of what stands above it (the operator's L1.a, 20 Nov: a read page's states beneath the five levels, set apart). A
 * view may give a row more, which its own `label` and `value` slots draw (a level's number, its meter and its share). */
export interface CardRow {
  label: string
  value: string | null | undefined
  group?: string
  caption?: string
  indent?: boolean
}
