import { expect, test, type Page } from '@playwright/test'
import { NOT_MEASURABLE, usd } from '../src/cost_format'

/**
 * The views in a real browser, against the built UI and the tracked data: what jsdom cannot show, such as an image that
 * really loads, KaTeX's fonts that really arrive and a page without a console error. Each test leaves a screenshot in
 * test-results/views/ for a person, or a session, to look at. The app runs with --public-only, so every screenshot holds
 * free pages only.
 */
const KELLY = 'carta_conversano_kelly_criterion_2020'
const FINANCE = 'openstax_principles_of_finance_2e'
const SHOTS = 'test-results/views'

let problems: string[] = []

test.beforeEach(async ({ page }) => {
  problems = []
  page.on('console', message => {
    if (message.type() === 'error') problems.push(message.text())
  })
  page.on('pageerror', error => problems.push(error.message))
})

test.afterEach(() => {
  expect(problems, 'the browser reported errors').toEqual([])
})

async function settled(page: Page, timeout?: number): Promise<void> {
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout })
}

// Opens every fold a view shows, nested ones too, looked up anew after each click: opening a fold may draw the view again,
// and a list taken once can hold a row that is gone by the time it is clicked. `limit` stops after that many, in reading
// order, for a check that needs each kind of fold opened rather than each fold
async function openEveryFold(page: Page, limit = 300): Promise<void> {
  for (let clicks = 0; clicks < limit; clicks++) {
    const closed = page.locator('details:not([open]) > summary:visible').first()
    if (!(await closed.count())) return
    await closed.click()
  }
}

// The overview asks every reading file whether it changed, so a file changed a moment ago counts (69.a). Since 10 Nov a file
// is hashed once at start and then known by its time and size, and the search reads its pages in a process of its own:
// 0.6 to 0.8 s once warm, about 4 s while the start still hashes. The bound stays wide for a cold disk.
const OVERVIEW_LOADS = 20_000

// A work with an outline opens on its chapters, where a page in two units stands twice: a check of the flat list asks for it
async function asTable(page: Page): Promise<void> {
  const table = page.locator('.view-switch button', { hasText: 'table' })
  if (await table.count()) await table.click()
}

test('the overview shows the pipeline at a glance, and a figure opens exactly the pages it counts', async ({ page, request }) => {
  type Row = { value: string, free: number | null }
  const sections = (await (await request.get('/api/overview')).json() as { sections: { title: string, rows: Row[] }[] }).sections
  const blocked = sections.find(section => section.title === 'State')!.rows.find(row => row.value === 'blocked')!
  await page.goto('/#/')
  await expect(page).toHaveURL(/#\/overview$/)
  await settled(page, OVERVIEW_LOADS)
  // the app runs with --public-only: the licensed base is said not to be read, and nothing of it shows
  await expect(page.locator('.headline[data-kb="licensed"] .not-served')).toContainText('--public-only')
  await page.screenshot({ path: `${SHOTS}/overview.png` })
  await page.locator('[data-section="State"] [data-value="blocked"] [data-kb="free"] a').click()
  await expect(page).toHaveURL(/#\/pages\?knowledge_base=free&state=blocked$/)
  await settled(page)
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(blocked.free!)
  await page.screenshot({ path: `${SHOTS}/pages_filtered.png` })
})

test('the overview says which model did what, and a model\'s count opens the pages it read', async ({ page, request }) => {
  type Row = { value: string, free: number | null, free_usd: number | null }
  const models = (await (await request.get('/api/overview')).json() as { models: { title: string, rows: Row[] }[] }).models
  // the fewest pages a model read in the free base: a short list to count in the browser
  const fewest = models.find(section => section.title === 'Readings by model')!.rows.filter(row => row.free !== null)
    .sort((one, other) => one.free! - other.free!)[0]
  await page.goto('/#/overview')
  await settled(page, OVERVIEW_LOADS)
  const box = page.locator('[data-band="cost"] [data-section="Readings by model"]')
  await expect(box.locator('thead th')).toHaveText(['Readings by model', 'free', 'USD', 'licensed', 'USD'])
  const row = box.locator(`tr[data-value="${fewest.value}"]`)
  await expect(row.locator('[data-kb-usd="free"]')).toHaveText(fewest.free_usd === null ? '—' : usd(fewest.free_usd))
  await row.locator('[data-kb="free"] a').click()
  await settled(page)
  await expect(page.locator('[data-filter="reader"]')).toContainText(fewest.value)
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(fewest.free!)
})

test('the runs list every run, and a run that chose readings opens their pages', async ({ page, request }) => {
  type Line = { knowledge_base: string, run_id: number }
  const listed = await (await request.get('/api/runs')).json() as { runs: Line[] }
  test.skip(!listed.runs.length, 'no pipeline database on this machine, as on a clone')
  // a run that chose a reading for a page the export holds, the oldest first: the rollout's runs chose readings, while the
  // newest are judge and prototype runs that choose none (390 runs on 10 Nov, the first hundred of them choosing nothing)
  let chosen: { line: Line, pdfPage: number } | null = null
  for (const line of [...listed.runs].reverse().slice(0, 40)) {
    const detail = await (await request.get(`/api/${line.knowledge_base}/runs/${line.run_id}`)).json() as {
      chose: { pdf_page: number, source_id: string | null }[]
    }
    const exported = detail.chose.find(choice => choice.source_id)
    if (exported) {
      chosen = { line, pdfPage: exported.pdf_page }
      break
    }
  }
  await page.goto('/#/runs')
  await settled(page)
  // at least the runs listed a moment ago: a run started meanwhile by the core is listed too
  expect(await page.locator('.run-rows tbody tr').count()).toBeGreaterThanOrEqual(listed.runs.length)
  await page.screenshot({ path: `${SHOTS}/runs.png` })
  test.skip(!chosen, 'no run on this machine chose a reading')
  await page.locator(`tr[data-run="${chosen!.line.knowledge_base}/${chosen!.line.run_id}"] .run-id a`).click()
  await settled(page)
  await expect(page.locator('.view-title')).toContainText(`Run #${chosen!.line.run_id}`)
  await page.screenshot({ path: `${SHOTS}/run.png` })
  await page.locator(`.chose-rows tr[data-page="${chosen!.pdfPage}"] a`).first().click()
  await expect(page).toHaveURL(new RegExp(`/page/${chosen!.pdfPage}$`))
})

test('the sources list every work of the catalog, each marked free', async ({ page, request }) => {
  const works = await (await request.get('/api/works')).json() as unknown[]
  await page.goto('/#/sources')
  await settled(page)
  await expect(page.locator('tbody tr')).toHaveCount(works.length)
  await expect(page.locator('tbody .kb-mark[data-kb="free"]')).toHaveCount(works.length)
  await page.screenshot({ path: `${SHOTS}/sources.png` })
})

// 211.a (the operator: "I would like to take pages judged by a person out of the issues"): a page the check listed to look at that a
// person settled counts in a bucket of its own, never as an issue. Finance, where a person walked the issues: its Sources row
// counts as the API lists its pages, the Issues fold the settled pages below the open ones, and a settled page's record
// keeps the check's state, named as the check's, after the person
test('a page a person settled counts in its own bucket, folds apart in the Issues and keeps the check\'s state', async ({ page, request }) => {
  type Row = { pdf_page: number, check: { state: string }, person: { standing: string } | null, listed_state: string }
  const pages = (await (await request.get(`/api/free/works/${FINANCE}/pages`)).json() as { pages: Row[] }).pages
  const settledPages = pages.filter(row => ['issue', 'blocked', 'stopped'].includes(row.check.state) && row.person)
  expect(pages.filter(row => row.listed_state === 'decided_by_a_person')).toEqual(settledPages)
  test.skip(!settledPages.length, 'no page of finance is settled by a person today')
  await page.goto('/#/sources')
  await settled(page)
  const counts = page.locator(`tr[data-work="${FINANCE}"] .state-counts`)
  const decided = counts.locator('.state-count[data-state="decided_by_a_person"]')
  await expect(decided.locator('.count')).toHaveText(String(settledPages.length))
  await expect(decided.locator('.state-word')).toHaveText('decided by a person')
  await expect(decided.locator('svg')).toBeVisible()
  const open = pages.filter(row => row.listed_state === 'issue').length
  if (open) await expect(counts.locator('.state-count[data-state="issue"] .count')).toHaveText(String(open))
  else await expect(counts.locator('.state-count[data-state="issue"]')).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/sources_decided.png` })
  // the Issues: the settled page in the fold below, not in the open list
  const one = settledPages[0]
  await page.goto('/#/issues')
  await settled(page)
  const fold = page.locator('[data-part="decided"]')
  await expect(fold.locator('summary')).toContainText('Decided by a person')
  await fold.locator('summary').click()
  await expect(fold.locator(`tr[data-page="free/${FINANCE}/${one.pdf_page}"]`)).toBeVisible()
  await expect(page.locator(`tr[data-page="free/${FINANCE}/${one.pdf_page}"]`)).toHaveCount(1)
  // its record: the person first, then the check's state, kept and receding
  await page.goto(`/#/free/sources/${FINANCE}/page/${one.pdf_page}`)
  await settled(page)
  const facts = page.locator('[data-part="page-facts"]')
  await expect(facts.locator('.line-label').first()).toHaveText('A person:')
  await expect(facts.locator('[data-label="Check"] .state-mark')).toHaveAttribute('data-state', one.check.state)
  await expect(facts.locator('[data-label="Check"] .state-mark')).toHaveClass(/quiet/)
})

// 219.a (the operator: "the detail page turned out well. Here I would carry the same line through"): a work's head reads as a page's
// does, its labels in a column as wide, so neither its labels nor its values move from a work to one of its pages
test('a work\'s head stands on the grid of its pages\' head, labels and values where a page has them', async ({ page }) => {
  // measured once the head stands, and from the head's own edge: a centred column moves by half a scrollbar while a long
  // view is still filling, which the window's x would read as a head off its grid (one full run of twelve, 12 Nov)
  const columns = async (part: string) => {
    await expect(page.locator(`[data-part="${part}"] .labelled-line`).first()).toBeVisible()
    return page.locator(`[data-part="${part}"]`).evaluate(head => {
      const edge = head.getBoundingClientRect().left
      return [...head.querySelectorAll('.labelled-line')].map(line => ({
        label: Math.round(line.querySelector('.line-label')!.getBoundingClientRect().left - edge),
        value: Math.round(line.querySelector('.line-value')!.getBoundingClientRect().left - edge),
      }))
    })
  }
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  const work = await columns('work-facts')
  // every line of the work's head, the facets' among them, in one label column and one value column
  expect(new Set(work.map(line => line.label)).size).toBe(1)
  expect(new Set(work.map(line => line.value)).size).toBe(1)
  await page.screenshot({ path: `${SHOTS}/work_head.png` })
  await page.goto(`/#/free/sources/${FINANCE}/page/119`)
  await settled(page)
  const one = (await columns('page-facts'))[0]
  expect([work[0].label, work[0].value]).toEqual([one.label, one.value])
  // and the check sees a head whose label column is wider: the work's, set wider for a moment
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  // by a rule rather than on the element: the view draws its head again when the work's pages arrive anew, and Vue sets
  // the grid's own width back on it then (a full run caught the control measuring the head already drawn again)
  await page.addStyleTag({ content: '[data-part="work-facts"] .labelled-lines { --label-width: 14ch !important; }' })
  expect((await columns('work-facts'))[0].value).not.toBe(one.value)
})

// A label's words and its value's words on one line (12 Nov): set by their baselines, a value that begins with a glyph (a
// person's mark, a state's) put its label 3px below its words. Measured by the line box of each one's first text
async function wordsApart(page: Page, part: string): Promise<string[]> {
  return page.locator(`[data-part="${part}"] .labelled-line`).evaluateAll(lines => lines.flatMap(line => {
    const firstText = (root: Element) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: node => (node.textContent!.trim() ? 1 : 3) })
      const node = walker.nextNode()
      if (!node) return null
      const range = document.createRange()
      range.selectNodeContents(node)
      return range.getClientRects()[0]?.bottom ?? null
    }
    const [label, value] = [firstText(line.querySelector('.line-label')!), firstText(line.querySelector('.line-value')!)]
    return label !== null && value !== null && Math.abs(label - value) > 1 ? [`${(line as HTMLElement).dataset.label}: ${Math.round(label - value)}px`] : []
  }))
}

test('a head\'s labels and their values\' words stand on one line, a value that begins with a glyph too', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  expect(await wordsApart(page, 'work-facts')).toEqual([])
  await page.goto(`/#/free/sources/${FINANCE}/page/119`)
  await settled(page)
  expect(await wordsApart(page, 'page-facts')).toEqual([])
  // and the check sees them apart where they are: the lines set by their baselines again, a moment
  await page.addStyleTag({ content: '.labelled-lines > .labelled-line { align-items: baseline !important; }' })
  expect((await wordsApart(page, 'page-facts')).length).toBeGreaterThan(0)
})

test('a work lists its pages and narrows them by state', async ({ page, request }) => {
  const listed = await (await request.get(`/api/free/works/${KELLY}/pages`)).json() as { pages: { check: { state: string } }[] }
  await page.goto(`/#/free/sources/${KELLY}`)
  await settled(page)
  await asTable(page)
  await expect(page.locator('tr[data-page]')).toHaveCount(listed.pages.length)
  await page.locator('[data-facet="state"] [data-value="blocked"]').click()
  await expect(page.locator('tr[data-page]')).toHaveCount(listed.pages.filter(row => row.check.state === 'blocked').length)
  await page.screenshot({ path: `${SHOTS}/work_pages.png` })
})

test('a work folds its routes to one line of levels, opens them to a row each, and a route chosen keeps its pages', async ({ page, request }) => {
  type Route = { route: string, level: string | null, pages: number }
  type Listed = { routes: Route[], route_levels: { level: string, pages: number }[], pages: { route: string }[] }
  // a work that has a fallback route today, as a person's walk moves pages off it: chosen when the check runs
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, route_level: string | null }[] }).rows
  const work = issues.find(row => row.route_level === 'fallback')?.source_id ?? FINANCE
  const listed = await (await request.get(`/api/free/works/${work}/pages`)).json() as Listed
  await page.goto(`/#/free/sources/${work}`)
  await settled(page)
  await asTable(page)
  // folded (159.a): one line, each level serving a page with the API's count, the fallback always named
  const named = listed.route_levels.filter(level => level.pages > 0 || level.level === 'fallback')
  await expect(page.locator('.routes-line .level-count')).toHaveText(named.map(level => `${level.pages.toLocaleString('en')} ${level.level}`))
  await expect(page.locator('#routes-table')).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/work_head.png` })
  await page.locator('[data-part="routes-toggle"]').click()
  const rows = page.locator('.route-table tbody tr')
  await expect(rows).toHaveCount(listed.routes.length)
  await expect(rows.first()).toHaveAttribute('data-level', 'checked')
  const fallback = listed.routes.find(route => route.level === 'fallback')
  test.skip(!fallback, 'the work has no fallback route')
  const row = page.locator(`.route-table tr[data-level="fallback"][data-route="${fallback!.route}"]`)
  await expect(row.locator('[data-icon="route-fallback"]')).toBeVisible()
  await row.click()
  await expect(page.locator('tr[data-page]')).toHaveCount(fallback!.pages)
  await page.screenshot({ path: `${SHOTS}/work_routes.png` })
})

// 179: one way to ask what something means, the registry's hint, closable; and data under the pointer in a card that the
// window holds, never a browser tooltip
test('a hint opens from its mark with its lead and closes, and a card shows a route\'s data within the window', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  await page.locator('[data-part="routes-hint-button"]').click()
  const panel = page.locator('[data-hint="routes"]')
  await expect(panel.locator('.hint-lead')).toContainText('How each page\'s text is served')
  await expect(panel.locator('[data-part="routes-legend"] dt')).not.toHaveCount(0)
  await panel.locator('[data-part="routes-hint-close"]').click()
  await expect(panel).toHaveCount(0)
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  await page.locator('[data-label="Route"] .route').hover()
  const card = page.locator('[data-part="hover-card"]')
  await expect(card.locator('.card-title')).toHaveText('Route')
  await expect(card.locator('[data-row="level"] .card-value')).toHaveText('noted')
  const box = (await card.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.locator('[data-label="Route"] [title]').count()).toBe(0)
})

// 225.a (the operator, 12 Nov): a chapter's count of pages to look at, or of pages a person decided, is a way to them: a click opens
// the sections holding them and marks them, the first in view; a chapter whose counts are all fine has no such control.
// Accounting's chapter 6: p. 398 (decided since the operator's verdict) under "Multiple Choice", p. 360 (blocked) under 6.2
test('a chapter\'s count opens the sections that hold its pages and marks them, and a fine count stays a figure', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Unit = { id: string, title: string, level: number, state_pages: { value: string, pages: number[] }[] }
  const work = await (await request.get(`/api/free/works/${ACCOUNTING}/pages`)).json() as { outline: Unit[] }
  const chapter = work.outline.find(unit => unit.level === 1 && unit.title.startsWith('Chapter 6'))!
  test.skip(!chapter.state_pages.length, 'chapter 6 has no count to open today')
  const fine = work.outline.find(unit => unit.level === 1 && unit.state_pages.length === 0)!
  await page.goto(`/#/free/sources/${ACCOUNTING}`)
  await settled(page)
  await expect(page.locator(`[data-unit="${fine.id}"] > summary [data-show-state]`)).toHaveCount(0)
  const head = page.locator(`[data-unit="${chapter.id}"] > summary`)
  await expect(head.locator('[data-show-state]')).toHaveCount(chapter.state_pages.length)
  for (const { value, pages } of chapter.state_pages) {
    await head.locator(`[data-show-state="${value}"]`).click()
    const marked = page.locator('tr.marked')
    // every page behind the count marked, in the sections that hold it, the first in view; the chapter stays open
    expect((await marked.evaluateAll(rows => rows.map(row => Number(row.getAttribute('data-page'))))).sort((a, b) => a - b))
      .toEqual(expect.arrayContaining(pages))
    await expect(marked.first()).toBeInViewport()
    // the chapters' box is not scrolled sideways: the titles keep their start
    expect(await page.locator('.outline-scroll').evaluate(box => box.scrollLeft)).toBe(0)
    await expect(page.locator(`[data-unit="${chapter.id}"]`)).toHaveAttribute('open', '')
    for (const pdfPage of pages) {
      const holder = page.locator(`[data-unit]:has(> .fold-body tr.marked[data-page="${pdfPage}"])`).last()
      await expect(holder).toHaveAttribute('open', '')
    }
  }
  await page.locator(`[data-unit="${chapter.id}"]`).screenshot({ path: `${SHOTS}/chapter_count_opens.png` })
})

