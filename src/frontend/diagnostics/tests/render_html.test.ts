import { describe, it, expect } from 'vitest'
import { renderStripped } from '@/render_html'

describe('renderStripped', () => {
  it('keeps what the core keeps: headings with their id, table spans, spans and an image\'s alt text', () => {
    const html = renderStripped('<h2 id="History">History</h2><table><tbody><tr><td colspan="2" rowspan="3">x</td></tr></tbody></table>'
      + '<p>a <span>b</span> <span data-image="A chart"></span></p>')
    expect(html).toContain('<h2 id="History">History</h2>')
    expect(html).toContain('colspan="2"')
    expect(html).toContain('rowspan="3"')
    expect(html).toContain('<span>b</span>')
    expect(html).toContain('data-image="A chart"')
    // a plain div, where the core keeps a browser's line break at an element it does not keep (loader 4)
    expect(renderStripped('<div>a figure\'s words</div><div class="x" style="color:red">b</div>'))
      .toBe('<div>a figure\'s words</div><div>b</div>')
  })

  it('typesets a formula from its LaTeX, as a block where the core says so, and keeps a refused one as text', () => {
    const html = renderStripped('<p>a <span data-tex="S_{a}" data-display="inline">S_{a}</span></p>'
      + '<span data-tex="\\frac{1}{2}" data-display="block">\\frac{1}{2}</span>'
      + '<span data-tex="\\notacommand{" data-display="inline">\\notacommand{</span>')
    const holder = document.createElement('div')
    holder.innerHTML = html
    const [inline, block, refused] = holder.querySelectorAll('span[data-tex]')
    expect(inline.getAttribute('data-display')).toBe('inline')
    expect(inline.querySelector('.katex')).not.toBeNull()
    expect(inline.querySelector('.katex-display')).toBeNull()
    expect(block.querySelector('.katex-display')).not.toBeNull()
    // the LaTeX itself stays in the annotation KaTeX writes beside the drawing
    expect(block.querySelector('annotation')?.textContent).toBe('\\frac{1}{2}')
    expect(refused.querySelector('.katex')).toBeNull()
    expect(refused.textContent).toBe('\\notacommand{')
  })

  it('lets a formula\'s LaTeX ask for no link, class or style', () => {
    const html = renderStripped('<span data-tex="\\href{javascript:alert(1)}{x}\\htmlClass{evil}{y}" data-display="inline">x</span>')
    const holder = document.createElement('div')
    holder.innerHTML = html
    // the LaTeX stays as text in its attribute and annotation, where it does nothing; nothing became a link or a class
    expect(holder.querySelector('a, [href]')).toBeNull()
    expect(holder.querySelector('.evil')).toBeNull()
  })

  it('drops what could load, run or restyle, and opens an outward link in a new tab', () => {
    const html = renderStripped('<p style="color:red" class="x" onclick="alert(1)">t</p><script>alert(1)</script><img src="http://x/i.png">'
      + '<iframe src="http://x"></iframe><a href="javascript:alert(1)">j</a><a href="https://en.wikipedia.org/wiki/X">w</a>'
      + '<a href="#Notes">n</a><span data-other="1">o</span>')
    expect(html).not.toMatch(/style=|class=|onclick|<script|<img|<iframe|javascript:|data-other/)
    expect(html).toContain('<a href="https://en.wikipedia.org/wiki/X" target="_blank" rel="noopener noreferrer">w</a>')
    expect(html).toContain('<a href="#Notes">n</a>')
  })
})
