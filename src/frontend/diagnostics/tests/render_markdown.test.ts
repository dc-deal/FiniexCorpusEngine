import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/render_markdown'

// The source of this Markdown is a model, and a model can be steered by the passages it reads. Half these tests are about
// formatting; the other half are the reason the output is sanitised at all (ported from the operator's earlier chat).

describe('renderMarkdown, formatting', () => {
  it('renders bold text', () => {
    expect(renderMarkdown('**Sharpe ratio**')).toContain('<strong>')
  })

  it('renders bullet lists as lists', () => {
    const html = renderMarkdown('- first\n- second')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>')
  })

  it('renders numbered lists', () => {
    expect(renderMarkdown('1. first\n2. second')).toContain('<ol>')
  })

  it('renders headings', () => {
    expect(renderMarkdown('## Position size')).toContain('<h2>')
  })

  it('renders code blocks', () => {
    const html = renderMarkdown('```\nSELECT 1\n```')
    expect(html).toContain('<pre>')
    expect(html).toContain('<code>')
  })

  it('renders tables, without their column alignment, since a style attribute is never let through', () => {
    const html = renderMarkdown('| a | b |\n|--:|---|\n| 1 | 2 |')
    expect(html).toContain('<table>')
    expect(html).not.toContain('style=')
  })

  it('keeps single newlines as line breaks', () => {
    expect(renderMarkdown('one\ntwo')).toContain('<br>')
  })

  it('handles empty input without throwing', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
  })

  it('keeps a formula word for word, its backslashes and underscores untouched', () => {
    const html = renderMarkdown('The excess return \\(R_p - R_f\\) over its spread [1]: \\[S = \\frac{R_p - R_f}{\\sigma_p}\\]')
    expect(html).toContain('<code>\\(R_p - R_f\\)</code>')
    expect(html).toContain('<code>\\[S = \\frac{R_p - R_f}{\\sigma_p}\\]</code>')
    expect(html).not.toContain('<em>')
  })
})

describe('renderMarkdown, sanitising', () => {
  it('never emits a script element', () => {
    // markdown-it escapes raw HTML rather than deleting it, so the characters survive as visible text. That is a valid
    // defence: what must never appear is an executable element.
    const html = renderMarkdown('Hello <script>alert(1)</script>')
    expect(html).not.toContain('<script')
    expect(html).toContain('&lt;script&gt;')
  })

  it('never emits an inline event handler attribute', () => {
    const html = renderMarkdown('<div onclick="alert(1)">click</div>')
    expect(html).not.toMatch(/<[a-z]+[^>]*\sonclick=/i)
  })

  it('never emits a javascript: href', () => {
    expect(renderMarkdown('[click me](javascript:alert(1))')).not.toMatch(/href="javascript:/i)
  })

  it('never emits a data: href', () => {
    expect(renderMarkdown('[x](data:text/html;base64,PHNjcmlwdD4=)')).not.toMatch(/href="data:/i)
  })

  it('never emits a protocol-relative href, which would leave this server unnamed', () => {
    expect(renderMarkdown('[x](//elsewhere.example/page)')).not.toMatch(/href="\/\//i)
  })

  it('strips iframes and objects', () => {
    const html = renderMarkdown('<iframe src="https://example.com"></iframe><object></object>')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('<object')
  })

  it('strips img tags, which could beacon out', () => {
    expect(renderMarkdown('![x](https://example.com/pixel.png)')).not.toContain('<img')
  })

  it('keeps ordinary https links and an address in this app, and opens them out of this page\'s reach', () => {
    const html = renderMarkdown('[docs](https://example.com) and [a page](#/free/sources/kelly/page/3)')
    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('href="#/free/sources/kelly/page/3"')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).toContain('target="_blank"')
  })
})