test('a work with an order of its own stands its pages under its chapters, folded, the table one click away', async ({ page, request }) => {
  // The free export carries no outline yet (84.a follows 83.a's judge batches): an invented one over Kelly's real pages
  // shows the view in a real browser until it does. The figures are counted here, as the API counts them.
  type Row = { pdf_page: number, check: { state: string }, units: string[] | null }
  const real = await (await request.get(`/api/free/works/${KELLY}/pages`)).json() as { pages: Row[] }
  const order: [string, string, string | null, number, number][] = [
    ['u001', '1 Introduction', null, 2, 3],
    ['u002', '2 The Kelly criterion', null, 4, 8],
    ['u003', '2.1 One asset', 'u002', 5, 8],
    ['u004', '3 Results', null, 9, 13],
    ['u005', 'References', null, 14, 15],
  ]
  // a page lies in the innermost unit whose pages hold it; page 1, the title page, in none
  const unitsOf = (pdfPage: number) => order.filter(([, , , first, last]) => first <= pdfPage && pdfPage <= last).slice(-1)
    .map(([id]) => id)
  const pages = real.pages.map(row => ({ ...row, units: unitsOf(row.pdf_page) }))
  const inside = (id: string) => pages.filter(row => row.units.some(unit => unit === id || order.find(entry => entry[0] === unit)?.[2] === id))
  const counted = (rows: Row[]) => [...new Set(rows.map(row => row.check.state))]
    .map(value => ({ value, count: rows.filter(row => row.check.state === value).length }))
  // a unit's own pages: those whose text lies in it and in no unit beneath it, as the API counts them (161.a)
  const outline = order.map(([id, title, parent, first, last]) => ({
    id, level: parent ? 2 : 1, title, parent, first_page: first, last_page: last, indexed: id !== 'u005',
    pages: inside(id).length, own_pages: pages.filter(row => row.units.includes(id)).length, states: counted(inside(id)),
  }))
  const outside = pages.filter(row => row.units.length === 0)
  await page.route(`**/api/free/works/${KELLY}/pages`, route => route.fulfill({
    json: { ...real, pages, outline, outside_outline: { pages: outside.length, states: counted(outside), routes: [] } },
  }))

  await page.goto(`/#/free/sources/${KELLY}`)
  await settled(page)
  await expect(page.locator('.outline > details')).toHaveCount(5)
  await expect(page.locator('.outline details[open]')).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/work_chapters.png` })

  // a chapter opens to its own pages and its sections
  await page.locator('[data-unit="u002"] > summary').click()
  await expect(page.locator('[data-unit="u002"] > .fold-body > .unit-body > [data-part="own-pages"] table [data-page="4"]')).toBeVisible()
  await page.locator('[data-unit="u003"] > summary').click()
  await expect(page.locator('[data-unit="u003"] [data-page="7"]')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/work_chapters_open.png` })

  // with a filter, only the chapters holding a matching page stand, opened down to the page (the operator's 6.a)
  await page.locator('[data-facet="state"] [data-value="blocked"]').click()
  const blocked = pages.filter(row => row.check.state === 'blocked')
  await expect(page.locator('tr[data-page]')).toHaveCount(blocked.length)
  for (const row of blocked) await expect(page.locator(`tr[data-page="${row.pdf_page}"]`)).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/work_chapters_filtered.png` })

  // the flat table, one click away, and remembered across a reload
  await page.locator('.view-switch button', { hasText: 'table' }).click()
  await expect(page.locator('.outline')).toHaveCount(0)
  await page.reload()
  await settled(page)
  await expect(page.locator('.outline')).toHaveCount(0)
  await expect(page.locator('tr[data-page]')).toHaveCount(pages.length)
})

// 159.a: the chapters are a table, and every page table of the work stands in one column grid, whatever its depth
test('a work\'s chapters are one table, and every page table in them stands in the same columns at any depth', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  // every heading keeps to its own column: a state's word never runs into the next (the operator, 11 Nov: "decided by a person" ran
  // into "Note")
  const overrunning = () => page.locator('[data-part="chapter-head"] > span').evaluateAll(cells => cells
    .map(cell => ({ right: (cell.firstElementChild ?? cell).getBoundingClientRect().right, edge: cell.getBoundingClientRect().right }))
    .filter(head => Math.round(head.right) > Math.round(head.edge)).length)
  expect(await overrunning()).toBe(0)
  // a chapter's own pages and a section's: two depths of blocks (161.a)
  const tops = page.locator('.outline > details[data-unit]:not([data-unit="outside"])')
  for (const at of [1, 2, 3]) {
    const top = tops.nth(at)
    await top.locator('> summary').click()
    const child = top.locator('> .fold-body > .unit-body > details[data-unit]').first()
    if (await child.count()) await child.locator('> summary').click()
  }
  const blocks = await page.locator('[data-part="own-pages"]').evaluateAll(found => found
    .filter(block => block.getClientRects().length > 0)
    .map(block => ({
      left: block.getBoundingClientRect().left,
      title: block.closest('details')!.querySelector(':scope > summary .unit-title')!.getBoundingClientRect().left,
      depth: block.closest('details')!.querySelectorAll(':scope').length,
    })))
  expect(blocks.length).toBeGreaterThan(1)
  // each block stands one step deeper than its unit's title, at any depth
  for (const block of blocks) expect(block.left).toBeGreaterThan(block.title)
  expect(new Set(blocks.map(block => Math.round(block.left))).size, 'blocks at two depths').toBeGreaterThan(1)
  // the first column gives up the indent; every other column's head at one x in every page table on show
  const columnX = (column: number) => page.locator('table.pages').evaluateAll((tables, n) => tables
    .filter(table => table.getClientRects().length > 0)
    .map(table => Math.round(table.querySelector(`thead th:nth-child(${n})`)!.getBoundingClientRect().x)), column)
  for (const column of [2, 3, 4, 5, 6, 7, 8]) {
    const xs = await columnX(column)
    expect(xs.length, `tables on show for column ${column}`).toBeGreaterThan(1)
    expect(Math.max(...xs) - Math.min(...xs), `column ${column}`).toBeLessThanOrEqual(1)
  }
  // and the chapters' figures stand under their heads: a row's pages under "Pages"
  const headX = await page.locator('[data-part="chapter-head"] > span:nth-child(3)').evaluate(cell => Math.round(cell.getBoundingClientRect().right))
  const rowX = await tops.first().locator('> summary .unit-pages').evaluate(cell => Math.round(cell.getBoundingClientRect().right))
  expect(Math.abs(headX - rowX)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: `${SHOTS}/work_chapters_grid.png` })
  // and the heading check sees a word run over where one does: every state's column at the old fixed 7rem, a moment
  const states = await page.locator('[data-part="chapter-head"] .state-mark').count()
  const longest = Math.max(...(await page.locator('[data-part="chapter-head"] .state-word').allInnerTexts()).map(word => word.length))
  test.skip(longest < 14, 'no state word of this work is longer than its old column')
  await page.locator('.outline').evaluate((outline, count) => (outline as HTMLElement).style.setProperty('--chapter-columns',
    `minmax(12rem, 1fr) 7rem 4rem repeat(${count}, 7rem) minmax(18rem, 21rem)`), states)
  expect(await overrunning()).toBeGreaterThan(0)
})

// 159.a, the operator's worry: "a worry that things get lost, also in smaller views". At a wide and a phone's width,
// every field the API serves for a page stands in its row, reachable in the table's own scroller, and the page itself
// never scrolls sideways
test('nothing a page row carries is lost at 1280 or at 390 px, and the page never scrolls sideways', async ({ page, request }) => {
  type Row = { pdf_page: number, printed_label: string | null, cost_usd: number | null, attempt: number, error_message: string | null,
    route_level: string | null, route_why: string | null, check: { reasons: { value: string }[] } }
  const { pages } = await (await request.get(`/api/free/works/${FINANCE}/pages`)).json() as { pages: Row[] }
  const sample = [...pages.slice(0, 5), ...pages.filter(row => row.route_level !== 'checked' || row.attempt > 0 || row.check.reasons.length)]
    .slice(0, 25)
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const view of ['table', 'chapters']) {
      await page.goto(`/#/free/sources/${FINANCE}`)
      await settled(page)
      await page.locator('.view-switch button', { hasText: view }).click()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
        `${view} at ${width} px scrolls sideways`).toBe(true)
    }
    await asTable(page)
    for (const row of sample) {
      const line = page.locator(`tr[data-page="${row.pdf_page}"]`)
      const text = await line.textContent()
      const expected = [`p. ${row.pdf_page}`, row.printed_label, row.cost_usd === null ? NOT_MEASURABLE : usd(row.cost_usd),
        row.attempt > 0 ? String(row.attempt) : null,
        row.error_message ?? (row.route_level && row.route_level !== 'checked' ? row.route_why : null),
        ...row.check.reasons.map(reason => reason.value)]
      for (const field of expected.filter(Boolean)) expect(text, `p. ${row.pdf_page} at ${width} px`).toContain(field)
      await expect(line).toBeVisible()
    }
  }
  await page.screenshot({ path: `${SHOTS}/work_narrow.png` })
})

test('a page shows the image the reader received beside its reading, tables included', async ({ page }) => {
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  const image = page.locator('.original img')
  await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBe(1680)
  await expect(page.locator('.image-mark.same')).toBeVisible()
  await expect(page.locator('table.cells').first()).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/page_table.png` })
})

// Every visible text in the one size (the operator, 11 Nov: "I prefer everything uniform"; three before, 159.a): an element
// holding text of its own, or a form control, which does not inherit a font by itself. A formula's parts keep their own
// scale, KaTeX's and a sub- or superscript's. The size is read from the token, so the check holds the rule, not a number.
async function sizesOffScale(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const probe = document.createElement('span')
    probe.style.fontSize = 'var(--font-size)'
    document.body.append(probe)
    const size = getComputedStyle(probe).fontSize
    probe.remove()
    const found = new Set<string>()
    for (const element of document.querySelectorAll<HTMLElement>('body *')) {
      if (element.closest('.katex, svg, script, style, sub, sup')) continue
      const control = ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(element.tagName)
      const own = [...element.childNodes].some(node => node.nodeType === Node.TEXT_NODE && node.textContent!.trim())
      if (!(own || control) || element.getClientRects().length === 0) continue
      const here = getComputedStyle(element).fontSize
      if (here !== size) found.add(`${here} ${element.tagName.toLowerCase()}.${[...element.classList].join('.')}`)
    }
    return [...found]
  })
}

test('every view sets its text in the one size, its details and menus opened', async ({ page, request }) => {
  test.setTimeout(180_000)
  const WIKIPEDIA = 'wikipedia_trading_set'
  const runs = (await (await request.get('/api/runs')).json() as { runs: { knowledge_base: string, run_id: number }[] }).runs
  const views = ['/#/overview', '/#/sources', '/#/shelf', `/#/free/sources/${FINANCE}`, `/#/free/sources/${FINANCE}/page/5`,
    '/#/free/sources/openstax_principles_of_accounting_v1/page/305', '/#/pages?knowledge_base=free&state=blocked', '/#/issues',
    '/#/errors', '/#/runs', '/#/prompts?version=judge%2F2', '/#/calls', '/#/search', '/#/chat', `/#/free/html/${WIKIPEDIA}`,
    `/#/free/html/${WIKIPEDIA}/s1`, ...runs.slice(-1).map(run => `/#/${run.knowledge_base}/runs/${run.run_id}`)]
  const off: string[] = []
  for (const view of views) {
    await page.goto(view)
    await settled(page, OVERVIEW_LOADS)
    // what a click unfolds counts too: a page's details and history, the lab, the menu
    await openEveryFold(page)
    await page.getByRole('button', { name: 'Menu' }).click()
    off.push(...(await sizesOffScale(page)).map(found => `${view}: ${found}`))
  }
  expect(off).toEqual([])
  // a view's title is told by its weight, at the one size
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  expect(await page.locator('h1.view-title').evaluate(element => Number(getComputedStyle(element).fontWeight))).toBeGreaterThanOrEqual(700)
  // and the check sees another size where there is one, a title's and a form control's alike
  const tag = await page.addStyleTag({ content: '.view-title { font-size: 19px !important; } .page-jump input { font-size: 13.33px !important; }' })
  const found = await sizesOffScale(page)
  expect(found).toContain('19px h1.view-title')
  expect(found.some(one => one.startsWith('13.33px input'))).toBe(true)
  await tag.evaluate(element => (element as Element).remove())
})

// The operator, 10 Nov: "every time stated in the project must get a human date format". The API keeps ISO 8601; a view says a
// time as a person does ("2 h ago", "yesterday, 09:21", "9 Nov, 09:21"), its full form in the reader's zone on hover
const MACHINE_TIME = /\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?/g

async function machineTimesShown(page: Page): Promise<string[]> {
  return page.evaluate(pattern => [...document.body.innerText.matchAll(new RegExp(pattern, 'g'))].map(found => found[0]),
    MACHINE_TIME.source)
}

test('no view shows a machine\'s timestamp as text, and every time it says has its full form on hover', async ({ page, request }) => {
  test.setTimeout(180_000)
  const runs = (await (await request.get('/api/runs')).json() as { runs: { knowledge_base: string, run_id: number }[] }).runs
  // the oldest run chose readings, the newest a judge's run: both kinds of run page
  const views = ['/#/overview', '/#/sources', '/#/shelf', '/#/runs', '/#/calls', '/#/prompts?version=judge%2F2', '/#/issues',
    '/#/errors', '/#/pages?knowledge_base=free&state=issue', '/#/search', '/#/chat', `/#/free/sources/${FINANCE}`,
    `/#/free/sources/${KELLY}/page/7`, `/#/free/sources/${FINANCE}/page/5`, '/#/free/html/wikipedia_trading_set',
    '/#/free/html/wikipedia_trading_set/s1', ...[runs.at(-1), runs[0]].filter(Boolean)
      .map(run => `/#/${run!.knowledge_base}/runs/${run!.run_id}`)]
  const shown: string[] = []
  let said = 0
  for (const view of views) {
    await page.goto(view)
    await settled(page, OVERVIEW_LOADS)
    // the first 60 folds of a view, each kind of fold among them: every time is said by one component, and the calls' log
    // grows with every session (12 Nov: over 300 folds, 24 s to open them all, the walk past its 180 s)
    await openEveryFold(page, 60)
    shown.push(...(await machineTimesShown(page)).map(found => `${view}: ${found}`))
    const times = page.locator('time.human-time')
    said += await times.count()
    for (const time of await times.all()) {
      expect(await time.getAttribute('title'), `${view}: a time without its full form`).toMatch(/\d{2}:\d{2}:\d{2}|\d{4}$/)
    }
  }
  expect(shown).toEqual([])
  // the views said times at all, so the check above looked at some
  expect(said).toBeGreaterThan(0)
  // and the check sees a machine's timestamp where one stands
  await page.evaluate(() => document.querySelector('main')!.append('stored 2026-11-09T09:21:52+00:00'))
  expect(await machineTimesShown(page)).toEqual(['2026-11-09T09:21:52+00:00'])
})

// decision 160 (the operator on a 2,340 px window: "so that not everything floats so far apart"): every view in one centred
// container of at most 1,440 px, a view of two panes in one of at most 1,920 px, the header's row lined up with it
test('a wide screen holds every view to one centred column, and a view of two panes to a wider one', async ({ page }) => {
  await page.setViewportSize({ width: 2400, height: 1000 })
  const placed = (selector: string) => page.locator(selector).evaluate(element => {
    const box = element.getBoundingClientRect()
    return { left: box.left, width: box.width, right: document.documentElement.clientWidth - box.right }
  })
  await page.goto(`/#/free/sources/${FINANCE}`)
  await settled(page)
  const main = await placed('main.frame-main')
  expect(main.width).toBeLessThanOrEqual(1440)
  expect(Math.abs(main.left - main.right)).toBeLessThanOrEqual(1)
  expect(Math.abs((await placed('.frame-row')).left - main.left)).toBeLessThanOrEqual(1)
  // a short note stays on one line while there is room: the chapters' first row says why its pages stand outside them
  const note = page.locator('[data-unit="outside"] > summary .note')
  const [height, lineHeight] = await note.evaluate(cell => [cell.getBoundingClientRect().height, parseFloat(getComputedStyle(cell).lineHeight)])
  expect(height).toBeLessThan(lineHeight * 1.5)
  // and a chapter's title, which matters more than a note, keeps one line where it can: the longest under 50 characters
  const titles = await page.locator('.outline > details > summary .unit-title').evaluateAll(cells => cells
    .filter(cell => (cell.textContent ?? '').length < 50)
    .map(cell => cell.getBoundingClientRect().height / parseFloat(getComputedStyle(cell).lineHeight)))
  expect(Math.max(...titles)).toBeLessThan(1.5)
  await page.screenshot({ path: `${SHOTS}/wide_work.png` })
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  const pane = await placed('main.frame-main')
  expect(pane.width).toBeGreaterThan(1440)
  expect(pane.width).toBeLessThanOrEqual(1920)
  expect(Math.abs(pane.left - pane.right)).toBeLessThanOrEqual(1)
  // decision 183: the record zone of a view with an analysis in the standard width and centred, the header's row lined up
  // with it; the analysis alone wide
  for (const [view, root] of [[`/#/free/sources/${FINANCE}/page/5`, '.page-view'], ['/#/free/html/wikipedia_trading_set/s1', '.html-article']]) {
    await page.goto(view)
    await settled(page)
    // measured once the view's own analysis stands, never the view it replaced
    await expect(page.locator(`${root} [data-zone="analysis"]`)).toBeVisible()
    const record = await placed(`${root} [data-zone="record"]`)
    expect(record.width, view).toBeLessThanOrEqual(1440)
    expect(Math.abs(record.left - record.right), `${view} ${JSON.stringify(record)}`).toBeLessThanOrEqual(1)
    expect(Math.abs((await placed('.frame-row')).left - record.left), view).toBeLessThanOrEqual(1)
    const analysis = await placed(`${root} [data-zone="analysis"]`)
    expect(analysis.width, view).toBeGreaterThan(1440)
    expect(analysis.width, view).toBeLessThanOrEqual(1920)
  }
  await page.screenshot({ path: `${SHOTS}/wide_page.png` })
})

