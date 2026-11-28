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
        aFormVerdict({ version: 'judge/3', recall: 'k2:judge/3:0', verdict_said: 'ok', reason_said: 'wrong word, struck by code', overruled: 'bad',
          show_why_not: null, block: null }),
        aFormVerdict({ kind: 'person', kind_said: 'person', model: '', cost_usd: null, version: null, version_said: null,
          verdict_said: 'agree', reason_said: 'the judge was right', state: 'note', recall: null, show_why_not: null, block: 'b03' }),
      ] }),
      aFormReading({ key: 'k1', shown: false, recall: 'k1', result_state: 'issue', result_said: '2 issues',
        verdicts: [aFormVerdict({ recall: 'k1:judge/1:0', state: 'issue', verdict_said: 'bad', reason_said: '2 findings: 2 major', show_why_not: null,
          rules: [{ kind: 'vocabulary', block_class: 'note', attribute: 'marker', value: 'superscript' }] })] }),
    ],
    lab: [aFormReading({ key: 'k3', shown: false, recall: 'k3', version: 'page/2', test_reading: true,
      result_state: 'none', result_said: 'no judge', verdicts: [],
      hover: [{ label: 'reading key', value: 'k3' }, { label: 'purpose', value: 'a test reading' }] })],
    verdicts: shownVerdicts([
      aVerdictRow({ kind: 'person', kind_said: 'person', verdict: 'agree', state: 'note', reason: 'the judge was right',
        about: 'b03', recall: null, judge_said: 'judge/3', who: 'person', who_said: 'the operator' }),
      aVerdictRow({ recall: 'k2:judge/3:0', overruled: 'bad', reason: 'wrong word, struck by code', about: 'b12' }),
    ]),
  })
}

