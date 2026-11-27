import { describe, it, expect } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { navigationType, returnStandingOnReload, standingOnReload } from '@/reload_standing'

const PAGE = { template: '<p />' }

function aRouter(loadedBy: string | null) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/free/sources/:work/page/:page', component: PAGE }] })
  returnStandingOnReload(router, loadedBy)
  return router
}

describe('a reload returns the standing view, a link opened fresh keeps its recall (30.a)', () => {
  it('drops the recall from the first address after a reload, and only the recall', async () => {
    const router = aRouter('reload')
    await router.push('/free/sources/kelly/page/4?judgement=k1:judge/2:0&tab=x')
    expect(router.currentRoute.value.query).toEqual({ tab: 'x' })
    expect(router.currentRoute.value.path).toBe('/free/sources/kelly/page/4')
    // every later navigation is the reader's own: a recall asked for now stands
    await router.push('/free/sources/kelly/page/4?judgement=k1:judge/2:0')
    expect(router.currentRoute.value.query.judgement).toBe('k1:judge/2:0')
  })

  it('keeps the recall a link names where the page was opened fresh, or the browser does not say how', async () => {
    for (const loadedBy of ['navigate', 'back_forward', null]) {
      const router = aRouter(loadedBy)
      await router.push('/free/sources/kelly/page/4?judgement=k1:judge/2:0')
      expect([loadedBy, router.currentRoute.value.query.judgement]).toEqual([loadedBy, 'k1:judge/2:0'])
    }
  })

  it('leaves an address without a recall as it is, and says how the document was loaded where the browser can', async () => {
    const router = aRouter('reload')
    const to = router.resolve('/free/sources/kelly/page/4')
    expect(standingOnReload(to, 'reload')).toBe(true)
    // jsdom keeps no navigation entry: not known, so nothing is touched
    expect(navigationType()).toBeNull()
  })
})
