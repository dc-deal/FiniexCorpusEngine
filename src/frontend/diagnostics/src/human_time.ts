/**
 * Every time a person reads, written as a person says it (the operator, 10 Nov: "every time stated in the project must get a human date format"): relative where it is recent, "just now", "12 min ago", "2 h ago" the same day, "yesterday,
 * 09:21", "3 days ago" within the week; else a date in words, "9 Nov, 09:21", with the year where it is not this one. The
 * full timestamp in the reader's own zone goes in the hover. The API and every file keep ISO 8601; only the view formats.
 * A text that is no time is shown as it came. Built on the browser's own `Intl`, which knows the zone and the month names;
 * no library is needed for this.
 */
export interface SaidTime {
  text: string
  title: string
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

// the calendar day of an instant in a zone, as YYYY-MM-DD, to tell today and yesterday apart
function dayOf(instant: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(instant)
}

function daysBetween(earlier: string, later: string): number {
  return Math.round((Date.parse(`${later}T00:00:00Z`) - Date.parse(`${earlier}T00:00:00Z`)) / (24 * HOUR))
}

function clock(instant: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hour12: false }).format(instant)
}

function dayInWords(instant: Date, withYear: boolean, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone, day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}) })
    .format(instant)
}

function full(instant: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short',
  }).format(instant)
}

/** A moment as a person says it, and in full for the hover. `now` and `timeZone` are for tests; the view takes its own. */
export function sayTime(iso: string | null | undefined, now: Date = new Date(), timeZone?: string): SaidTime {
  if (!iso) return { text: '', title: '' }
  if (DATE_ONLY.test(iso)) return sayDate(iso, now, timeZone)
  const instant = new Date(iso)
  if (Number.isNaN(instant.getTime())) return { text: iso, title: iso }
  const title = full(instant, timeZone)
  const ago = now.getTime() - instant.getTime()
  const days = daysBetween(dayOf(instant, timeZone), dayOf(now, timeZone))
  if (ago >= 0 && ago < MINUTE) return { text: 'just now', title }
  if (ago >= 0 && ago < HOUR) return { text: `${Math.floor(ago / MINUTE)} min ago`, title }
  if (ago >= 0 && days === 0) return { text: `${Math.floor(ago / HOUR)} h ago`, title }
  if (ago >= 0 && days === 1) return { text: `yesterday, ${clock(instant, timeZone)}`, title }
  if (ago >= 0 && days < 7) return { text: `${days} days ago`, title }
  const sameYear = dayOf(instant, timeZone).slice(0, 4) === dayOf(now, timeZone).slice(0, 4)
  return { text: `${dayInWords(instant, !sameYear, timeZone)}, ${clock(instant, timeZone)}`, title }
}

/**
 * A moment under a heading that already names its day, as a day's calls are: relative while it is today ("2 h ago"),
 * else only its clock ("09:21"), since the heading says the rest. The hover keeps the full timestamp.
 */
export function sayClock(iso: string | null | undefined, now: Date = new Date(), timeZone?: string): SaidTime {
  const said = sayTime(iso, now, timeZone)
  if (!iso || DATE_ONLY.test(iso) || said.text === iso) return said
  const instant = new Date(iso)
  if (dayOf(instant, timeZone) === dayOf(now, timeZone) && instant.getTime() <= now.getTime()) return said
  return { text: clock(instant, timeZone), title: said.title }
}

/** A calendar day, such as the day a prompt was frozen: "today", "yesterday", else "30 Oct", the year where not this one. */
export function sayDate(iso: string, now: Date = new Date(), timeZone?: string): SaidTime {
  if (!DATE_ONLY.test(iso)) return { text: iso, title: iso }
  const noon = new Date(`${iso}T12:00:00Z`)
  const days = daysBetween(iso, dayOf(now, timeZone))
  const title = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(noon)
  if (days === 0) return { text: 'today', title }
  if (days === 1) return { text: 'yesterday', title }
  return { text: dayInWords(noon, iso.slice(0, 4) !== dayOf(now, timeZone).slice(0, 4), 'UTC'), title }
}

/** The local calendar day of a moment, YYYY-MM-DD: what a list of the day's events groups by. */
export function localDay(iso: string, timeZone?: string): string {
  return dayOf(new Date(iso), timeZone)
}
