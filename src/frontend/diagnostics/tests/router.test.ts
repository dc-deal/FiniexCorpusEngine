import { describe, it, expect, vi } from 'vitest'
import { router } from '@/router'

vi.mock('@/api/api_client', () => ({ getWorks: vi.fn() }))

describe('router', () => {
  it('opens on the overview', async () => {
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('overview')
  })

  it('keeps the address in the hash, so the API serves one page for every view', () => {
    expect(router.resolve({ name: 'sources' }).href).toBe('#/sources')
  })

  it('addresses a work within its knowledge base, as the API does', () => {
    expect(router.resolve({ name: 'page', params: { kb: 'licensed', work: 'x', page: 3 } }).href)
      .toBe('#/licensed/sources/x/page/3')
    expect(router.resolve('/other/sources/x').matched).toEqual([])
    // the API's knowledge base is case-sensitive, and so is the address: no view to be refused in
    expect(router.resolve('/FREE/sources/x').matched).toEqual([])
    expect(router.resolve('/Licensed/sources/x/page/3').matched).toEqual([])
  })

  it('sends an address from before the knowledge base was part of it to the free work, and the bin to the issues', async () => {
    await router.push('/sources/kelly/page/3')
    expect(router.currentRoute.value.fullPath).toBe('/free/sources/kelly/page/3')
    await router.push('/sources/kelly')
    expect(router.currentRoute.value.fullPath).toBe('/free/sources/kelly')
    await router.push('/bin')
    expect(router.currentRoute.value.name).toBe('issues')
  })
})