// decision 183: on a phone the two panes stack, the image above the reading; the Reading History opens folded and stays as
// the reader leaves it; and the knowledge base's badge stands centred on its line (179)
test('a page stacks its panes on a phone, opens its history folded and keeps it opened, and centres its badge', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  const history = page.locator('details.history')
  await expect(history).not.toHaveAttribute('open')
  await history.locator('> summary').click()
  // the fold's toggle is said after the click returns: the reload waits until the choice is kept
  await expect.poll(() => page.evaluate(() => localStorage.getItem('settings.v1') ?? '')).toContain('"page.history":true')
  await page.reload()
  await settled(page)
  await expect(page.locator('details.history')).toHaveAttribute('open', '')
  // the badge's middle on the trail's text middle
  const middle = (selector: string) => page.locator(selector).first().evaluate(element => {
    const box = element.getBoundingClientRect()
    return box.top + box.height / 2
  })
  expect(Math.abs(await middle('.trail .kb-mark') - await middle('.trail a'))).toBeLessThanOrEqual(2)
  await page.setViewportSize({ width: 390, height: 900 })
  const image = (await page.locator('[data-zone="analysis"] figure.original').boundingBox())!
  const reading = (await page.locator('[data-zone="analysis"] .reading').boundingBox())!
  expect(reading.y).toBeGreaterThanOrEqual(image.y + image.height - 1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)
})

// 179 (the operator: "Lab has no indentation ... the same style and indentation concept"): every fold is the one FoldSection, its
// content exactly one indent step right of its title at every depth, and the folds of one depth at one x
async function foldsOffStep(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const probe = document.createElement('div')
    probe.style.width = 'var(--indent-step)'
    document.body.append(probe)
    const step = probe.getBoundingClientRect().width
    probe.remove()
    const off: string[] = []
    const rows = new Map<Element | null, number[]>()
    for (const fold of document.querySelectorAll<HTMLDetailsElement>('details.fold[open]:not(.flat):not(.mark-in-title)')) {
      const title = fold.querySelector(':scope > summary .fold-title')!.getBoundingClientRect().left
      const body = fold.querySelector<HTMLElement>(':scope > .fold-body')!
      const start = body.getBoundingClientRect().left + parseFloat(getComputedStyle(body).paddingLeft)
      const name = fold.className
      if (Math.abs(start - title - step) > 1) off.push(`${name}: content at ${Math.round(start - title)} px from its title, not ${step}`)
      // folds that are siblings in one container stand at one x
      const at = fold.getBoundingClientRect().left
      rows.set(fold.parentElement, [...rows.get(fold.parentElement) ?? [], at])
    }
    for (const [parent, xs] of rows) {
      if (Math.max(...xs) - Math.min(...xs) > 1) off.push(`folds in ${parent?.className ?? 'a container'} at x ${xs.map(Math.round).join(', ')}`)
    }
    return off
  })
}

test('every fold sets its content one indent step right of its title, and folds side by side stand at one x', async ({ page }) => {
  test.setTimeout(180_000)
  const views = [`/#/free/sources/${FINANCE}/page/5`, '/#/calls', '/#/errors', '/#/overview', '/#/shelf',
    '/#/free/html/wikipedia_trading_set/s1']
  const off: string[] = []
  let looked = 0
  for (const view of views) {
    await page.goto(view)
    await settled(page, OVERVIEW_LOADS)
    await openEveryFold(page)
    looked += await page.locator('details.fold[open]:not(.flat):not(.mark-in-title)').count()
    off.push(...(await foldsOffStep(page)).map(found => `${view}: ${found}`))
  }
  expect(off).toEqual([])
  expect(looked).toBeGreaterThan(5)
  // and the check sees a fold whose content stands at its title, as the Lab's once did
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  await page.locator('details.lab').evaluate(element => { (element as HTMLDetailsElement).open = true })
  await page.addStyleTag({ content: 'details.lab > .fold-body { padding-left: 0 !important; }' })
  expect((await foldsOffStep(page)).join(' ')).toContain('lab')
})

// 159.a: at a phone's width no view scrolls sideways; a table or a grid wider than the window scrolls in its own box
test('no view scrolls sideways at 390 px, its tables scrolling in their own boxes', async ({ page, request }) => {
  test.setTimeout(180_000)
  const runs = (await (await request.get('/api/runs')).json() as { runs: { knowledge_base: string, run_id: number }[] }).runs
  const views = ['/#/overview', '/#/sources', '/#/shelf', `/#/free/sources/${FINANCE}`, `/#/free/sources/${FINANCE}/page/5`,
    '/#/pages?knowledge_base=free&state=issue', '/#/issues', '/#/errors', '/#/runs', '/#/prompts?version=judge%2F2', '/#/calls',
    '/#/search', '/#/chat', '/#/free/html/wikipedia_trading_set', '/#/free/html/wikipedia_trading_set/s1',
    ...runs.slice(-1).map(run => `/#/${run.knowledge_base}/runs/${run.run_id}`)]
  const sideways = () => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  await page.setViewportSize({ width: 390, height: 900 })
  const wide: string[] = []
  for (const view of views) {
    await page.goto(view)
    await settled(page, OVERVIEW_LOADS)
    if (await sideways()) wide.push(view)
  }
  expect(wide).toEqual([])
  // and the check sees a page that does scroll sideways
  await page.evaluate(() => document.querySelector('main')!.append(Object.assign(document.createElement('div'), { style: 'width: 2000px; height: 1px' })))
  expect(await sideways()).toBe(true)
})

type Box = { x: number, y: number, width: number, height: number }

// a control clicked again and again stays under the pointer: its box within a pixel of where it stood (the operator, 10 Nov)
function inPlace(box: Box | null, at: Box | null, what: string): void {
  expect(box, what).not.toBeNull()
  for (const side of ['x', 'y', 'width', 'height'] as const) {
    expect(Math.abs(box![side] - at![side]), `${what}: ${side}`).toBeLessThanOrEqual(1)
  }
}

// The operator, 10 Nov: "page forward and back jumps when clicked ... something like that must always be tested": next three times and back
// again, across neighbours whose titles and numbers differ in length, the boxes never move
test('previous and next stay under the pointer, article after article and page after page', async ({ page, request }) => {
  const WIKIPEDIA = 'wikipedia_trading_set'
  const work = await (await request.get(`/api/free/html/${WIKIPEDIA}`)).json() as {
    why_not: string | null, outline: { title: string, parent: string | null, label: string | null, first: string | null }[]
  }
  const pageTurns = async (titles: (string | RegExp)[], start: string): Promise<void> => {
    await page.goto(start)
    await settled(page)
    await expect(page.locator('.view-title')).toHaveText(titles[0])
    for (const [side, order] of [['next', titles.slice(1)], ['previous', titles.slice(0, -1).reverse()]] as const) {
      const control = page.locator(`[data-part="${side}"]`)
      const at = await control.boundingBox()
      for (const title of order) {
        await control.click()
        await expect(page.locator('.view-title')).toHaveText(title)
        inPlace(await control.boundingBox(), at, `${side} before ${title}`)
      }
    }
  }
  // the HTML view: four articles in a row, their titles of different lengths
  const tops = work.outline.filter(node => node.parent === null && (node.label ?? node.first))
  if (!work.why_not && tops.length >= 4) {
    const four = tops.slice(1, 5)
    expect(new Set(four.map(node => node.title.length)).size).toBeGreaterThan(1)
    await pageTurns(four.map(node => node.title), `/#/free/html/${WIKIPEDIA}/${four[0].label ?? four[0].first}`)
  }
  // the PDF page view: four pages in a row, from a one-digit page to a two-digit one where the work has them
  const numbers = [7]
  while (numbers.length < 4) {
    const detail = await (await request.get(`/api/free/works/${KELLY}/pages/${numbers.at(-1)}`)).json() as { next_page: number | null }
    if (detail.next_page === null) break
    numbers.push(detail.next_page)
  }
  test.skip(numbers.length < 4, 'the work has no four pages in a row')
  await pageTurns(numbers.map(number => new RegExp(`^\\s*PDF page ${number}(\\s|$)`)), `/#/free/sources/${KELLY}/page/${numbers[0]}`)
  await page.screenshot({ path: `${SHOTS}/pager.png` })
})

// The operator on accounting p. 305 (10 Nov): the description has no box and frames the figure it describes, dashed; the figure's
// eleven T-accounts stand as eleven boxes, as the reader grouped them
test('a description frames the figure it describes, and a grouped figure shows each container in its own box', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Block = { id: string, block_class: string, text: string | null, attrs: Record<string, string>, bbox: number[] | null }
  const detail = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/305`)).json() as { reading: { blocks: Block[] } | null }
  const blocks = detail.reading?.blocks ?? []
  const description = blocks.find(block => block.block_class === 'description' && !block.bbox && block.attrs.of)
  const grouped = blocks.find(block => block.attrs.grouped === '1' && block.text)
  test.skip(!description || !grouped, 'the export no longer holds this page as read on 10 Nov')
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/305`)
  await settled(page)
  await page.locator(`[data-block="${description!.id}"]`).hover()
  const box = page.locator('.block-box.described')
  await expect(box).toBeVisible()
  await expect(box.locator('.block-box-label')).toHaveText(`${description!.id} describes ${description!.attrs.of}`)
  const containers = grouped!.text!.split(/\n[ \t]*\n/).filter(group => group.trim()).length
  await expect(page.locator(`[data-block="${grouped!.id}"] .text-group`)).toHaveCount(containers)
  await expect(page.locator(`[data-block="${grouped!.id}"] .block-attrs`)).toContainText('grouped=1')
  await page.screenshot({ path: `${SHOTS}/page_grouped_figure.png` })
})

test('the frame takes its name from the app config, names the page on show, and holds every view in a grouped menu', async ({ page, request }) => {
  const app = await (await request.get('/api/app')).json() as { title: string, subtitle: string | null }
  const detail = await (await request.get(`/api/free/works/${KELLY}/pages/7`)).json() as { title: string }
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  await expect(page.locator('.frame-title')).toContainText(app.title)
  await expect(page.locator('.frame-view')).toHaveText(`${detail.title} p. 7`)
  await expect(page).toHaveTitle(`${app.title} · ${detail.title} p. 7`)
  const button = page.getByRole('button', { name: 'Menu' })
  await button.click()
  await expect(page.locator('#frame-menu [data-group]')).toHaveCount(4)
  await page.screenshot({ path: `${SHOTS}/frame_menu.png` })
  await page.keyboard.press('Escape')
  await expect(page.locator('#frame-menu')).toHaveCount(0)
  await button.click()
  await page.locator('#frame-menu').getByRole('link', { name: 'Errors' }).click()
  await expect(page).toHaveURL(/#\/errors$/)
  await expect(page.locator('#frame-menu')).toHaveCount(0)
  await expect(page).toHaveTitle(`${app.title} · Errors`)
})

// 181.a (the operator on finance p. 5: "you see what the old judge looked like, applied to the page"): any judgement is shown on the
// page as it judged, the view marked as not the standing one (the annotation role, dashed, its glyph and words), and back
test('a judgement from the Lab is shown on the page as it judged, marked as recalled, and the standing view comes back', async ({ page, request }) => {
  type Judgement = { version: string | null, again: number, recall: string, findings: { block: string | null, void: boolean }[] }
  const detail = await (await request.get(`/api/free/works/${FINANCE}/pages/5`)).json() as { attempts: { shown: boolean, judgements: Judgement[] }[] }
  const judgements = detail.attempts.find(attempt => attempt.shown)!.judgements
  const judge3 = judgements.find(one => one.version === 'judge/3' && !one.again)!
  const judge2 = judgements.find(one => one.version === 'judge/2' && !one.again)!
  expect(judge3.findings).toHaveLength(0)
  expect(judge2.findings.find(one => one.block === 'b12')?.void).toBe(true)
  const recalled = async (on: boolean) => {
    await expect(page.locator('[data-part="recall-chip"]')).toHaveCount(on ? 1 : 0)
    await expect(page.locator('[data-part="analysis"][data-overlay="yes"]')).toHaveCount(on ? 1 : 0)
    if (on) {
      const frame = await page.locator('[data-part="analysis"]').evaluate(element => getComputedStyle(element).outlineStyle)
      expect(frame).toBe('dashed')
    }
  }
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  await recalled(false)
  await page.locator('.lab > summary').click()
  // judge/3, a prototype that found nothing: no finding stands on any block
  await page.locator('.lab tr.judgement:has(.judge-version:text-is("judge/3")) [data-part="recall"]').first().click()
  // the address names it, so it can be sent: the router keeps its colons and its slash as they are
  await expect.poll(() => decodeURIComponent(page.url())).toContain(`judgement=${judge3.recall}`)
  await settled(page)
  await recalled(true)
  await expect(page.locator('[data-part="recall-chip"]')).toContainText('Recalled: judge/3 (prototype) on reading')
  await expect(page.locator('.lab tr.recalled-source')).toHaveCount(1)
  await expect(page.locator('[data-part="analysis"] .block-findings [data-finding]')).toHaveCount(0)
  // judge/2: its void finding on b12, in the three voices, the code's ruling among them
  await page.locator('.lab tr.judgement:has(.judge-version:text-is("judge/2")) [data-part="recall"]').first().click()
  await settled(page)
  await recalled(true)
  await expect(page.locator('[data-part="analysis"] [data-block="b12"] [data-voice="code"]')).toHaveCount(1)
  await page.locator('[data-part="analysis"] [data-block="b12"]').hover()
  await expect(page.locator('.block-box.recalled')).toHaveCount(1)
  await page.screenshot({ path: `${SHOTS}/page_recalled.png` })
  // and back: the standing view, unmarked
  await page.locator('[data-part="show-standing"]').click()
  await settled(page)
  await recalled(false)
  await expect(page).not.toHaveURL(/judgement=/)
})

// 181.a (the operator on finance p. 5): the analysis, the original beside its reading, stands under a heading and a rule of its own,
// below the history, the Lab and the details, so it no longer runs on from them
test('a page sets its analysis apart under a heading and a rule, below everything that is said of the page', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  const analysis = page.locator('[data-part="analysis"]')
  await expect(analysis.locator('h2.analysis-title')).toContainText('Analysis')
  // told by its form (179): a rule through the middle of its heading
  expect(await analysis.locator('h2.analysis-title').evaluate(element => getComputedStyle(element, '::after').borderTopStyle)).toBe('solid')
  // the image and the reading stand inside it, and everything said of the page above it
  await expect(analysis.locator('figure.original')).toHaveCount(1)
  await expect(analysis.locator('.reading')).toHaveCount(1)
  const top = (await analysis.boundingBox())!.y
  for (const above of ['.history', 'details.details']) {
    const box = await page.locator(above).first().boundingBox()
    if (box) expect(box.y + box.height).toBeLessThanOrEqual(top + 1)
  }
})

test('a page opens on one line of what matters, its details folded until asked for and then remembered', async ({ page }) => {
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  // the line is seen without scrolling, and so is the start of the original and its reading
  await expect(page.locator('.summary')).toBeInViewport()
  await expect(page.locator('.summary .image-mark.same')).toBeVisible()
  await expect(page.locator('.side-by-side')).toBeInViewport()
  const details = page.locator('details.details')
  await expect(details).not.toHaveAttribute('open')
  await page.screenshot({ path: `${SHOTS}/page_summary.png` })

  await details.locator('summary').click()
  await expect(details).toHaveAttribute('open')
  // the browser sets `open` at once but fires `toggle`, which stores the choice, as a task of its own: a reload before it
  // would lose the choice, so the check waits for the store (the cause of a check that failed now and then, 2026-11-06)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('settings.v1'))).toContain('"pageDetailsOpen":true')
  await page.reload()
  await settled(page)
  await expect(page.locator('details.details')).toHaveAttribute('open')
  await page.screenshot({ path: `${SHOTS}/page_details.png` })
})

// The operator, 2026-11-10: a chapter opened, a page clicked, and on coming back it was folded again; now it stays open
test('a chapter the reader opened stands open again on coming back from one of its pages', async ({ page }) => {
  await page.goto('/#/free/sources/openstax_principles_of_finance_2e')
  await settled(page)
  // the first chapter that holds pages of its own: its table shows once it is open
  const chapter = page.locator('.outline > details[data-unit]:not([data-unit="outside"])').filter({ has: page.locator('> .fold-body > .unit-body > [data-part="own-pages"]') }).first()
  const unit = await chapter.getAttribute('data-unit')
  await chapter.locator('> summary').click()
  await chapter.locator('> .fold-body > .unit-body > [data-part="own-pages"] a').first().click()
  await expect(page).toHaveURL(/\/page\/\d+$/)
  await page.goBack()
  await settled(page)
  await expect(page.locator(`[data-unit="${unit}"]`)).toHaveAttribute('open', '')
})

