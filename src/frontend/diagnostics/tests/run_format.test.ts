import { describe, it, expect } from 'vitest'
import { shortCommand } from '@/run_format'

describe('run_format', () => {
  it('drops only the module path every command shares', () => {
    expect(shortCommand('python -m backend.conversion.check_run submit --cells LIC-R04 --cap 75'))
      .toBe('check_run submit --cells LIC-R04 --cap 75')
    expect(shortCommand('python -m backend.search.build')).toBe('python -m backend.search.build')
  })

  it('says a run started since the modules have folders (208.b) as it says an earlier one', () => {
    expect(shortCommand('python -m backend.conversion.checks.check_run submit --cells LIC-R04 --cap 75'))
      .toBe('check_run submit --cells LIC-R04 --cap 75')
    for (const folder of ['contract', 'reading', 'checks', 'judge', 'measurement', 'store']) {
      expect(shortCommand(`python -m backend.conversion.${folder}.a_module --flag`)).toBe('a_module --flag')
    }
    // a folder the conversion does not have is no concern folder: only the shared path goes
    expect(shortCommand('python -m backend.conversion.vendor.tool')).toBe('vendor.tool')
  })
})
