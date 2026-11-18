import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ReadingBlocks from '@/components/reading/ReadingBlocks.vue'
import { aBlock } from './page_fixture'

function mountBlocks(blocks: ReturnType<typeof aBlock>[], highlight: string | null = null) {
  return mount(ReadingBlocks, { props: { blocks, highlight } })
}

describe('ReadingBlocks', () => {
  it('names every block by its id and class, as the raw text and the judge do', () => {
    const view = mountBlocks([aBlock({ id: 'b07', block_class: 'heading' })])
    expect(view.find('[data-block="b07"] .block-head').text()).toContain('b07')
    expect(view.find('[data-block="b07"] .block-head').text()).toContain('heading')
  })

  it('never turns the model\'s text into markup', () => {
    const view = mountBlocks([aBlock({ segments: [{ kind: 'text', content: '<script>alert(1)</script><b>bold</b>' }] })])
    expect(view.find('script').exists()).toBe(false)
    expect(view.find('b').exists()).toBe(false)
    expect(view.text()).toContain('<script>alert(1)</script><b>bold</b>')
  })

  it('typesets inline and display math with KaTeX', () => {
    const view = mountBlocks([
      aBlock({ id: 'b01', segments: [{ kind: 'text', content: 'with ' }, { kind: 'math', content: 'x^2' }] }),
      aBlock({ id: 'b02', block_class: 'formula', segments: null, latex: '\\frac{a}{b}', attrs: { label: '6.3' } }),
    ])
    expect(view.find('[data-block="b01"] .katex').exists()).toBe(true)
    expect(view.find('[data-block="b02"] .katex-display').exists()).toBe(true)
    expect(view.find('[data-block="b02"] .formula-label').text()).toBe('(6.3)')
  })

  it('shows a formula KaTeX refuses with its error, in place', () => {
    const view = mountBlocks([aBlock({ block_class: 'formula', segments: null, latex: '\\frac{a' })])
    expect(view.find('.katex-error').exists()).toBe(true)
  })

  it('builds a table from its parsed cells, header cells and spans included', () => {
    const view = mountBlocks([aBlock({
      block_class: 'table',
      segments: null,
      rows: [
        [{ segments: [{ kind: 'text', content: 'WT statistics' }], header: true, rowspan: 1, colspan: 2 }],
        [{ segments: [{ kind: 'text', content: 'Mean' }], header: false, rowspan: 1, colspan: 1 },
          { segments: [{ kind: 'math', content: '1.019' }], header: false, rowspan: 1, colspan: 1 }],
      ],
    })])
    expect(view.find('th').attributes('colspan')).toBe('2')
    expect(view.findAll('td')).toHaveLength(2)
    expect(view.find('td').attributes('colspan')).toBeUndefined()
  })

  it('draws a line break in a cell as a break, the amount a line below its account, as printed (accounting p. 398)', () => {
    const text = (content: string) => ({ kind: 'text' as const, content })
    const br = { kind: 'br' as const, content: '\n' }
    const view = mountBlocks([aBlock({
      block_class: 'table',
      segments: null,
      rows: [[
        { segments: [text('Accounts Payable'), br, text('Merchandise Inventory')], header: false, rowspan: 1, colspan: 1 },
        { segments: [text('600')], header: false, rowspan: 1, colspan: 1 },
        { segments: [br, text('600')], header: false, rowspan: 1, colspan: 1 },
      ]],
    })])
    const cells = view.findAll('td')
    expect(cells.map(cell => cell.findAll('br[data-segment="br"]').length)).toEqual([1, 0, 1])
    expect(cells[0].element.innerHTML).toMatch(/Accounts Payable<br[^>]*>Merchandise Inventory/)
    expect(cells[2].element.innerHTML).toMatch(/<br[^>]*>600/)
  })

  it('marks a derived block, which is never quoted', () => {
    const view = mountBlocks([aBlock({ block_class: 'description', content: 'D', segments: null, text: 'A bar chart.' })])
    expect(view.find('.derived').exists()).toBe(true)
    expect(view.text()).toContain('A bar chart.')
  })

  it('shows a grouped figure as one small box per drawn container, its title first, and says grouped=1', () => {
    // invented T-accounts in the reading's form: one label a line, a blank line between containers
    const text = 'Cash\nAug. 1 700\nBal. 700\n\nSupplies\nAug. 6 30\nBal. 30\n'
    const view = mountBlocks([aBlock({ id: 'b03', block_class: 'figure', segments: null, text, attrs: { kind: 'diagram', grouped: '1' } })])
    const groups = view.findAll('[data-block="b03"] .text-group')
    expect(groups.map(group => group.find('.group-title').text())).toEqual(['Cash', 'Supplies'])
    expect(groups[0].findAll('.group-line').map(line => line.text())).toEqual(['Aug. 1 700', 'Bal. 700'])
    expect(view.find('[data-block="b03"] .block-attrs').text()).toBe('kind=diagram grouped=1')
  })

  it('keeps an ungrouped body\'s lines as the reader wrote them, where it is no figure', () => {
    const view = mountBlocks([aBlock({ id: 'b03', block_class: 'other', segments: null, text: 'Cash\nAug. 1 700', attrs: {} })])
    expect(view.find('[data-block="b03"] .text-group').exists()).toBe(false)
    expect((view.find('[data-block="b03"] .block-body.text').element as HTMLElement).textContent).toBe('Cash\nAug. 1 700')
  })

  it('runs an ungrouped figure\'s labels on one line, folds them beyond a dozen, and a photo\'s always (2c)', () => {
    const many = Array.from({ length: 13 }, (_, at) => `${at * 10}`).join('\n')
    const view = mountBlocks([
      aBlock({ id: 'b01', block_class: 'figure', segments: null, text: 'Cash\nAug. 1 700', attrs: { kind: 'chart' } }),
      aBlock({ id: 'b02', block_class: 'figure', segments: null, text: many, attrs: { kind: 'chart' } }),
      aBlock({ id: 'b03', block_class: 'figure', segments: null, text: 'CAGR +47%\n165B', attrs: { kind: 'photo' } }),
      aBlock({ id: 'b04', block_class: 'description', segments: null, text: 'A photograph of a desk. It holds charts.', attrs: { of: 'b03' } }),
    ])
    expect(view.find('[data-block="b01"] .label-run').text()).toBe('Cash · Aug. 1 700')
    expect(view.find('[data-block="b01"] details').exists()).toBe(false)
    expect(view.find('[data-block="b02"] details.labels-fold summary').text()).toBe('13 labels')
    // a photo folds whatever its count, its title the description's first sentence
    expect(view.find('[data-block="b03"] details.labels-fold summary').text()).toBe('A photograph of a desk. · 2 labels read from the photo')
  })

  it('names a figure the API marks as decoration chapter art, folded and quiet, never hidden (194.a)', () => {
    const view = mountBlocks([aBlock({ id: 'b01', block_class: 'figure', segments: null, text: 'CAGR +47%\n165B',
      attrs: { kind: 'photo' }, decorative: 'a photo on a chapter opener' })])
    const fold = view.find('[data-block="b01"] details.labels-fold')
    expect(fold.classes()).toContain('chapter-art')
    expect(fold.attributes('open')).toBeUndefined()
    expect(fold.find('summary').text()).toBe('Chapter art · 2 labels read from the photo')
    expect(fold.find('.label-run').text()).toBe('CAGR +47% · 165B')
  })

  it('says which block the pointer is over, and when it leaves', async () => {
    const view = mountBlocks([aBlock({ id: 'b04' })])
    await view.find('[data-block="b04"]').trigger('mouseenter')
    await view.find('[data-block="b04"]').trigger('mouseleave')
    expect(view.emitted('hover')).toEqual([['b04'], [null]])
  })

  it('shows the printed words an attribute carries: a term before its definition, a key before, a target after (190.a)', () => {
    const prose = (content: string) => [{ kind: 'text' as const, content }]
    const view = mountBlocks([
      aBlock({ id: 'b19', block_class: 'glossary_entry', attrs: { term: 'accrual-basis accounting' }, segments: prose('an accounting system') }),
      aBlock({ id: 'b30', block_class: 'bib_entry', attrs: { key: '12' }, segments: prose('Sharpe, W. F. (1966).') }),
      aBlock({ id: 'b40', block_class: 'toc_entry', attrs: { target: '23' }, segments: prose('Chapter 1 Introduction') }),
      aBlock({ id: 'b50', block_class: 'paragraph', attrs: { term: 'not printed here' }, segments: prose('a paragraph') }),
    ])
    const term = view.find('[data-block="b19"] [data-part="entry-term"]')
    expect(term.element.tagName).toBe('STRONG')
    expect(view.find('[data-block="b19"] .block-body').text()).toBe('accrual-basis accounting: an accounting system')
    expect(view.find('[data-block="b30"] .block-body').text()).toBe('12 Sharpe, W. F. (1966).')
    expect(view.find('[data-block="b40"] .block-body').text()).toBe('Chapter 1 Introduction 23')
    // only the classes whose attribute is printed: any other block's attribute stays an attribute
    expect(view.find('[data-block="b50"] [data-part="entry-term"]').exists()).toBe(false)
  })

  it('puts the judge\'s findings about a block right beneath it, each with a glyph and its words', () => {
    const view = mountBlocks([
      aBlock({ id: 'b03', findings: [{ kind: 'structure', block: 'b03', severity: 'major', evidence: 'colspan=9 over 7 columns', void: false }] }),
      aBlock({ id: 'b04' }),
    ])
    const block = view.find('[data-block="b03"]')
    expect(block.classes()).toContain('has-findings')
    const finding = block.find('.block-findings [data-finding="0"]')
    expect(finding.text()).toContain('structure')
    expect(finding.text()).toContain('major')
    expect(finding.text()).toContain('colspan=9 over 7 columns')
    expect(finding.find('[data-icon="finding"]').exists()).toBe(true)
    expect(view.find('[data-block="b04"] .block-findings').exists()).toBe(false)
  })

  it('frames the block a finding names', () => {
    const view = mountBlocks([aBlock({ id: 'b01' }), aBlock({ id: 'b02' })], 'b02')
    expect(view.find('[data-block="b02"]').classes()).toContain('highlighted')
    expect(view.find('[data-block="b01"]').classes()).not.toContain('highlighted')
  })
})
