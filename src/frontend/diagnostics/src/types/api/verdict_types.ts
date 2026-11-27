import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Whether a person's verdict is taken here, the dialog's lists in the core's words, and each base's export (213.b). */
export type VerdictForm = Schemas['VerdictForm']
/** A verdict on the reading a page shows, as the page view sends it. */
export type VerdictRequest = Schemas['VerdictRequest']
export type VerdictGiven = Schemas['VerdictGiven']
/** A person's promotion of a Lab reading to the page's reading (#18), and what it set going. */
export type PromoteRequest = Schemas['PromoteRequest']
export type PromoteGiven = Schemas['PromoteGiven']
/** A correction's text as the table it would be, read by the core's table parser (204.a); `rows` null where it is none. */
export type TablePreview = Schemas['TablePreview']
/** ✦ propose (W2.a): a model's correction of one block, asked of the core, never recorded by itself. */
export type ProposalRequest = Schemas['ProposalRequest']
export type Proposal = Schemas['Proposal']
