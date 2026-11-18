import { describe, expect, it } from 'vitest'

import { isDecided, standingOf } from '@/listed_state'
import { assessmentLabel, correctionLabel, lookedSaid, verdictBy, verdictLabel } from '@/person_words'

// the operator's 2.a and 3.a, 18 Nov: "a person is always manual"; a verdict a session gave on the operator's delegation is an
// automated review's, named so wherever it stands
const PERSON = { by_a_person: true }
const REVIEW = { by_a_person: false }

describe('whose verdict it is, named the same everywhere', () => {
  it('names a person\'s and an automated review\'s apart, and a record without the field as a person\'s', () => {
    expect([verdictBy(PERSON), verdictBy(REVIEW), verdictBy({}), verdictBy(null)]).toEqual(['A person', 'Automated review', 'A person', 'A person'])
    expect([verdictLabel(PERSON), verdictLabel(PERSON, true), verdictLabel(REVIEW), verdictLabel(REVIEW, true)])
      .toEqual(["A person's verdict", "A person's verdict on the page", 'Automated review', 'Automated review on the page'])
    expect([correctionLabel(PERSON), correctionLabel(PERSON, true), correctionLabel(REVIEW), correctionLabel(REVIEW, true)])
      .toEqual(['Manual correction by a person', 'An earlier manual correction by a person', 'Correction by an automated review',
        'An earlier correction by an automated review'])
    expect([assessmentLabel(PERSON, 'judge/1'), assessmentLabel(REVIEW)])
      .toEqual(["A person's assessment of judge/1", "An automated review's assessment of the judge"])
  })

  it('says who looked at an error in the same words', () => {
    expect(lookedSaid({ looked: 'accept', looked_at: 'block', block: 'b04', looked_by_a_person: false }))
      .toBe('an automated review accepted b04')
    expect(lookedSaid({ looked: 'note', looked_at: 'page', looked_by_a_person: true })).toBe('a person noted the page')
  })

  it('counts a settled page as settled whoever settled it, and each facet by its own voice', () => {
    expect([isDecided('decided_by_a_person'), isDecided('decided_by_an_automated_review'), isDecided('issue'), isDecided(null)])
      .toEqual([true, true, false, false])
    const reviewed = { standing: 'accepted', by_a_person: false }
    expect([standingOf(reviewed, true), standingOf(reviewed, false)]).toEqual(['', 'accepted'])
    expect([standingOf({ standing: 'noted' }, true), standingOf(null, false)]).toEqual(['noted', ''])
  })
})
