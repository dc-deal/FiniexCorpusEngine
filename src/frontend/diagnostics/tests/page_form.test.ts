import { describe, it, expect, afterEach } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { router } from '@/router'
import PageForm from '@/components/PageForm.vue'
import type { PageForm as Form, ShownVerdicts } from '@/types/api/page_types'
import { aFormReading, aFormVerdict, aPageForm, aVerdictRow, shownVerdicts } from './page_fixture'

enableAutoUnmount(afterEach)

const SHOW_WHY_NOT = 'no difference: this judgement found nothing; use show on its reading'

function mountForm(form: Form, recallId: string | null = null, recalledVerdicts: ShownVerdicts | null = null) {
  return mount(PageForm, {
    props: { form, recallId, recallTo: (recall: string) => ({ query: { judgement: recall } }), recalledVerdicts },
    global: { plugins: [router] },
  })
}

/** A page read twice by the pipeline and once in the Lab, with a person's verdict, as the API's form serves it. */
function aForm(): Form {
  return aPageForm({
    shown_judgement: 'k2:judge/3:0',
    readings: [
      aFormReading({ key: 'k2', time: '2026-11-06T10:00:00+00:00', verdicts: [
        aFormVerdict({ version: 'judge/3', recall: 'k2:judge/3:0', verdict_said: 'ok · 1 finding', show_why_not: null, block: null }),
        aFormVerdict({ kind: 'person', kind_said: 'person', model: '', cost_usd: null, version: null, version_said: null,
          verdict_said: 'agree · the judge was right', state: 'note', recall: null, show_why_not: null, block: 'b03' }),
      ] }),
      aFormReading({ key: 'k1', shown: false, recall: 'k1', result_state: 'issue', result_said: '2 issues',
        verdicts: [aFormVerdict({ recall: 'k1:judge/1:0', state: 'issue', verdict_said: 'bad · 2 findings', show_why_not: null,
          rules: [{ kind: 'vocabulary', block_class: 'note', attribute: 'marker', value: 'superscript' }] })] }),
    ],
    lab: [aFormReading({ key: 'k3', shown: false, recall: 'k3', version: 'page/2', test_reading: true,
      result_state: 'none', result_said: 'no judge', verdicts: [],
      hover: [{ label: 'reading key', value: 'k3' }, { label: 'purpose', value: 'a test reading' }] })],
    verdicts: shownVerdicts([
      aVerdictRow({ kind: 'person', kind_said: 'person', standing: false, standing_said: 'replaced', verdict: 'reject', state: 'issue',
        about: 'b03', recall: null, who: 'person', who_said: 'the operator' }),
      aVerdictRow({ recall: 'k2:judge/3:0' }),
      aVerdictRow({ kind: 'person', kind_said: 'person', verdict: 'agree', state: 'note', reason: 'the judge was right',
        about: 'b03', recall: null, answered: { version: 'judge/3', model: 'an-invented-judge', stored_at: null, derived: true },
        who: 'person', who_said: 'the operator' }),
    ]),
  })
}