describe('PageForm, a page\'s readings and verdicts in one form (#18)', () => {
  it('names its three tabs with the API\'s counts, the readings first, and a click shows the tab\'s own rows', async () => {
    const form = mountForm(aForm())
    expect(form.findAll('[role="tab"]').map(tab => [tab.attributes('data-tab'), tab.text()]))
      .toEqual([['readings', 'Readings 2'], ['lab', 'Lab 1'], ['verdicts', 'Verdicts 2']])
    expect(form.find('[data-tab="readings"]').attributes('aria-selected')).toBe('true')
    expect(form.findAll('[data-panel="readings"] tbody[data-reading]').map(body => body.attributes('data-reading'))).toEqual(['k2', 'k1'])
    await form.find('[data-tab="lab"]').trigger('click')
    expect(form.findAll('[data-panel="lab"] tbody[data-reading]').map(body => body.attributes('data-reading'))).toEqual(['k3'])
    await form.find('[data-tab="verdicts"]').trigger('click')
    expect(form.findAll('[data-panel="verdicts"] tr[data-verdict-row]')).toHaveLength(2)
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
    expect(form.find('tbody[data-reading="k2"] [data-part="shown"]').text()).toBe('● served')
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

  it('greys a reading\'s own show where a judge beneath it shows it with its findings, its card naming that judge (42.a)', async () => {
    const why = 'show on judge/1: the same reading with its findings'
    const form = mountForm(aPageForm({ readings: [
      aFormReading({ key: 'k1' }),
      aFormReading({ key: 'k0', shown: false, recall: 'k0', show_why_not: why,
        verdicts: [aFormVerdict({ recall: 'k0:judge/1:0', show_why_not: null })] }),
    ] }))
    const row = form.find('tbody[data-reading="k0"] .reading-row')
    expect(row.find('[data-part="show-reading"]').exists()).toBe(false)
    const off = row.find('[data-part="show-reading-off"]')
    expect([off.find('button').attributes('disabled'), off.find('button').attributes('title')]).toEqual(['', undefined])
    await off.element.closest('.hover-card-host')!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await form.vm.$nextTick()
    expect(form.find('[data-part="hover-card"] [data-row="why not"] .card-value').text()).toBe(why)
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
      .toEqual([['true', '● standing'], ['true', '● standing']])
    // a person's row names the judge it answers, in short; a judge's says "—" there
    const [person, judge] = [rows[0]!, rows[1]!]
    expect(person.find('[data-kind]').text()).toBe('person')
    expect(person.text()).toContain('the judge was right')
    expect([person.find('[data-part="judge-said"]').text(), judge.find('[data-part="judge-said"]').text()]).toEqual(['judge/3', '—'])
    expect(person.text()).toContain('the operator')
    // a judge's word is the result that counts, its own beside it, struck (32.a), its finding in short (33.a)
    expect(judge.find('.result').text().replace(/\s+/g, ' ')).toBe('ok bad')
    expect([judge.find('s[data-part="overruled"]').text(), judge.text()]).toEqual(['bad', expect.stringContaining('wrong word, struck by code')])
  })

  it('strikes a judge\'s own word right behind the result that counts, its reason a column apart (32.a, 47.a)', () => {
    const form = mountForm(aForm())
    const verdict = form.find('tbody[data-reading="k2"] tr.verdict-row[data-verdict="k2/0"]')
    expect(verdict.find('.result').text().replace(/\s+/g, ' ')).toBe('ok bad')
    expect(verdict.find('s[data-part="overruled"]').text()).toBe('bad')
    expect(verdict.find('[data-part="reason"]').text()).toBe('wrong word, struck by code')
    // a person's reason in the same column; the reading's own empty where it adds nothing
    expect(form.find('tbody[data-reading="k2"] tr.verdict-row[data-verdict="k2/1"] [data-part="reason"]').text()).toBe('the judge was right')
    expect(form.find('tbody[data-reading="k2"] .reading-row [data-part="reason"]').text()).toBe('')
    expect(form.findAll('[data-panel="readings"] thead th').map(head => head.text())).toEqual(
      ['Kind', 'Time', 'Model', 'Cost', 'Version', 'Result', 'Reason', 'Show'])
  })

  it('shows the verdicts as then in focus, the recalled one marked ↺, its caption the API\'s with its moment in words (29.d)', async () => {
    const then = shownVerdicts([aVerdictRow({ recall: 'k1:judge/1:0', standing_said: 'recalled', recalled: true })],
      { said: 'as then: the verdicts on reading 2 on', said_at: '2026-11-09T10:56:48+00:00', recalled: true })
    const form = mountForm(aForm(), 'k1:judge/1:0', then)
    await form.find('[data-tab="verdicts"]').trigger('click')
    const said = form.find('[data-part="verdicts-said"]')
    expect(said.text()).toMatch(/^as then: the verdicts on reading 2 on \d{1,2} Nov, \d{2}:\d{2}$/)
    expect(said.find('time').attributes('datetime')).toBe('2026-11-09T10:56:48+00:00')
    expect(form.find('tr[data-verdict-row] .standing-mark').text()).toBe('↺ recalled')
  })

  it('keeps the Verdicts tab in its place for a recalled trial, greyed, "–", its card saying why, and opens the Lab (38.a)', async () => {
    const why = 'a trial in the Lab: no verdict applies to it; a person judges only what counts'
    const trial = shownVerdicts([], { said: 'in the Lab: no verdict applies', count: null, recalled: true, why_not: why })
    const form = mountForm(aForm(), null, null)
    await form.find('[data-tab="verdicts"]').trigger('click')
    expect(form.find('[data-panel="verdicts"]').exists()).toBe(true)
    // the trial recalled while Verdicts was open: the Lab is shown instead, the tab greyed in its place
    await form.setProps({ recallId: 'k3', recalledVerdicts: trial })
    expect(form.find('[data-panel="lab"]').exists()).toBe(true)
    const tab = form.find('[data-tab="verdicts"]')
    expect([tab.text(), tab.attributes('disabled'), tab.attributes('title')]).toEqual(['Verdicts –', '', undefined])
    await tab.element.closest('.hover-card-host')!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await form.vm.$nextTick()
    expect(form.find('[data-part="hover-card"] [data-row="why not"] .card-value').text()).toBe(why)
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
