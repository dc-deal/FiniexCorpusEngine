import type { components } from '@/types/api/diagnostics_api'

type Schemas = components['schemas']

/** Whether a person's verdict is taken here, the dialog's lists in the core's words, and each base's export (213.b). */
export type VerdictForm = Schemas['VerdictForm']
/** A verdict on the reading a page shows, as the page view sends it. */
export type VerdictRequest = Schemas['VerdictRequest']
export type VerdictGiven = Schemas['VerdictGiven']
/** A correction's text as the table it would be, read by the core's table parser (204.a); `rows` null where it is none. */
export type TablePreview = Schemas['TablePreview']
