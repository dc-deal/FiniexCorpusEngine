import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** How far a work or the corpus is refined, in the five levels of U1.a, with the details its fold shows. */
export type Ladder = Schemas['Ladder']
/** One level of a ladder: how many of the whole reach it, said in a line, and where its pages are listed. */
export type Rung = Schemas['Rung']
/** A page's or a section's own ladder (V2.a), and the text the librarian serves for it. */
export type PageLadder = Schemas['PageLadder']
export type PageRung = Schemas['PageRung']
