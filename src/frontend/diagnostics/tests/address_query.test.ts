import { describe, it, expect } from 'vitest'
import { queryValues } from '@/address_query'

describe('queryValues', () => {
  it('reads none, one or several values of a key, and drops empty ones', () => {
    expect(queryValues({}, 'state')).toEqual([])
    expect(queryValues({ state: 'issue' }, 'state')).toEqual(['issue'])
    expect(queryValues({ state: ['issue', 'blocked'] }, 'state')).toEqual(['issue', 'blocked'])
    expect(queryValues({ state: ['', null, 'issue'], kb: 'free' }, 'state')).toEqual(['issue'])
  })
})
