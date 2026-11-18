import { describe, expect, it } from 'vitest'

import { NOT_MEASURABLE, readingCost, usd } from '@/cost_format'

describe('a cost as a person reads it', () => {
  it('says nothing paid as 0, never with a row of zeros', () => {
    expect(usd(0)).toBe('0')
  })

  it('keeps the cents of a dollar or more', () => {
    expect(usd(37.767)).toBe('37.77')
    expect(usd(1)).toBe('1.00')
  })

  it('keeps two significant digits below a dollar, without trailing zeros', () => {
    expect(usd(0.0136)).toBe('0.014')
    expect(usd(0.0157879)).toBe('0.016')
    expect(usd(0.0083)).toBe('0.0083')
    expect(usd(0.5)).toBe('0.5')
    expect(usd(0.0588)).toBe('0.059')
  })

  it('never writes an exponent for a tiny amount', () => {
    expect(usd(0.00000123)).toBe('< 0.0001')
  })

  it("says a session reading's cost is not measurable, in the operator's words, never 0", () => {
    expect(readingCost(null)).toBe(NOT_MEASURABLE)
    expect(NOT_MEASURABLE).toBe('external cost, not measurable')
    expect(readingCost(0.0136)).toBe('0.014 USD')
    expect(readingCost(0)).toBe('0 USD')
  })
})
