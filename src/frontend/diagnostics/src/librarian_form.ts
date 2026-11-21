import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { LibrarianField } from '@/types/api/librarian_types'

/**
 * A tool's form and its address (the operator's L1.a, 21 Nov): the values a form's controls hold, the arguments a call sends
 * in each field's schema type, and the same arguments in the address, so F5 and a pasted link make the same call again.
 * The fields are the API's, from the tool's input schema; nothing here knows a tool by name.
 */

/** A form's values as its controls hold them: a checkbox's boolean, every other control's text. */
export type FormValues = Record<string, string | boolean>

function asControl(field: LibrarianField, value: unknown): string | boolean {
  if (field.kind === 'boolean') return value === true
  if (value === null || value === undefined) return ''
  return Array.isArray(value) ? value.join(', ') : String(value)
}

/** The form a tool opens with, its fields' defaults (the view's own where it has one, as the router's off), or a call's
 * arguments over them. */
export function valuesOf(fields: LibrarianField[], args: Record<string, unknown> = {}): FormValues {
  return Object.fromEntries(fields.map(field => [field.name, asControl(field, field.name in args ? args[field.name] : field.default)]))
}

function typed(field: LibrarianField, text: string): unknown {
  if (field.kind === 'integer' || field.kind === 'number') {
    const number = field.kind === 'integer' ? Number.parseInt(text, 10) : Number.parseFloat(text)
    return Number.isNaN(number) ? text : number  // the server says what is wrong with it, as it would tell a client
  }
  return text
}

/**
 * The arguments a call sends: what the form holds, each in its schema's type, a list from its comma-separated words; an
 * empty field left out, and a value the server would take by default too, so a call reads as a client makes it. A field
 * whose form starts other than the server would is always sent, either way: the router's off reaches the librarian as
 * `router: false`, and a router ticked as `router: true`, so the address that names the call opens its form as it was.
 */
export function argumentsOf(fields: LibrarianField[], values: FormValues): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  for (const field of fields) {
    const value = values[field.name]
    let sent: unknown
    if (field.kind === 'boolean') {
      sent = value === true
    } else {
      const text = String(value ?? '').trim()
      if (!text) continue
      sent = field.kind === 'list' ? text.split(',').map(word => word.trim()).filter(Boolean) : typed(field, text)
      if (Array.isArray(sent) && sent.length === 0) continue
    }
    const serverDefault = JSON.stringify(field.server_default ?? null)
    if (JSON.stringify(sent) === serverDefault && JSON.stringify(field.default ?? null) === serverDefault) continue
    args[field.name] = sent
  }
  return args
}

/** A call in the address: its tool, and each argument by its own name, a list as the name repeated. */
export function queryOf(tool: string, args: Record<string, unknown>): LocationQueryRaw {
  const query: LocationQueryRaw = { tool }
  for (const [name, value] of Object.entries(args)) query[name] = Array.isArray(value) ? value.map(String) : String(value)
  return query
}

/**
 * The arguments an address names for a tool, each in its field's type; null where a required one is missing, so a link to
 * a tab alone calls nothing. A tool that requires nothing is called on its tab alone, as `works` is: free and local.
 */
export function argumentsFromQuery(fields: LibrarianField[], query: LocationQuery): Record<string, unknown> | null {
  const args: Record<string, unknown> = {}
  for (const field of fields) {
    const raw = query[field.name]
    const texts = (Array.isArray(raw) ? raw : [raw]).filter((text): text is string => typeof text === 'string')
    if (!texts.length) {
      if (field.required) return null
      continue
    }
    if (field.kind === 'list') args[field.name] = texts
    else if (field.kind === 'boolean') args[field.name] = texts[0] === 'true'
    else args[field.name] = typed(field, texts[0])
  }
  return args
}