// The EU regulation's recital heading is a unit title longer than a line: it wrapped below its marker, which stood alone
test('a chapter whose title is longer than a line keeps its marker beside it', async ({ page, request }) => {
  const EU = 'eu_delegated_regulation_2017_565'
  const response = await request.get(`/api/free/works/${EU}/pages`)
  test.skip(!response.ok(), 'the export holds no EU regulation')
  const { outline } = await response.json() as { outline: { id: string, title: string, parent: string | null }[] }
  const longest = outline.reduce((best, unit) => unit.title.length > best.title.length ? unit : best)
  await page.goto(`/#/free/sources/${EU}`)
  await settled(page)
  // since loader 7 the unit may stand nested, inside folded parents: open them first, the outermost first
  const parents: string[] = []
  for (let id = longest.parent; id; id = outline.find(unit => unit.id === id)?.parent ?? null) parents.unshift(id)
  for (const id of parents) await page.locator(`[data-unit="${id}"] > summary`).click()
  const head = page.locator(`[data-unit="${longest.id}"] > summary`)
  await expect(head).toBeVisible()
  const title = head.locator('.unit-title')
  await expect(title).toHaveText(longest.title)
  const [headBox, titleBox] = [await head.boundingBox(), await title.boundingBox()]
  // the title starts on the row's first line and wraps in its own cell; the marker is the cell's own first character
  // (159.a), so it can never stand alone above a wrapped title
  expect(titleBox!.y - headBox!.y).toBeLessThan(6)
  expect(titleBox!.height).toBeGreaterThan(30)
  // the mark is the title cell's own first element, the one fold's (179)
  expect(await title.locator('.fold-inline-mark').evaluate(element => getComputedStyle(element, '::before').content)).toContain('▸')
  await head.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/work_chapters_long_title.png` })
})

// 179 steps 3a and 3b: every data table of every view is the library's, so they share one look; a reading's own table
// stands apart, as it is the page's content, not data
test('every data table of every view is the library\'s table', async ({ page, request }) => {
  test.setTimeout(180_000)
  const runs = (await (await request.get('/api/runs')).json() as { runs: { knowledge_base: string, run_id: number }[] }).runs
  const views = [`/#/free/sources/${FINANCE}`, `/#/free/sources/${FINANCE}/page/5`, '/#/issues', '/#/overview', '/#/runs',
    '/#/calls', '/#/errors', '/#/prompts?version=judge%2F2', '/#/shelf', '/#/sources', '/#/free/html/wikipedia_trading_set',
    ...runs.slice(-1).map(run => `/#/${run.knowledge_base}/runs/${run.run_id}`)]
  const own: string[] = []
  for (const view of views) {
    await page.goto(view)
    await settled(page, OVERVIEW_LOADS)
    await openEveryFold(page)
    if (view.endsWith('/sources/' + FINANCE)) await page.locator('[data-part="routes-toggle"]').click()
    own.push(...(await page.locator('main table:not(.data-table):not(.cells)').evaluateAll(tables =>
      tables.map(table => `${table.className || table.tagName}`))).map(name => `${view}: ${name}`))
  }
  expect(own).toEqual([])
  // and the check sees a table that is not the library's
  await page.evaluate(() => document.querySelector('main')!.append(Object.assign(document.createElement('table'), { className: 'own' })))
  expect(await page.locator('main table:not(.data-table):not(.cells)').count()).toBe(1)
})

// The operator, 2026-11-09: rows ran into each other; every list parts its rows with one fine line, the same token everywhere,
// between rows only, so the first row has none
test('the rows of every list are parted by the same fine line, the chapters included', async ({ page }) => {
  await page.goto('/#/sources')
  await settled(page)
  // the token as the browser computes it, read from an element that wears it
  const token = await page.evaluate(() => {
    const probe = document.createElement('span')
    probe.style.color = 'var(--color-row-rule)'
    document.body.append(probe)
    const colour = getComputedStyle(probe).color
    probe.remove()
    return colour
  })
  const topRule = (selector: string): Promise<string> => page.locator(selector).first().evaluate(element => {
    const style = getComputedStyle(element)
    return `${style.borderTopWidth} ${style.borderTopStyle} ${style.borderTopColor}`
  })
  const expectParted = async (first: string, second: string): Promise<void> => {
    await expect(page.locator(second).first()).toBeVisible()
    expect(await topRule(first)).toMatch(/^0px/)
    expect(await topRule(second)).toBe(`1px solid ${token}`)
  }
  await expectParted('.works tbody tr:nth-child(1) td', '.works tbody tr:nth-child(2) td')
  // a work with many chapters side by side: since loader 7 the Kelly paper's chapters all stand under its title
  await page.goto('/#/free/sources/eu_delegated_regulation_2017_565')
  await settled(page)
  await expectParted('.outline > details:nth-of-type(1)', '.outline > details:nth-of-type(2)')
  await page.goto('/#/issues')
  await settled(page)
  // the first work's group: its title row, then its first page beneath a line
  await expectParted('.grouped-rows tbody:nth-of-type(1) tr:nth-child(1) th', '.grouped-rows tbody:nth-of-type(1) tr:nth-child(2) td')
  await page.screenshot({ path: `${SHOTS}/issues_ruled.png` })

  // a page's details, a key-value list: the same line between its pairs, through both columns
  await page.goto(`/#/free/sources/${KELLY}/page/4`)
  await settled(page)
  await page.locator('details.details > summary').click()
  await expectParted('.details dl > dt:nth-of-type(1)', '.details dl > dt:nth-of-type(2)')
  expect(await topRule('.details dl > dt:nth-of-type(2) + dd')).toBe(`1px solid ${token}`)
  // and every block of the readable reading in a fine box of its own, in the same colour
  const box = await page.locator('.blocks > .block').first().evaluate(element => {
    const style = getComputedStyle(element)
    return [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth, style.borderTopColor].join(' ')
  })
  expect(box).toBe(`1px 1px 1px 1px ${token}`)
  await page.screenshot({ path: `${SHOTS}/page_boxes.png` })
})

// The operator, 16 Nov ("purely visual finalizing only"): the details' stage 3 says one fact a line, each named, as the page's
// head does: why the judge looked, its verdict, and which judge it was; a page it left out says only why
test('the details\' judge stage says why, the verdict and the judge each on a named line, an unjudged page only why', async ({ page, request }) => {
  const FINANCE = 'openstax_principles_of_finance_2e'
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Detail = { check: { judged: boolean, why_judged: string, verdict: { verdict: string, outcome: string } | null, judge: { version: string | null, model: string } | null } }
  for (const [work, number] of [[FINANCE, 113], [FINANCE, 21], [ACCOUNTING, 524]] as const) {
    const { check } = await (await request.get(`/api/free/works/${work}/pages/${number}`)).json() as Detail
    await page.goto(`/#/free/sources/${work}/page/${number}`)
    await settled(page)
    if (!(await page.locator('details.details').getAttribute('open') !== null)) await page.locator('details.details > summary').click()
    const stage3 = page.locator('[data-stage="3"]')
    const labels = ['Why:', ...(check.verdict ? ['Verdict:'] : []), ...(check.judge ? ['Judge:'] : [])]
    await expect(stage3.locator('.line-label')).toHaveText(labels)
    await expect(stage3.locator('[data-part="stage3-why"] .line-value')).toHaveText(check.why_judged)
    if (check.verdict) await expect(stage3.locator('[data-part="stage3-verdict"] .line-value')).toContainText(`${check.verdict.verdict}, counts as ${check.verdict.outcome}`)
    if (check.judge?.version) await expect(stage3.locator('[data-part="judge-version"]')).toHaveText(check.judge.version)
    // each line below the one before it
    const tops = await stage3.locator('.labelled-line').evaluateAll(lines => lines.map(line => line.getBoundingClientRect().top))
    tops.forEach((top, at) => { if (at > 0) expect(top).toBeGreaterThan(tops[at - 1]) })
    await stage3.scrollIntoViewIfNeeded()
    await page.locator('details.details').screenshot({ path: `${SHOTS}/details_stage3_${number}.png` })
  }
})

// 146.a, 147.a, 150.a: the review's showcase page lists every judgement, the pipeline's in its Reading History and what was
// tried beside it in the Lab, a void finding named as code's; its details give the three stages one by one, then a person
test('a page parts its judgements into the Reading History and the Lab, and its details give the three stages, then a person', async ({ page, request }) => {
  const FINANCE = 'openstax_principles_of_finance_2e'
  const detail = await (await request.get(`/api/free/works/${FINANCE}/pages/5`)).json() as {
    attempts: { judgements: { version_state: string | null, counts: boolean, again: number }[] }[] | null
    check: { verdict: { findings: { void: boolean }[] } | null }
  }
  const judgements = (detail.attempts ?? []).flatMap(attempt => attempt.judgements)
  test.skip(judgements.length < 2, 'the export holds no page judged more than once')
  const tried = judgements.filter(j => !j.counts && (j.again > 0 || j.version_state === 'prototype'))
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  await expect(page.locator('details.history > summary')).toContainText('Reading History · ')
  // every judgement once: the pipeline's under its reading, a folded reading's too, the rest in the Lab
  await expect(page.locator('.history tr.judgement')).toHaveCount(judgements.length - tried.length)
  await expect(page.locator('.lab tr.judgement')).toHaveCount(tried.length)
  await expect(page.locator('.history [data-part="prototype"], .history [data-part="again"]')).toHaveCount(0)
  if (tried.length) await page.locator('.lab > summary').click()
  await page.locator('details.details > summary').click()
  for (const stage of ['1', '2', '3', 'person']) await expect(page.locator(`[data-stage="${stage}"]`)).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/page_judgements.png` })
  if (detail.check.verdict?.findings.some(finding => finding.void)) {
    await page.locator('.found-at button').first().click()
    const mark = page.locator('.blocks [data-part="void"]').first()
    await expect(mark).toHaveText("void: the judge's evidence names no difference")
    // the rule in the library's card (203.a)
    await mark.hover()
    await expect(page.locator('[data-part="hover-card"] [data-row="rule"]')).toContainText('strings it quotes stand in the block and in the PDF\'s text layer')
    await page.screenshot({ path: `${SHOTS}/page_void_finding.png` })
  }
})

// error classes: the findings by kind, block class and work, void apart, stage 2 beside, each class opening its pages
test('the errors list the findings by kind, block class and work, and a class opens its pages', async ({ page, request }) => {
  const { classes } = await (await request.get('/api/error-classes')).json() as {
    classes: { stage: string, void: boolean, source_id: string, pages: number[] }[]
  }
  test.skip(classes.length === 0, 'the export holds no finding')
  await page.goto('/#/errors')
  await settled(page)
  const counting = classes.filter(one => one.stage === 'judge' && !one.void).length
  await expect(page.locator('[data-table="judge"] tbody tr')).toHaveCount(counting)
  await expect(page.locator('[data-table="stage2"] tbody tr')).toHaveCount(classes.filter(one => one.stage === 'stage 2').length)
  const first = page.locator('[data-table="stage2"] tbody tr').first()
  await first.locator('details.pages > summary').click()
  await expect(first.locator('.page-links a').first()).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/errors.png` })
  await first.locator('.page-links a').first().click()
  await expect(page).toHaveURL(/#\/free\/sources\/.+\/page\/\d+$/)
})

// 148.a: every prompt version with its state, its hash as frozen, and its change from the version before, the words marked
test('the prompts stand in a tab per part, a folded row per version, and a version opens to its change', async ({ page, request }) => {
  type File = { part: string | null, sha256: string, frozen_sha256: string | null,
    diff: { parts: { changed: boolean }[] | null }[] | null }
  const { parts, versions } = await (await request.get('/api/prompts')).json() as {
    parts: { key: string, label: string }[], versions: { version: string, state: string, previous: string | null, files: File[] }[]
  }
  await page.goto('/#/prompts')
  await settled(page)
  await expect(page.locator('[data-tab]')).toHaveCount(parts.length)
  // every file of every version stands once, in the tab of its part, its state beside it
  for (const part of parts) {
    await page.locator(`[data-tab="${part.key}"]`).click()
    const mine = versions.filter(version => version.files.some(file => file.part === part.key))
    await expect(page.locator('tbody.version')).toHaveCount(mine.length)
    for (const version of mine) {
      await expect(page.locator(`tbody[data-version="${version.version}"] [data-part="state"]`)).toHaveText(version.state)
    }
  }
  // a version whose change replaced words in a line: one rewritten whole (page/2 beside page/1) has added and removed lines,
  // and no words to mark
  const changed = versions.find(version => version.previous
    && version.files.some(file => file.diff?.some(line => line.parts?.some(part => part.changed))))
  test.skip(!changed, 'no version changed words in a line of the one before it')
  // a page's link opens the version's tab and row
  await page.goto(`/#/prompts?version=${encodeURIComponent(changed!.version)}`)
  await settled(page)
  await expect(page.locator(`tbody[data-version="${changed!.version}"] .diff .changed`).first()).toBeVisible()
  // the table, an opened version's text included, stays inside the window
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  await page.screenshot({ path: `${SHOTS}/prompts.png` })
})

// The operator's 6.a: an HTML work opens from Sources as its outline by heading, and a section shows its chunks, each in its box
test('an HTML work opens from Sources by its headings, and a section shows its chunks in boxes', async ({ page, request }) => {
  const WIKIPEDIA = 'wikipedia_trading_set'
  const work = await (await request.get(`/api/free/html/${WIKIPEDIA}`)).json() as {
    why_not: string | null, sections: number, outline: { id: string, title: string, parent: string | null, label: string | null }[]
  }
  test.skip(Boolean(work.why_not), 'no search index on this machine, as on a clone')
  await page.goto('/#/sources')
  await settled(page)
  await expect(page.locator(`tr[data-work="${WIKIPEDIA}"] [data-cell="structure"]`)).toContainText(`${work.sections} sections by heading`)
  await page.locator(`tr[data-work="${WIKIPEDIA}"] a.work-title`).click()
  await expect(page).toHaveURL(new RegExp(`#/free/html/${WIKIPEDIA}$`))
  await settled(page)
  // a heading without text of its own (rule 4) is no link; its parent opens it
  const algorithmic = work.outline.find(node => node.title === 'Algorithmic trading' && node.parent === null)!
  const history = work.outline.find(node => node.title === 'History' && node.parent === algorithmic.id)!
  expect(history.label).toBeNull()
  await page.locator(`[data-node="${algorithmic.id}"] > summary`).click()
  await expect(page.locator(`[data-node="${history.id}"] > summary .unit-title`)).toHaveText('History')
  await expect(page.locator(`[data-node="${history.id}"] > summary a`)).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/html_outline.png` })
  await page.locator(`[data-node="${algorithmic.id}"] > summary a.unit-title`).click()
  await expect(page).toHaveURL(new RegExp(`#/free/html/${WIKIPEDIA}/${algorithmic.label}$`))
  // the whole article opens (the operator, 10 Nov), every section of it with its chunks, the one clicked marked
  const article = await (await request.get(`/api/free/html/${WIKIPEDIA}/articles/${algorithmic.label}`)).json() as {
    entries: { label: string | null, section: { chunks: unknown[], not_found: number } | null }[]
  }
  const labelled = article.entries.filter(entry => entry.label)
  await expect(page.locator('article.entry[data-entry]')).toHaveCount(labelled.length)
  const own = page.locator(`[data-entry="${algorithmic.label}"]`)
  await expect(own).toHaveClass(/chosen/)
  const section = await (await request.get(`/api/free/html/${WIKIPEDIA}/sections/${algorithmic.label}`)).json() as { chunks: unknown[], not_found: number }
  await expect(own.locator('.chunk')).toHaveCount(section.chunks.length)
  expect(section.not_found).toBe(0)
  await expect(page.locator('.chunk')).toHaveCount(article.entries.reduce((sum, entry) => sum + (entry.section?.chunks.length ?? 0), 0))
  // the original beside its chunks, as line 1's function strips it
  await expect(own.locator('[data-part="original"]')).not.toBeEmpty()
  await page.screenshot({ path: `${SHOTS}/html_section.png` })
  // a heading dropped as noise stands greyed at its place, and opens its original with no chunks (the operator's 2.a)
  const outline = (await (await request.get(`/api/free/html/${WIKIPEDIA}`)).json() as { outline: { dropped: string | null }[] }).outline
  const dropped = outline.find(node => node.dropped)
  test.skip(!dropped, 'no raw file to strip on this machine')
  await page.goto(`/#/free/html/${WIKIPEDIA}/${dropped!.dropped}`)
  const entry = page.locator(`[data-entry="${dropped!.dropped}"]`)
  await expect(entry.locator('[data-part="dropped"]')).toContainText('not indexed')
  await expect(entry.locator('.chunk')).toHaveCount(0)
  await expect(entry).toBeInViewport()
})

// line 1's formula mark (10 Nov): the original typesets a formula once, the chunks keep the LaTeX the index holds, and
// the indexed text's line breaks stand as paragraphs
test('an HTML section typesets its formulas in the original, keeps their LaTeX in the chunks, and parts its paragraphs', async ({ page, request }) => {
  const WIKIPEDIA = 'wikipedia_trading_set'
  const work = await (await request.get(`/api/free/html/${WIKIPEDIA}`)).json() as {
    why_not: string | null, outline: { id: string, title: string, parent: string | null, label: string | null }[]
  }
  test.skip(Boolean(work.why_not), 'no search index on this machine, as on a clone')
  const sharpe = work.outline.find(node => node.title === 'Sharpe ratio' && node.parent === null)
  const definition = work.outline.find(node => node.title === 'Definition' && node.parent === sharpe?.id)
  test.skip(!definition?.label, 'the index holds no Sharpe ratio article')
  const section = await (await request.get(`/api/free/html/${WIKIPEDIA}/sections/${definition!.label}`)).json() as {
    original: string | null, chunks: { text: string }[]
  }
  test.skip(!section.original?.includes('data-tex'), 'no raw file to strip on this machine')
  await page.goto(`/#/free/html/${WIKIPEDIA}/${definition!.label}`)
  await settled(page)
  const own = page.locator(`[data-entry="${definition!.label}"]`)
  // the section asked for comes into view in its article's scroll
  await expect(own).toBeInViewport()
  const formulas = own.locator('[data-part="original"] span[data-tex]')
  await expect(formulas.first().locator('.katex')).toBeVisible()
  // no picture of the formula beside its typesetting: it would show twice
  await expect(own.locator('[data-part="original"] span[data-image*="displaystyle"]')).toHaveCount(0)
  // the dashed line's hint only when asked for
  await expect(page.locator('[data-part="overlap-legend"]')).toHaveCount(0)
  const breaks = section.chunks[0].text.split('\n').length
  await expect(own.locator('.chunk').first().locator('.paragraph')).toHaveCount(breaks)
  await page.screenshot({ path: `${SHOTS}/html_formula.png` })
})

