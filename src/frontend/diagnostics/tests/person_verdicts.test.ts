import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FindingList from '@/components/FindingList.vue'
import PersonVerdictList from '@/components/PersonVerdictList.vue'
import type { PersonVerdict } from '@/types/api/page_types'

// invented: a person's verdicts as the export gives them since 191.a
function aVerdict(overrides: Partial<PersonVerdict>): PersonVerdict {
  return { reading_key: 'r1', applies: true, block: 'b05', verdict: 'accept', reason: 'other', reason_text: 'another reason, said in the note',
    note: 'all values match the text layer', given_by: 'maintainer', given_at: '2026-11-10T22:03:55+00:00', ...overrides }
}

const FINDING = { kind: 'wrong_value', block: 'b10', severity: 'major', evidence: 'a value', void: false }

describe('a person\'s verdicts beside the findings and in the history (191.a, 408)', () => {
  it('says a page-level verdict as the page\'s under a finding no verdict names, and never the placeholder of `other`', () => {
    const list = mount(FindingList, { props: { findings: [FINDING], people: [aVerdict({ block: null })] } })
    const person = list.find('[data-voice="person"]')
    expect(person.find('.part-label').text()).toBe("A person's verdict on the page:")
    // the reason `other` has no words of its own: none beside the verdict, the note a line of its own beneath (the operator, 11 Nov)
    expect(person.findAll('.person-part')).toEqual([])
    expect(list.find('[data-part="person-note"]').text()).toBe('all values match the text layer')
  })

  it('says a named reason beside the verdict and the note beneath it, never parted by a dot at a line\'s start', () => {
    const list = mount(FindingList, { props: { findings: [FINDING], people: [aVerdict({ reason: 'reading_wrong',
      reason_text: 'the reading does not say what the page prints', note: 'the lines cross about 2012' })] } })
    expect(list.find('[data-voice="person"] .person-part').text()).toBe('· the reading does not say what the page prints')
    expect(list.find('[data-part="person-note"]').text()).toBe('the lines cross about 2012')
  })

  it('draws a table block\'s correction as a table, never its source, and any other correction as text (204.a)', () => {
    const grid = '<table><tr><th>Assets</th><td>Debit<br>Increase</td></tr></table>'
    const cells = [[{ segments: [{ kind: 'text' as const, content: 'Assets' }], header: true, rowspan: 1, colspan: 1 },
      { segments: [{ kind: 'text' as const, content: 'Debit Increase' }], header: false, rowspan: 1, colspan: 1 }]]
    const table = mount(FindingList, { props: { findings: [FINDING], people: [aVerdict({ correction: grid, correction_rows: cells })] } })
    const drawn = table.find('[data-part="correction"]')
    expect(drawn.find('table.cells').exists()).toBe(true)
    expect(drawn.findAll('th, td').map(cell => cell.text())).toEqual(['Assets', 'Debit Increase'])
    expect(drawn.text()).not.toContain('<table>')
    const words = mount(FindingList, { props: { findings: [FINDING], people: [aVerdict({ correction: 'the crossing around 2012' })] } })
    expect(words.find('p[data-part="correction"]').text()).toBe('the crossing around 2012')
  })

  it('says a verdict in the history and the details as it reads beneath a block: the same label and word, the note beneath', () => {
    const list = mount(PersonVerdictList, { props: { people: [aVerdict({ block: 'b03', reason: 'reading_wrong',
      reason_text: 'the reading does not say what the page prints', note: 'the lines cross about 2012' })], namesBlocks: true } })
    const line = list.find('[data-person="0"] .person-line')
    expect(line.find('.part-label').text()).toBe("A person's verdict:")
    expect(line.find('.person-verdict').text()).toBe('accepted')
    expect(line.text()).not.toContain('the lines cross about 2012')
    // the note a line of its own, never begun by the dot that parts the line's fields
    expect(list.find('[data-part="person-note"]').text()).toBe('the lines cross about 2012')
    const finding = mount(FindingList, { props: { findings: [FINDING], people: [aVerdict({ block: 'b03' })] } })
    expect(finding.find('[data-voice="person"] .part-label').text()).toBe(line.find('.part-label').text())
    expect(finding.find('.person-standing').text()).toBe(line.find('.person-verdict').text())
  })

  it('shows a verdict archived by a reset, greyed, with the reset\'s time, never as given on an earlier reading', () => {
    const list = mount(PersonVerdictList, { props: { people: [aVerdict({ applies: false, archived: true, archived_at: '2026-11-11T09:00:00+00:00' })] } })
    const line = list.find('[data-person="0"]')
    expect(line.classes()).toContain('archived')
    expect(line.find('.person-archived').text()).toContain('archived by a reset')
    expect(line.find('.person-archived time').attributes('datetime')).toBe('2026-11-11T09:00:00+00:00')
    expect(line.find('.person-earlier').exists()).toBe(false)
    expect(line.find('.person-reason').exists()).toBe(false)
  })
})
