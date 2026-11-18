import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

/**
 * Model output as safe HTML, for the chat's answer, its gaps and follow-up question, and a calculation's text (ported from
 * the operator's earlier chat, its rules kept and two holes closed). The text comes from a model, which the passages it read can
 * steer, so it passes two layers: markdown-it with `html: false` escapes raw HTML instead of passing it on, and DOMPurify
 * keeps an allow-list of tags and the `href` attribute alone, whose value must begin with http(s):, mailto:, # or one /.
 * No image survives, so nothing in a reply calls a third party when it renders. A quote never comes through here: it is
 * verbatim text, shown by interpolation.
 */
const md = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })

// A formula stays exactly as written. `\(` and `\[` are Markdown escapes, which would eat the backslash, and an underscore
// inside could turn into emphasis: `\( … \)` and `\[ … \]` become code, word for word. Typesetting them comes later.
md.inline.ruler.before('escape', 'formula', (state, silent) => {
  const opener = state.src.slice(state.pos, state.pos + 2)
  const closer = opener === '\\(' ? '\\)' : opener === '\\[' ? '\\]' : null
  if (!closer) return false
  const end = state.src.indexOf(closer, state.pos + 2)
  if (end < 0) return false
  if (!silent) {
    const token = state.push('code_inline', 'code', 0)
    token.markup = opener
    token.content = state.src.slice(state.pos, end + 2)
  }
  state.pos = end + 2
  return true
})

const ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'a', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td']
// http(s), mail, an address in this app or a path on this server; never a protocol-relative //host, a javascript: or a data:
const ALLOWED_URI_REGEXP = /^(?:https?:|mailto:|#|\/(?!\/))/i

// An instance of its own, so its hook touches no other sanitising in the app. A link leads somewhere no one here chose: a
// new tab, out of this page's reach. Set after sanitising: DOMPurify tests every attribute it does not know to be inert
// against the URI rule, so a `target` or `rel` given earlier would not survive it.
const purify = DOMPurify(window)
purify.addHook('afterSanitizeAttributes', node => {
  if (node.tagName === 'A' && node.hasAttribute('href')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(source: string | null | undefined): string {
  return purify.sanitize(md.render(source ?? ''), { ALLOWED_TAGS, ALLOWED_ATTR: ['href'], ALLOWED_URI_REGEXP })
}