describe('PageForm, a page\'s readings and verdicts in one form (#18)', () => {
  it('names its three tabs with the API\'s counts, the readings first, and a click shows the tab\'s own rows', async () => {
    const form = mountForm(aForm())
    expect(form.findAll('[role="tab"]').map(tab => [tab.attributes('data-tab'), tab.text()]))
      .toEqual([['readings', 'Readings 2'], ['lab', 'Lab 1'], ['verdicts', 'Verdicts 3']])
    expect(form.find('[data-tab="readings"]').attributes('aria-selected')).toBe('true')
    expect(form.findAll('[data-panel="readings"] tbody[data-reading]').map(body => body.attributes('data-reading'))).toEqual(['k2', 'k1'])
    await form.find('[data-tab="lab"]').trigger('click')
    expect(form.findAll('[data-panel="lab"] tbody[data-reading]').map(body => body.attributes('data-reading'))).toEqual(['k3'])
    await form.find('[data-tab="verdicts"]').trigger('click')
    expect(form.findAll('[data-panel="verdicts"] tr[data-verdict-row]')).toHaveLength(3)
  })

  it('says each row\'s kind in front, a glyph and a word, and folds the reading shown open to its verdicts', async () => {
    const form = mountForm(aForm())
    const shown = form.find('tbody[data-reading="k2"]')
    expect(shown.find('.reading-row [data-kind]').text()).toBe('reading')
    expect(shown.find('.reading-row [data-kind] svg').exists()).toBe(true)
    expect(shown.findAll('tr[data-verdict] [data-kind]').map(kind => kind.text())).toEqual(['judge', 'person'])
    // the reading shown is open; the other folds closed until its mark is clicked, which says what it does
    const other = form.find('tbody[data-reading="k1"]')
    expect(other.findAll('tr[data-verdict]')).toHaveLength(0)
    const mark = other.find('[data-part="fold-reading"]')
    expect([mark.text(), mark.attributes('aria-expanded'), mark.attributes('aria-label')]).toEqual(['▸', 'false', 'open its verdicts'])
    await mark.trigger('click')
    expect(other.findAll('tr[data-verdict]')).toHaveLength(1)
    expect(other.find('[data-part="fold-reading"]').text()).toBe('▾')
    // a judge's rules for the reader stand beneath its verdict, read-only (202.a)
    expect(other.find('tr[data-rules]').exists()).toBe(true)
  })

  it('shows the result in the API\'s words with a glyph, and says the shown reading where the others offer show', () => {
    const form = mountForm(aForm())
    const results = form.findAll('.reading-row [data-result]')
    expect(results.map(result => [result.attributes('data-result'), result.text()])).toEqual([['ok', 'ok'], ['issue', '2 issues']])
    expect(results.every(result => result.find('svg').exists())).toBe(true)
    expect(form.find('tbody[data-reading="k2"] [data-part="shown"]').text()).toBe('● shown')
    // the other reading shows itself alone, by its key
    expect(form.find('tbody[data-reading="k1"] [data-part="show-reading"]').attributes('href')).toContain('judgement=k1')
  })

  it('greys a show that would change nothing, keeping its place, its card saying why (decision 25)', async () => {
    const form = mountForm(aPageForm({ readings: [aFormReading({ verdicts: [aFormVerdict()] })] }))
    expect(form.find('[data-part="recall"]').exists()).toBe(false)
    const off = form.find('[data-part="show-off"]')
    expect(off.find('button').attributes('disabled')).toBeDefined()
    expect(off.find('button').attributes('title')).toBeUndefined()
    await off.element.closest('.hover-card-host')!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await form.vm.$nextTick()
    expect(form.find('[data-part="hover-card"] [data-row="why not"] .card-value').text()).toBe(SHOW_WHY_NOT)
  })

  it('offers show on a judgement with findings, and marks the one on the page in its place, opening its tab', async () => {
    const form = mountForm(aForm())
    expect(form.find('tbody[data-reading="k2"] [data-part="recall"]').attributes('href')).toContain('judgement=k2:judge/3:0')
    // a person's verdict about a block jumps to it
    expect(form.find('tbody[data-reading="k2"] [data-jump="b03"]').text()).toBe('b03')
    const recalled = mountForm(aForm(), 'k1:judge/1:0')
    expect(recalled.find('[data-tab="readings"]').attributes('aria-selected')).toBe('true')
    // the row it came from framed dashed, in the overlay's role (181.a)
    expect(recalled.find('tbody[data-reading="k1"] tr.verdict-row.recalled-source [data-part="recalled-here"]').text()).toBe('on the page')
    expect(recalled.findAll('tr.recalled-source')).toHaveLength(1)
    // a Lab reading shown alone opens the Lab
    const alone = mountForm(aForm(), 'k3')
    expect(alone.find('[data-tab="lab"]').attributes('aria-selected')).toBe('true')
    expect(alone.find('tbody[data-reading="k3"] tr.reading-row.recalled-source [data-part="recalled-here"]').exists()).toBe(true)
  })

  it('keeps a reading\'s bookkeeping in its card under the pointer, never in a column', async () => {
    const form = mountForm(aForm())
    await form.find('[data-tab="lab"]').trigger('click')
    expect(form.find('tbody[data-reading="k3"] .reading-row').text()).not.toContain('a test reading')
    await form.find('tbody[data-reading="k3"] .time-cell .hover-card-host').trigger('focusin')
    expect(form.find('[data-part="hover-card"]').findAll('.card-row').map(row => row.attributes('data-row'))).toEqual(['reading key', 'purpose'])
  })

  it('says a promoted reading so in its result', () => {
    const form = mountForm(aPageForm({ readings: [aFormReading({ promoted_said: 'promoted from the Lab: better tables' })] }))
    expect(form.find('[data-part="promoted"]').text()).toBe('· promoted from the Lab: better tables')
  })

  it('shows the verdicts as shown, its caption saying on which reading, each standing or not in the API\'s words (26)', async () => {
    const form = mountForm(aForm())
    await form.find('[data-tab="verdicts"]').trigger('click')
    expect(form.find('[data-part="verdicts-said"]').text()).toBe('as shown: the verdicts on the served reading')
    expect(form.find('[data-tab="verdicts"]').classes()).not.toContain('overlay')
    const rows = form.findAll('tr[data-verdict-row]')
    expect(rows.map(row => [row.attributes('data-standing'), row.find('.standing-mark').text()]))
      .toEqual([['false', '○ replaced'], ['true', '● standing'], ['true', '● standing']])
    expect(rows[0]!.classes()).toContain('history')
    const person = rows[2]!
    expect(person.find('[data-kind]').text()).toBe('person')
    expect(person.text()).toContain('the judge was right')
    expect(person.text().replace(/\s+/g, ' ')).toContain('judge/3 · an-invented-judge · by time')
    expect(person.text()).toContain('the operator')
  })

  it('shows a recalled reading\'s verdicts in their place, the tab and its table framed as the analysis is, the row shown framed (26, 27.a)', async () => {
    const recalled = shownVerdicts([aVerdictRow({ recall: 'k1:judge/1:0', verdict: 'bad', state: 'issue', reason: '2 findings' })],
      { said: 'as shown: the verdicts on reading 1 (recalled)', recalled: true })
    const form = mountForm(aForm(), 'k1:judge/1:0', recalled)
    const tab = form.find('[data-tab="verdicts"]')
    // the count is the recall's, and the tab is framed while the recall stands, before it is opened
    expect(tab.text()).toBe('Verdicts 1')
    expect([tab.classes(), tab.attributes('data-overlay')]).toEqual([expect.arrayContaining(['overlay']), 'yes'])
    await tab.trigger('click')
    expect(form.find('[data-part="verdicts-panel"]').classes()).toContain('overlay')
    const said = form.find('[data-part="verdicts-said"]')
    expect([said.text(), said.classes(), said.find('svg').exists()]).toEqual(['as shown: the verdicts on reading 1 (recalled)',
      expect.arrayContaining(['recalled']), true])
    const rows = form.findAll('tr[data-verdict-row]')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.classes()).toContain('recalled-source')
  })

  it('says none in a tab that holds nothing', async () => {
    const form = mountForm(aPageForm({ verdicts: shownVerdicts([]) }))
    await form.find('[data-tab="lab"]').trigger('click')
    expect(form.find('[data-panel="lab"] .none').text()).toBe('none')
    await form.find('[data-tab="verdicts"]').trigger('click')
    expect(form.find('[data-panel="verdicts"] .none').text()).toBe('none')
  })
})
