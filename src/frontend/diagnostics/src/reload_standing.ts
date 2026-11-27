import type { RouteLocationNormalized, RouteLocationRaw, Router } from 'vue-router'

/**
 * Decision 30.a (the operator: "when people panic, F5 back to the normal state; it is only history after all"): a reload in
 * the same tab always returns the standing view, so a recall (`?judgement=`) leaves the address and its frames go with it;
 * a link opened fresh still shows the recall it names, so a recall stays shareable. The two are told apart by how the
 * document was loaded (`PerformanceNavigationTiming.type`), read once, and only the first navigation after it is touched:
 * every later one is the reader's own.
 */

/** How the document was loaded: 'navigate', 'reload', 'back_forward', or null where the browser does not say. */
export function navigationType(): string | null {
  try {
    const entry = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    return entry?.type ?? null
  } catch {
    return null
  }
}

/** Where a first navigation goes: the same address without its recall where the document was reloaded, else as asked. */
export function standingOnReload(to: Pick<RouteLocationNormalized, 'path' | 'query' | 'hash'>, loadedBy: string | null): true | RouteLocationRaw {
  if (loadedBy !== 'reload' || typeof to.query.judgement !== 'string') return true
  const query = Object.fromEntries(Object.entries(to.query).filter(([key]) => key !== 'judgement'))
  return { path: to.path, query, hash: to.hash, replace: true }
}

/** Sets the rule on a router: its first navigation, and that one alone, returns the standing view after a reload. */
export function returnStandingOnReload(router: Router, loadedBy: string | null = navigationType()): void {
  let first = true
  router.beforeEach(to => {
    if (!first) return true
    first = false
    return standingOnReload(to, loadedBy)
  })
}