test('a blocked page says why in the provider\'s own words, in its line and in its work\'s list', async ({ page, request }) => {
  const listed = await (await request.get(`/api/free/works/${KELLY}/pages`)).json() as {
    pages: { pdf_page: number, check: { state: string }, error_message: string | null }[]
  }
  const blocked = listed.pages.find(row => row.check.state === 'blocked' && row.error_message)
  test.skip(!blocked, 'the export holds no blocked page with an error message for this work')
  await page.goto(`/#/free/sources/${KELLY}/page/${blocked!.pdf_page}`)
  await settled(page)
  await expect(page.locator('.summary .error-message')).toHaveText(blocked!.error_message!)
  await page.screenshot({ path: `${SHOTS}/page_blocked.png` })
  await page.goto(`/#/free/sources/${KELLY}`)
  await settled(page)
  await asTable(page)
  await expect(page.locator(`tr[data-page="${blocked!.pdf_page}"] .why`)).toHaveText(blocked!.error_message!)
})

test('a page the reader declined says so by its route, where the provider gave no sentence', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  const listed = await (await request.get(`/api/free/works/${ACCOUNTING}/pages`)).json() as {
    pages: { pdf_page: number, route: string, error_message: string | null, from_text_layer: boolean }[]
  }
  const declined = listed.pages.find(row => row.from_text_layer && !row.error_message && row.route.includes('declined'))
  test.skip(!declined, 'the export holds no declined page for this work')
  await page.goto(`/#/free/sources/${ACCOUNTING}`)
  await settled(page)
  await asTable(page)
  await page.locator('[data-facet="state"] [data-value="blocked"]').click()
  await expect(page.locator(`tr[data-page="${declined!.pdf_page}"] .why`)).toHaveText(declined!.route)
  await page.screenshot({ path: `${SHOTS}/work_pages_declined.png` })
})

test('a PDF page opens straight from its number', async ({ page }) => {
  await page.goto(`/#/free/sources/${KELLY}`)
  await settled(page)
  await page.locator('.page-jump input').fill('7')
  await page.locator('.page-jump input').press('Enter')
  await expect(page).toHaveURL(new RegExp(`#/free/sources/${KELLY}/page/7$`))
  await settled(page)
  await expect(page.locator('.original img')).toBeVisible()
})

test('an address from before the knowledge base was part of it still opens its page', async ({ page }) => {
  await page.goto(`/#/sources/${KELLY}/page/7`)
  await expect(page).toHaveURL(new RegExp(`#/free/sources/${KELLY}/page/7$`))
  await settled(page)
  await expect(page.locator('.original img')).toBeVisible()
})

test('a page that was read again lists its readings, the one shown marked and why it was chosen', async ({ page, request }) => {
  // The export lists attempts once line 1 refreshes it; until then an invented history over a real free page shows the view.
  const real = await (await request.get(`/api/free/works/${KELLY}/pages/7`)).json() as { trace: { reading_key: string, model: string } }
  // shaped as the API sends a reading since 147.a: every one carries its judgements, here none
  const first = { reading_key: '0123456789abcdef', number: 1, purpose: 'first reading', model: real.trace.model, mode: 'batch',
    attempt: 0, class_now: 'malformed', stored_at: '2026-11-02T14:48:03+00:00', deviation: null, judgements: [], shown: false,
    cost_usd: 0.0157879, format_errors: ['block b03 (line 22): in=b00 points to no block on this page'], check: null }
  const second = { ...first, reading_key: real.trace.reading_key, number: 2, purpose: 'read again by a replay', mode: 'standard',
    attempt: 1, class_now: 'ok', stored_at: '2026-11-04T09:12:00+00:00', shown: true }
  await page.route(`**/api/free/works/${KELLY}/pages/7`, async route => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), attempts: [first, second],
      chosen: { why: 're-read after the format retry', run_id: '7', chosen_at: '2026-11-04T09:13:00+00:00' } } })
  })
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  await expect(page.locator('.history [data-reading]')).toHaveCount(2)
  await expect(page.locator('.history .current')).toContainText('shown here')
  await expect(page.locator('.history .chosen')).toContainText('re-read after the format retry')
  // the first reading says why it is malformed, in the validator's words, though no check reached it (A.a, 18 Nov)
  await expect(page.locator('.history [data-reading="0123456789abcdef"] [data-part="format-error"]'))
    .toHaveText(first.format_errors)
  await expect(page.locator('.history')).toBeInViewport()
  await page.screenshot({ path: `${SHOTS}/page_history.png` })
})

// 166.a (the operator): a page a person accepted still showed only the judge's "issue"; a person's standing verdict now stands beside
// the state wherever it stands, its reason and note in the hover, counted in the state's chip. p. 635 is accepted, p. 524 noted
test('a person\'s verdict stands beside the state in the page, its work, the Issues and the overview', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Mark = { standing: string, reason: string | null, note: string | null }
  const markOf = async (pdfPage: number) => (await (await request.get(`/api/free/works/${ACCOUNTING}/pages/${pdfPage}`)).json() as {
    person: Mark, check: { state: string }, listed_state: string })
  const [accepted, noted] = [await markOf(635), await markOf(524)]
  expect(accepted.person.standing).toBe('accepted')
  expect(noted.person.standing).toBe('noted')
  // the page's head: beside the judge's state, the person's word, the reason in the hover
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/635`)
  await settled(page)
  const head = page.locator('.summary [data-person="accepted"]')
  await expect(head).toHaveText('accepted')
  // under the pointer a card of data, no browser tooltip (179): the verdict and its reason
  await head.hover()
  await expect(page.locator('[data-part="hover-card"] [data-row="verdict"] .card-value')).toHaveText('accepted')
  await expect(page.locator('[data-part="hover-card"] [data-row="reason"] .card-value')).toHaveText(accepted.person.reason!)
  await page.screenshot({ path: `${SHOTS}/page_person.png` })
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/524`)
  await settled(page)
  await expect(page.locator('.summary [data-person="noted"]')).toHaveText('noted')
  // the work: each page's row, and the chip of the state it is listed in counting what a person accepted, as the API counted
  // it; a page the check listed to look at that a person settled is listed as decided (211.a)
  type Count = { value: string, accepted?: number | null }
  const summary = (await (await request.get(`/api/free/works/${ACCOUNTING}/pages`)).json() as { summary: { states: Count[] } }).summary
  const state = summary.states.find(count => count.value === accepted.listed_state)!
  await page.goto(`/#/free/sources/${ACCOUNTING}`)
  await settled(page)
  await expect(page.locator(`.facet-bar [data-facet="state"] [data-value="${state.value}"] .person-tally [data-person="accepted"]`))
    .toContainText(`${state.accepted} accepted`)
  await asTable(page)
  await expect(page.locator('tr[data-page="635"] [data-person="accepted"]')).toHaveText('accepted')
  await expect(page.locator('tr[data-page="524"] [data-person="noted"]')).toHaveText('noted')
  // the Issues: the mark in its row, in the fold of what a person settled where it is settled (211.a), and "a person" one
  // click away
  await page.goto('/#/issues')
  await settled(page)
  if (noted.listed_state === 'decided_by_a_person') await page.locator('[data-part="decided"] > summary').click()
  await expect(page.locator(`tr[data-page="free/${ACCOUNTING}/524"] [data-person="noted"]`)).toHaveText('noted')
  await page.locator('[data-facet="person"] [data-value="noted"]').click()
  await expect(page.locator(`tr[data-page="free/${ACCOUNTING}/524"]`)).toBeVisible()
  await expect(page.locator('tbody tr[data-page] [data-person="noted"]')).toHaveCount(await page.locator('tbody tr[data-page]').count())
  // the overview: a person's verdicts by standing, each count opening exactly its pages
  await page.goto('/#/overview')
  await settled(page, OVERVIEW_LOADS)
  const box = page.locator('[data-section="A person\'s verdict"]')
  const count = Number(await box.locator('tr[data-value="accepted"] [data-kb="free"] a').textContent())
  await box.locator('tr[data-value="accepted"] [data-kb="free"] a').click()
  await expect(page).toHaveURL(/person=accepted/)
  await settled(page)
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(count)
})

// 178.a (the operator on finance p. 5, b12: "a pity that 'The judge's evidence:' is not on a new line beneath"): a
// finding speaks with up to three voices and a person with a fourth, each its own labelled line, in this order
test('a finding speaks one voice a line: the judge, the code, the judge\'s evidence, then a person', async ({ page, request }) => {
  // a person's two manual parts (188.a) follow their verdict where they gave them; the assessment names the judge it rates
  const LABELS: Record<string, RegExp> = { judge: /^The judge's finding:$/, code: /^The code's ruling:$/, evidence: /^The judge's evidence:$/,
    person: /^A person's verdict:$/, correction: /^Manual correction by a person:$/, assessment: /^A person's assessment of (the judge|judge\/\d+):$/ }
  type Person = { applies: boolean, correction: string | null, judge_assessment: string | null, given_at: string | null }
  type Block = { id: string, findings: { void: boolean, evidence: string | null }[], people: Person[],
    correction: { text: string, given_at: string | null } | null }
  // the correction that stands is drawn first in its block (229.a), so beneath the findings only an earlier one speaks
  const personVoices = (block: Block) => (person: Person) => ['person',
    ...(person.correction && !(block.correction?.text === person.correction && block.correction.given_at === person.given_at) ? ['correction'] : []),
    ...(person.judge_assessment ? ['assessment'] : [])]
  type Shown = { reading: { blocks: Block[] } }
  // each voice's label in order, each lower on the page than the one before it: a line of its own
  async function voicesOf(work: string, pdfPage: number, blockId: string): Promise<string[]> {
    await page.goto(`/#/free/sources/${work}/page/${pdfPage}`)
    await settled(page)
    const voices = page.locator(`[data-block="${blockId}"] .block-findings [data-voice]`)
    await expect(voices.first()).toBeVisible()
    const placed = await voices.evaluateAll(lines => lines.map(line => ({
      voice: line.getAttribute('data-voice')!, label: line.querySelector('.part-label')?.textContent ?? '',
      weight: Number(getComputedStyle(line.querySelector('.part-label')!).fontWeight), top: line.getBoundingClientRect().top })))
    placed.forEach((line, at) => {
      expect(line.label).toMatch(LABELS[line.voice])
      expect(line.weight, `${line.label} in bold`).toBeGreaterThanOrEqual(700)
      if (at > 0) expect(line.top).toBeGreaterThan(placed[at - 1].top)
    })
    // the evidence itself stands beneath its label
    const evidence = page.locator(`[data-block="${blockId}"] .block-findings .evidence`).first()
    const label = page.locator(`[data-block="${blockId}"] .block-findings [data-voice="evidence"]`).first()
    expect((await evidence.boundingBox())!.y).toBeGreaterThan((await label.boundingBox())!.y)
    return placed.map(line => line.voice)
  }
  // finance p. 5, b12: the judge's finding, voided by code, and its evidence; no person has judged it
  const FINANCE_5 = await (await request.get(`/api/free/works/${FINANCE}/pages/5`)).json() as Shown
  const b12 = FINANCE_5.reading.blocks.find(block => block.id === 'b12')!
  expect(b12.findings[0].void).toBe(true)
  expect(await voicesOf(FINANCE, 5, 'b12')).toEqual(['judge', 'code', 'evidence', ...b12.people.filter(one => one.applies).flatMap(personVoices(b12))])
  await page.locator('[data-block="b12"]').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/finding_voices.png` })
  // accounting p. 635, b08: the judge's finding and its evidence, then a person's accept
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  const p635 = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/635`)).json() as Shown
  const b08 = p635.reading.blocks.find(block => block.id === 'b08')!
  const voices = await voicesOf(ACCOUNTING, 635, 'b08')
  expect(voices).toContain('person')
  expect(voices).toEqual([...b08.findings.flatMap(one => ['judge', ...(one.void ? ['code'] : []), ...(one.evidence ? ['evidence'] : [])]),
    ...b08.people.filter(one => one.applies).flatMap(personVoices(b08))])
})

// 229.a (the operator, 12 Nov: "what you really want to see first is the correction"), after 188.a on finance p. 94, b05 ("both must be marked as a manual change"): a person's correction stands first in its block, marked as manual and
// not served yet, the reader's text muted beneath it; their verdict, its note and their assessment of the judge stay
// beneath the finding's voices, the correction not drawn again there
test('a person\'s correction stands first in its block, the reading muted beneath it, the assessment beneath the finding', async ({ page, request }) => {
  type Person = { block: string | null, applies: boolean, correction: string | null, judge_assessment_text: string | null }
  type Block = { id: string, text: string | null, people: Person[], correction: { text: string } | null }
  const detail = await (await request.get(`/api/free/works/${FINANCE}/pages/94`)).json() as { reading: { blocks: Block[] } }
  const b05 = detail.reading.blocks.find(block => block.id === 'b05')!
  const person = b05.people.find(one => one.applies && one.correction)!
  expect(b05.correction?.text).toBe(person.correction)
  await page.goto(`/#/free/sources/${FINANCE}/page/94`)
  await settled(page)
  const shown = page.locator('[data-block="b05"]')
  const standing = shown.locator('[data-part="standing-correction"]')
  await expect(standing.locator('.part-label').first()).toHaveText('Manual correction by a person')
  await expect(standing.locator('[data-part="correction-given"]')).toContainText('not served yet')
  await expect(standing.locator('[data-part="correction-content"]')).toHaveText(person.correction!)
  expect(await standing.locator('[data-part="correction-content"]').evaluate(element => getComputedStyle(element).borderLeftStyle)).toBe('dashed')
  // the reading beneath, as the reader wrote it, labelled and in the muted colour, never struck
  await expect(standing.locator('[data-part="as-read-said"]')).toHaveText('The reading, as the reader wrote it:')
  const asRead = shown.locator('[data-part="as-read"]')
  await expect(asRead).toHaveText(b05.text!.trim())
  const colour = (selector: string) => page.locator(selector).first().evaluate(element => getComputedStyle(element).color)
  expect(await colour('[data-block="b05"] [data-part="as-read"] .block-body')).toBe(await colour('[data-block="b05"] .block-head'))
  const correctionTop = (await standing.boundingBox())!.y
  expect((await asRead.boundingBox())!.y).toBeGreaterThan(correctionTop)
  const findings = shown.locator('.block-findings')
  expect((await findings.boundingBox())!.y).toBeGreaterThan((await asRead.boundingBox())!.y)
  const voices = await findings.locator('[data-voice]').evaluateAll(lines => lines.map(line => line.getAttribute('data-voice')))
  expect(voices.slice(-2)).toEqual(['person', 'assessment'])
  await expect(findings.locator('[data-part="correction"]')).toHaveCount(0)
  await expect(findings.locator('[data-voice="assessment"] .assessment')).toHaveText(person.judge_assessment_text!)
  await shown.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/finding_correction.png` })
})

// 229.a on accounting p. 524: tables corrected over a table the reader marked unreadable, which holds no text to show
// beneath the correction; the line beneath says so rather than label nothing
test('a correction over a table the reader could not read says the reading holds no text there', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Unread = { id: string, rows: unknown[] | null, text: string | null, segments: unknown[] | null, correction: { rows: unknown[] | null } | null }
  const p524 = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/524`)).json() as { reading: { blocks: Unread[] } }
  const unread = p524.reading.blocks.filter(block => block.correction?.rows && !block.rows && !block.text && !block.segments)
  test.skip(!unread.length, 'accounting p. 524 holds no correction over an unreadable table today')
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/524`)
  await settled(page)
  for (const block of unread) {
    const corrected = page.locator(`[data-block="${block.id}"] [data-part="standing-correction"]`)
    await expect(corrected.locator('[data-part="correction-content"] table.cells tr')).toHaveCount(block.correction!.rows!.length)
    await expect(corrected.locator('[data-part="as-read-said"]')).toHaveText('The reading holds no text for this block.')
  }
  await page.locator(`[data-block="${unread[0].id}"]`).screenshot({ path: `${SHOTS}/correction_over_unreadable.png` })
})

// accounting p. 398, b04: the first verdict given from the page view (verdict 32), a note with a correction of a list item
// that has no finding, which the page did not show before 229.a; it stands first, the person's verdict and note beneath
test('a text correction of a block without findings stands first, its verdict and note beneath (accounting p. 398, b04)', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Person = { applies: boolean, note: string | null, correction: string | null }
  type Block = { id: string, findings: unknown[], people: Person[], correction: { text: string, rows: unknown[] | null } | null }
  const detail = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/398`)).json() as { reading: { blocks: Block[] } }
  const b04 = detail.reading.blocks.find(block => block.id === 'b04')!
  test.skip(!b04.correction, 'accounting p. 398, b04 carries no correction today')
  expect(b04.findings).toEqual([])
  expect(b04.correction!.rows).toBeNull()
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/398`)
  await settled(page)
  const shown = page.locator('[data-block="b04"]')
  await expect(shown.locator('[data-part="standing-correction"] [data-part="correction-content"]')).toHaveText(b04.correction!.text)
  await expect(shown.locator('[data-part="correction-given"]')).toContainText('not served yet')
  await expect(shown.locator('[data-part="as-read-said"]')).toHaveText('The reading, as the reader wrote it:')
  const person = b04.people.find(one => one.applies && one.correction)!
  await expect(shown.locator('.block-findings [data-part="person-note"]')).toHaveText(person.note!)
  await shown.scrollIntoViewIfNeeded()
  await shown.screenshot({ path: `${SHOTS}/correction_without_findings.png` })
})

// 204.a (the operator on finance p. 119: the correction of a table showed as its HTML source): a table block's correction stands as a
// table, drawn as a reading's table is, dashed as a person's, first in its block (229.a); the page is found at run time,
// among those a person settled
test('a person\'s correction of a table stands as a table, never as its source', async ({ page, request }) => {
  type Detail = { reading: { blocks: { id: string, correction: { rows: unknown[] | null } | null }[] } | null }
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, pdf_page: number }[] }).rows
  let found: { work: string, page: number, block: string, rows: number } | null = null
  for (const row of issues) {
    const detail = await (await request.get(`/api/free/works/${row.source_id}/pages/${row.pdf_page}`)).json() as Detail
    const block = detail.reading?.blocks.find(one => one.correction?.rows)
    if (block) {
      found = { work: row.source_id, page: row.pdf_page, block: block.id, rows: block.correction!.rows!.length }
      break
    }
  }
  test.skip(!found, 'no listed page holds a person\'s correction of a table today')
  await page.goto(`/#/free/sources/${found!.work}/page/${found!.page}`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const correction = page.locator(`[data-block="${found!.block}"] [data-part="standing-correction"] [data-part="correction-content"]`)
  await expect(correction.locator('table.cells tr')).toHaveCount(found!.rows)
  await expect(correction).not.toContainText('<table')
  expect(await correction.evaluate(element => getComputedStyle(element).borderLeftStyle)).toBe('dashed')
  await correction.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/finding_table_correction.png` })
})

// line 1 on accounting p. 398 (12 Nov): a cell's <br>, which page/1 allows, drew as a space, so a journal entry read as if
// both amounts stood on one line. The break is drawn now; a table without one is drawn as before (Kelly p. 7)
test('a line break in a table cell is drawn as a line, and a table without one as before', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Cell = { segments: { kind: string, content: string }[] }
  type Detail = { reading: { blocks: { id: string, rows: Cell[][] | null }[] } }
  const p398 = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/398`)).json() as Detail
  const b05 = p398.reading.blocks.find(block => block.id === 'b05')!
  const breaks = b05.rows!.map(row => row.map(cell => cell.segments.filter(segment => segment.kind === 'br').length))
  expect(breaks.flat().some(count => count > 0)).toBe(true)
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/398`)
  await settled(page)
  const table = page.locator('[data-block="b05"] table.cells')
  expect(await table.locator('tr').evaluateAll(rows => rows.map(row => [...row.children].map(cell => cell.querySelectorAll('br').length)))).toEqual(breaks)
  // the debit account on one line, the credit account on the next: the first cell is two lines high, its amount beside it
  const lineHeight = await table.locator('td').first().evaluate(cell => parseFloat(getComputedStyle(cell).lineHeight))
  const first = (await table.locator('td').first().boundingBox())!
  expect(first.height).toBeGreaterThan(1.8 * lineHeight)
  await table.scrollIntoViewIfNeeded()
  await page.locator('[data-block="b05"]').screenshot({ path: `${SHOTS}/table_cell_breaks.png` })
  const p7 = await (await request.get(`/api/free/works/${KELLY}/pages/7`)).json() as Detail
  expect(p7.reading.blocks.some(block => block.rows)).toBe(true)
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  await expect(page.locator('table.cells br')).toHaveCount(0)
})

// 213.b (the operator, 12 Nov: "this really is the last proper feature before the freeze"): the check's app is started without
// --allow-verdicts, so a page has no control and the one write route refuses. The dialog's look is checked with the form
// answered as a switched-on app answers it and the correction's preview answered with the cells the API gives for the
// block, and nothing is ever sent. The page is found at run time: one whose first finding names a table
test('a page offers no verdict where the app is read-only, and the dialog opens on the finding\'s block, never sending', async ({ page, request }) => {
  type Block = { id: string, block_class: string, body?: string | null, rows: unknown[] | null,
    correction: { text: string, rows: unknown[] | null } | null }
  type Detail = { focus?: string | null, reading: { blocks: Block[] } | null }
  const form = await (await request.get('/api/verdict')).json() as { enabled: boolean, why_not: string | null }
  expect(form.enabled).toBe(false)
  const refused = await request.post('/api/verdict', { data: { knowledge_base: 'free', work: KELLY, pdf_page: 4, verdict: 'note', reason: 'other', note: 'never sent' } })
  expect(refused.status()).toBe(403)
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, pdf_page: number }[] }).rows
  let found: { work: string, page: number, block: Block } | null = null
  for (const row of issues) {
    const detail = await (await request.get(`/api/free/works/${row.source_id}/pages/${row.pdf_page}`)).json() as Detail
    const block = detail.reading?.blocks.find(one => one.id === detail.focus && one.block_class === 'table')
    if (block) {
      found = { work: row.source_id, page: row.pdf_page, block }
      break
    }
  }
  test.skip(!found, 'no listed page has a first finding on a table today')
  // the field starts from the correction that stands for the block (229.a), else from the block's own text
  const prefill = found!.block.correction?.text ?? found!.block.body ?? ''
  const cells = found!.block.correction ? found!.block.correction.rows : found!.block.rows
  await page.goto(`/#/free/sources/${found!.work}/page/${found!.page}`)
  await settled(page)
  await expect(page.locator('[data-part="give-verdict"]')).toHaveCount(0)

  let sent = 0
  await page.route('**/api/verdict', route => {
    if (route.request().method() !== 'GET') {
      sent++
      return route.abort()
    }
    return route.fulfill({ json: { ...form, enabled: true, why_not: null } })
  })
  await page.route('**/api/verdict/preview', route => route.fulfill({ json: { rows: cells } }))
  await page.reload()
  await settled(page)
  await page.locator('[data-part="give-verdict"]').click()
  const dialog = page.locator('[data-part="verdict-dialog"]')
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('[data-part="block"]')).toHaveValue(found!.block.id)
  await expect(dialog.locator('[data-part="correction-field"]')).toHaveValue(prefill)
  if (cells?.length) await expect(dialog.locator('[data-part="correction-preview"] table.cells tr')).toHaveCount(cells.length)
  // a verdict and a reason before it can be sent; chosen here, and still not sent
  await expect(dialog.locator('[data-part="send"]')).toBeDisabled()
  await dialog.locator('[data-verdict="note"]').click()
  await dialog.locator('[data-part="reason"]').selectOption('reading_wrong')
  await expect(dialog.locator('[data-part="send"]')).toBeEnabled()
  await dialog.screenshot({ path: `${SHOTS}/verdict_dialog.png` })
  await dialog.locator('[data-part="cancel"]').click()
  await expect(dialog).toHaveCount(0)
  expect(sent).toBe(0)
})

