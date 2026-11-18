/**
 * A request to the diagnostics API that did not succeed. `status` is the HTTP status of the refusal, or
 * null when no answer came at all; `detail` is the API's own words where it gave some. The sentence a
 * reader sees is the view's to write.
 */
export class ApiError extends Error {
  readonly status: number | null
  readonly detail: string

  constructor(status: number | null, detail: string) {
    super(status === null ? `no answer: ${detail}` : `${status}: ${detail}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}
