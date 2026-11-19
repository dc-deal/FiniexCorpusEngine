import { describe, it, expect } from 'vitest'
import { counted, noun, pageCount } from '@/counted'

// stage D1 (the viewer's tip 9: "1 sections by heading", "toc 1 calls"): one helper says every count with its noun
describe('counted', () => {
  it('says a count with the noun that agrees with it, the count in English figures', () => {
    expect(counted(1, 'section')).toBe('1 section')
    expect(counted(0, 'section')).toBe('0 sections')
    expect(counted(1234, 'page')).toBe('1,234 pages')
    expect(counted(2, 'batch', 'batches')).toBe('2 batches')
    expect(pageCount(1)).toBe('1 page')
  })

  it('gives the noun alone for a figure that stands in a span of its own, and a verb that agrees', () => {
    expect(noun(1, 'call')).toBe('call')
    expect(noun(1156, 'call')).toBe('calls')
    expect(noun(1, 'counts', 'count')).toBe('counts')
    expect(noun(3, 'counts', 'count')).toBe('count')
  })
})