// 202.a: a judge's rules for the reader stand in the Lab beneath the judgement that proposed them, read-only, never applied;
// the page is found at run time among those listed
test('a judge\'s rules for the reader stand beneath its judgement in the Lab, never applied', async ({ page, request }) => {
  type Rule = { kind: string, block: string | null, rule: string | null }
  type Attempt = { number: number, judgements: { version: string | null, reader_rules: Rule[] | null }[] }
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, pdf_page: number }[] }).rows
  let found: { work: string, page: number, rules: Rule[] } | null = null
  for (const row of issues) {
    const detail = await (await request.get(`/api/free/works/${row.source_id}/pages/${row.pdf_page}`)).json() as { attempts: Attempt[] | null }
    const judgement = detail.attempts?.flatMap(attempt => attempt.judgements).find(one => one.reader_rules?.length)
    if (judgement) {
      found = { work: row.source_id, page: row.pdf_page, rules: judgement.reader_rules! }
      break
    }
  }
  test.skip(!found, 'no listed page holds a judge\'s rules for the reader today')
  await page.goto(`/#/free/sources/${found!.work}/page/${found!.page}`)
  await settled(page)
  const lab = page.locator('details.lab')
  if (await lab.getAttribute('open') === null) await lab.locator('summary').click()
  const rules = lab.locator('[data-part="reader-rules"]').first()
  await expect(rules.locator('.part-label')).toHaveText('Proposals for the reader, never applied:')
  await expect(rules.locator('.rule-text').first()).toHaveText(found!.rules[0].rule!)
  // the row above it is the judgement that proposed them
  const above = await rules.evaluate(element => element.closest('tr')!.previousElementSibling?.getAttribute('data-judgement'))
  expect(above).toBeTruthy()
  await rules.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/page_reader_rules.png` })
})

// 210.a: a reader prototype's reading (page/2) stands in the Lab beside the judge prototypes, never in the Reading History,
// and shows on the page as its judge saw it; the page is found at run time among those listed
test('a reader prototype\'s reading stands in the Lab, never in the history, and shows on the page', async ({ page, request }) => {
  type Attempt = { reading_key: string, number: number, prototype: boolean | null, reader_version: string | null, judgements: { recall: string | null }[] }
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, pdf_page: number }[] }).rows
  let found: { work: string, page: number, attempts: Attempt[] } | null = null
  for (const row of issues) {
    const detail = await (await request.get(`/api/free/works/${row.source_id}/pages/${row.pdf_page}`)).json() as { attempts: Attempt[] | null }
    if (detail.attempts?.some(attempt => attempt.prototype && attempt.judgements.length)) {
      found = { work: row.source_id, page: row.pdf_page, attempts: detail.attempts }
      break
    }
  }
  test.skip(!found, 'no listed page holds a reader prototype\'s judged reading today')
  const prototype = found!.attempts.find(attempt => attempt.prototype && attempt.judgements.length)!
  const pipeline = found!.attempts.filter(attempt => !attempt.prototype).length
  await page.goto(`/#/free/sources/${found!.work}/page/${found!.page}`)
  await settled(page)
  await expect(page.locator('details.history > summary')).toContainText(`${pipeline} reading${pipeline === 1 ? '' : 's'}`)
  await expect(page.locator(`details.history [data-reading="${prototype.reading_key}"]`)).toHaveCount(0)
  const lab = page.locator('details.lab')
  if (await lab.getAttribute('open') === null) await lab.locator('summary').click()
  const cell = lab.locator(`[data-reader="${prototype.reader_version}"]`).first()
  await expect(cell).toHaveText(`reading ${prototype.number}, ${prototype.reader_version} (prototype), never served`)
  await cell.locator('xpath=ancestor::tr').locator('[data-part="recall"]').click()
  await expect(page.locator('[data-part="recall-chip"]')).toContainText(`read by ${prototype.reader_version} (prototype), never served`)
  await page.screenshot({ path: `${SHOTS}/page_reader_prototype.png` })
})

// 184 (the operator on finance p. 5: "I would rather have this line with labels"): the page's record as labelled lines, each block of
// its findings a jump. And each thing said once, the labels and values in two columns (the operator, 11 Nov: "best overview"):
// a person's accept before the state, which recedes; no "Why:" and no outcome where the person's line and the note beneath
// the block say it; the values in one place from page to page
test('a page says its record in aligned labelled lines, each thing once, a person\'s accept first', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/5`)
  await settled(page)
  const facts = page.locator('[data-part="page-facts"]')
  await expect(facts.locator('.line-label')).toHaveText(['A person:', 'Check:', 'Category:', 'Route:', 'Reading:', 'Findings:'])
  expect(await facts.locator('.line-label').first().evaluate(element => Number(getComputedStyle(element).fontWeight))).toBeGreaterThanOrEqual(700)
  await expect(facts.locator('[data-label="Check"] .state-mark')).toHaveClass(/quiet/)
  const findings = facts.locator('[data-label="Findings"]')
  await expect(findings.locator('[data-jump="b12"]')).toBeVisible()
  await expect(findings.locator('[data-said]')).toHaveText('void by code')
  // a block whose findings code voided keeps the flag, receding with the ruling (the operator, 12 Nov)
  await expect(findings.locator('[data-finding-at="b12"]')).toHaveClass(/void/)
  await expect(findings.locator('[data-part="findings-outcome"]')).toHaveCount(0)
  // every value starts where the others do, and where a page with fewer labels has its own
  const starts = () => facts.locator('.line-value').evaluateAll(values => values.map(value => Math.round(value.getBoundingClientRect().left)))
  const here = await starts()
  expect(new Set(here).size).toBe(1)
  await page.screenshot({ path: `${SHOTS}/page_facts.png` })
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  await expect(facts.locator('[data-label="A person"]')).toHaveCount(0)
  expect(new Set([...here, ...(await starts())]).size).toBe(1)
})

// The operator, 12 Nov, on accounting p. 524: "Findings in the header should get the red flag or red text ... so that they catch the eye at once by their colour". A block in the head wears the look its finding wears beneath it: the same flag in the
// same colour, the severity's word too. The page is found at run time among those listed, one with a standing major finding
test('the head names a block\'s findings in the look they have beneath the block', async ({ page, request }) => {
  type Detail = { findings_at: { block: string, severity: string | null }[] | null }
  const issues = (await (await request.get('/api/issues')).json() as { rows: { source_id: string, pdf_page: number }[] }).rows
  let found: { work: string, page: number, block: string } | null = null
  for (const row of issues) {
    const detail = await (await request.get(`/api/free/works/${row.source_id}/pages/${row.pdf_page}`)).json() as Detail
    const major = detail.findings_at?.find(one => one.severity === 'major')
    if (major) {
      found = { work: row.source_id, page: row.pdf_page, block: major.block }
      break
    }
  }
  test.skip(!found, 'no listed page holds a standing major finding today')
  await page.goto(`/#/free/sources/${found!.work}/page/${found!.page}`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const colourOf = (selector: string) => page.locator(selector).first().evaluate(element => getComputedStyle(element).color)
  const head = `[data-label="Findings"] [data-finding-at="${found!.block}"]`
  await expect(page.locator(`${head} [data-severity]`)).toHaveText('major')
  const beneath = `[data-block="${found!.block}"] .block-findings li.major`
  expect(await colourOf(`${head} .finding-mark`)).toBe(await colourOf(`${beneath} .finding-mark`))
  expect(await colourOf(`${head} [data-severity]`)).toBe(await colourOf(`${beneath} .severity`))
  // and it is not the text's own colour: it stands out
  expect(await colourOf(`${head} .finding-mark`)).not.toBe(await colourOf('[data-label="Findings"] .line-label'))
  await page.locator('[data-part="page-facts"]').screenshot({ path: `${SHOTS}/page_head_findings.png` })
})

// 186 (the operator: "can already be focused right on entry"): a page with findings opens on the first, framed on the
// image and in view in the reading's own pane, the record above it unmoved; a page without opens at its top
test('a page opens on its first finding in its reading pane, and a page without findings at its top', async ({ page, request }) => {
  type Detail = { focus: string | null }
  const p94 = await (await request.get(`/api/free/works/${FINANCE}/pages/94`)).json() as Detail
  expect(p94.focus).toBe('b05')
  await page.goto(`/#/free/sources/${FINANCE}/page/94`)
  await settled(page)
  await expect(page.locator('.block-box[data-box="b05"]')).toBeVisible()
  await expect(page.locator('[data-block="b05"]')).toHaveClass(/highlighted/)
  // the window did not move: the record stands where it did
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  // a link from the Issues carries the block it opens on, and a reload keeps it
  await page.goto(`/#/free/sources/${FINANCE}/page/94?focus=b05`)
  await settled(page)
  await page.reload()
  await settled(page)
  await expect(page.locator('.block-box[data-box="b05"]')).toBeVisible()
  await page.goto('/#/issues')
  await settled(page)
  await expect(page.locator(`tr[data-page="free/${FINANCE}/94"] a`)).toHaveAttribute('href', /focus=b05/)
  // an ok page without findings: nothing framed, the window at its top
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)
  await expect(page.locator('.block-box')).toHaveCount(0)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
})

// The operator on finance p. 408: the finding on b10 showed no person's verdict, as the walk's named b05 only; a verdict on the page
// as a whole now speaks for a finding no verdict names. And the head says the accept once, the page protected (191.a)
test('a page verdict speaks for a finding no verdict names, and the head says the accept once and the page protected', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/408`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const voice = (block: string) => page.locator(`[data-block="${block}"] .block-findings [data-voice="person"]`)
  await expect(voice('b05').locator('.person-standing')).toHaveText('accepted')
  await expect(voice('b05').locator('.part-label')).toHaveText("A person's verdict:")
  await expect(voice('b10').locator('.person-standing')).toHaveText('accepted')
  await expect(voice('b10').locator('.part-label')).toHaveText("A person's verdict on the page:")
  // the note stands once: the sentence above the head says the accept short, the note stands beneath the block the
  // verdict speaks for, a line of its own, and the head has no "Why:" to say it again (the operator, 11 Nov)
  await expect(page.locator('[data-part="said"]')).toHaveText('Served: a person accepted the reading.')
  await expect(page.locator('[data-block="b10"] [data-part="person-note"]')).toContainText('All 100 portfolio values')
  // the head's, not the details' stage 3, whose "Why:" says why the judge looked (16 Nov)
  await expect(page.locator('[data-part="page-facts"] [data-label="Why"]')).toHaveCount(0)
  await expect(page.locator('[data-label="A person"] [data-part="protected"]')).toHaveText('protected')
  await expect(page.locator('[data-label="A person"]')).not.toContainText('another reason')
})

// 2c and 194.a (the operator on finance pp. 94 and 387): a figure's labels run on in one line and fold beyond a dozen, a photo's
// always; a photo on a chapter opener is chapter art, folded and quiet; a grouped figure keeps its boxes
test('a figure\'s labels run on and fold, chapter art folds quietly, and a grouped figure keeps its boxes', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/387`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const art = page.locator('[data-block="b01"] details.labels-fold')
  await expect(art).not.toHaveAttribute('open')
  await expect(art.locator('> summary')).toHaveText(/^Chapter art · \d+ labels read from the photo$/)
  await page.goto(`/#/free/sources/${FINANCE}/page/94`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const chart = page.locator('[data-block="b03"] [data-part="figure-labels"]')
  const [height, lineHeight] = await chart.evaluate(element => [element.getBoundingClientRect().height, parseFloat(getComputedStyle(element).lineHeight)])
  expect(height).toBeLessThanOrEqual(lineHeight * 2 + 4)
  await page.goto('/#/free/sources/openstax_principles_of_accounting_v1/page/305')
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  await expect(page.locator('[data-block="b03"] .text-group')).toHaveCount(11)
})

