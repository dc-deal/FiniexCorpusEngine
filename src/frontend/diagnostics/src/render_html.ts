import DOMPurify from 'dompurify'
import katex from 'katex'

/**
 * An HTML work's section as line 1's `html_stripped` gives it (the operator's 1.a): already allow-listed in the core, and
 * sanitised here again before it is shown, with DOMPurify, the library the chat's answers pass through. Its own list, the
 * core's kept elements and no more: headings with their id, prose and lists, tables with their spans, code, quotes and
 * emphasis, links over http(s) or to an anchor; every other element the core turns into a plain `<span>`, an image into an
 * empty `<span data-image="alt text">`, which the view shows as a placeholder, and a formula into
 * `<span data-tex="LaTeX" data-display="inline|block">LaTeX</span>` (line 1, 10 Nov). No style, class or handler, and
 * nothing that loads: the Markdown list of the chat would drop the spans, the ids and the table spans this needs.
 *
 * After the sanitiser, each formula is typeset by KaTeX from its `data-tex`, as `MathTex` does it (trust off, so the LaTeX
 * can ask for no link, class or style); one KaTeX refuses keeps its LaTeX as text, as the index holds it.
 */
// a plain `div` stands where the core keeps a line break a browser makes at an element it does not keep (loader 4, line 1)
const ALLOWED_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody',
  'tr', 'th', 'td', 'pre', 'code', 'blockquote', 'em', 'strong', 'i', 'b', 'sub', 'sup', 'br', 'a', 'span', 'div']
const ALLOWED_ATTR = ['href', 'id', 'colspan', 'rowspan', 'data-image', 'data-tex', 'data-display']
const ALLOWED_URI_REGEXP = /^(?:https?:|#)/i

// an instance of its own, so its hook touches no other sanitising in the app; an outward link opens a new tab, out of reach
const purify = DOMPurify(window)
purify.addHook('afterSanitizeAttributes', node => {
  if (node.tagName === 'A' && /^https?:/i.test(node.getAttribute('href') ?? '')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

// DOMPurify tests the value of every attribute it does not know to be inert against the URI rule: a table's spans, an
// image's alt text and a formula's LaTeX are inert, so they are named as such, or "2", "A chart" and "S_{a}" would fail
// `https?:|#` and be dropped
const ADD_URI_SAFE_ATTR = ['colspan', 'rowspan', 'data-image', 'data-tex', 'data-display']

function typeset(fragment: DocumentFragment): void {
  for (const formula of fragment.querySelectorAll<HTMLElement>('span[data-tex]')) {
    try {
      formula.innerHTML = katex.renderToString(formula.getAttribute('data-tex') ?? '', {
        displayMode: formula.getAttribute('data-display') === 'block',
        throwOnError: true,
        trust: false,
        strict: 'ignore',
        output: 'htmlAndMathml',
      })
    } catch {
      // KaTeX refused the LaTeX: the span keeps it as text, the way the index holds it
    }
  }
}

export function renderStripped(source: string | null | undefined): string {
  const fragment = purify.sanitize(source ?? '', {
    ALLOWED_TAGS, ALLOWED_ATTR, ALLOWED_URI_REGEXP, ADD_URI_SAFE_ATTR, ALLOW_DATA_ATTR: false, RETURN_DOM_FRAGMENT: true,
  })
  typeset(fragment)
  const holder = document.createElement('div')
  holder.append(fragment)
  return holder.innerHTML
}
