import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOpenUnitsStore } from '@/stores/open_units_store'

describe('useOpenUnitsStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('remembers a work\'s opened chapters in this browser, and forgets one folded again', () => {
    const store = useOpenUnitsStore()
    store.setOpen('free/kelly', '4:2 The Kelly criterion', true)
    store.setOpen('free/kelly', '9:3 Results', true)
    store.setOpen('free/kelly', '9:3 Results', false)
    // a new page load reads what the last one left
    setActivePinia(createPinia())
    const again = useOpenUnitsStore()
    expect(again.isOpen('free/kelly', '4:2 The Kelly criterion')).toBe(true)
    expect(again.isOpen('free/kelly', '9:3 Results')).toBe(false)
    expect(again.isOpen('free/other', '4:2 The Kelly criterion')).toBe(false)
  })

  it('keeps the works touched last, the oldest giving way, and survives a corrupt entry', () => {
    const store = useOpenUnitsStore()
    for (let at = 0; at < 45; at++) store.setOpen(`free/work${at}`, 'u', true)
    const kept = Object.keys(JSON.parse(localStorage.getItem('openUnits.v1')!) as object)
    expect(kept).toHaveLength(40)
    expect(kept).not.toContain('free/work0')
    expect(kept).toContain('free/work44')
    localStorage.setItem('openUnits.v1', '{not json')
    setActivePinia(createPinia())
    expect(useOpenUnitsStore().isOpen('free/work44', 'u')).toBe(false)
  })
})