// 190.a (the operator on finance p. 136): a glossary entry's term stands in its attribute, and the readable mode showed the
// definition alone; the term now stands in bold before it, as the core's quotable text has it
test('a glossary entry shows its term in bold before its definition', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/136`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'readable' }).click()
  const body = page.locator('[data-block="b19"] .block-body')
  const term = body.locator('[data-part="entry-term"]')
  await expect(term).toHaveText('accrual-basis accounting')
  expect(await term.evaluate(element => Number(getComputedStyle(element).fontWeight))).toBeGreaterThanOrEqual(700)
  await expect(body).toHaveText(/^accrual-basis accounting: an accounting system/)
})

// 172.a (the operator): an index, contents, front or back matter, a cover, a blank page or an exercise page is a category of its own,
// marked quietly beside the state, a facet with nothing chosen; in the Issues such pages stand last, noted, not repaired
test('a page that is not content says its category beside its state, and the lists narrow by it', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Row = { pdf_page: number, category: string | null, page_kind: string | null, category_said: string | null }
  type Count = { value: string, count: number }
  const work = await (await request.get(`/api/free/works/${ACCOUNTING}/pages`)).json() as { pages: Row[], summary: { categories: Count[] } }
  const index = work.pages.find(row => row.category === 'index')!
  const exercises = work.summary.categories.find(count => count.value === 'exercise')!
  // the page's head: the category beside the state; its hover says what it means, the API's line (177.a), and what the
  // reader called the page
  expect(index.category_said).toBeTruthy()
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/${index.pdf_page}`)
  await settled(page)
  await page.locator('.summary [data-category="index"]').hover()
  const card = page.locator('[data-part="hover-card"]')
  await expect(card.locator('[data-row="means"] .card-value')).toHaveText(index.category_said!)
  await expect(card.locator('[data-row="the reader called it"] .card-value')).toHaveText(index.page_kind!.replace(/_/g, ' '))
  // the work: every category a chip, none chosen; a click narrows the table to exactly its pages
  await page.goto(`/#/free/sources/${ACCOUNTING}`)
  await settled(page)
  await asTable(page)
  const chips = page.locator('.facet-bar [data-facet="category"] button')
  await expect(chips).toHaveCount(work.summary.categories.length)
  await expect(page.locator('.facet-bar [data-facet="category"] button[aria-pressed="true"]')).toHaveCount(0)
  await expect(page.locator(`tr[data-page="${index.pdf_page}"] [data-category="index"]`)).toHaveText('index')
  await page.locator('.facet-bar [data-facet="category"] [data-value="exercise"]').click()
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(exercises.count)
  await expect(page.locator('tbody tr[data-page] [data-category="exercise"]')).toHaveCount(exercises.count)
  // the Issues: the open pages that are not content after the rest, under their own heading, as the API ordered them; a
  // page a person settled stands in its own fold below (211.a)
  type Issue = { source_id: string, pdf_page: number, apart: boolean, listed_state: string }
  const issues = (await (await request.get('/api/issues')).json() as { rows: Issue[] }).rows
  await page.goto('/#/issues')
  await settled(page)
  const apart = page.locator('[data-part="apart"] tbody tr[data-page]')
  const SETTLED = ['decided_by_a_person', 'decided_by_an_automated_review']
  const open = issues.filter(row => !SETTLED.includes(row.listed_state ?? ''))
  const apartCount = open.filter(row => row.apart).length
  await expect(apart).toHaveCount(apartCount)
  // the heading only where such a page waits: on 18 Nov the last one, accounting p. 338, got a valid reading
  await expect(page.locator('[data-part="apart"] h2')).toHaveCount(apartCount ? 1 : 0)
  if (apartCount) await expect(page.locator('[data-part="apart"] h2')).toContainText('Not content: noted, not repaired')
  // every list stands in one grid, the settled pages' folds opened, a person's and an automated review's: their State,
  // Reasons and Why columns start at one x
  const folds = [['decided_by_a_person', 'decided'], ['decided_by_an_automated_review', 'reviewed']]
    .filter(([state]) => issues.some(row => row.listed_state === state))
  for (const [, part] of folds) await page.locator(`[data-part="${part}"] > summary`).click()
  const lists = (open.some(row => !row.apart) ? 1 : 0) + (apartCount ? 1 : 0) + folds.length
  for (const column of [2, 3, 4]) {
    const at = await page.locator(`.grouped-rows thead th:nth-child(${column})`).evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().left))
    expect(at).toHaveLength(lists)
    expect(Math.max(...at) - Math.min(...at)).toBeLessThanOrEqual(1)
  }
  await page.screenshot({ path: `${SHOTS}/issues_apart.png`, fullPage: true })
  // the overview: the pages by category, each count opening exactly its pages
  await page.goto('/#/overview')
  await settled(page, OVERVIEW_LOADS)
  const box = page.locator('[data-section="Page category"] tr[data-value="exercise"] [data-kb="free"] a')
  const count = Number(await box.textContent())
  await box.click()
  await expect(page).toHaveURL(/category=exercise/)
  await settled(page)
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(count)
})

// The operator on accounting p. 524: its head "reads as code", and its readings said "attempt 0, 1, 0, 2". The sentence and each
// reading's number and words are the API's, the core's words for what a reading was (86efdb2); checked against its JSON
test('a page not served says why in one sentence first, and its readings stand numbered, each saying what it was', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Shown = { said: string | null, attempts: { number: number, purpose: string, attempt: number, shown: boolean, prototype: boolean | null }[] }
  const api = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/524`)).json() as Shown
  expect(api.said).toMatch(/^Not served: .+; the PDF's text layer is served instead\.$/)
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/524`)
  await settled(page)
  const said = page.locator('[data-part="said"]')
  await expect(said).toHaveText(api.said!)
  // the sentence stands first, above the chips
  const [sentence, chips] = await Promise.all([said.boundingBox(), page.locator('.summary').boundingBox()])
  expect(sentence!.y).toBeLessThan(chips!.y)
  // the shown reading first, the others newest first, each by its number across readers and in the core's words; a reader
  // prototype's reading stands in the Lab, not here (210.a)
  const pipeline = api.attempts.filter(one => !one.prototype)
  const inOrder = [...pipeline.filter(one => one.shown), ...pipeline.filter(one => !one.shown).reverse()]
  await expect(page.locator('.history .reading-number')).toHaveText(inOrder.map(one => `reading ${one.number}`))
  await expect(page.locator('.history [data-part="purpose"]')).toHaveText(inOrder.map(one => one.purpose))
  // the reader's own count stands folded inside, not in the line
  await expect(page.locator('.history .current [data-part="reader-attempt"]')).toContainText(`the reader's attempt ${inOrder[0].attempt}`)
  await page.screenshot({ path: `${SHOTS}/page_not_served.png` })
})

test('a table wider than its column stays inside the column', async ({ page }) => {
  await page.goto(`/#/free/sources/${FINANCE}/page/119`)
  await settled(page)
  // the page opens on its reading, as every page does (227.a)
  await expect(page.locator('.mode button', { hasText: 'readable' })).toHaveAttribute('aria-pressed', 'true')
  const overflow = await page.locator('.reading').evaluate(reading => {
    const edge = reading.getBoundingClientRect().right
    return [...reading.querySelectorAll('.table-scroll')].map(scroller => scroller.getBoundingClientRect().right - edge)
  })
  expect(overflow.length).toBeGreaterThan(0)
  expect(Math.max(...overflow)).toBeLessThanOrEqual(1)
})

test('a block under the pointer is framed on the original exactly where the reader placed it', async ({ page, request }) => {
  type Detail = { trace: { image_size: number[] }, reading: { blocks: { id: string, bbox: number[] | null }[] } }
  const detail = await (await request.get(`/api/free/works/${KELLY}/pages/7`)).json() as Detail
  const [width, height] = detail.trace.image_size
  const placed = detail.reading.blocks.filter(block => block.bbox)
  await page.goto(`/#/free/sources/${KELLY}/page/7`)
  await settled(page)

  // the first table: its frame must sit on the image's pixels the reader named, within two pixels
  const table = placed.find(block => block.id === 'b04') ?? placed[0]
  await page.locator(`[data-block="${table.id}"]`).hover()
  const frame = page.locator(`[data-box="${table.id}"]`)
  await expect(frame).toBeVisible()
  const image = (await page.locator('.page-frame img').boundingBox())!
  const drawn = (await frame.boundingBox())!
  const [x0, y0, x1, y1] = table.bbox!
  expect(Math.abs(drawn.x - (image.x + x0 / width * image.width))).toBeLessThanOrEqual(2)
  expect(Math.abs(drawn.y - (image.y + y0 / height * image.height))).toBeLessThanOrEqual(2)
  expect(Math.abs(drawn.width - (x1 - x0) / width * image.width)).toBeLessThanOrEqual(2)
  expect(Math.abs(drawn.height - (y1 - y0) / height * image.height)).toBeLessThanOrEqual(2)
  // its stroke stands outside the box: a box hugs the printed text, and a stroke drawn inside it covered the glyphs' outer
  // pixels, which read as a box a little off (the operator, 18 Nov)
  expect(await frame.evaluate(element => {
    const style = getComputedStyle(element)
    return [style.borderTopWidth, style.borderLeftWidth, style.outlineWidth, style.outlineStyle]
  })).toEqual(['0px', '0px', '2px', 'solid'])
  await page.screenshot({ path: `${SHOTS}/page_box.png` })

  // the last placed block lies low on the page: its frame is brought into the original's view
  const last = placed.at(-1)!
  await page.locator(`[data-block="${last.id}"]`).scrollIntoViewIfNeeded()
  await page.locator(`[data-block="${last.id}"]`).hover()
  await expect(page.locator(`[data-box="${last.id}"]`)).toBeInViewport()
  await page.screenshot({ path: `${SHOTS}/page_box_low.png` })
})

test('formulas are typeset with KaTeX and its fonts arrive', async ({ page }) => {
  await page.goto(`/#/free/sources/${KELLY}/page/4`)
  await settled(page)
  await expect(page.locator('.katex-display').first()).toBeVisible()
  await expect(page.locator('.katex-error')).toHaveCount(0)
  expect(await page.evaluate(() => document.fonts.ready.then(() => document.fonts.check('16px KaTeX_Main')))).toBe(true)
  await page.locator('.reading').screenshot({ path: `${SHOTS}/page_formulas.png` })
})

test('the raw reading is shown as text, exactly as stored', async ({ page }) => {
  await page.goto(`/#/free/sources/${KELLY}/page/4`)
  await settled(page)
  await page.locator('.mode button', { hasText: 'raw' }).click()
  await expect(page.locator('pre.raw')).toContainText(':::')
})

// 228.a (the operator on accounting p. 398: "then the only thing that still confuses me is that the error stands at the top, although I entered a correction"; on p. 338: "line 86? then please line numbers in the read-only editor too"): a validator's error stands on
// the block it names, in a finding's look, muted and saying so where a person has looked; each error in the list above
// jumps to its block and opens the raw text at its line, marked, the lines numbered as the validator counts them in a
// gutter the copied text leaves out
test('a validator\'s error stands on its block, muted once a person looked, and opens the raw text at its numbered line', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Placed = { said: string, message: string, block: string | null, line: number | null, at_line?: number | null, looked: string | null,
    corrected: boolean }
  type Detail = { raw: string, reading: { error_places: Placed[] } }
  const colour = (selector: string) => page.locator(selector).first().evaluate(element => getComputedStyle(element).color)
  const p398 = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/398`)).json() as Detail
  const b04 = p398.reading.error_places.find(error => error.block === 'b04')
  test.skip(!b04 || !b04.looked, 'accounting p. 398 holds no error on b04 a person looked at today')
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/398`)
  await settled(page)
  // on its block: the flag and the message, muted, saying who looked
  const onBlock = page.locator('[data-block="b04"] [data-part="block-errors"] li').first()
  await expect(onBlock.locator('.error-message')).toHaveText(b04!.message)
  await expect(onBlock.locator('[data-part="error-looked"]')).toHaveText(`a person noted${b04!.corrected ? ' and corrected' : ''} b04`)
  expect(await colour('[data-block="b04"] [data-part="block-errors"] .error-message')).toBe(await colour('[data-block="b04"] .block-head'))
  // in the list: the error as the validator wrote it, muted the same way, its block a jump and its line a way to the raw text
  const listed = page.locator('[data-part="parse-errors"] li').first()
  await expect(listed.locator('.error-said')).toHaveText(b04!.said)
  await expect(listed.locator('[data-part="error-looked"]')).toContainText('a person noted')
  await page.locator('[data-part="parse-errors"]').screenshot({ path: `${SHOTS}/errors_listed.png` })
  await onBlock.locator('[data-part="show-raw"]').click()
  // the raw text opens at the fault's own line where page/1.4 names it in its message, else at the line the block opens on
  const at = b04!.at_line ?? b04!.line
  const marked = page.locator('pre.raw .raw-line.marked')
  await expect(marked).toHaveAttribute('data-line', String(at))
  await expect(page.locator(`pre.raw .raw-line[data-line="${b04!.line}"]`)).toContainText('#b04')
  await expect(marked).toBeInViewport()
  // every line an error names, marked as the API spans it (its block, from the opening fence to the closing one), here
  // quietly, as a person has looked at b04's error; the core's own data, where the unit tests invent theirs
  const spanned = new Set((p398.reading.error_places as (Placed & { lines?: number[] | null })[]).flatMap(error => {
    const [from, to] = error.lines ?? (error.line ? [error.line, error.line] : [1, 0])
    return [...Array.from({ length: to - from + 1 }, (_, step) => from + step), ...(error.at_line ? [error.at_line] : [])]
  }))
  await expect(page.locator('pre.raw [data-error-line]')).toHaveCount(spanned.size)
  await expect(page.locator(`pre.raw .raw-line[data-line="${at}"]`)).toHaveAttribute('data-error-line', 'error-looked')
  // the gutter's number is the line's, and none of it is text: the pre holds the reading as stored, a selection copies it
  expect(await marked.evaluate(line => getComputedStyle(line, '::before').content)).toBe(`"${at}"`)
  expect(await page.locator('pre.raw').evaluate(pre => pre.textContent)).toBe(p398.raw)
  const copied = await page.locator('pre.raw').evaluate(pre => {
    const range = document.createRange()
    range.selectNodeContents(pre)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    return selection.toString()
  })
  expect(copied.replace(/\n+$/, '')).toBe(p398.raw.replace(/\n+$/, ''))
  await page.locator('pre.raw').screenshot({ path: `${SHOTS}/raw_numbered.png` })
})

test('a validator\'s error nobody looked at stands red, on its block and in the raw text as a compiler marks it', async ({ page, request }) => {
  // accounting p. 338 as read until 18 Nov, when a valid direct reading replaced it: skipped while no free page holds such
  // errors; the unit tests hold the marks on an invented reading
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Placed = { said: string, message: string, block: string | null, line: number | null, at_line?: number | null, looked: string | null,
    corrected: boolean }
  type Detail = { raw: string, reading: { error_places: Placed[] } | null }
  const colour = (selector: string) => page.locator(selector).first().evaluate(element => getComputedStyle(element).color)
  const p338 = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/338`)).json() as Detail
  test.skip(!p338.reading, 'accounting p. 338 has no reading today')
  const lineOnly = p338.reading!.error_places.find(error => !error.block && error.line)
  const b13 = p338.reading!.error_places.find(error => error.block === 'b13')
  test.skip(!lineOnly || !b13 || Boolean(b13.looked), 'accounting p. 338 holds no such errors today')
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/338`)
  await settled(page)
  expect(await colour('[data-block="b13"] [data-part="block-errors"] .error-message')).not.toBe(await colour('[data-block="b13"] .block-head'))
  await expect(page.locator('[data-block="b13"] [data-part="error-looked"]')).toHaveCount(0)
  const alone = page.locator('[data-part="parse-errors"] li', { hasText: lineOnly!.said })
  await expect(alone.locator('[data-part="error-block"]')).toHaveCount(0)
  await alone.locator('[data-part="show-raw"]').click()
  await expect(page.locator('pre.raw .raw-line.marked')).toHaveAttribute('data-line', String(lineOnly!.line))
  await expect(page.locator('pre.raw .raw-line.marked')).toBeInViewport()
  // as a compiler marks an error (line 1's A.a, 18 Nov): b13's whole block from its opening fence to its closing one, the
  // named line strongest and in the error's colour, and the line named alone; nothing else
  const [first, last] = (b13 as Placed & { lines: number[] }).lines
  const named = page.locator(`pre.raw .raw-line[data-line="${b13!.at_line ?? b13!.line}"]`)
  await expect(named).toHaveAttribute('data-error-line', 'error-named')
  await expect(page.locator(`pre.raw .raw-line[data-line="${last}"]`)).toHaveAttribute('data-error-line', 'error-block')
  await expect(page.locator(`pre.raw .raw-line[data-line="${last}"]`)).toHaveText(/^:::\s*$/)
  expect(first).toBe(b13!.line)
  const marked338 = new Set((p338.reading!.error_places as (Placed & { lines: number[] | null })[]).flatMap(error => {
    const [from, to] = error.lines ?? (error.line ? [error.line, error.line] : [1, 0])
    return Array.from({ length: to - from + 1 }, (_, at) => from + at)
  }))
  await expect(page.locator('pre.raw [data-error-line]')).toHaveCount(marked338.size)
  expect(await named.evaluate(line => getComputedStyle(line, '::before').color)).toBe(await colour('[data-part="parse-errors"] li'))
  await named.scrollIntoViewIfNeeded()
  await page.locator('pre.raw').screenshot({ path: `${SHOTS}/raw_error_block.png` })
})

