import { describe, it, expect } from 'vitest'
import { localDay, sayClock, sayDate, sayTime } from '@/human_time'

// a fixed clock, and a fixed zone so the test reads the same on every machine: Tuesday 10 Nov 2026, 14:30 in Berlin
const NOW = new Date('2026-11-10T13:30:00Z')
const BERLIN = 'Europe/Berlin'
const say = (iso: string) => sayTime(iso, NOW, BERLIN)

describe('sayTime', () => {
  it('says a recent moment relative to now', () => {
    expect(say('2026-11-10T13:29:40Z').text).toBe('just now')
    expect(say('2026-11-10T13:18:00Z').text).toBe('12 min ago')
    expect(say('2026-11-10T11:25:00+00:00').text).toBe('2 h ago')
  })

  it('says yesterday with its time, and the days of this week by their count', () => {
    expect(say('2026-11-09T08:21:52+00:00').text).toBe('yesterday, 09:21')
    expect(say('2026-11-07T10:00:00Z').text).toBe('3 days ago')
  })

  it('says an older moment as a date in words, the year only where it is not this one', () => {
    expect(say('2026-10-30T09:00:00Z').text).toBe('30 Oct, 10:00')
    expect(say('2025-12-31T22:30:00Z').text).toBe('31 Dec 2025, 23:30')
  })

  it('counts days by the reader\'s own calendar, not by UTC', () => {
    // 23:30 UTC on 9 Nov is 00:30 on 10 Nov in Berlin: today, 14 hours before 14:30, not yesterday
    expect(say('2026-11-09T23:30:00Z').text).toBe('14 h ago')
    expect(localDay('2026-11-09T23:30:00Z', BERLIN)).toBe('2026-11-10')
  })

  it('keeps the full timestamp in the reader\'s zone for the hover', () => {
    const title = say('2026-11-09T08:21:52+00:00').title
    expect(title).toContain('9 Nov 2026')
    expect(title).toContain('09:21:52')
    expect(title).toMatch(/CET|GMT\+1/)
  })

  it('shows what is no time as it came, and nothing for nothing', () => {
    expect(say('not recorded')).toEqual({ text: 'not recorded', title: 'not recorded' })
    expect(sayTime(null, NOW, BERLIN)).toEqual({ text: '', title: '' })
  })
})

describe('sayClock', () => {
  it('under a heading that names the day, says today relative and any other day by its clock alone', () => {
    expect(sayClock('2026-11-10T11:25:00Z', NOW, BERLIN).text).toBe('2 h ago')
    expect(sayClock('2026-11-09T08:21:52+00:00', NOW, BERLIN).text).toBe('09:21')
    expect(sayClock('2026-10-30T09:00:00Z', NOW, BERLIN).text).toBe('10:00')
    expect(sayClock('2026-10-30T09:00:00Z', NOW, BERLIN).title).toContain('30 Oct 2026')
  })
})

describe('sayDate', () => {
  it('says a calendar day as today, yesterday, or in words', () => {
    expect(sayDate('2026-11-10', NOW, BERLIN).text).toBe('today')
    expect(sayDate('2026-11-09', NOW, BERLIN).text).toBe('yesterday')
    expect(sayDate('2026-10-30', NOW, BERLIN).text).toBe('30 Oct')
    expect(sayDate('2025-10-30', NOW, BERLIN).text).toBe('30 Oct 2025')
    expect(sayTime('2026-10-30', NOW, BERLIN).title).toBe('Fri, 30 Oct 2026')
  })
})
