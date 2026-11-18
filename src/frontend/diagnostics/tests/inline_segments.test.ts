import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InlineSegments from '@/components/reading/InlineSegments.vue'
import type { Segment } from '@/types/api/page_types'

// invented prose: "processes.[4]{.fn}", a squared figure and a subscript, as the core parses them since 205.a
const SEGMENTS: Segment[] = [
  { kind: 'text', content: 'processes.' },
  { kind: 'fn', content: '4', note: 'b09', note_text: 'The source of the figures.' },
  { kind: 'text', content: ' 12.5' },
  { kind: 'sup', content: '2' },
  { kind: 'text', content: ' at r' },
  { kind: 'sub', content: 't' },
  { kind: 'text', content: ' and' },
  { kind: 'fn', content: '7' },
]

describe('InlineSegments, the inline marks (206.a)', () => {
  it('raises a superscript and a note marker, lowers a subscript, and never runs a marker into the text', () => {
    const view = mount(InlineSegments, { props: { segments: SEGMENTS } })
    expect(view.find('sup[data-segment="sup"]').text()).toBe('2')
    expect(view.find('sub[data-segment="sub"]').text()).toBe('t')
    expect(view.findAll('sup[data-segment="fn"]').map(mark => mark.text())).toEqual(['4', '7'])
    expect(view.text()).toBe('processes.4 12.52 at rt and7')
  })

  it('links a marker to the note its page holds: the note in a card, a click asking for the note', async () => {
    const view = mount(InlineSegments, { props: { segments: SEGMENTS } })
    const link = view.find('[data-note="b09"]')
    expect(link.text()).toBe('4')
    await link.trigger('click')
    expect(view.emitted('jump')).toEqual([['b09']])
    // the card: titled by the marker, holding the note's text
    await view.find('.hover-card-host').trigger('mouseenter')
    expect(view.find('[data-part="hover-card"] .card-title').text()).toBe('Note 4')
    expect(view.find('[data-part="hover-card"] [data-row="note"] .card-value').text()).toBe('The source of the figures.')
    // a marker without a note is no link
    expect(view.findAll('[data-note]')).toHaveLength(1)
  })
})
