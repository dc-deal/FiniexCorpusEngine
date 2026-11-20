import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** How far a work or the corpus is refined, in the five levels of U1.a, with the details its fold shows. */
export type Ladder = Schemas['Ladder']
/** One level of a ladder: how many of the whole reach it, said in a line, and where its pages are listed. */
export type Rung = Schemas['Rung']