test('a page without a reading opens on the text the search and the chat quote, its one choice', async ({ page, request }) => {
  // the Kelly paper's page 3: the provider blocked its reading, so its text layer is quoted
  const quoted = await (await request.get(`/api/free/works/${KELLY}/pages/3/quoted`)).json() as { text: string | null }
  test.skip(!quoted.text, 'the core holds no quoted text for this page')
  await page.goto(`/#/free/sources/${KELLY}/page/3`)
  await settled(page)
  await expect(page.locator('.mode button')).toHaveText(['quoted'])
  await expect(page.locator('.mode button', { hasText: 'quoted' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.quoted-from')).toContainText('text layer')
  await expect(page.locator('.quoted-text')).toHaveText(quoted.text!)
  await page.screenshot({ path: `${SHOTS}/page_quoted.png` })
})

// 227.a (the operator, 12 Nov): every page with a reading opens on it, one served from its text layer too, so the switch a person
// uses page after page never moves; the head says what is served, and the quoted text is one click away. Accounting
// p. 398 is served from its text layer (its reading stayed malformed), Kelly p. 4 from its reading
test('a page served from its text layer opens on its reading as a served page does, the quoted text a click away', async ({ page, request }) => {
  const ACCOUNTING = 'openstax_principles_of_accounting_v1'
  type Detail = { from_text_layer: boolean, reading: unknown | null }
  const textLayer = await (await request.get(`/api/free/works/${ACCOUNTING}/pages/398`)).json() as Detail
  test.skip(!textLayer.from_text_layer || !textLayer.reading, 'accounting p. 398 is no longer a text-layer page with a reading')
  for (const [work, number] of [[ACCOUNTING, 398], [KELLY, 4]] as const) {
    await page.goto(`/#/free/sources/${work}/page/${number}`)
    await settled(page)
    await expect(page.locator('.mode button')).toHaveText(['readable', 'raw', 'quoted'])
    await expect(page.locator('.mode button', { hasText: 'readable' })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.quoted-text')).toHaveCount(0)
  }
  // on the text-layer page the head says what is served, and the quoted text is one click away
  await page.goto(`/#/free/sources/${ACCOUNTING}/page/398`)
  await settled(page)
  await expect(page.locator('[data-part="page-facts"]')).toContainText('text layer')
  await page.locator('.mode button', { hasText: 'quoted' }).click()
  await expect(page.locator('.quoted-from')).toContainText('text layer')
  await page.screenshot({ path: `${SHOTS}/page_text_layer_readable.png` })
})

test('a finding of the judge stands beneath the block it names, and the line above leads to it', async ({ page, request }) => {
  // a page chosen by its state when the check runs, not by its number: a person's walk changes the real pages
  type Issue = { source_id: string, pdf_page: number, from_text_layer: boolean, focus: string | null }
  const issues = (await (await request.get('/api/issues')).json() as { rows: Issue[] }).rows
  const chosen = issues.find(row => row.from_text_layer && row.focus)
  test.skip(!chosen, 'the export holds no page served from its text layer with a finding on a block')
  const detail = await (await request.get(`/api/free/works/${chosen!.source_id}/pages/${chosen!.pdf_page}`)).json() as {
    reading: { blocks: { id: string, findings: unknown[] }[] } | null
  }
  const named = detail.reading?.blocks.find(block => block.findings.length > 0)
  test.skip(!named, 'the export holds no finding with a block on this page')
  await page.goto(`/#/free/sources/${chosen!.source_id}/page/${chosen!.pdf_page}`)
  await settled(page)
  // a page the judge found bad is served from its text layer, and opens on its reading as every page does (227.a)
  await expect(page.locator('.mode button', { hasText: 'readable' })).toHaveAttribute('aria-pressed', 'true')
  const block = page.locator(`[data-block="${named!.id}"]`)
  await expect(block.locator('.block-findings [data-finding]')).toHaveCount(named!.findings.length)
  await page.locator('.found-at button', { hasText: named!.id }).click()
  await expect(block).toHaveClass(/highlighted/)
  // marked is not enough: the reader has to see it without searching, from its start: its top in the window. A share of the
  // block stood for that before the page's record grew to labelled lines (184); a tall block below them shows its start,
  // not half of itself, and the window must not move
  const startInView = async () => {
    const box = (await block.boundingBox())!
    expect(box.y).toBeGreaterThanOrEqual(-1)
    expect(box.y).toBeLessThan(page.viewportSize()!.height - 40)
  }
  await startInView()
  // and only the reading's column scrolls: the window stays, so the line and the pointer above stay in sight
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  await expect(page.locator('.summary')).toBeInViewport()
  // a pixel of slack: the scroll lands the top on a subpixel (measured -0.22 px)
  expect((await block.boundingBox())!.y).toBeGreaterThanOrEqual(-1)
  await page.screenshot({ path: `${SHOTS}/page_finding.png` })

  // a second click brings the block back after the reader scrolled away, and so does a click from the raw text
  await page.locator('.reading').evaluate(reading => reading.scrollTo({ top: reading.scrollHeight }))
  await expect(block).not.toBeInViewport()
  await page.locator('.found-at button', { hasText: named!.id }).click()
  await expect(block).toBeInViewport()
  await startInView()
  await page.locator('.mode button', { hasText: 'raw' }).click()
  await page.locator('.found-at button', { hasText: named!.id }).click()
  await expect(block).toBeInViewport()
  await startInView()
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
})

test('a question finds its pages, each with its page numbers and route, and opens the page beside its original', async ({ page }) => {
  // the first search after the start waits for the index, which the server builds as it comes up: about 20 s, free alone
  test.setTimeout(150_000)
  await page.goto('/#/search?q=kelly%20criterion%20growth%20rate')
  await expect(page.locator('[data-hit]').first()).toBeVisible({ timeout: 120_000 })
  await expect(page.locator('[data-hit] .route').first()).not.toBeEmpty()
  await page.screenshot({ path: `${SHOTS}/search.png` })
  await page.locator('[data-hit] a.hit-title').first().click()
  await expect(page).toHaveURL(/#\/free\/sources\/.+\/page\/\d+$/)
  await settled(page)
  await expect(page.locator('.original img')).toBeVisible()
})

test('a question no page answers says so, as an answer', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/#/search?q=xylophonequartzbanjo')
  await expect(page.locator('.nothing')).toContainText('Nothing found', { timeout: 120_000 })
})

type IssueRow = { knowledge_base: string, source_id: string, pdf_page: number, route: string, from_text_layer: boolean,
  route_why: string | null, check: { state: string }, listed_state: string }

// The operator's 24.a: the walk through the issues goes page, back, next page; the choice made above the list must survive it
test('the issues list the pages to look at, one click from each, and keep their choice on the way back', async ({ page, request }) => {
  const issues = await (await request.get('/api/issues')).json() as { rows: IssueRow[] }
  test.skip(issues.rows.length === 0, 'no page needs a look on this machine')
  await page.goto('/#/issues')
  await settled(page)
  await expect(page.locator('.view-title')).toHaveText('Issues')
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(issues.rows.length)
  // a state the open list holds, as the facet narrows by it: the state a page is listed in (211.a)
  const state = issues.rows.find(row => row.listed_state !== 'decided_by_a_person')!.listed_state
  const chosen = issues.rows.filter(row => row.listed_state === state).length
  await page.locator(`[data-facet="state"] [data-value="${state}"]`).click()
  await expect(page).toHaveURL(new RegExp(`#/issues\\?state=${state}$`))
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(chosen)
  await page.locator('tbody tr[data-page] a').first().click()
  await expect(page).toHaveURL(/#\/free\/sources\/.+\/page\/\d+$/)
  await page.goBack()
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(chosen)
  await page.screenshot({ path: `${SHOTS}/issues.png` })
})

// The operator's 25.a: a reading the judge found bad that the search serves all the same says why, by its route
test('a page the judge found bad but whose reading is served says why in the issues', async ({ page, request }) => {
  const issues = await (await request.get('/api/issues')).json() as { rows: IssueRow[] }
  // an open one where there is, else one a person settled, in its fold (211.a): its row says the same
  const candidates = issues.rows.filter(row => row.check.state === 'issue' && !row.from_text_layer)
  const served = candidates.find(row => row.listed_state === 'issue') ?? candidates[0]
  test.skip(!served, 'the export holds no issue whose reading is served')
  await page.goto('/#/issues')
  await settled(page)
  if (served!.listed_state === 'decided_by_a_person') await page.locator('[data-part="decided"] > summary').click()
  const row = page.locator(`[data-page="${served!.knowledge_base}/${served!.source_id}/${served!.pdf_page}"]`)
  // the route's why on the row, the whole route in its card (159.a, 203.a), no browser tooltip
  const why = served!.route_why ?? served!.route
  await expect(row.locator('.why')).toHaveText(why)
  await expect(row.locator('.why [title]')).toHaveCount(0)
  await row.locator('.why .route-why').hover()
  await expect(page.locator('[data-part="hover-card"] [data-row="route"] .card-value')).toHaveText(served!.route)
  await row.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/issues_served_despite.png` })
})

// The chat in the browser check: the app runs with --no-chat, so these answers come from the browser and no check reaches
// a model. Invented words over a free work, so the screenshot holds no licensed text.
const CHAT_TURN = {
  kind: 'knowledge', turn_id: 'a1b2c3d4', question: 'What is the Kelly criterion?', text: '', server: null, usd: 0.0031,
  seconds: 11.2, model_calls: 2, call_limit_reached: null, logged: true,
  turn: {
    behaviour: 'answer', answer: 'The Kelly criterion sizes a bet as a **fraction** of wealth [1].', gaps: null, follow_up: null,
    disclaimer: 'Not trading advice. For educational purposes only.',
    quotes: [{ passage: 1, text: 'the optimal strategy is to bet a fraction of wealth',
      citation: { text: 'Practical Implementation of the Kelly Criterion · p. 3', link: null, licence: 'CC BY 4.0' },
      view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } }],
    sources: [{ number: 1, work: KELLY, page: { label: '3', pdf: '3', printed: null },
      citation: { text: 'Practical Implementation of the Kelly Criterion · p. 3', link: null, licence: 'CC BY 4.0' },
      view: { knowledge_base: 'free', source_id: KELLY, pdf_page: 3 } }],
  },
  security: [{ check: 'input', name: 'Input check: not empty, not too long', status: 'passed', detail: '28 characters' }],
}

test('the chat answers, each quote word for word, and a quote opens the page it comes from', async ({ page }) => {
  await page.route('**/api/chat', route => route.request().method() === 'GET'
    ? route.fulfill({ json: { enabled: true, why_not: null, examples: ['What is the Kelly criterion?', 'What is a maximum drawdown?'] } })
    : route.fulfill({ json: CHAT_TURN }))
  await page.goto('/#/chat')
  await settled(page)
  await page.locator('.examples button').first().click()
  await expect(page.locator('textarea')).toHaveValue('What is the Kelly criterion?')
  await page.locator('textarea').press('Enter')
  await expect(page.locator('.chat-turn .quote-text')).toHaveText('the optimal strategy is to bet a fraction of wealth')
  await expect(page.locator('.chat-turn .answer strong')).toHaveText('fraction')
  await page.screenshot({ path: `${SHOTS}/chat.png` })
  await page.locator('.quote a.open').click()
  await expect(page).toHaveURL(new RegExp(`#/free/sources/${KELLY}/page/3$`))
})

// 164.a: a quote from an HTML section opens its article, scrolled to the section, beside the source's own page; the
// section is a real one of the index, its words in the fixture invented
test('a quote from an HTML section opens its article at that section', async ({ page, request }) => {
  const WIKIPEDIA = 'wikipedia_trading_set'
  const work = await (await request.get(`/api/free/html/${WIKIPEDIA}`)).json() as {
    why_not: string | null, outline: { title: string, parent: string | null, id: string, label: string | null }[]
  }
  test.skip(Boolean(work.why_not), 'no search index on this machine, as on a clone')
  const sharpe = work.outline.find(node => node.title === 'Sharpe ratio' && node.parent === null)
  const history = work.outline.find(node => node.title === 'History' && node.parent === sharpe?.id)
  test.skip(!history?.label, 'the index holds no Sharpe ratio history')
  const article = { knowledge_base: 'free', source_id: WIKIPEDIA, label: history!.label }
  const citation = { text: 'Sharpe ratio (Wikipedia) · History', link: 'https://en.wikipedia.org/wiki/Sharpe_ratio#History', licence: 'CC BY-SA 4.0' }
  const turn = { ...CHAT_TURN, turn: { ...CHAT_TURN.turn, answer: 'Sharpe developed it in 1966 [1].',
    quotes: [{ passage: 1, text: 'In 1966, William F. Sharpe developed the ratio.', citation, view: null, article }],
    sources: [{ number: 1, work: WIKIPEDIA, page: { label: history!.label, pdf: null, printed: null }, citation, view: null, article }] } }
  await page.route('**/api/chat', route => route.request().method() === 'GET'
    ? route.fulfill({ json: { enabled: true, why_not: null, examples: ['What is the Sharpe ratio?'] } })
    : route.fulfill({ json: turn }))
  await page.goto('/#/chat')
  await settled(page)
  await page.locator('textarea').fill('Who developed the Sharpe ratio?')
  await page.locator('textarea').press('Enter')
  const quote = page.locator('.chat-turn .quote')
  await expect(quote.locator('a.open')).toHaveText(['open the source', 'open in the article'])
  await quote.locator('[data-part="article"]').click()
  await expect(page).toHaveURL(new RegExp(`#/free/html/${WIKIPEDIA}/${history!.label}$`))
  await settled(page)
  const entry = page.locator(`[data-entry="${history!.label}"]`)
  await expect(entry).toHaveClass(/chosen/)
  await expect(entry).toBeInViewport()
  await page.screenshot({ path: `${SHOTS}/chat_article.png` })
})

test('without its fixtures the chat in the browser check is switched off, so no check can reach a model', async ({ page }) => {
  await page.goto('/#/chat')
  await settled(page)
  await expect(page.locator('.switched-off')).toContainText('--no-chat')
})

test('the calls list who asked what, and an answered page opens its view', async ({ page, request }) => {
  type Answered = { view: { pdf_page: number } | null }
  const listed = await (await request.get('/api/calls')).json() as { why_not: string | null, calls: { answered: Answered[] }[] }
  test.skip(Boolean(listed.why_not), 'no call log on this machine, as on a clone')
  await page.goto('/#/calls')
  await settled(page)
  await expect(page.locator('.call-rows tbody tr')).toHaveCount(listed.calls.length)
  await page.screenshot({ path: `${SHOTS}/calls.png` })
  // a page's link: a call that answered with a work (its contents, say) links to the work, which is no page (16 Nov)
  const linked = page.locator('.answered:not(details) a[href*="/page/"]').first()
  test.skip(await linked.count() === 0, 'no listed call names a page the export holds on its line')
  await linked.click()
  await expect(page).toHaveURL(/\/page\/\d+$/)
})

// The view's part is that a reason opens the work's pages on that reason's route; that the shelf's count and the export's
// routes agree is the core's, pinned by its own test. The two can part for a while on a machine where the shelf was built
// from an export not yet committed, so the check counts the pages on that route as the API serves them.
test('the shelf shows every work, and a reason opens the work\'s pages on exactly that reason\'s route', async ({ page, request }) => {
  type Reason = { reason: string, count: number, route: string | null }
  type Row = { source_id: string | null, has_pages: boolean, not_passed: Reason[] }
  const shelf = await (await request.get('/api/shelf')).json() as { bases: { knowledge_base: string, why_not: string | null, works: Row[] }[] }
  const free = shelf.bases.find(base => base.knowledge_base === 'free')!
  test.skip(Boolean(free.why_not), 'no shelf built on this machine, as on a clone')
  await page.goto('/#/shelf')
  await settled(page)
  await expect(page.locator('[data-kb="free"] .shelf-rows tbody tr')).toHaveCount(free.works.length)
  await page.screenshot({ path: `${SHOTS}/shelf.png` })
  const row = free.works.find(work => work.has_pages && work.not_passed.some(reason => reason.route))
  test.skip(!row, 'no free work has a reason to open')
  const reason = row!.not_passed.find(item => item.route)!
  const pages = (await (await request.get(`/api/free/works/${row!.source_id}/pages`)).json() as { pages: { route: string }[] }).pages
  await page.locator(`[data-kb="free"] [data-work="${row!.source_id}"] a[data-reason="${reason.reason}"]`).click()
  await settled(page)
  await asTable(page)
  await expect(page.locator('tbody tr[data-page]')).toHaveCount(pages.filter(item => item.route === reason.route).length)
})

test('an automated review\'s verdict is named so, never a person\'s, and settles its page in a fold of its own (18 Nov)', async ({ page, request }) => {
  // the operator's 2.a and 3.a: "a person is always manual"; Regulation NMS 600 p. 4 holds the free base's one delegated accept
  const NMS = 'sec_regulation_nms_rule_600_2025'
  type Detail = { person: { by_a_person: boolean } | null, protected: boolean | null, listed_state: string | null }
  const detail = await (await request.get(`/api/free/works/${NMS}/pages/4`)).json() as Detail
  test.skip(!detail.person || detail.person.by_a_person, 'Regulation NMS 600 p. 4 holds no automated review today')
  await page.goto(`/#/free/sources/${NMS}/page/4`)
  await settled(page)
  const facts = page.locator('[data-part="page-facts"]')
  await expect(facts.locator('[data-label="Automated review"] [data-icon="review"]')).toBeVisible()
  await expect(facts.locator('[data-label="A person"]')).toHaveCount(0)
  await expect(page.locator('[data-part="protected"]')).toHaveCount(detail.protected ? 1 : 0)
  await facts.screenshot({ path: `${SHOTS}/page_automated_review.png` })
  if (detail.listed_state !== 'decided_by_an_automated_review') return
  await page.goto('/#/issues')
  await settled(page)
  await expect(page.locator(`[data-part="reviewed"] tr[data-page="free/${NMS}/4"]`)).toHaveCount(1)
  await expect(page.locator(`[data-part="decided"] tr[data-page="free/${NMS}/4"]`)).toHaveCount(0)
})

test('the sources table fits the window at 1,280 and 2,000 px, its last column inside it (18 Nov)', async ({ page }) => {
  // the operator, on a 2,000 px window: the licence column was cut and the table's scroll bar lay out of sight at the
  // list's end. An invented work with the longest fields a licensed row has, so the check holds whatever the export holds
  const long = { knowledge_base: 'licensed', id: 'an_invented_work_whose_file_stem_runs_long_without_a_single_space_in_it',
    title: 'An Invented Work With a Title Long Enough to Wrap Over Two or Three Lines of Its Column',
    authors: 'First Author, Second Author, Third Author, Fourth Author', publisher: 'An Invented Publishing House of Some Length',
    year: 2001, edition: '12th', licence: 'private copy (licensed)', format: 'epub', shelf: 'trading_finance',
    notes: 'stand-in file; re-typeset copy; printed pages differ', readings: null, sections: null, chunks: null,
    structure_why_not: null, not_read: 'not read page by page' }
  await page.route('**/api/works', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, json: [...await response.json() as object[], long] })
  })
  for (const width of [1280, 2000]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/#/sources')
    await settled(page)
    const last = (await page.locator('table.works thead th').last().boundingBox())!
    expect(last.x + last.width, `the last column at ${width} px`).toBeLessThanOrEqual(width)
    expect(await page.locator('.data-scroll').evaluate(box => box.scrollWidth <= box.clientWidth), `a hidden scroll at ${width} px`).toBe(true)
  }
  await page.screenshot({ path: `${SHOTS}/sources_fit.png` })
})
