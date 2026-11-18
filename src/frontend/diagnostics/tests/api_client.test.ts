import { describe, it, expect } from 'vitest'
import { AxiosError, type AxiosResponse } from 'axios'
import { ApiError } from '@/api/api_error'
import { pageImageUrl, typedError } from '@/api/api_client'

function refusal(status: number, data: unknown): AxiosError {
  const response = { status, data, statusText: '', headers: {}, config: {} } as AxiosResponse
  return new AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_RESPONSE', undefined, undefined, response)
}

describe('typedError', () => {
  it('names no status when no answer came at all', () => {
    const error = typedError(new AxiosError('Network Error', 'ERR_NETWORK'))
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBeNull()
  })

  it("keeps the API's own words for a refusal", () => {
    const error = typedError(refusal(404, { detail: 'Not Found' })) as ApiError
    expect(error.status).toBe(404)
    expect(error.detail).toBe('Not Found')
  })

  it('falls back to the transport message where the detail is not a sentence', () => {
    const error = typedError(refusal(422, { detail: [{ loc: ['query', 'page'], msg: 'not an integer' }] })) as ApiError
    expect(error.status).toBe(422)
    expect(error.detail).toBe('Request failed with status code 422')
  })

  it('passes anything that is not a failed request unchanged', () => {
    const programming = new TypeError('undefined is not a function')
    expect(typedError(programming)).toBe(programming)
  })
})

describe('pageImageUrl', () => {
  it('names the page of a work within its knowledge base, the id made safe for a path', () => {
    expect(pageImageUrl('free', 'a b/c', 12)).toBe('/api/free/works/a%20b%2Fc/pages/12/image.png')
    expect(pageImageUrl('licensed', 'x', 3)).toBe('/api/licensed/works/x/pages/3/image.png')
  })
})
