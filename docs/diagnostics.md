# The diagnostics frontend

A web interface that makes the pipeline visible and traceable. Its purpose: from a reported fault, say a chunk that ends in
mid-sentence, one click to the source, its original beside its conversion, and the code version that made it. It is not a
pipeline stage: it reads what the stages wrote. **It is read-only unless started with `--allow-verdicts`; then it has one
write route, local only, Origin-checked, append-only:** a person's verdict on a page's reading, recorded by the core (see
*A person's verdict from the page view* below). The Streamlit chat demo stays as it is (→ now: removed on 17 Nov 2026, decision 286.a; the chat lives in this view).

```bash
python -m backend.diagnostics            # serves the UI and its API on http://127.0.0.1:8001 (loopback only)
python -m backend.diagnostics --public-only   # the free knowledge base alone: the licensed one is never read
python -m backend.diagnostics --allow-verdicts   # a page takes a person's verdict; off by default
python -m backend.diagnostics.build      # developers only, needs Node.js: schema, types, type-check, build, stamp
```

In `src/frontend/diagnostics/`: `npm ci` once, then `npm run dev` (port 5174, `/api` forwarded to 8001), `npm run test`,
`npm run lint:check`, `npm run knip`, and `npm run test:e2e`: the built UI in a real browser (Playwright; its browser once
with `npx playwright install chromium`), which leaves screenshots of every view in `test-results/views/`.

## V0.5: the scaffold

### Plan

**What.** One view, the works of the catalog, carried through the whole chain once, so every later view only adds to it:

1. a pydantic model in a FastAPI route (`src/backend/diagnostics/`),
2. the OpenAPI schema FastAPI derives from it, committed as `src/frontend/diagnostics/openapi.json`,
3. TypeScript types generated from that schema by `openapi-typescript`,
4. a Vue view that reads them,
5. a build stamped with one hash over its inputs, committed in `dist/` and served by the same Python process.

**Which technique.** Outside the course, which teaches no interface technique; Streamlit appears in the briefs only.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| More Streamlit pages | The agents-sprint review asked for a frontend beyond Streamlit, and a rerun of the whole script on every click makes a click-through view slow |
| FastAPI with server-rendered HTML and HTMX, no build step | Proposed first. Vue won because the author knows it, and the components, colour tokens and test patterns of the author's existing Vue project can be reused |
| Next.js as a static export | A static export drops what makes Next.js worth it (server rendering, API routes) and keeps a heavier toolchain |
| The reviewer installs Node | `pip install -r requirements.txt` is the only install a reviewer makes. The build is committed instead, and a contract test keeps it current |
| TypeScript types written by hand | They drift from the Python models without a sound. Generated types turn a renamed field into a type error |

**Gates.**

- The chain runs end to end from one command, and the API serves the built UI without Node.
- A contract test recomputes the build's hash in Python, offline, and fails when any input changed after the last build. Line
  endings are normalised, so a clone with `core.autocrlf=true` passes too.
- A test fails when the committed schema differs from what the API serves.
- The views have their states: loading, empty, populated, failed.

### Report

**Done.** The API serves `GET /api/works` and the UI at `/`. The view lists the eight works of the catalog. The colour tokens,
the button and the icon component come from the author's existing Vue project.

**Measured on 2026-11-02:**

- pytest 786 passed (774 before, 12 new).
- Vitest 20 passed. ESLint and knip report nothing.
- The bundle is 157 kB, 60 kB gzipped. A build takes about 2 s.
- A rebuild after a fresh install of every package produced the same bundle file name, so the same content.
- Against the running process: the page, its script, `/api/works` with 8 works and `/docs` all answered 200.

**Found on the way:**

- **The catalog's Wikipedia set has no year** (`null`), and the first test against the real catalog failed on it. The model
  says `int | None` now, and the generated type became `number | null` by itself: the first change the generated types carried.
- **npm chose TypeScript 7**, the native compiler, which `vue-tsc` (below 7), `openapi-typescript` (5.x) and `typescript-eslint`
  (below 6.1) do not support yet. Pinned to 5.9.3.
- **`npm audit`:** 20 moderate findings, all in development tools (minimatch and glob under ESLint, js-beautify under Vue Test
  Utils, Redocly under openapi-typescript). The runtime packages that enter the build have none.

**Not verified:** the UI in a real browser beyond the HTTP checks. A browser test (Playwright) comes with the first view
worth a screenshot.

## V1: from a work to a page, and the bin

### Plan

**What.** From a work to its pages, and from a page one click to its original beside its reading, with the reading's trace
and the judge's verdict. A bin lists the pages a person should look at: the judge's bin, the readings the provider blocked,
a stopped work's pages. Within the capstone it stands in for tickets, which come later.

**The data is tracked, so every view works on a clone.** `corpus/readings/index.json` holds one row per free PDF page with
its reading's trace and check, `corpus/readings/<work>/pNNNN.md` the reading, `corpus/raw/` the PDFs. The core's own parser
(`page_contract.parse`) turns a reading into blocks, and the core's own renderer (`page_render.render`) gives the original.

**Which technique.** Outside the course, as V0.5.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| Read the private reading store | Nothing would show on a clone. The export carries what the views need |
| The model's table HTML through a sanitiser (DOMPurify) | Model output is untrusted input. A table built from the parser's cells needs no sanitiser, and the cells are what the pipeline checked against the text layer |
| A Markdown parser in the browser | A second parser could show a page differently from how the core understood it |
| Serve the stored input image | It lives in the private store. A fresh render from the tracked PDF is byte for byte the same image (measured) |
| The latest KaTeX | Pinned to 0.19.1, the version the core checks formulas with, so a formula renders as it was checked |

**Gates.**

- The original is shown only with the comparison of its sha256 against the image the reader received.
- No text of the model reaches the page as markup: prose comes as text, math and code segments, a table as cells, the raw
  reading as escaped text. KaTeX's own markup, with `trust` off, is the one exception.
- Every figure on screen is a field the API served; the UI filters lists, it counts nothing.
- Every view has its states: loading, empty, populated, failed.

### Report

**Done.** New API routes: `GET /api/works/{source_id}/pages`, `GET /api/works/{source_id}/pages/{pdf_page}` with its
`image.png`, and `GET /api/bin` (**→ now** `/api/<knowledge base>/works/...` and `/api/issues`, V1.2); `GET /api/works`
also gives each work's states and routes. Views: a work's page list with
a facet bar over state and route, the page view (original and reading side by side, readable or raw, check and trace below),
and the bin. A finding of the judge that names a block marks that block in the reading.

**Measured on 2026-11-04:**

- A fresh render matched the image the reader received byte for byte on four pages of four works.
- A page's detail, the render included, took 143 ms against the running process.
- 973 page rows for the largest work, 84 rows in the bin (40 in the judge's bin, 44 blocked).
- The bundle grew to 436 kB of script (144 kB gzipped) and, with KaTeX's fonts, 1.5 MB in 63 files.

**Found on the way:**

- **The reading index named works differently from the catalog** (`openstax-finance-2e` against
  `openstax_principles_of_finance_2e`). Instead of a mapping in this API, the core's export now carries `source_id`, and with
  it each page's `route`, the string its search hits carry.
- **The judge's findings were exported as kinds only.** The export now carries each finding's block, severity and evidence,
  which lets a finding mark its block.
- **The contract test for imports read git-ignored files:** KaTeX ships two Python helper scripts in `node_modules`, and
  their imports counted as undeclared. The test now asks git which files it would commit.

**Checked in a real browser** (Playwright, 8 checks in about 7 s, against the built UI on a port of its own): the original
loads at its full 1,680 px, KaTeX's fonts arrive, no view logs an error, a finding marks its block and brings it into view
from its top, a wide table stays inside its column, and the bin opens a page. Looking at the screenshots the check leaves
found three things no unit test had:

- the bin repeated a work's long title on every row; it now stands once above the work's pages;
- a table wider than its column was cut off at the window's edge; it now scrolls inside the column;
- a marked block landed with its top above the edge, because the reading column and the window scrolled smoothly at once;
  it now scrolls at once, top first.

A suspected misreading turned out faithful: the reading's "3,9%" stands so in the PDF's own text layer.

**The block's place on the original.** Every block of a reading carries the box the reader gave it, in pixels of the
image it received. The block under the pointer, or else the one a finding marked, is framed on the original at that box;
the original's pane scrolls to a frame out of its view, the window never does. The browser check measured the frame of a
table within 2 px of the reader's box. The box stays the reader's claim, checked only for form, area and bounds, so a
frame beside its text is itself a finding.

**Public only.** Every view will give out both knowledge bases, each row marked (decision 80.a). Started with
`--public-only`, the app never reads the licensed one (decision 81.a): a recorded session cannot show a licensed title, page
or count, by construction rather than by care. A test makes reading the licensed knowledge base raise and calls every route.
The browser check starts the app this way, so its screenshots hold free pages only.

**Not yet:** the history of a page's readings and their
integrity mark for the review's self-healing demo, the reader adapter and its deviation, the free page check's signals, the
licensed works (local display only), and filters kept across a reload. Subscripts and superscripts read as plain text
(`Mean(WT)` for W with subscript T): the core's segments carry no inline marks.

## V1.1: a page at a glance

### Plan

**What** (the operator, 2026-11-04). The page view opens on one line of what matters most, and the rest unfolds when wanted. A
PDF page opens straight from its number instead of by scrolling a list of hundreds.

**Which technique.** Outside the course, as V0.5.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| A row of figure tiles | Takes a screen's height for a handful of words, and pushes the original and its reading below the fold |
| Tabs for check and trace | Would hide the judge's findings, which are why a page is looked at |
| A collapsible panel from a component library | The HTML `<details>` element folds natively, with keyboard and screen reader, and needs no package |

**Gates.**

- At 1,400 × 900 px the line and the start of the original and its reading are seen without scrolling.
- The findings are never folded away. Where everything is fine, the line says no more than state, route, cost and image.
- Whether the details are open is kept in this browser under one versioned key, `settings.v1`. A stored field is taken only
  when it passes its own check; another version's entry is removed.

### Report

**Done.** The line: state, reasons, route, a changed class and a retry only where there is one, cost, and whether the image
is the one the reader received. Below it the findings, then the details (judge, verdict, trace), folded and remembered.
The page view and a work's page list have a field that opens a PDF page by its number; it takes digits only, so `1e2` does
not open page 100.

**Found by looking at the screenshots:**

- **The judge's verdict stood twice on a bin page.** The core's states already carry it: in the export all 239 pages in state
  `ok` are judged ok, and all 15 judged bad are in the bin with "judge: bad" among their reasons. The line has no word of its
  own for the judge.
- **Choosing a finding scrolled the window** and hid the page's title, now that the findings stand above the original and
  the reading. Only the reading's column scrolls; the window moves only when the column itself is out of sight, as on a
  narrow screen. The browser check now asserts that the window stays.
- The field's placeholder was cut off.

**Measured:** 73 unit tests, 11 checks in the browser, 916 Python tests.

**Not yet:** a work's pages grouped by its chapters, with the flat table as a switch: the outline is the core's to export
(decision 84, open). A blocked page's sentence and the printed page label are in the export since this step and come next.

## V1.2: both knowledge bases, the issues, a finding at its block

### Plan

**What** (the operator, 2026-11-04). The licensed knowledge base beside the free one, every row marked with its own (decision 80.a):
free, or licensed and on this machine only. The view of pages to look at is called Issues, since it lists more than the
judge's bin. A judge's finding stands beneath the block it names. A blocked page says why in the provider's own words, and a
page shows the number printed on it.

**Which technique.** Outside the course, as V0.5.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| A work by its id alone, the knowledge base as a query parameter | An id alone is not a key, and a link without the parameter would quietly mean the free one. The knowledge base is the first part of a work's address, `/api/<knowledge base>/works/<id>` and `#/<knowledge base>/sources/<id>`, as the operator chose (1.a) |
| Rename the check state `bin` as well | It is the core's word, used by the judge, the export and the decisions; only the view was renamed (4.a) |
| Match findings to blocks in the browser | The API attaches them, so the UI joins nothing. A finding that names no block, or a block the reading lacks, stays with the page |
| Mark the knowledge base on every row of a work's page list | All rows of a work share it, and a figure already on screen is not printed again: it stands once, above the pages |

**Gates.**

- Started with `--public-only`, the app never reads the licensed export, and `/api/licensed/...` answers 404.
- A page, an issue, a licensed work and a work's page list take their knowledge base from the export's own field, never
  from a path; only the free catalog's works are free by their catalog, which no export lists.
- No test, fixture or screenshot holds a licensed title or text: the tests run against the free knowledge base alone or an
  invented export, and the browser check starts the app with `--public-only`.

### Report

**Done.** `/api/works` and `/api/issues` span every knowledge base served; a work's pages, page and original are addressed
within their knowledge base. A licensed work has no catalog entry: it is listed by id and title, the PDF's stem as on the
search server. The Sources and Issues views mark every work with its knowledge base, and Issues offers it as a filter where
more than one is served. Old addresses (`#/sources/<id>/...`, `#/bin`) lead to the new ones. A block the judge found fault
with keeps an edge in the error role, its findings beneath it; above the original, a line points to each such block. The
provider's sentence stands in the page's line and in the Error column (**→ now** Why, 25.a) of a work's pages and of the issues; the printed
number in the page's heading and in a Printed column.

**Checked against the data:** every blocked page without a sentence, in both knowledge bases, is one the reader declined
rather than one the provider refused; among the free pages there is one. Its route says so ("the reader declined the page"),
and its raw text holds the reader's own words. Asked whether the export should carry a sentence for these too, line 1 kept
`error_message` for the provider's own words. So the API marks every page whose text comes from its text layer, by the
core's own list of such routes (`served_readings.TEXT_LAYER_WHY`), and where the provider gave no sentence the Error column
shows that page's route (**→ now** the Why column, which also gives the route of a page the judge found bad whose reading
is served all the same, 25.a).

**Checked over HTTP against the local licensed export:** every work and issue is marked with its own knowledge base, a
licensed page's original is byte for byte the image the reader received, and a licensed id is refused under `free`.

**An independent review** (two read-only agents, one on correctness, one on the licensed gate) confirmed the gate: under
`--public-only` no request reached for the licensed export, and neither the schema nor the built UI holds a licensed id,
title or text. It found six small defects, all fixed with a test: the address matched the knowledge base regardless of
case, where the API does not; a click on the pointer did not scroll from the raw text or a second time; the test of a
differing image had been lost; three link tests named the knowledge base but tried the free one alone; a red edge stood
beside minor findings; and the module-level app, which the tests and the schema build import, built a reader of the
licensed export. The views now take an answer by the request it answers, not by its fields.

**Measured:** 90 unit tests, 14 checks in the browser, 945 Python tests (the last with the core's newest tests).

## V1.3: a work's pages by its own order

### Plan

**What** (the operator, 2026-11-04). A work's pages stand under the work's own chapters, folded, instead of one endless list; the
flat table in PDF order is one click away, but not the first view. A chapter's head counts every page in it and beneath it,
so a folded chapter still shows whether anything inside needs a look (the operator's 7.a). With a filter chosen, only the chapters
holding a matching page stand, opened down to the page (6.a). A work without an order of its own is listed flat and says
why.

**Which technique.** Outside the course, as V0.5.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| Read the PDF's bookmarks in this API | A second ordering beside the chat's own sections. The core cuts the outline with the chat loader's function and exports it with the readings (decision 84.a) |
| Count a chapter's pages in the browser | The UI computes nothing: the API counts each unit's whole subtree, a page shared by two units once |
| Keep which chapters are open in the settings | A unit's id changes when the outline does, so a link or a setting names a page, never a unit; the choice of view is kept |

**Gates.** Every figure in a chapter's head is a field the API served. A page lying in two units stands under both. A page in
no unit (a title page, a contents page) stands apart, before the first chapter. Back matter, which the chat's index leaves
out, says so.

### Report

**Done.** The API passes on each work's outline with every unit's pages and states counted over its subtree, the pages
outside every unit summed apart, and each page's units. The page list draws the outline as nested, folded units, with a
switch to the flat table that the browser remembers. The Judge column left the table (the operator's 5.a): the state says a judged
page is ok, and the reasons name a bad verdict.

**Checked against the data:** the licensed export carries outlines now, checked by shape only: some works have none (their
PDFs have no bookmarks), every parent stands before its children, and no page names a unit outside its work. The free export
follows once the judge batches of decision 83.a are collected; until then the browser check lays an invented outline over
the Kelly paper's real pages, with the figures counted as the API counts them.

**Measured:** 98 unit tests, 15 checks in the browser, 947 Python tests.

**Next:** the other media the project holds, HTML first, shown the same way: a work's own order, its places, each place's
original beside its conversion. Their data comes from the core's export.

## V4: the search, shown

### Plan

**What** (the operator, 2026-11-04, 14.a). A question in, the pages that hold its words out, best first: the same answer the MCP
server gives a coding session, each hit with its quote, both page numbers, source, knowledge base, licence and the route
that made its text. A hit on a page the diagnostics shows opens that page, its original beside its reading. This is the
entrance the project's title promises: an answer with a verbatim quote and its page, verified rather than guessed.

**Which technique.** The course's retrieval lesson, keyword side: BM25 over pages, the core's ported ranking (decision 56.b).
The screen adds no ranking of its own.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| Ask the MCP server over its protocol | A second process and a transport for a call the core offers as a plain method (`SearchService.search`) |
| Build the index on the first search | It takes about half a minute (**→ now** 20 s free, 50 s with both bases, measured 10 Nov); the start command builds it while the app comes up, and until it stands the search says it is waiting for it, never an empty list |
| Link a hit by mapping the search's work keys to catalog ids here | The export carries both on every row, so a hit finds its page by the work and PDF page it names; a hit whose page the diagnostics does not show (an HTML section, a legacy Markdown page) names its file instead |

**Gates.** "Nothing found" is said as an answer. Under `--public-only` the search never reads the licensed knowledge base,
as the core's own switch guarantees. A hit's words stay text.

### Report

**Done.** `GET /api/search` answers with the core's hits, each with the page view it opens where there is one, and the
knowledge bases the search holds, so a choice of corpus is offered only where there is one. The Search view keeps the
question in the address, so a search can be linked. Each hit shows `p. 105 (PDF p. 119)` where both numbers are known, as
a citation gives them.

**Checked in a real browser** against the free knowledge base: a question about the Kelly criterion found a Wikipedia
section, a page of the Kelly paper read by vision, and two of its pages served from the text layer because the provider
blocked their reading, each saying so; the first linked hit opened its page beside its original.

**Measured:** 104 unit tests, 17 checks in the browser, 957 Python tests.

**Found by following a hit to its page:** a hit served from the text layer showed its words in the search, but its page
showed none of them, and a page in the judge's bin showed its rejected reading as if it were what is quoted. The page view
now says so wherever a page's text comes from its text layer: beside a reading that is shown but not quoted, and where no
reading came back. The text the search and the chat quote is for the core to give out, one function for every route, so
the view shows it rather than extracting a text layer of its own; asked of line 1. Measured after: 105 unit tests, 17
checks in the browser, 968 Python tests.

## V5: a page's readings over time

### Plan

**What** (the operator, 2026-11-05, 15.a). Every reading bought for a page, oldest first, the one the page shows marked, and why it
was chosen, by which run and when. It is the view of the review's self-healing demo (decision 69.a): a page that came back
malformed and was read again shows both readings and the choice that made the second one the page's.

**Which technique.** Outside the course, as V0.5. The choices come from the core's pipeline database (decision 51.a),
exported with the readings, so a clone shows them too.

**Gates.** The attempts are the export's: the view reads no private store. Only the reading a page shows is exported in
full, so the others stand by their record alone: model, how it was asked, its class, when, and any deviation from the
default reader. Where a page has one reading and no recorded choice, nothing is printed.

### Report

**Done.** The API passes on each page's attempts, marking the one the page shows, and its recorded choice; the page view
lists them beneath the page's line. Built against the shape line 1 announced, before its export carried it; the browser
check lays an invented history over a real free page until it does.

**Measured:** 106 unit tests, 18 checks in the browser, 987 Python tests.

## V6: the overview

### Plan

**What** (the operator, 2026-11-05). The whole pipeline at a glance, each knowledge base beside the other: how each page's text was
made, its state, the judge (how many pages, why, which verdicts), the reasons a page carries, what the readings shown cost,
what the search holds of every medium, and the latest runs. Every count of pages opens the pages it counts. It is the app's
first view.

**Which technique.** Outside the course, as V0.5.

**Gates.** Every figure is counted in the API, from the exports, the search index and the pipeline databases; the browser
lays them out. Each block names the field it counts, the page list filters by that field, and a test checks for every block
that a figure opens exactly as many pages as it says. A knowledge base this app does not serve says why. The search index
is counted only once it stands, and the overview never waits for it.

### Report

**Done.** `GET /api/overview` and `GET /api/pages` with filters by knowledge base, state, route, why judged, verdict and
reason; the Overview view, now the app's first, and the Pages view, its filters above the list, each removable. The Issues
and the Pages share one grouped table. Also: a page no check run has reached yet is said to be `unchecked`, neither fine nor
an issue; the state `bin` is read under its new name `issue` as well (decision 97.a); and states stand in one order wherever
they are counted.

**Found by a unit test:** a figure's link was off everywhere, because Vue casts a boolean property that is not given to
false. It defaults to true explicitly now.

**Measured:** 113 unit tests, 19 checks in the browser, 1,004 Python tests.

**Redrawn the same day as compact boxes** (the operator: the first version was clumsy, each title stood twice). On top, a row of key
figures per knowledge base; below, boxes in which each value stands once with its count in each knowledge base beside it,
"—" where it does not occur. The API now joins the two bases' counts per value, so the browser still counts nothing. A page
no check run has reached yet is now `not_yet_checked`, line 1's word for it.

**Which model did what** (the operator's 17.a), under the key figures: three boxes, the readings by model and the upstream that
served them, the judgements by model, and both by provider. Each names the pages a model or provider worked on, which open
like every other count, and what all its work on them cost, retries included. A cost the export does not give stays "—",
never 0.00. The cost tile is now "USD spent", the provider box's sum; before, it counted only the reading each page shows,
which left the retries and the judge out (free: 23.63 USD against 32.49 spent). Since every export says `issue`, the old
word `bin` is no longer read; an old `#/bin` address still leads to the issues. **Measured:** 113 unit tests, 20 checks in
the browser, 1,007 Python tests.

**Set in bands** (the operator's 18.a: the boxes still looked unordered). Each subject stands under a heading of its own: cost,
the pages through the pipeline, the search, the runs. A band's boxes flow down two columns the browser balances, so a short
box leaves no hole beside a long one, and the balance holds as the data grows. Each run takes one line: the time short
and in UTC (**→ now** said as a person says it, V16), the command without the module path every one shares (whole on
hover), its batches folded to a count. The API gives the search's box a field of its own, so the view sorts nothing out
of a list. **Measured:** 116 unit tests, 20 checks in the browser, 1,007 Python tests.

## V7: the text that is quoted

### Plan

**What** (the operator, 2026-11-05, 20.a). A page shows the text the search and the chat quote for it, beside its reading as parsed
and as stored: the served reading as quotable text, formulas as LaTeX and tables as rows, or the page's text layer cleaned
of running heads and page numbers where the reading is not served. A page quoted from its text layer opens on it (**→ now**
227.a, 12 Nov: every page with a reading opens on it, so the switch never moves; only a page without one opens here). This
closes the gap V4 found, where the view could only say that a reading shown was not the one quoted.

**Which technique.** Outside the course, as V0.5. The text comes from the core's one function for it
(`reading_export.quoted_pages`, decision 93.a), so the view cannot quote a page apart from the search and the chat.

**Gates.** The quoted text is asked for only when it is to be shown: where the export has not cut a book's quoted text on
a machine, the core cuts it on the first call (about a minute for a large book) and keeps it, and a page view must not
wait for that. One lock per book, so two pages of it asked at once do not both cut it. Under `--public-only` the licensed
knowledge base is refused here as everywhere.

### Report

**Done.** `GET /api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/quoted`, and a third switch in the page view,
"quoted", beside "readable" and "raw". The note "Not quoted" is gone: the switch, and the route above the quoted text, say
where the text comes from. A page without a reading shows the one switch. Read from the files the export cut, a page's
quoted text came back in 64 to 126 ms.

**Measured:** 118 unit tests, 21 checks in the browser, 1,009 Python tests.

## V8: is the reading what was checked, and what each reading's check made of it

### Plan

**What** (the review demo, decision 69.a, the operator, 2026-11-03). The demo damages one free page on purpose and heals it: a
number changed in a stored reading, or a reading deleted. The views must show both: whether a page's reading file is still
the text that stages 1 and 2 and the judge saw, and, after `replay --reread`, every reading of the page side by side, each
with what its check made of it and which one stands.

**Which technique.** Outside the course, as V0.5. Both answers come from the core: `integrity.page_state` hashes one
reading file against the sha256 its row recorded (the same function the integrity scan uses, so the two cannot disagree),
and the export gives each attempt its check.

**Gates.** Asked on every visit, never cached: a cache would miss a change made a moment ago, which is the demo. Where all
is fine nothing is printed. A reading file that is gone must not break the page view.

### Report

**Done.** The page view says in its line when a reading file differs from the checked text, or is gone, in the core's word
with a glyph; a tampered reading is still shown as it now reads. The readings of a page each carry their check: the state,
and the judge's verdict where the state does not already say it; "not checked" where no check ran. The overview's pipeline
band has a box "Is the reading what was checked", each count opening its pages, and the page list filters by it. Measured
on the free export: 1,646 whole and 6 without a reading, the licensed export alike; the overview with the box takes about
0.8 s for both, since every reading file is hashed.

**Measured:** 124 unit tests, 20 checks in the browser (one skipped: the export holds no declined page any more), 1,069
Python tests.

## V9: the runs, and what one run did

### Plan

**What** (21.a, taken by line 1 on 2026-11-06 at the operator's request). A menu item "Runs": every run of the
pipeline, newest first, both knowledge bases together, one line each; a run opens a page of its own with the whole command,
its code version (the commit, and whether the tree held uncommitted changes), its cost by provider, its batches and the pages
it chose a reading for, each opening its page view. It is the place of the replay run's trace in the review demo (69.a): the
run that healed a page names the page, and the page names the run.

**Which technique.** Outside the course, as V0.5. Runs and choices are the core's pipeline database (decision 51.a), read
through `pipeline_db.runs` and `pipeline_db.choices`; the overview's band of the latest runs now uses the same reading.

**Gates.** Nothing is counted here; a run stands as recorded. A base without a pipeline database on this machine, as on a
clone, says so; under `--public-only` the licensed runs are never read.

### Report

**Done.** `GET /api/runs` and `GET /api/{knowledge_base}/runs/{run_id}`, the Runs view and the run page; the overview's run
numbers open their pages. Found by the screenshot of run 28, which chose 46 pages of one book: its title on every row, the
same defect V1's first browser check had found in the bin, so a work is named once where its pages begin.

**Measured:** 129 unit tests, 21 checks in the browser (one skipped, as before), 1,075 Python tests.

## V10: the chat, compact

### Plan

**What** (the operator, 2026-11-05, 100.a: "yes, but please keep it purposefully compact"). The chat in this app, beside the Streamlit demo,
which stays as the fallback (→ now: the only chat; the demo was removed on 17 Nov 2026, decision 286.a): a first screen with the chat's example questions, then question and turn after turn, each turn
shown by its kind, its quotes word for word with the page each comes from. Timeboxed: if it is not stable by 11 Nov, the
review shows Streamlit.

**Which technique.** The chat is the core's: the agent with its tools, the search server as its MCP client, the quotes
verified after generation (the course's RAG and agents sprints). This view adds no retrieval and no prompt; it renders the
turn as the core returns it. Outside the course: the port of the rendering rules from the operator's first chatbot (Markdown without
HTML, then DOMPurify with an allow-list), which that project had tested.

**Gates.** The one route in this app that spends money: the read-only rule lifted for it alone (the operator). It answers only a
request addressed to this machine by name, takes a JSON body only, and the browser check starts the app with `--no-chat`, so
no test can reach a model; pytest hands the app a fake agent. Model text is untrusted: rendered only through the sanitiser;
a quote is verbatim and shown as text. No streaming: quotes are checked after generation, so raw tokens would show what is
not yet checked. The agent's own words never reach the browser.

### Report

**Done.** `GET /api/chat` (whether the chat answers, and its examples) and `POST /api/chat` (one turn). The core's
`ChatAgent` is built once per process on the first message, under a lock, and closed with the app; one turn runs at a time;
each conversation's turn log path is set once, at its first turn. The turn returns as `turn_log.stored` keeps it, pixels
kept, without `agent_text` and `discarded_text`; a cited page and a hit gain the link to their page view by the search's
own lookup, and a page image becomes one data address, png or jpeg only. A missing key is said in the core's words; a
failed turn in one sentence, and a stuck search server is replaced at the next message. The view: examples that fill the
input, Enter to send and Shift+Enter for a line (an input method's confirming key sends nothing), the seconds a turn has
taken while it runs, the turn by kind, its id, time and cost beneath it ("agent, router and generator; query embeddings not
counted"), the security checks folded away, the conversation kept for the tab, a "New conversation" button. A failed turn
gives its question back to the input and is never sent again by itself. The chat is loaded only when opened, so its
libraries stay out of the main bundle (475 kB; the chat's part 139 kB).

**Found on the way:** a browser check failed now and then: a click opens `<details>` at once but fires `toggle`, which
stores the choice, as a task of its own, so a reload could come first. The check now waits for the store.

**Measured:** 159 unit tests, 23 checks in the browser (one skipped, as before), 1,105 Python tests; the markdown-it and
DOMPurify packages pass `npm audit --omit=dev` with no finding. Not yet: one live turn through the real agent, which spends;
it waits for the operator's OK.

**A live turn, checked for fidelity (the operator, 9 Nov).** One real question ran through this view from the main tree, at about
0.004 USD. Every passage and every quote the route returned stood in the view, none dropped and none reordered, and each
quote opened the page it was taken from. Two things were the view's own and are mended: the answer and the quotes stood
apart but nothing said whose words were whose, so the answer is now named as the model's own words, its bracketed numbers
as the passages a sentence draws on, and the quotes as word for word and checked; and the best passage's relevance stood
only in the folded security checks, so a near miss read like a clear hit. The relevance and its floor now stand above the
answer, with a warning where the core says the best passage lies below the floor. A question back is named as one.

## V11: the search server's calls

### Plan

**What** (decision 98.c, "line 2 visualises the server's call log"; the form 19.a). A menu item "Calls": who asked what,
which pages answered, how long it took. On top each tool's figures; then the calls newest first by day, filtered by tool,
state, caller and knowledge base. Since the chat became the server's MCP client, its questions stand beside an IDE's and a
measurement run's, each named by its client.

**Which technique.** Outside the course, as V0.5. The log is the core's (`search_server.CALL_LOG`), read as line 1 described
it: split at the newline alone, both shapes of an answered page (strings before 5 Nov, objects with the PDF page since).

**Gates.** Nothing of a page's text is in the log, and nothing is computed in the browser: the API counts every figure and
gives each call the words it is filtered by. An old record names no PDF page, so it opens no view: never a guess. Under
`--public-only` a call is listed only where it concerns the free knowledge base alone (every answered page free, no
licensed corpus asked, no other work named); old records cannot be told and are left out; how many is said.

### Report

**Done.** `GET /api/calls` and the Calls view; the worktree reaches the main tree's `logs/` through a junction, like its
other git-ignored data. Measured on the real log under `--public-only`: 228 calls listed and 15 left out, read in 0.24 s;
`semantic_search` took 8.9 s at the median, `search` 38 ms.

**Searches over works (decision 124.a, line 1's announcement of 2026-11-08):** `search_works` answers with works, not pages
(`answered_works`). A call that named a licensed work is left out under `--public-only`, as one that answered with a licensed
page; each work answered opens its page list where this app holds its readings. The key a work is named by maps to this
app's id through one function (`search_hits.work_sources`), which the page links use too.

**Measured:** 163 unit tests, 24 checks in the browser (one skipped, as before), 1,110 Python tests.

## V12: the shelf

### Plan

**What** (the operator, 2026-11-08, decision 129.a, handed over by line 1). Every work of both knowledge bases with how far it is
converted (planned, read, passed, the share passed), why pages did not pass, what the search serves of it and from where,
and what passed but is not served, and why. The operator's example, its figures invented here: a work's row reads "120 planned · 90 passed · 75 %", and a click
on a reason's count opens exactly those pages. Where the shelf stands in the UI is the operator's question 22.

**Which technique.** Outside the course, as V0.5. The shelf is the core's (`backend.search.shelf`), written by line 1 at
milestones and read here; every count and the share passed are the core's.

**Gates.** Nothing counted again. A reason opens the work's pages filtered on its route: by construction the route the
export wrote for that page (`served_readings.TEXT_LAYER_WHY[reason]`), which a test in the core pins. The licensed shelf is
never loaded under `--public-only`; a machine without a shelf says how to build it.

### Report so far

**Done.** `GET /api/shelf`; a work's page list takes its filter from the address (`?route=`, `?state=`), so a count lands
on exactly its pages. Checked against the real shelves: free 8 works, 1,652 planned, 1,588 passed, the licensed shelf alike,
as line 1 counted. **Found on the way:** the shelf's reasons are not the check states (a "blocked"
state holds both the provider's blocks and the reader's refusals), but they match the routes one to one for every work
with reasons; line 1 confirmed this holds by construction. And a licensed search hit names its work by the server's key,
not the export's, so licensed hits and the call log's licensed pages found no page view; they now map through the shelf.

**The view (the operator's 22.a, 9 Nov): a Shelf menu item.** Each knowledge base under its heading with the shelf's build time and
the core's totals, then one row per work: its format, planned, passed, the share passed, every reason with its count opening
the work's pages on that reason's route, what the search serves and how much of it from readings, and what passed but is
not served, folded with its reasons. A count the core cannot explain ("unexplained") stands in the open, in the error role.
A work this app holds no readings of opens nothing. **Found on the way:** the shelf is local, built where line 1 works,
while the free export is tracked; in the worktree the two parted for a while when line 1's new export was not yet
committed. The browser check therefore tests the view's part (a reason opens exactly the pages on its route) and leaves
the agreement of counts and routes to the core's test. Since line 1 names in each shelf the export it was built from
(`export_sha256`), the view says so where that is not the export this app serves, hashing only the index it reads. **Measured:** 170 unit tests, 25 checks in the browser (one
skipped, as before).

## After the seal: walking the issues

### Plan

**What** (the operator, 2026-11-09). Features are sealed (decision 142.a); a fault a check finds is still mended, as are small
changes that practice calls for. The practice: the operator judges the free pages the judge found bad, page by page, beside their
originals ("a person stays the final judge"). Walked through in a browser beforehand, the way the operator will, it showed two
frictions and one misleading heading, mended as the operator chose:

| | found | mended |
|---|---|---|
| 24.a | The Issues view held its choice in memory: narrowed to 27 rows, a page opened and left by the browser's back brought all 506 back | The choice lives in the address (`#/issues?state=issue&kb=free`); a toggle replaces the address rather than adding a step, so back leaves the list instead of undoing toggles |
| 25.a | Five free pages the judge found bad still serve their reading, since its findings lie on blocks never quoted; their Error column stood empty, so they read like the others without saying why they differ | The column is called Why, in the issues and in a work's page list, and shows the route for these pages too ("the judge's findings lie on blocks never quoted") |
| 23.a | Sources headed the catalog's topic (trading_finance, architecture) "Shelf", the name of the Shelf view's counts | Headed "Topic" |

**Which technique.** Outside the course, as V0.5.

### Report

**Done** as planned. The 11 pages the operator judges open as one list from the overview's route row, its filter in the address;
on a page, "findings at" frames the faulted block on the original with the judge's finding beneath it. Line 1 records
the operator's verdicts in the core's report; this view stays read-only. **Measured:** 175 unit tests, 26 checks in the browser
(one skipped, as before); the check walks list, page and back, and finds a served-despite page's route in the Why column.

**The last free work (143.a), checked in the views.** The EU cost-disclosure regulation and SEC Rules 600, 605 and 606
stand in Sources, on the shelf with the core's counts, and in their page lists; the shelf names the export it was built
from as the one served. **Found on the way:** a chapter title longer than a line (the regulation's recital heading) wrapped
below its marker, which stood alone; the marker now stays beside the title and only the rest wraps, pinned by a browser
check on that work. And the pages a call answered, opened from their fold, ran into each other once their titles were the
regulation's ("… (MiFID II) p. 75Regulation NMS …"); they now stand one a line. **Measured:** 175 unit tests, 27 checks in
the browser (one skipped).

**The overview's tiles say what they count (the operator's 1.a, via line 1).** The search server's start banner said "free 2,315
pages in 15 works" where the overview's tiles said 11 works and 1,822 pages: both right, but counting different things, so
a reviewer seeing both would ask where four works went. The tiles counted the readings export, the works read page by page
and their pages; the banner counts everything the search serves, an HTML source and legacy Markdown too. The tiles now say
"works read page by page" and "pages read", with what the search serves beneath each ("15 in the search"), counted exactly
as the banner counts it; while the index is still being built they say so. A test checks the count against the banner's
own line. **Measured on this machine:** free 11 works read, 15 in the search, 1,822 pages read, 2,315 in the search;
the licensed base alike; 1,207 tests, 176 unit tests.

**A fine line between the rows of every list (the operator, 2026-11-09, via line 1).** In a work's chapters the rows ran into each
other, and the eye lost the line between a chapter's title and its counts. One token (`--color-row-rule`, a step fainter
than the border) and one rule in the base styles (`.ruled`): a line between sibling rows only, never around the list, drawn
as the row's own border so no space is added; a table's head keeps its line in the border colour. Every list wears it: a
work's chapters and its pages, the issues and the pages behind a figure, a page's readings, Sources, the shelf, the runs and
a run's pages, the calls and the pages a call answered, the overview's boxes and runs, the search hits, and in the chat the
passages, the security checks and a server answer's hits and works; the judge's findings too. Eight tables drew their own
line before, in the border colour; they now use the shared rule. **Measured:** a browser check reads the computed border
of the first and second row in Sources, the chapters and the issues: none, then 1px in the token's colour; 28 checks in the
browser (one skipped).

**The page's details, and a box for every block (the operator, 2026-11-09, via line 1).** The key-value lists, a page's details and a
run's facts, take the same line between their pairs; their grid sets no column gap, so the line runs through both columns.
In the readable reading every block stands in a fine box of its own in the same colour, its label inside at the top, the
boxes close together; the raw text stays one text, as stored, and the quoted text has no blocks. The mark of a block the
judge found fault with, and of the block on show, stays as it was: an edge on the left, now drawn inside the box.

## V14: the check in stages, its judges and a person (146.a, 147.a)

### Plan

**What** (the operator, 2026-11-09, decisions 146.a, 147.a and the wish "in the details, all three stages one by one", handed over by
line 1; with 148.a named as exceptions to the feature seal 142.a). A page's details give the check's three stages one by
one, then a person: stage 1 the format, stage 2 the reading against the PDF's text layer (recall, precision, its findings
and the blocks it cannot check), stage 3 the judge (why it judged, its verdict, the outcome that counts and the judge's own
where they differ, the version of its prompt). A person's verdict stands at the page and beside the block it names; one given
on an earlier reading says it does not apply. A finding the core found void, naming no difference, stands receded and says
so, never hidden. Every judgement of a reading stands beneath it in the page's history, oldest first: a prototype judge, one
asked again and one that does not count, each marked. The review's showcase is free Principles of Finance p. 5.

**Gates.** Every word the export's: nothing judged or counted in the view. Stage 2 and the judge reach only a page's own
view: a list of a thousand pages does not carry them.

### Report so far

**Done:** the details' stages and a person; the void mark; a person's verdicts at the page and the block; every judgement
under its reading, a check carried over from before saying "an earlier check". **Measured:** finance p. 5 shows judge/1
counted, judge/1 asked again, judge/2 as a prototype, each with its void finding; 187 unit tests, 30 checks in the browser
(one skipped). **Next from line 1's order:** the prompts tab (148.a), then error classes.

**The prompts tab (the operator's 148.a), done.** A Prompts menu item lists every version of the reader's and the judge's
instructions, split by role, in the registry's order (`prompt_versions.json`): its state (prototype, active, retired), the day
it was frozen, why it was made, each file's sha256 now beside the one the frozen contract holds, and the change from the
version before it in its role. The change is a line diff from Python's own `difflib`; a replaced line also carries its words,
the changed ones marked, so judge/2's one added sentence stands out of a long paragraph line rather than the line twice.
A page's judge version, in its details and in each judgement line, opens the tab with that version marked. **Measured:**
judge/2's change is exactly its sentence on proper names, judge/3's the "X and Y different" rule and the sentence to read
the block again; every file's hash equals the frozen one; 189 unit tests, 31 checks in the browser (one skipped).
**→ now (10 Nov, the operator through line 1): a tab per part, a folded row per version.** The registry now names each file's part
(the reader's rules, its format, the judge, the class check) and gives each version a title and a model; the API serves
them, and the tab shows one tab per part, so page/1, a version of two files, stands in two. In a tab, one row per version,
folded: version, title, state, model, the day it was frozen, whether its sha256 is the frozen one, and why, cut to a line;
opened, the whole why, the file's hash and its change from the version before, or its text. A version is compared with
the previous version's file of the same part. A page's link opens the version's tab and row. **Found on the way:** the
table grew to 3,575 px once a version was opened, as an automatic table layout lets a cell's content widen it; it is laid
out fixed now, and a browser check holds it inside the window. The class `same` stood both for a diff's unchanged line and
for "as frozen", so the unchanged lines took the hash's no-wrap rule and ran past the window; the hash's classes are named
apart. 211 unit tests, 36 checks in the browser (one skipped), 1,272 Python tests.

**A description frames what it describes; a grouped figure shows its containers (the operator on accounting p. 305, 10 Nov).** A
description has no box by contract: the reader wrote it, the page does not print it. Hovered, it now frames the block it
names in `of`, dashed and labelled "b05 describes b03"; the same holds for any `of` block without a box of its own. A
figure's body kept its lines only in the raw mode: the readable mode ran them together. It now keeps the reader's line
breaks, and a figure marked `grouped=1` shows each drawn container as its own small box, its title line first, as the
contract has the reader write it (one group per container, a blank line between them); the block's head names
`grouped=1` with the other attributes. Display only: the text is the reading's. **Measured:** p. 305's eleven T-accounts
stand as eleven boxes; 215 unit tests, 37 checks in the browser (one skipped), 1,272 Python tests.

**Error classes, done.** An Errors menu item groups the export's findings by what they are: the judge's by kind, block class
and work, the void ones in a table of their own, never counted; beside them stage 2's, the reading against the text layer,
by kind and work. Each class gives its count and its pages, drawn when the class is opened (one holds 206 pages), each page
one click from its view. **Measured:** the free export in 0.12 s, 64 classes; a test checks that every finding of the
export stands in exactly one class; 195 unit tests, 32 checks in the browser (one skipped).

**The frame: a name from the config and a grouped menu, done** (decision 149.c and the operator's "the menus are too big", 10 Nov).
The view's name is a working name kept in `configs/app_config.json` under `ui` and served by `GET /api/app`; the header
and the browser tab show it, never a name written in the UI, and without one the API says "Diagnostics". The row of ten
links gave way to a menu button beside the name: its panel holds every view in four groups, by what a person comes for
(Ask: Chat, Search; Holding: Sources, Shelf; Checks: Issues, Errors, Prompts; Operations: Runs, Calls), and closes on a
choice, on Escape and on a click outside it. Overview stays in the header, and so does the name of the view on show: a
view that knows what it shows names itself once its data has come (`Finance 2e p. 5`, a work's title, a section, a run),
otherwise its route's label stands. The name is kept with the address it was given at, so a view on its way out cannot
lend its name to the next one. The tab reads `Capstone · Principles of Finance 2e p. 5`. The page's own `<title>` stays
"Diagnostics" for the moment before the script runs. **Measured:** 203 unit tests,
34 checks in the browser (one skipped), 1,264 Python tests.

**The Reading History and the Lab, done** (decision 150.a, the operator: "save everything, but keep it apart"). A page's readings stand
under "Reading History", which shows what the pipeline did: each reading, its judgements that the pipeline made (the one
that counts first) and a person's verdicts beneath the reading they judged. What was tried beside the pipeline moves to its
own folded section "Lab" below it: a prototype's judgement and a judge asked again, each with the reading it judged,
labelled and never served; nothing is deleted. The split reads the export's own fields (`counts`, `again`, `version_state`);
a judgement that counts is never the Lab's. A folded reading says how many of its judgements the Lab holds ("1 judgement:
judge/1 counts · 3 in the Lab"). Reader prototypes and previews will go to the Lab when the export lists them. **Who said
what (the operator on finance p. 5, b12):** each part of a finding is named: "The judge's finding:" before its kind and severity;
"void, by code: names no difference" where code voided it under rule 146.a, the rule's sentence in its hover; "The judge's
evidence:" before the judge's own words. Nothing in the reading changes when a finding is void. A person's verdict stands
as its own line, "A person: accept · the reason · tag ...". **Measured:** finance p. 5 shows judge/1 counting in its
history, judge/1 asked again and judge/2 and judge/3 in the Lab; 205 unit tests, 34 checks in the browser (one skipped).

**A work's routes in a table, done** (the operator, 10 Nov: "is this route a faulty one?"). The route chips gave way to a
table, one row per route: its level as the export gives it (checked, noted or fallback, `route_level`), its source (vision
reading, second reader, text layer), its reader (model, contract, validator), why, and its pages. The API parts the route
where the core's own route strings part it (`readings.route_parts`) and orders the rows: checked first,
then noted, the fallback last, each by its pages. A fallback stands out with its glyph and word in the warning role, since
formulas and tables may be garbled in the text layer; the legend beneath gives each level in the core's words
(`served_readings.ROUTE_LEVELS`), and each level's badge holds its sentence in the hover. A row chosen narrows the
chapters or the table to its pages, as the chips did, and the shelf's links by route still land on exactly those pages.
**Measured:** finance shows 617 pages checked, three noted routes (3, 2 and 1 pages, the second reader among them) and two
fallbacks (5 and 1); 206 unit tests, 35 checks in the browser (one skipped), 1,266 Python tests.

**The overview's first load (line 1's measurement of the operator's 22 s, 10 Nov).** Three causes, three changes. Every call hashed
every reading file, 9,600 pages, 1.8 s with a warm disk: a file's state is now remembered by its modification time and
size, and hashed again only when one changed (`page_integrity`), so a file changed a moment ago still counts at once (69.a).
The rows of each export were counted on every call: they are counted once per state of the export, by its index file's
time. And the search read its 9,600 pages in a thread for 45 s, much of it in PyMuPDF, which holds the interpreter's lock,
so every request beside it starved: the overview five seconds after a start took 8 s. The pages are now read in a process
of their own, by the core's own `knowledge_bases` with the app's switch, and handed back pickled (57 MB in a quarter of a
second); the index over them is built here in 4.9 s. The start warms the reading files and the counts first, then the
search. **Measured** with both knowledge bases: the overview right at the start 4.2 s (the files still being hashed), five
seconds on 0.76 s instead of 8 s, once warm 0.6 to 0.8 s instead of 2.2 s; the first search still waits for its index,
about 50 s after a start. 1,270 Python tests, 36 checks in the browser (one skipped).

## V13: the HTML works, an exception to the feature seal

### Plan

**What** (the operator, 2026-11-09, decision 6.a, through line_features). **An explicit exception to the feature seal (142.a),
named as such.** The four HTML works (Google's SRE book, the Wikipedia set, Lefèvre, Kleppmann) become works one can open:
an outline by heading in the book's own flow, every section flat in a table, and a section's view with its original on the
left and its chunks on the right. The operator's decisions: the left pane is a stripped, readable HTML per section, derived on demand
by a core function (1.a); dropped headings stand greyed at their place (2.a); their content stays out of the index (3.a);
Sources' column "Page readings" becomes "Structure", each cell naming its format's model (4.a). Hard cut: what is not in
main by Thursday 12 Nov, evening, waits until after the push.

**Which technique.** Outside the course, as V0.5. The data is the chat's own index, `corpus/index/knowledge.sqlite3`, read
read-only: the sections the loader cut by heading and the chunks embedded from them.

**The outline's rules (the operator's 1.a).** The top level is the work's own unit; built from the heading paths, so a heading
without text of its own is a node without a section label; a work's only top node that is its own title gives way to its
children; ranges are section labels as the search server gives them (`s` and the position from 1), never pages; counts are
sections and chunks.

**Gates.** Every figure the index's; nothing written. A chunk's place in its section is found by searching its text, and a
miss is counted, never hidden. Without the index, every view says so and names the build command. The licence and the
attribution stand beside every section.

### Report so far

**Done:** `GET /api/free/html/<work>` and `.../sections/<label>`; Sources' Structure column ("629 pages · read and judged",
"611 sections by heading · 1,541 chunks"), an HTML title opening its outline; the outline and the table; a section's chunks,
each in a fine box with its id, its characters in the section's text and the characters it shares with the chunk before,
marked dashed in the annotation role. **The left pane and the dropped headings, done** with line 1's function
(`html_stripped.strip_source`): a section's original, allow-listed in the core from the raw file and sanitised again here
with DOMPurify under a list of its own (the core's kept elements, span, and the attributes href, id, colspan, rowspan,
data-image, and since 10 Nov data-tex and data-display; an image shows as its alt text), made on the first ask and kept in the process's memory only, never on disk
(SRE is CC BY-NC-ND, decision 91.a); each heading the loader drops as noise stands greyed at its place in the outline
("dropped as noise: not indexed"), and opens its original with no chunks. **Found on the way:** DOMPurify tests the value
of every attribute it does not know to be inert against the URI rule, so a table's spans and an image's alt text were
dropped until named as inert (`ADD_URI_SAFE_ATTR`). **Measured:** Wikipedia's 32 dropped headings and Lefèvre's one in
place; SRE's 40 files stripped in 1.4 s on the first ask, 0.05 s after. **Checked against the index:** Wikipedia 11 articles at the top, its five headings without text of
their own among them the three the operator's plan names; Lefèvre's 24 chapters beside its title; SRE's 40 chapters; every one of the
2,632 chunks found in its section's text. **Found on the way:** the overlap between chunks is not a fixed 200 characters:
measured 0 to 196, as the chunker cuts at sentence and word boundaries; the view shows what is measured. **Measured:** the
largest work's outline 0.24 s; 183 unit tests, 29 checks in the browser (one skipped).

**Formulas, paragraphs and the overlap's legend (the operator on Wikipedia's Sharpe ratio, 10 Nov).** Line 1's stripper now marks
a formula as `<span data-tex="LaTeX" data-display="inline|block">` and drops Wikipedia's picture of the same formula, which
showed it twice. The view's sanitiser lets the two attributes through, as inert values, and KaTeX typesets each formula
after it, `trust` off as everywhere; one KaTeX refuses keeps its LaTeX as text. The chunks keep the LaTeX as the index
holds it, since that is what the search and the model read. The index joins a section's blocks with one line break, so a
chunk read as one run; each break is now drawn as a paragraph, the text and its offsets unchanged, the shared characters
marked across it. What the dashed line is, with the splitter's own figures from the API (`chunking.splitting_config`:
RecursiveCharacterTextSplitter, 1,000 characters, 200 shared), is a hint on demand (the operator: "rather show it as a hint"): an
info mark beside the chunks' count opens it, and the dashed text and "N shared" carry it in their hover; a section whose
chunks share nothing offers none. **Measured:** Sharpe
ratio's Definition typesets its formula once; 209 unit tests, 37 checks in the browser (one skipped).

**The whole article on one scroll (the operator, 10 Nov: a click on "Sharpe ratio" should show the article).** A section's address
now opens the top unit of the outline that holds it, whole: `GET /api/free/html/<work>/articles/<label>` gives every place
of it in the work's order, each section with its original and its chunks side by side, each heading the loader dropped as
noise greyed at its place, and each heading with no text of its own as a heading. The section in the address is marked
and scrolled to; a folded list of contents jumps within the scroll without asking the API again; the neighbouring
articles are a click away. The grouping is the outline's built from the index, not the raw files', so it stands where the
raw files are absent, and a book in one file, Lefèvre's, opens chapter by chapter rather than as one scroll. **Measured:**
Wikipedia's largest article, 38 places, in 0.10 s and 0.27 MB; SRE's largest chapter, 43 places, in 0.31 s.

**Previous and next stay under the pointer (the operator, 10 Nov: "page forward and back jumps when clicked ... a no-go in design, something like that must always be tested").** The section view's "← s146 s148 →" stood after the heading path and moved with
its length, and the page view's after "PDF page N · printed X". Both now stand first in their row, in boxes of one width
(`PagerLinks`), a neighbour's title or number cut to the box and whole in its hover, a missing neighbour's box kept as an
empty place; the title follows them. Opening an article's first section scrolls nothing while the head is in sight. A
browser check turns three articles forward and back, titles of different lengths, and four PDF pages from 7 to 10, and holds
each box within a pixel; set back after the title, the check fails by 22 px. 216 unit tests, 38 checks in the browser (one
skipped), 1,275 Python tests.

## V15: one layout, less at once, uniform type (decision 159.a)

### Plan

**What** (the operator, 10 Nov, through line 1: "on the whole we have too much information on our pages anyway ... What can definitely be better: the font sizes should be uniform"; "I like the state selection; when tidying up we must also look at all the detail views"). A minor design change under 142.a, in four steps the operator can look at one by one: the type
scale; the work page's head and its routes folded to one line; the chapters as a table and one column grid for every page
table; the other views in the same pattern. **Gates:** every visible text in one of three sizes; every count once; nothing
the API serves lost, at 1,280 and at 390 px, the page never scrolling sideways.

### Report

**Step 1, the type scale, done.** Exactly three sizes, named by their role in `tokens.css`: `--font-size-title` for a
view's title, `--font-size-body` for the text and every other heading, set apart by weight, and `--font-size-meta` for what
stands beside it. The old names `sm`, `md` and `lg` gave way across 37 files, the browser's own scale for headings, small
print, sub- and superscripts is set to the three in `base.css`, and the two sizes beside the scale (the overview's tile
figures at 1.6rem, the calls' at 1.3rem) take the title's. A browser check visits every view, its folds and the menu
opened, and finds every visible text in one of the three, KaTeX's formulas aside; it injects a size beside the scale and
sees it, so it cannot pass for want of looking. 216 unit tests, 39 checks in the browser (one skipped), 1,275 Python tests. **→ now** one size for every text (11 Nov, at the end of this chapter).

**Step 2, the work page's head and its routes, done.** Every count stands once: the head line reads the work's pages, then
the State chips, which count and filter at once (the operator: "I like the state selection"), then the page to jump to; the counts
beside the page total are gone. The routes fold to one line by default, "Routes 617 checked · 6 noted · 6 fallback", each
level's pages counted by the API (`RouteLevel.pages`), the fallback always named and, where it serves a page, in the warning
role with its glyph; what each level means is a hint on demand, and open or folded is kept in `settings.v1`
(`routesOpen`, an entry written before it reads as folded). Opened, the table stands as before. A route chosen while the
line is folded, as the shelf's links choose one, says so in the line and can be let go there. 219 unit tests, 39 checks
in the browser (one skipped), 1,275 Python tests.

**Step 3, the tables, done.** The chapters are one table: a head naming its columns, Chapter, PDF pages, Pages, one
column per check state the work has (ok, ok unjudged and issue for finance; ok and blocked for Kelly), and Note, then a
row per unit at any depth in the same columns, its title indented by its depth, its counts right-aligned under their
state, a state without pages left empty; a row folds open to its pages and its sections as before. Every page table of
the work shares one column grid, laid out fixed: PDF page, Printed, State, Class, Retry and Cost at fixed widths, Reasons
and Why sharing the rest, and no table indented, so each column stands at one x in every chapter. The Why column says a
page's route level and why as the API parts them (`PageRow.route_level`, `route_why`), the fallback with its glyph, the
whole route in the hover, and the provider's own sentence where it gave one. On a narrow screen the tables keep their
columns and scroll in their own boxes; the page never scrolls sideways. **Measured by two browser checks:** the heads of
six columns stand within a pixel of each other across the page tables of two chapters and two sections; and at 1,280 and
at 390 px, in the table and the chapters, the page never scrolls sideways while every field the API serves for 25 pages
(page, printed number, cost, retry, reasons, the provider's sentence or the route's why) stands in its row. **Not done as
proposed:** line 1 suggested moving Reader and Why into a row's fold at a narrow width; the tables scroll in their own
box instead, which loses nothing and keeps one layout. 219 unit tests, 41 checks in the browser (one skipped), 1,275
Python tests.

**Step 4, the other views, done.** Every list of pages says its Why as the work's page tables do: the Issues and the pages
behind an overview figure now carry each page's route level and why from the API (`IssueRow.route_level`, `route_why`),
one cell for all of them (`RouteWhy`): the provider's own sentence first, else the level's glyph and the why, the whole
route in the hover, never repeated in full on every row. At 390 px, eight views scrolled sideways (the overview's runs,
sources, shelf, a page's readings and its Lab, errors, runs, prompts, calls); each wide table or grid now scrolls in its
own box (`.scroll-x`), and the Lab's line wraps. A browser check visits every view at 390 px and finds none scrolling
sideways, and sees a page that does when one is made. The sanitiser lets a plain `div` through, where line 1's HTML
loader 4 keeps a browser's line break at an element it does not keep. 223 unit tests, 42 checks in the browser (one
skipped).

**One content width (decision 160, the operator on a 2,340 px window: "so that not everything floats so far apart").** Every view
stands in one container of at most 90rem (1,440 px), centred, its gutter inside, as documentation sites and dashboards
hold their content; the two views of two panes side by side, a page beside its reading and an article's original beside
its chunks, take 120rem (`--content-max-width`, `--content-max-width-wide` in `tokens.css`, the route's `meta.wide`). The
header's bar keeps its background across the window, its row in the same container as the view below. In the chapters
table the short columns are as narrow as their content and the note takes 18 to 21rem, so a note such as "not in the
chat's index" keeps one line and a chapter's title, which matters more, keeps the rest; the note of the pages outside the
chapters was shortened to fit. A browser check at a 2,400 px window finds the view at most 1,440 px wide and centred, the
header's row lined up with it, the note on one line, every chapter title under 50 characters on one line, and the page
view between 1,440 and 1,920 px.

**A unit's own pages under it (decision 161.a, the operator: "okay, indentation is missing"; "here too, for the sub-sub-items").**
An opened unit's own pages, those whose text is its own outside every unit beneath it, read as a second table at the
chapters' left edge. They now stand in a tinted block with a rule on its left, one step deeper than the unit's title at
every depth, captioned with their count as the API gives it (`OutlineUnit.own_pages`): "1 page of Chapter 1 Introduction
to Finance itself, outside its sections"; the pages outside every chapter likewise. The block's first column gives up its
indent, so Printed, State, Reasons, Why, Class, Retry and Cost stand at one x at every depth. The chapters' browser check
opens blocks at two depths, finds each to the right of its unit's title, and holds the seven columns within a pixel.
224 unit tests, 43 checks in the browser (one skipped).

**A chat quote from an HTML section opens its article (decision 164.a, from the Sharpe check-along).** A quote from a
Wikipedia, SRE, Lefèvre or Kleppmann section linked only to the source's own page. The chat route now gives each source
whose work is an HTML work of the free catalog its article link, `{source_id, label}`, and a quote the link of the
passage it is quoted from; the view shows "open in the article" beside "open the source", never instead of it. The core
needed no new field: each source already carries its work and its section label (`s5`), and the search names an HTML
work by its catalog id and a section by `s` and its position from 1, as the article view does (`search_server.
free_html_pages`). A test holds that rule for all four HTML works: every work key the search serves is a catalog HTML
work's id, every section label of it resolves, and the article API opens each work's first and last section. A browser
check opens the Sharpe ratio's History from a quote and finds the section marked and in view. 225 unit tests, 44 checks in
the browser (one skipped), 1,285 Python tests.

## V16: said as a person says it (the operator's three items on accounting p. 524)

### Plan

**What** (the operator, 10 Nov, through line 1, on accounting p. 524). Three display items, a minor design change under 142.a, in
this order: (1) every time a person reads is said as a person says it (the operator: "every time stated in the project must get a human date format"); (2) a page's readings are numbered across its readers and each says what it was; (3) a page that
is not served says why in one plain sentence before its chips. **Gates:** a unit test of the formatter on a fixed clock; a
browser check that no view shows a machine's timestamp as text; every word built from fields the API serves.

### Report

**Step 1, human times, done.** The API and every file keep ISO 8601; only the view formats, in one shared formatter
(`human_time.ts`) and one component (`HumanTime`), a `<time>` element that keeps the machine's value in `datetime` and the
full timestamp in the reader's own zone in its hover ("Mon, 9 Nov 2026, 10:21:52 CET"). Recent times are relative ("just
now", "12 min ago", "2 h ago" the same day, "yesterday, 09:21", "3 days ago" within the week), older ones a date in words
("30 Oct, 10:00"), the year only where it is not this one; a calendar day such as a prompt's freezing reads "today",
"yesterday" or "30 Oct". Days are counted by the reader's calendar, not by UTC. The calls group by the reader's day under
a heading said the same way, each call saying its clock alone beneath it. Every view converted: the overview's and the
runs' start times, a run's start, end and chosen pages, the shelf's build, a page's readings, judgements, choice and
trace, a person's verdicts, the prompts' freezing and the calls; the old `shortTime` and its "UTC" headings are gone. Built
on the browser's own `Intl`, which knows the zone and the month names; no library was needed. **Measured:** the formatter's
unit test runs on a fixed clock in a fixed zone; a browser check visits 18 views, every fold opened, finds no ISO
timestamp in the visible text and a full form in the hover of every time said, and finds one when one is put on the page.

**Step 2, a page's readings numbered and said, done.** The Reading History said "attempt 0, 1, 0, 2" for accounting
p. 524: the reader's own count, which starts again for a second reader. Each reading now carries its place among all the
page's readings, every reader's, from 1 for the oldest (`Attempt.number`), and the line reads "reading 4", the one shown
first, the others newest first. What it was is said in the core's own words, which the export carries since line 1's
86efdb2 (`purpose`): "first reading", "the one format retry", "format retry with the errors as a hint, after a plain
retry" (113.a), "read again with the judge's findings as a hint", "second reader", "read again by a replay". The reader's
own attempt, its cell and, for a re-read, the number of the reading it re-read stand in the reading's fold. **On the way:**
before the core said it, the API inferred the words from the reader, the mode and the reading before, and its counts
matched the core's words exactly once they came (40, 37, 19, 1 and 78 second readings); the inference was dropped, so the
API says what the core says.

**Step 3, one sentence first, done.** A page that is not plainly ok says so in one plain sentence above its chips, built in
the API from the export's fields (`PageDetail.said`): whether its reading is served, why, and what stands instead. For a
reading that failed the format check it counts the page's readings that fail it today and names what the one shown left
wrong, from the core's validator messages: "Not served: 4 readings failed the format check, the one shown here with 2
blocks left empty (b12, b15); the PDF's text layer is served instead." Any other page takes the why of its route: "Not
served: the provider blocked the reading; …", "Served despite the judge's findings: the judge's findings lie on blocks
never quoted." An ok page, or one no check has reached, says nothing more. What stands instead is the fallback the export
names in the row's `fallback` (H2.a, 19 Nov): a licensed work with page-numbered legacy Markdown falls back to it, never
to its PDF's text layer, and its page reads "…; the IDE's legacy Markdown is served instead", its route's source
"legacy markdown" in the head and the Routes table; an export written before the field keeps the text layer for every
route that serves no reading. **Found on the way:** two free pages, finance
p. 229 and Reg NMS p. 4, read "1 of 2 readings fails the format check today": their first reading passes today's
validator and their format retry does not, while the text layer is served; passed to line 1. **Measured:** a test of the
sentences for each kind of page, one that every page of the free export not plainly ok has its sentence and no ok page
one, one that every reading is numbered and said; a browser check on p. 524 finds the API's sentence above the chips and
the readings' numbers and words as the API sends them. 233 unit tests, 46 checks in the browser (one skipped), 1,291
Python tests.

**A person's verdict beside the state (decision 166.a, the operator).** A page a person accepted (free accounting p. 635, 657, 706,
the voided 580) still showed the judge's "issue" where its state stood; the accept appeared only in its route and its
Reading History. Every page row, the Issues, the pages behind an overview figure and a page's head now carry a person's
standing verdict (`PersonMark`), which the API takes from the core's own rule (`served_readings.human_standing`): the
latest accept or reject that applies to the reading shown decides, a note never changes it, and a page with only a note
is "noted". It stands beside the judge's state as a person's glyph and its word, "accepted", "rejected" or "noted", the
reason and the note in its hover. A state's chip counts how many of its pages a person accepted or rejected, "issue 9 ·
3 accepted", counted in the API (`Count.accepted`, `rejected`). The Issues and a work's pages offer "A person" as a facet
where a person judged any page, and the overview has a box "A person's verdict" whose counts open exactly their pages
(`/api/pages?person=`). A state's figures are a `StateCount`, so no other count carries them. **Measured:** a test of the standing over a note, an accept, a later note and a reject, and of a
verdict on an earlier reading; a test of the state counts; one of the overview's box and its filter; a browser check that
finds p. 635 accepted and p. 524 noted in the page's head, its work's table and chip, the Issues and its facet, and the
overview's count opening its pages.

**What kind of page it is (decision 172.a, the operator).** Since line 1's d389c0a every exported page carries the reader's
`page_kind` and a `category` from it: content, exercise (a content page whose every outline unit is an exercise section),
index, contents, front matter, back matter, cover, blank, advertisement, or none where no reading named the kind. Every
page row, the Issues, the pages behind an overview figure and a page's head carry both; a page that is not content says
its category quietly beside its state, what the reader called the page in the hover, and a content page says nothing.
A work's pages and the Issues offer the categories as a facet, every one shown and none chosen, so a click narrows; the
API counts them with content first and the pages no reading named, "not named", last. In the Issues the pages that are
not content stand after the rest, ordered so by the API (`IssueRow.apart`), under their own heading, "Not content: noted,
not repaired", as an issue on them is noted rather than repaired (169.a); both lists share one column grid. The overview
has a box "Page category" whose counts open their pages (`/api/pages?category=`). **Measured:** tests of the counts and
their order, of the Issues' order within and across knowledge bases, and of the overview's box and filter; a browser
check finds an index page's mark and hover, the work's chips with none chosen narrowing to exactly the exercise pages,
the Issues' second list as long as the API's pages apart with its columns at the first list's x, and the overview's count
opening its pages. 235 unit tests, 48 checks in the
browser (one skipped), 1,301 Python tests.

**One voice a line (decision 178.a, the operator on finance p. 5, b12: "a pity that 'The judge's evidence:' is not on a new line beneath, and that 'void, by code: names no difference' has no title").** A finding ran its voices into
one line. Each now has a labelled line of its own, the label in bold: "The judge's finding:" with the kind and severity,
struck through where void; "The code's ruling:" with "void: the judge's evidence names no difference", only where the
core voided it, rule 146.a in its hover; "The judge's evidence:" on its own line, the evidence beneath it. After a block's
findings, or the page's own, a person's verdict that applies to the reading shown and names that block, or the page as a
whole, stands as the fourth: "A person's verdict:" accepted, rejected or noted, its reason and its note. A verdict given
on an earlier reading, or on a block without findings, keeps its list as before. One component draws every finding, so
the layout is the same wherever findings show; the Reading History and the Lab count findings and draw none. A browser
check finds on finance p. 5, b12, the judge's, the code's and the evidence's labels in bold and in this order, each lower
than the one before, the evidence beneath its label, and on accounting p. 635, b08, a person's accept as the last voice.

**What a category means (decision 177.a).** A category's hover says what it holds, in one line the API serves with each
row (`category_said`): "back matter: after the main text: appendix, answers, glossary, references, index", "front
matter: before the main text: title pages, copyright, preface, acknowledgements, supporters", and likewise for exercise,
index, contents, cover, blank and advertisement, then what the reader called the page. The terms stay as they are. A test
holds that every category the core can give, but content, has its line (`reading_export.CATEGORY_OF_KIND` and exercise).

**The analysis set apart (decision 181.a, item 2).** The original beside its reading ran on from the Reading History, the
Lab and the details above it. It now stands in a section of its own, "Analysis", under a rule, the image and the reading
inside it. A browser check on finance p. 5 finds the heading, the rule, both panes inside and the history and the details
above it. 235 unit tests, 50 checks in the browser (one skipped), 1,302 Python tests.

**A judgement recalled on the page (decision 181.a, item 1, the operator on finance p. 5: "you see what the old judge looked like, applied to the page").** The analysis showed only the standing judgement's findings. Every judgement row, in the
Reading History and in the Lab, now offers "show on the page": the analysis switches to the reading that judgement judged,
read-only, the shown reading's text from the export and an older one's from the core's reading store on this machine,
with that judgement's findings on their blocks in the voices of 178.a and its block frames on the image. The API serves
it (`/pages/{page}/recall?judgement=<reading key>:<version>:<again>`, `Recalled`), each judgement carrying its id
(`Judgement.recall`), and says so where an older reading's text is not on the machine, as on a clone. The address names
the judgement, so a person can send it. While a judgement is recalled the view is unmistakably not the standing one: a
chip in the top row, "Recalled: judge/2 (prototype) on reading 2, never served", with "Show standing" beside it; a dashed
frame around the analysis and around the row it came from, whose fold stands open; the image's frames dashed; all in the
annotation role, which now also marks a view other than the standing state, its glyph and words always with it. The
quoted text is the standing view's and is not offered while one is recalled. **The annotation role's hue, computed:**
checked with the validator against every role on both themes, the old hues stood 7.4 (dark) and 6.0 (light, a fail) from
the link blue under deutan; the new #f06cc0 and #9c1a8c stand 11.0 and 11.2, 15.1 and 16.3 from error, at 6.4:1 and 7.1:1
text contrast. **Measured:** tests of the recall from the export, from a store and without one, and of ids the page does
not have; a unit test of the switch and the way back; a browser check on finance p. 5 that shows judge/3 with no finding,
judge/2 with its void finding on b12 and its frame dashed, the chip and the frame present while recalled and gone after
"Show standing". 237 unit tests, 51 checks in the browser (one skipped), 1,306 Python tests.

## V16b: one library, one theme (decision 179)

### Plan

**What** (the operator, 10 Nov, on finance p. 5: "Lab has no indentation ... all pages that are alike checked so that the same style and indentation concept is used. A uniform component library and a theme suggest themselves"). An audit of every fold, labelled line, detail list and data table across the views, then one small library
they all use, in steps that each land green: step 1, the folds, the two zones of a view with an analysis part (183) and
the page head's sizes; step 2, labelled lines, detail lists and the page head (184), with the hint registry and the hover
card; step 3a and 3b, the data tables. The audit found 13 folds in 10 files, 3 detail lists, the labelled lines of the
findings, a person's verdicts and the chat, and 16 data tables.

### Report

**Step 1a, one fold, done.** One indent step in `tokens.css` (`--indent-step`, 1.25rem, the step the chapters already
used) and one fold, `FoldSection`: its mark, its title, a count set apart from the name by " · " so "Lab 3" no longer
reads as a numbering ("Lab · 3 judgements tried beside the pipeline, never served"), and its content one step right of
the title at every depth. A fold may be remembered in the reader's settings (`settings.v1`, `foldsOpen`, by a name the
build knows), or opened by its view, as when it holds a recalled judgement. The page's Reading History is now such a fold,
folded on first load and kept as the reader leaves it (183), its title saying what it holds ("Reading History · 2
readings · shown: reading 2 · 1 judgement counts"); the Lab and the details likewise. The folds of the overview's runs,
the calls, the error classes, the shelf, an HTML article's contents and a chat turn's sources and security checks moved
onto it, and their own styles went. The folds of a grid whose columns align at every depth (a reading's line, a chapter,
an HTML outline) follow in step 1b. A browser check opens every fold on six views and finds every fold's content exactly
one step right of its title and the folds side by side at one x; it finds a fold whose content stands at its title when
one is made, as the Lab's did. 241 unit tests, 52 checks in the browser (one skipped), 1,306 Python tests.

**Step 1b, the grid folds, two zones and one type scale per page, done.** The folds whose rows stand in a grid moved onto
the one fold too: a page's readings, whose line is now the fold's title, so the columns align from one reading to the
next behind one mark; an HTML work's outline, a heading with nothing beneath it keeping a mark's step so its title stands
with its siblings'; and a work's chapters and the pages outside them, whose columns must align at every depth, with the
mark in the title cell and the depth indent one `--indent-step` per level. A view with an analysis part, a PDF page and an
HTML article, now stands in two zones (decision 183): the record (`RecordZone`) in the standard width, centred and lined
up with the header's row, which keeps that width on every view; the analysis (`AnalysisSection`) alone in the wide
container, under its heading told by its form, a rule through the middle, framed when an overlay acts on it. On a phone
the panes stack, the image above the reading. The PDF page's title is set at the body's size in bold, as its work is named
in the trail (the operator: "never more than 3 font sizes per page"), and the knowledge base's badge stands centred on its
line wherever it stands. **Measured:** at 2,400 px the record zone at most 1,440 px, centred, under the header's row, the
analysis between 1,440 and 1,920 px, on a page and an article; at 390 px the panes stacked and nothing scrolling sideways;
the Reading History folded on first load and open after a reload once opened; the badge's middle within 2 px of the
trail's; and no text at the title's size on a page view, which the type scale check alone had let pass as the title size
is on the scale, shown failing when the title is set back. 241 unit tests, 53 checks in the browser (one skipped),
1,308 Python tests.

**A person's correction and assessment of the judge (decision 188.a, taken ahead of step 2; the operator: "both must be marked as a manual change").** Since line 1's 879233b a person's verdict may carry the block's text as the person
says it reads (`correction`) and their assessment of the judge (`judge_assessment`, its words in `judge_assessment_text`).
Beneath the finding's voices, where the verdict applies to the reading shown and names the block, two more stand: "Manual
correction by a person:", the reader's text struck through and the corrected text beneath it in the annotation role,
dashed (**→ now** 229.a, 12 Nov: the correction stands first in its block, the reading muted beneath it); and "A person's assessment of the judge:" in their words, their note in the hover. Nothing served changes: the
quoted text stays the reader's. A browser check on finance p. 94, b05 finds both after the person's verdict, the reader's
text struck through, the correction dashed, and the assessment in the person's words. 242 unit tests, 54 checks in
the browser (one skipped), 1,309 Python tests.

**The printed words an attribute carries (decision 190.a).** A glossary entry's term stands in its attribute
(`::: {#b19 .glossary_entry term="accrual-basis accounting"}`), its definition as the body, and the readable mode showed
the definition alone (finance p. 136, b18 to b24). The core reads its quotable text and chunks as "term: definition" since
PDF loader 9; the view now does the same, the term in bold before the definition, a bibliography entry's key (its
printed number) before the entry, and a contents entry's target (its printed page) after it, only for those classes. A
browser check on p. 136 finds b19's term in bold before its definition. 243 unit tests, 55 checks in the browser
(one skipped), 1,309 Python tests.

**Step 2a, labelled lines, the page's record and its first finding, done.** Two more parts joined the library:
`LabelledLine`, a bold label and its value at the body's size, and `DetailList`, the key-value list, which the page's
details, a run's facts and the routes' legend now use. A PDF page's head reads as labelled lines (decision 184): "State:"
with its reasons, "A person:" beside it, "Category:" where it is not content, "Route:" in its parts as the API parts them
(`route_level`, `route_source`, `route_reader`), "Why:" on its own line, "Reading:" with its place among the page's
readings, retry, cost and the image's match, and "Findings:" saying what they come to (`findings_at`,
`findings_outcome`): "b12 void by code · a person accepted the reading", or "b03 stands · the page serves its text layer",
each block still a jump. A page with findings opens on the first (decision 186, `focus`), framed on the image and in view
in the reading's own pane, the window unmoved; the Issues' links carry it (`?focus=b05`), and a reload keeps it. **Measured:**
tests of the new fields on finance pp. 5, 119 and an ok page; unit tests of the two components; browser checks that
p. 5's labels stand in order, bold, and its findings line names the void and the accept, and that p. 94 opens framed on
b05 with the window at its top, an Issues link carrying it and a reload keeping it, while an ok page frames nothing.
245 unit tests, 57 checks in the browser (one skipped), 1,310 Python tests.

**Step 2c, a figure's labels and chapter art, done.** Since a figure's body keeps its line breaks (accounting p. 305), a
chart's tick labels stood one per line down the pane (the operator on finance p. 94: "the line break here is spam; just imagine large diagrams"). An ungrouped figure's labels now run on in one wrapped line parted by " · ", folded to one line
beyond a dozen ("▸ 25 labels"); a photo's always, its fold's title the first sentence of the figure's description where
the reader wrote one (the operator on p. 387: "mostly the description is more interesting than the values"). A grouped figure keeps its
boxes, and the raw text keeps the reader's lines. A photo on a page the reader called a chapter opener is chapter art
(decision 194.a, the operator: "just a decorative image, not a real photo"): the API marks the block (`Block.decorative`, "a photo on a
chapter opener"), so the view decides nothing of its own and a later core rule can use the same field; the view names it
"Chapter art", folded and quiet, never hidden, and its findings come after the page's others in the record's findings
line. **Measured:** unit tests of the run, the fold, the photo's title and chapter art; a test that p. 387's b01 alone is
marked; a browser check that p. 387's b01 shows "Chapter art" folded with its count, p. 94's chart stands at most two lines
high, and accounting p. 305's grouped figure keeps its eleven boxes. 247 unit tests, 58 checks in the browser (two
skipped on today's data), 1,317 Python tests.

**Step 2b, part one: a person's verdicts, protection and reset, done.** Since line 1's latest exports a person's verdict
may be for the page as a whole, and may rate every finding of the page. Under a finding whose block no verdict names, the
latest page-level verdict that applies now speaks, as "A person's verdict on the page:" with its assessment of the judge
(the operator on finance p. 408: b10's finding showed no verdict, as the walk's named b05 only); the record's findings line follows
the same verdict. A page a person checked is `protected` (191.a), said with a shield and the word in the "A person:" line; a
person's `reset` (191.a) stands as its own line with its reason and time, and a verdict given before it is archived, shown
greyed in the history as "archived by a reset", with that reset's time, and never applying. Two repeats went: where a
page is served because a person accepted it, the sentence above the record says so short ("Served: a person accepted the
reading.") and leaves the person's note to "Why:"; and the reason `other`, whose words are a placeholder, reads as the
start of the note, the whole in the hover. **Measured:** tests on p. 408 and an invented reset; unit tests of the page
verdict's label, the placeholder left out and an archived verdict; a browser check on p. 408. 249 unit tests, 59
checks in the browser (two skipped on today's data), 1,319 Python tests.

**Step 2b, part two: one hint, one hover card, done.** Every explanation now takes one pattern (from the operator's viewer's rules):
a registry of hints (`hints.ts`), each with its label and lead sentence, opened by one mark (`HintToggle`) into one
closable panel (`HintPanel`) that adds the API's own figures beneath the lead. The route levels' legend and the dashed
line's meaning moved onto it. Data under the pointer is a card that holds data only (`HoverCard`): rows of a label and a
value, its title naming what it is about, opened by the pointer or the keyboard's focus and fixed to the window, so a
table's scroll box never cuts it. A page category's card says what it means and what the reader called the page, a
person's verdict's card its reason, note, who and when, and the page's route its level, source, reader and why; their
browser tooltips went. The tooltips of views not touched in this step stay until those views are. **Measured:** unit
tests of the hint and the card; a browser check that the routes' hint opens with its lead and legend and closes, and that
the route's card stands inside the window with its data while its line holds no tooltip; the checks of a person's mark and
a category read their cards. 251 unit tests, 61 checks in the browser (two skipped on today's data), 1,321
Python tests.

**Step 3a, the page and work tables, done.** One data table joined the library (`DataTable`): its scroll box, so a narrow
screen scrolls the table and never the page, its column grid from the widths a view gives, and one look for its head,
cells, links and figures. A work's page tables, the Issues' grouped lists, the routes' table and a page's two tables of
judgements, in its history and its Lab, now use it; each keeps only what is its own, such as a column's colour or a row's
rule, and the copies of the shared rules went. A browser check opens every fold of a work, a page and the Issues and finds
no table there that is not the library's (a reading's own table aside, which is the page's content), and finds one when one
is put there; the checks of the columns' alignment hold as before. Step 3b moves the other views' tables. 253 unit
tests, 62 checks in the browser (two skipped on today's data), 1,321 Python tests.

**Step 3b, every other table, done.** The tables of the overview (its boxes and its latest runs), the runs and a run, the
calls, the error classes, an HTML work's sections, the prompts' versions, the shelf, the sources and a chat turn's list of
works moved onto the library's table, taking its scroll box, its look and, where they stood at the column's whole width,
its `wide` option; the prompts' table keeps its fixed grid. Four views had wrapped their table in a scroll box of their own
under a condition; the condition moved onto the table and the second box went. Each view keeps its own rules for its cells
only. The browser check that finds no table outside the library now walks every view, every fold opened. With this the
library holds what decision 179 asked for: one fold, one indent step, two zones for a view with an analysis, a labelled
line, a key-value list, one hint, one hover card and one data table, on the type scale and the colour roles of
`tokens.css`. 253 unit tests, 62 checks in the browser (two skipped on today's data), 1,321 Python tests.

**Checked along: judge/4's verdicts (11 Nov).** Line 1 sent four pages on which judge/4, a prototype on another model, had
judged, for the operator to open before deciding which judge becomes active. Against this API's JSON: the export of the evening
before held none of its judgements, as they came in after it; line 1 wrote it again, and on finance pp. 94 and 119 and
accounting p. 969 judge/4 now stands in the Lab, a prototype, never served, its findings on the blocks they name when
recalled, the person's verdicts beside them as given. Accounting p. 69's judgement judged the mini pilot's reading of the
page, which is not among the page's readings, so the page does not show it; the reading it serves has the table's title
the pilot reading lacked. Two faults were the view's own. A judgement's row said "1 finding" and no more, so finance
p. 94's minor finding under judge/4's ok showed only once the judgement was recalled; a row now says the severity of the
findings that stand and how many are void ("1 finding: minor", "3 findings: 1 major, 1 minor, 1 void"). And a person's
assessment of the judge was said of "the judge" beside whichever judge's findings were shown, so on finance p. 119 the
person's "false alarm", given on judge/1's finding, stood under judge/4's as if it were said of it. The core records no
judge with an assessment; the person rated the finding the page showed them, the one of the judgement that counted on that
reading when they gave it, and the API now names that judge (`assessed`), so the line reads "A person's assessment of
judge/1:". **Measured:** Python tests of the judge named, from invented judgements and verdicts, and of a recalled
prototype keeping the assessment's judge; unit tests of the findings' severities in both tables and of the named judge;
pp. 94 and 119 looked at in the browser, judge/4 recalled. 255 unit tests, 62 checks in the browser (two skipped on
today's data), 1,323 Python tests.

**The page's head said once, and one text size (11 Nov).** The operator looked at finance p. 119 and asked what is best practice
for the best overview, then: "I prefer everything uniform". The head said "a person accepted the reading" four
times (the sentence, "Why:", the findings line, beneath the block) and the person's note three times; its values started
wherever their labels ended; a red "issue" stood beside a green "accepted" on a page served because a person accepted it;
and the text ran 150 characters a line. Now each thing is said once. The API gives the head's "Why:" its own field
(`why_line`): the route's why only where nothing else says it, so no line where the sentence above is built from the same
why, and for a person's why only their note, only where it stands beneath no block. The findings line says what they
come to only where neither the sentence nor a person's line does. The person's line holds their standing and the page's
protection, the reason and note in its card. The labels and values stand in two columns (`LabelledLines`, a library
part), the label column as wide as the longest label the record has, so the values stay in one place from page to page.
A person's accept or reject decides what is served, so their line comes first and the pipeline's state follows,
receding, its glyph and word kept. Running text is held to 100 characters a line, the person's note beneath their
verdict is a line of its own, as the judge's evidence is, and a long one no longer begins its second line with the dot
that parted it. **One text size:** measured in the browser over 17 views, the font was one already, monospace, form
controls included; the sizes were the three of 159.a, the head and the reading at 16 px beside lists, folds and findings
at 13.6. Every text now has one size, `--font-size`, the 13.6 px the lists and tables had, so their columns keep their
width; a view's title and a heading are told by their weight. A heading, `small` and a form control, which the browser
sizes by its own scale, take the body's; only a formula's own parts, KaTeX's and a sub- or superscript's, keep their own.
A side effect on p. 119: finance's Figure 4.4 table now fits the reading's pane without scrolling. The second pane's
share (whether a switch for image, both or reading) is left open for the operator. **Measured:** Python tests of the why and the
findings line, said once, from invented rows (an ok page with a void finding, a second reader's why, a person's accept on
the page and on a block); unit tests of the head's order, the receding state and the note on a line of its own; a browser
check that every view's text has the one size, with a control that finds a title and a form control set apart; a browser
check of the aligned values on two pages, one with a person's line and one without. 257 unit tests, 62 checks in the
browser (two skipped on today's data), 1,324 Python tests.

**A page a person settled leaves the issues (decision 211.a, 11 Nov).** The operator: "I would like to take pages judged by a person out of the issues". The Sources counted finance as "issue 8" where a person had accepted seven of those pages and
noted the eighth; the served route already followed the person, and so did the core's shelf, which counts by route; the
views alone counted by the check's state. The API now gives every page a `listed_state`: its check's state, or
`decided_by_a_person` where that state is one to look at (issue, blocked, stopped) and a person's verdict stands on the
reading shown, by the same rule as the page's person mark, so a verdict a reset archived, or one given on another reading,
settles nothing and the page is an issue again. Every count and every narrowing of the views goes by it: the Sources'
and a work's state counts, a chapter's columns, the overview's states and its "to look at", and the pages a figure opens.
The bucket stands between what is not known and what to look at, with a glyph of its own (a gavel, a decision's), quiet,
and its chip says the verdicts that settled it ("· 7 accepted · 1 noted"). The Issues keep a settled page as a record, in
a fold of its own below the open pages and the ones that are not content; "No page needs a look." says that every listed
page is settled, never that a filter hid the open ones. The check's state is never hidden: in a list's row it stays
beside the person's mark, receding, and in the page's record the line is now named "Check:", after the person's, so it is
read as what the check found, not as what the person decided. A note on a page the check passed changes nothing there.
**Measured on today's export:** finance issue 0, decided by a person 8 (7 accepted, 1 noted); accounting issue 9, decided
4 (2 accepted, 2 noted), blocked 3; Regulation NMS issue 1; the pages a person judged that the check passed (accounting 4,
finance 1) stay ok. Python tests from invented rows (an accept, a note, an accept a reset archived, an untouched issue,
an ok page accepted) through the counts, the lists, the page and the overview; unit tests of the Issues' fold, the bucket's
chip and its tally; a browser check of finance's counts in the Sources against the API's own listing, the Issues' fold and
a settled page's record. 259 unit tests, 63 checks in the browser (two skipped on today's data), 1,332 Python
tests.

**A note's marker, a superscript and a subscript, each as itself (decision 206.a, step 1, 11 Nov).** The reader writes a
note's marker as "[4]{.fn}" and a raised figure as "[2]{.sup}"; the core has so far given both as plain text, so the view
showed "processes.4" and "12.52". Before the core gives them as segments of their own (205.a), the view is ready for
them: a segment is now text, math, code, a note's marker (`fn`), a superscript (`sup`) or a subscript (`sub`). A
superscript is raised and a subscript lowered; a marker is raised and, where the page holds its note (a footnote block
whose `marker` is the marker's content), it is a link: the API names the note (`note`) and gives its text (`note_text`),
the card under the pointer shows it, and a click brings the note into view and marks it, as a finding's block is brought.
A marker without its note on the page stands alone; where two notes share a marker, the first stands. The text the
search and the chat quote is the core's ("processes.[4]"). **Measured:** a Python test of the link, in prose and in a
table's cell, from invented blocks, with a marker no note carries; unit tests of the marks, the card and the jump, and of
the page marking the note when its marker is clicked. Nothing changes on today's pages until the core gives the segments. 262
unit tests, 63 checks in the browser (two skipped on today's data), 1,333 Python tests.

**A person's correction of a table, as a table (decision 204.a, 11 Nov).** On finance p. 119 the correction of the Figure
4.4 table stood as its HTML source, safe but hard to read. A table block's correction is now read by the core's own table
parser, as a reading's tables are, and the API gives its cells (`correction_rows`); the view draws them with the table
a reading's block uses, now a library part of its own (`ReadingTable`, taken out of the reading's blocks), in the
annotation role and dashed as a person's correction is. A correction that parses to no row, or with a problem, and any
correction of another block stay the text they are; the correction's text itself is kept beside its cells. A line break
in a cell is a space, as in the reading's own tables. **Measured:** a Python test from invented blocks (a table corrected
with a grid, a paragraph corrected in words, a table corrected with words); a unit test of the drawn table and of a
correction in words; a browser check that finds a page with a table's correction among the listed pages at run time and
sees a dashed table with no source text.

**A reader prototype's reading stands in the Lab (decision 210.a, 11 Nov).** Line 1's export now lists the readings of
the reader prototype page/2 beside a page's own, 26 of them, each `prototype` and with its `reader_version`, never
served, chosen or checked. They had begun to stand in the Reading History as readings of the page. The history now holds
the pipeline's readings alone, and its count says so; the Lab holds a prototype reading with every judgement on it, its
reading said as line 1 names it ("reading 2, page/2 (prototype), never served"), and a prototype reading no judge has
judged as a row of its own. Its fold says what it holds ("1 reading and 4 judgements tried beside the pipeline, never
served"). Shown on the page, a judgement of such a reading says who read it: "judge/4 (prototype) on reading 2, read by
page/2 (prototype), never served"; accounting p. 305 shows eleven T-account tables there, where the page serves one
grouped figure. **Found on the operator's look at a work (11 Nov):** the chapters' state columns were 7rem each, and "decided by a
person" (211.a) ran into the note's heading; a state's column is now as wide as its word with its glyph, at least 7rem.
**Measured:** a Python test of a prototype attempt and its recall's line, from an invented row; a unit test of the history
without it and of the Lab with it, a judged and an unjudged one; a browser check that finds such a page at run time, sees
the history without the reading, the Lab's row and the recalled line; the chapters' check sees no heading run over, and,
with the old widths put back for a moment, sees one. 264 unit tests, 65 checks in the browser (two skipped on today's data),
1,338 Python tests.

**A person's verdict has one look, and a judge's rules for the reader stand in the Lab (11 Nov; decision 202.a).** The operator,
looking at finance p. 119's history: a clear line is wanted for every kind of thing, and a new way of showing one only
where it is really needed. A person's verdict had two: beneath a block "A person's verdict: accepted", its note a line of
its own; in the history and the details "A person: accept · …", in italics, its note run into the line and begun by a dot
where it wrapped. It now reads the same everywhere: the bold label, the word for what the person did (one module of
words for both, `person_words.ts`), the reason, the block, who and when in the line, and the note beneath. The rules
judge/4 proposed for the reader, which line 1's export now carries with each judgement (`reader_rules`), stand in the
Lab right beneath the judgement that proposed them, read-only, under "Proposals for the reader, never applied:": each its
kind, its block, the class, attribute and value it names where it names one, and the rule in the judge's words; on
finance p. 119 judge/4 proposed, twice, the very rule the person's correction follows (an account's heading spans its
two columns). **Measured:** a Python test of the rules from an invented judgement, a field the export leaves '' said as
none; unit tests of the verdict's one look in both lists and of the rules beneath their judgement and no other; a
browser check that finds a page with rules at run time and sees them beneath their judgement. 266 unit tests, 66 checks in the
browser (two skipped on today's data), 1,340 Python tests.

**The last browser tooltips, onto the library's card (decision 203.a, 11 Nov).** Where 179 left a browser tooltip in
parts it did not touch, the library's card now stands, or nothing, where the tooltip only said again what the page says
already. A page row's why opens a card with the route's level and its whole route; a row that says nothing has none. A
void finding's ruling opens a card with the rule that voided it. In an HTML section, "N shared" opens a card saying how
many characters and with which chunk; the dashed text itself carries no tooltip any more, as the view's hint says what
the dash means. A person's assessment of the judge no longer repeats their note in a tooltip, as the note stands beneath
their verdict. **Measured:** unit tests of each card and of the tooltips gone; the browser checks of a void finding and of
an issue's why open the cards. 266 unit tests, 66 checks in the browser (two skipped on today's data), 1,341 Python
tests.

**Checked along: the demo views for the deck (11 Nov).** Line 1 asked for a walk of the views the review will show, free
pages only, nothing built. Each view's claims were checked against the API in a browser at 1,600 px: the Sources' counts
agree with the Issues (finance issue 0, decided by a person 8; accounting issue 3, decided 4, blocked 3, the six pages
validator page/1.3 made servable gone from its issues); finance p. 94's description carries the person's correction, its
Lab holds judge/2 to judge/4 on reading 1, judge/4's minor finding reading the crossing at 2012, and nothing found on
page/2's reading; p. 119's correction stands as a table under judge/4's structure finding, with its proposals in the Lab;
accounting p. 305 shows one grouped figure under page/1 and eleven tables under page/2; SR 11-7 p. 5's marker opens its
note; accounting p. 958's route names validator page/1.3, its answer items 7 and 17 each right before their journal
table. **The view's own fault it found:** a hover card opened beneath its host whatever the room, so a note's marker at
the window's foot opened a card the window cut to its title; a card now opens above its host where the foot would cut it.
**Measured:** a unit test of the card beneath and above, from given boxes; the walk again, the card whole. 267 unit tests,
66 checks in the browser (two skipped on today's data), 1,341 Python tests.

**The head's findings in a finding's own look (12 Nov).** The operator on accounting p. 524: "Findings in the header should get the red flag or red text, whichever makes more sense for the UI, so that they catch the eye at once by their colour." The head named each block with findings and "stands" in plain text, while the blocks below carried the red flag
and "major". Now each block in the head wears its finding's look: the flag and the severity's word in that severity's
role, the error role for major, the warning role for minor, the block still a jump to it; where code voided every finding
on a block, the flag and the ruling ("void by code") recede. The API gives each block the gravest severity among its
findings that stand (`FindingsAt.severity`), so the view chooses nothing. Form before colour: the flag and the word read
in greyscale too. **Measured:** a Python test of the gravest severity, a void one counting for nothing; a unit test of a
major, a minor and a void block in the head; a browser check that finds a page with a standing major finding at run time
and sees the head's flag and word in exactly the colours the finding has beneath its block. 269 unit tests, 67 checks in
the browser (two skipped on today's data), 1,342 Python tests.

**A work's head on its pages' grid (decision 219.a, 12 Nov).** The operator: "the detail page turned out well. Here I would carry the same line through, as far as possible and sensible." A work's head now reads as a page's: labelled lines, the label
column as wide as the page head's, so neither labels nor values move between a work and its pages. "Work:" names its
knowledge base and id, "Pages:" its count, then each facet a line of its own (State, A person, Category), and "PDF page:"
the field that jumps to one; the routes stay a fold beneath, as a page's history and Lab do beneath its record. A work's
id and its facets have no line of the same kind on a page and take the same form. The facet bar is a set of labelled
lines wherever it stands, so the Issues and the calls read their filters the same way (the operator, 11 Nov: labels and buttons
in one line "looks messy"); a line of toggles sets its label level with the toggles' first row. And a label's words
now meet its value's: lines were set by their baselines, and a value that begins with a glyph (a person's mark, a
state's) set its label 3px below its words; label and value now stand at the line's top. **Measured:** a unit test of
the work head's lines and its jump named for a reader that cannot see the label; a browser check that a work's head and
one of its pages' share the label and the value column, with a control that widens one and sees them part; a browser
check that every line's label and value words meet on both heads, with a control that sets them by baseline again. On a
phone a facet's toggle wraps its own parts, as "decided by a person 8 · 7 accepted · 1 noted" is wider than the value
column beside the labels; and a hover card lets the pointer pass through it, as it holds nothing to click, so a card left
open over a row never takes a click meant for what lies beneath. 270 unit tests, 69 checks in the browser (two skipped
on today's data), 1,342 Python tests.

**A person's verdict from the page view (decision 213.b, 12 Nov).** The operator: "this really is the last proper feature before the freeze." Until now a person's verdict was given on the command line, the page open beside it; now it is
given on the page. **Off by default (223.a):** started without `--allow-verdicts`, the app has no write route and no
control, and `POST /api/verdict` answers 403 saying how to turn it on. Started with it, a page's head offers "Give a
verdict" on the standing reading, never on a recalled judgement, which is not what the page serves. The dialog takes the
verdict, its reason in the core's words, the page as a whole or one block (the first finding's by default), a note
(required for the reason `other`, which says so), the person's assessment of the judge where the page has a finding, and
a correction of the chosen block (224.b): started from the person's last correction of it, else the block's text as the
reader wrote it, a table's as its HTML, and shown beneath as the table it would be, read by the core's own table parser
(204.a's path, `POST /api/verdict/preview`, which writes nothing). A correction is sent only where it was changed.
**What this view adds is the form, not the rule:** the API hands everything to the core's `human_verdict.from_view`,
which checks each value again, records the verdict append-only in the pipeline database, and sets the export going in
the background; a value it refuses comes back as 422 in its own words. The dialog says "Recorded · the view updates after
the export (about a minute)", follows the export, and loads the page again when it has finished (line 1, once end to end
on copies of the export and the database: 53 s; 41 s for the export alone on an idle machine).

**Gates.** The write route stands behind the chat's guard (a request addressed to this machine by name) and an Origin
check (a browser page from another site cannot send one); under `--public-only` it takes no verdict on the licensed
knowledge base, which is not served. No test writes the real pipeline database or the real export: the Python tests
replace the core's function and give the export queue nothing to run, the browser check starts the app without the switch
and answers the form itself, and aborts any verdict sent. **Found on the way:** a person's correction of a table the reader
had marked unreadable (accounting p. 524, b11) showed as its HTML source, since the rule asked the block for cells of its
own; it now asks whether the block is a table, so that correction stands as a table too. **Measured:** Python tests of
the switch (403 and the form saying why), the form's lists from the core, a verdict reaching the core by the export's name
for the work, 422 in the core's words and 404 for a page or knowledge base not served, the host and Origin guard, the
preview, and the unreadable table's correction; unit tests of the dialog's rules, its prefill and preview, its send held
until valid, the export followed until it has finished, the core's refusal said, and the control only where verdicts are
taken and never on a recall; a browser check that the read-only app shows no control and refuses the route, and that the
dialog opens on the finding's block with its correction prefilled and previewed, never sending. 281 unit tests, 70
checks in the browser (two skipped on today's data), 1,358 Python tests.

**Every page opens on its reading (decision 227.a, 12 Nov).** The operator, on optics: a control a person uses again and again
never moves. A page served from its text layer opened on the quoted text since V7, every other on its reading, so the
switch stood on a different button from page to page while a person walked the issues. Now every page with a reading
opens on it, the text-layer pages too: their head already says what is served ("Not served: … the PDF's text layer is
served instead"), and the quoted text is one click away. A page without any reading (the provider blocked it) still opens
on the quoted text, its only choice. A text-layer page with a finding now also opens framed on that finding in its
reading, as other pages have since 186. **Measured:** the unit test of a text-layer page now pins the reading and the
quoted text asked only when chosen; a browser check opens accounting p. 398 (text layer, its reading malformed) and Kelly
p. 4 (served) on the same switch, and Kelly p. 3 (no reading) on quoted. 281 unit tests, 71 checks in the browser (two
skipped on today's data).

**A correction first, and a cell's line break drawn (decision 229.a and two faults, 12 Nov).** The operator gave the first real
verdict from the dialog on accounting p. 398 (verdict 32: b04, a list item that wrote its journal entry as HTML, corrected
to its marker "A."), and the page showed two faults. A text correction on a block without findings was not shown at all:
only a block with findings drew a person's correction, beneath them. And a `<br>` inside a table cell, which page/1
allows, was drawn as a space, so "Accounts Payable / Merchandise Inventory | 600 | / 600" read as if both amounts stood
on one line. The operator then decided how a corrected block reads: "what you really want to see first is the correction." **Now**
the API gives each block the correction that stands for it on the reading shown (`Block.correction`: the latest a person
gave that applies and was not archived by a reset), and the view draws it first, as the block's content, in the one look
of a person's correction (the annotation role, dashed, now one shared class), its line saying "Manual correction by a
person · not served yet", who and when; the reader's text stands beneath, muted, under "The reading, as the reader wrote
it:", or "The reading holds no text for this block." where the reader marked the table unreadable (p. 524, b11). The
verdict, its note and the assessment keep their place beneath the findings; the correction is not drawn twice, and an
earlier correction stays there, said as earlier. "Not served yet" because the search and the chat still quote the reading
or the text layer: the quoted pane stays the truth about what is served. The verdict dialog starts its correction from
the same `Block.correction`. **The break:** the core's table parser reads `<br>` as a space, which its quoted text needs
(a table quoted one line a row), so the API reads a cell again with the same parser, each break held by a private-use
character, and gives the view a `br` segment there; a table without a break is given exactly as before, and where the
second reading would not give the same grid the first stands. The reading's tables, a correction's table and a recalled
reading take the same path. **Measured:** Python tests of the breaks on p. 398's journal entry (and `<br/>`), of a table
without one given unchanged, and of the correction that stands (the latest of several, never one on an earlier reading or
archived, text or cells); unit tests of the correction first and the reading muted beneath, drawn once, an earlier one
kept, a block without one as before, and of a cell's break; browser checks on finance p. 94 (text over a description),
p. 524 (tables over unreadable tables), the table correction found at run time, and p. 398's journal entries two lines
high with Kelly p. 7's tables unchanged. 283 unit tests, 73 checks in the browser (two skipped on today's data), 1,363
Python tests.

**A validator's error on its block, and the raw text's lines numbered (decision 228.a, 12 Nov).** The operator on accounting
p. 398: "then the only thing that still confuses me is that the error stands at the top, although I entered a correction"; on p. 338:
"line 86? then please line numbers in the read-only editor too". The validator's errors stood as one red list above the
reading, whether or not a person had looked. Now the API parts each error into the block and the line it names
(`Reading.error_places`, read from the validator's own wording, "block b04 (line 26): ..." or "line 86: ...") and says
whether a person has looked: the latest verdict that applies to the block, else to the page as a whole, and whether a
correction stands for the block. The error stands on its block in the look a finding has beneath its block, "The
validator's error:" with the flag, red until a person has looked; then muted, and saying so ("a person noted and
corrected b04"), never hidden, since the error is the validator's verdict on the reading, which a person's verdict does
not change. The list above stays; each entry jumps to its block and offers "show raw", which opens the raw text at its
line, marked and in view; an error that names only a line (p. 338's line 86) has only the latter. The raw text numbers
its lines in a gutter as the validator counts them, line 1 the front matter's first `---`; the numbers are not part of
the text, so the text copied is the text stored. **Measured:** Python tests of the parting (a block and a line, a line
only, a block the parser could not name, no place at all) and of who looked (a verdict on the block, one on the page, one
on an earlier reading or archived never), and of p. 338's lines 86 and 101 in the tracked raw text; unit tests of the
words, the error on its block red and then muted, the list's ways to block and line, and the raw text numbered, marked
and left as stored; a browser check on p. 398 (b04 muted, line 26 marked and in view, the gutter's number not in the text
nor in a selection) and p. 338 (line 86 without a block, b13 red). 287 unit tests, 75 checks in the browser (two skipped
on today's data), 1,365 Python tests.

**A chapter's count opens its pages (decision 225.a, 12 Nov).** The operator: a click on chapter 6's red or yellow count should
lead to the pages behind it, "Multiple Choice" and p. 398, "6.2 Compare and Contrast ..." and p. 360. The API now gives
each unit of a work's order the pages behind each count that opens them (`OutlineUnit.state_pages`), counted exactly as
the count beside them: the states a person should look at (issue, blocked, stopped) and the pages a person decided,
since p. 398 left the issues for that bucket with the operator's verdict the same evening; a fine count, and one not yet checked,
stay figures. Such a count is a button in the state's own colour, underlined: a click opens every unit that holds those
pages, down from the chapter, as if the reader had opened them, and marks the pages as the block on show is marked, the
first brought into view; the row's own fold stays as it was. **Found on the way:** brought into view whole, a marked row,
wider than the chapters' box, scrolled the box sideways and cut the titles off; the row's first cell is brought into view
instead. **Measured:** a Python test that every count's pages are exactly as many as it counts, in its state, and that a
fine chapter opens nothing; a unit test of the issue count opening its chapter and section and marking page 5 alone, the
ok count a figure; a browser check on accounting's chapter 6 (each count's pages marked, the first in view, the box not
scrolled sideways) and a chapter whose counts are all fine. 288 unit tests, 76 checks in the browser (two skipped on
today's data), 1,366 Python tests.

**The judge's stage in the details, one fact a line (16 Nov).** The operator, before the review: "purely visual finalizing only". The details' stage 3 ran why the judge looked, its verdict and which judge it was into one line; they stand
as labelled lines now, in the page head's look (Why, Verdict, Judge), and a page the judge left out says only why. No
data changed. **Measured:** a unit test of the three lines and of the one line of an unjudged page; a browser check on
finance p. 113 (judged ok), p. 21 (not judged) and accounting p. 524 (judged bad).

**Ready for a public repository (decisions 263.a to 266.a, 16 Nov).** The repository goes public from its first push, so
three things changed here, none of them in a view. Every route now answers only a request addressed to this machine by
name (`app.TRUSTED_HOSTS`: 127.0.0.1, localhost and [::1], checked by Starlette's `TrustedHostMiddleware`): a page
elsewhere that points a name of its own at 127.0.0.1 (DNS rebinding) is refused with 400 before any route runs, where
before only the chat and the verdict route checked the Host; their own Host and Origin checks stay behind it as a second
wall. The build writes the licence notices of every package it bundles beside the UI, `dist/THIRD_PARTY_NOTICES.md`, with
Vite's own `build.license`, so no package was added and the notices list exactly what `dist/` ships. And the code, these
docs and the protocol name the operator by role, with their quotes in English; a licensed work's key and the licensed
shelf's counts gave way to invented names and to the free figures. **Measured:** a Python test that a foreign Host, the
test client's own `testserver` among them, gets 400 on the GET routes and the UI while 127.0.0.1, localhost and [::1] get
the works, and one that the routes' own check still refuses a foreign name; 291 unit tests, 75 checks in the browser (two
skipped on today's data), 1,368 Python tests.

**Why a reading stands as it does, what it cost, where its error lies, and a box's stroke (A.a, 18 Nov).** Four things the
operator found on licensed pages, built from fields the core exports. (a) A reading in the Reading History said
"malformed · issue" and not why: each reading now says the check's reasons in the core's words ("Why: format: malformed")
and the validator's own messages where it failed its format check ("Format check: block b04 (line 26): …", at most 8 as the
core exports them), in the look a validator's error has above the reading; a reading no check reached says it all the same.
The API's `Attempt` carries `format_errors` and its cost, `AttemptCheck` its `reasons`. (b) A reading read in a Claude Code
session (280.a) has no cost an API ledger holds: its cost is None, from the reading's own attempt where the export lists
it, and the view says "external cost, not measurable", never 0. Every cost in the UI now goes through one formatter,
`cost_format.ts`: nothing paid says 0, a dollar or more keeps its cents, less keeps two significant digits (0.014, not
0.0136), so the runs no longer stand in a column of 0.0000. (c) In the raw text an error is marked as a compiler marks
one: the whole block it names, from its opening fence to its closing `:::` (`ReadingError.lines`, from the core's own
`CLOSER`), since the validator names the line a block opens on while the fault may stand lines below; the named line
strongest, its number in the error's colour, and an error a person has looked at with a quiet bar. (d) The boxes on the
original "always a little off": measured against the bbox on finance pp. 21 and 113 and Kelly p. 4, every frame sat on
it to 0.03 px, so the transform was right; but a box hugs the printed text, and its 2px stroke, drawn inside the box,
covered the glyphs' outermost pixels. The stroke now stands just outside the box (an outline), the box itself unchanged.
**Measured:** Python tests of the attempts' reasons, messages and costs, a session reading's None and an older export's
row cost, and of a block's lines (closed, left open, last); unit tests of the formatter, of the history's why and costs,
and of the raw marks; a browser check of the stroke outside the box (shown failing first against the old build) and of
b13's block marked on accounting p. 338; 298 unit tests, 75 checks in the browser (two skipped on today's data), 1,403
Python tests. `npm audit --omit=dev` reports a new advisory on `picomatch` (every version), which reaches the list
through the build tools of Vite and vue-router and is not in the bundle; its only offered fix downgrades vue-router to 4.

**A fault's own line, and an automated review told apart from a person (18 Nov).** Two things line 1's core now
exports. The validator page/1.4 names, for three of its errors, the page line the fault stands on, after the problem's
name ("LaTeX command outside math on line 28: …" in a block that opens on line 26); `ReadingError.at_line` carries it,
and the raw view marks that line strongest inside the block's tint, and "show raw" opens the text there. And a verdict a
Claude Code session gave on the operator's delegation is now an automated review's, never a person's (the operator's
2.a and 3.a: "a person is always manual"): every verdict carries `by_a_person`, by the core's own rule
(`served_readings.by_a_person`), and the view names it so wherever it stands: "Automated review:" in the page head with
a machine's glyph instead of a person's, beside a block, in the history and the details, "Correction by an automated
review", and who looked at a validator's error. "Protected" is the export's alone, and only a person's verdict protects.
A page the check listed to look at that an automated review settled leaves the open Issues, as the core serves it so,
but in a bucket and a fold of its own, "Decided by an automated review" below "Decided by a person" (line 1's choice Q.a),
and the counts keep it apart: a facet "Automated review" beside "A person" in the Issues and a work's pages, and a section
"An automated review's verdict" in the overview, whose counts open their pages. **Measured:** Python tests of the exact
line, of a delegated verdict in an older export said by its giver, its bucket, its counts and the head's sentence, and of
a person's verdict standing as before; unit tests of the wording, the Issues' fold and facet, the page head and the raw
mark; a browser check on Regulation NMS 600 p. 4, the free base's one delegated accept. A state's word in a facet now
wraps where it alone is wider than a phone's column. 304 unit tests, 76 checks in the browser (two skipped on today's
data), 1,418 Python tests.

**A licensed work as the local catalog lists it (the operator's N1.a, 18 Nov).** The sources list showed a licensed work by
its file's stem with every other column empty. Line 1 keeps a catalog of the licensed shelf on this machine
(`data_paths.LICENSED_CATALOG`, git-ignored, in the shape of `corpus/catalog.json`), and the licensed knowledge base now
reads it: title, authors, publisher, year with the edition beside it, format, shelf and licence, as a free work shows
them, and a few words about the copy under its title ("stand-in file", "lecture slides"). The title stands wherever the
licensed export's work is named: the work's head, a page's head, the Issues. A work is matched by the export's work key,
else by its file. The catalog is handed to the licensed store alone (`licensed_readings`), which an app started with
`--public-only` never builds, so a public view never opens it (81.a); a missing or unreadable file leaves the columns as
they were, with no error and no warning, and an entry that does not read is left out. No licensed title enters a test or
the build: the tests invent their entries. **Measured:** Python tests of the fields and the title through an invented
catalog, by key and by file, of a missing, broken and empty catalog, and that a public-only app never reaches it; a unit
test of the row with its notes and edition; 305 unit tests, 76 checks in the browser (three skipped on today's data),
1,427 Python tests.

**The licensed catalog's unread works, a table that fits, and what an issue still serves (O1.a, 18 Nov).** The licensed
catalog's entries the export has no pages of (the EPUBs and the files not read yet) now stand in the sources list after
the read works, with their catalog columns and, in place of page counts, the API's "not read page by page" (`not_read`),
a state the export replaces once the core reads them, an EPUB by its sections. On a 2,000 px window the sources table ran
past the content width, its licence column cut and its scroll bar out of sight at the list's end: the table now fits,
its narrow columns at fixed widths, the title and the authors sharing the rest, every cell wrapping, a long id broken
anywhere; below 64rem, a phone's width, it scrolls in its own box, never the page. And a state to look at says how many
of its pages the core serves all the same ("issue 9 · 9 served", `StateCount.served`): an issue whose findings lie on
blocks never quoted is served (133.b), and "issue 9" alone read as nine pages held back. The state stays the core's
word. **Measured:** Python tests of the unread entries (listed after the read works, no pages to open) and of the
served count; unit tests of the not-read row and the served tally; a browser check that the table's last column stays
inside a 1,280 and a 2,000 px window with an invented row of the longest fields (shown failing first against the old
build); with the real licensed rows the table is 1,408 px in a 1,408 px box at 2,000 px. 307 unit tests, 77 checks in
the browser (three skipped on today's data), 1,429 Python tests.

**The licensed EPUB works (decision 123.a, the operator's P1.a, 18 Nov).** The core cuts a licensed EPUB into sections at
its headings and the librarian serves them as pages `s1`, `s2`, … (route "epub, parsed by section"); the view shows such a
work as it shows a free HTML work. `#/licensed/epub/<work key>` holds its outline by heading, the HTML works' own outline
component opening the EPUB's section route, or every section in a table with its characters and images; and
`#/licensed/epub/<work key>/s12` one section, the label a search hit names, with its heading path, its place in the EPUB
and its text, each image where its mark stood: inline in its line, as a formula most often stands, or a block of its own,
on a light ground, since a formula image is most often black on a transparent one. An image is read from the EPUB's own
zip by its path, only a path one of its sections names, with its content type from its extension; nothing is extracted.
The marks the provenance list records are stripped as the librarian strips them. Cutting all ten EPUBs takes about 20 s,
so each is cut once and kept while its file is unchanged, the app's warm-up cuts them ahead, and the sources list never
waits: it counts an EPUB's sections where it is cut, and says it is being counted where it is not. In the sources list
an EPUB the librarian serves leaves "not read page by page" and opens its view, by the librarian's key, which for a
legacy work differs from the catalog's id. Nothing of it under --public-only; no EPUB text, image or title in a test or
the build, and none was screenshot: an image of it would reach a model provider. **Measured:** Python tests over the
invented EPUB the core's own tests build (outline, labels equal to the librarian's pages, parts in order, a stripped
line, images by path and nothing else of the zip, the list's count before and after the cut, and that a public-only app
reaches none of it); unit tests of the outline's links, the section's runs and images and the list's row; on this
machine, measured without any text or image leaving the browser: ten works, every image loaded, none past a 1,400 or a
390 px window, an inline formula on its line, no console error. 310 unit tests, 77 checks in the browser (three skipped
on today's data), 1,442 Python tests.

**The sources list narrowed, a series grouped, and a reload that returns (the operator's Y1.a, 19 Nov; stage A of three).**
With the licensed catalog the sources list holds some eighty works, among them a lecture series in many parts, and it had
no way to narrow them. It now has the facet bar of the operator's FiniexViewer, derived rather than copied (the
operator, 19 Nov: "we orient on the viewer, we do not imitate it"): a facet each for the knowledge base, the format,
the topic, the structure and the series, a search over title, authors and id folded into its button until asked for,
and a sort by title, by author or by year, newest first, the sort in force named on its control. A facet that does not
fit waits behind `+N`, where it keeps its values, counts and picks; a facet every row agrees on stands disabled, so under
`--public-only` the knowledge base, all free, cannot be picked; nothing a pick changes moves the bar. The API gives each
work its structure in the list's own words ("read page by page", "sections by heading", "not read page by page") and
the series the local licensed catalog names (`Work.structure`, `Work.series`: its id, title, part, of, and an earlier
version's words). A series' parts stand under one heading where the first of them stands in the sort, closed until
opened, the heading saying the series' title and how many of its parts the bar leaves; its parts follow in their order,
a current part before an earlier version of it, one step in. A series narrowed to one part loses its heading. A reload
(F5) brings back the bar's picks, search and sort (`settings.v1`, written only once the bar is used), the open series
(the tab's session) and the place the reader stood, set once the works are drawn, since the browser restores it on a page
still too short to reach it; every storage access may fail and the view still draws. The counts beside a facet's values
and "N of M" are counted in the browser over the rows the API served (the operator's Q4.a); every figure on a row or a
heading stays the API's. **Measured:** unit tests of the filter, the bar (its search, its `+N`, a value drawn through a
view's slot), the overflow row, the stored bar (a cleared bar stays cleared, an untouched one stores nothing) and the
sources view over invented rows (facets, search, sorts, the series' heading and order, a reload, the scroll set after
the data, a blocked storage); a browser check over three invented licensed parts: the series opens and closes with its
toggle in place, a facet's panel in the one size, a pick moves no chip (shown failing once with the badge's reserved
room taken away: the chips after it moved 19 px), and a reload returns to the scroll position, the open series and the
bar, while a tab that kept no place opens at its top. 376 unit tests, 78 checks in the browser (3
skipped on today's data), 1,461 Python tests.

**The sources table ranked, its long fields in a card (Y1.a, stage B, first part: B1.a and B2, 19 Nov).** The sources
table scrolled sideways below 64 rem and its rows stood 6 to 20 lines high. Its columns now carry a rank, as the
FiniexViewer's lists do, and the library's data table gives them up as the TABLE narrows, measured on its own width
through a container query at the viewer's rungs of 34, 48, 62 and 80 rem: the topic goes first, then the year and the
format, then the authors, then the knowledge base, while the work and its structure stay. Any table of the library may
now rank its columns; a table that ranks none is measured by nothing and stays as it was. The rank stands on the column
and on each of its cells, and a browser check holds the two to agree. The publisher and the licence left the table for
the row's card, a hover card on the work that also holds its whole title, id, authors, year, edition, format, topic,
series and notes and why a structure is not built (where a browser tooltip stood); the title, the id, the notes and the
authors stand on one line each and end in an ellipsis. Taken from the viewer: the ladder, its rungs and the rank stated
twice. Left out: its rows as buttons and the subgrid they need, its bands, its second grouping level, its child records
and its detail and lead lines, since our rows hold links and a real table lines its columns up by itself. A series'
heading now stands in the work's column with an empty cell under each other column: one cell spanning all seven made a
phone's table, which keeps two, draw five columns of its own and squeeze the work's to 1.5 rem. **Measured:** a probe in
Chrome before the build, a fixed table giving up `col` and cells by a container query at 1,400 to 480 px, every column's
width returned to the others; unit tests of the table's ranks and of the view's columns, cells and card; a browser check
at 390, 600, 900, 1,100, 1,280 and 2,000 px that each width shows exactly the ranks its table's width allows, that no
cell, heading or ellipsis runs past its column, no word of a fixed column splits, the work's column keeps 8 rem, and the
table never scrolls, shown failing once with the ranks switched off (five columns too many at 22.4 rem, a scroll of
245 px) and once with the spanning heading put back (the work's column at 1.5 rem). 379 unit tests, 78 checks
in the browser (3 skipped on today's data), 1,461 Python tests. Open with the operator: the state counts as
figure columns (B3) and the id on its own line or in the card only (B4).

**Every list on the one facet bar (Y1.a, stage C, 19 Nov).** The Issues, a work's pages and the calls left the chip bar,
which stood every value of every facet on screen as a toggle, for the sources list's bar: one line of facets, each value in
its panel with how many of the rows the other facets leave carry it, the rest behind `+N`, "N of M" and clear. A value
keeps its look in the panel, a state its glyph, word and colour, a verdict whose it is, a knowledge base its glyph; a
facet lists its values in the order the API gives them (the core's state order), an addition to the viewer's bar, which
lists them alphabetically. The Issues and a work's pages keep their choice in the address (24.a), now both ways for a
work's pages too, so a reload (F5) and the browser's back find the list as it was left; there the Routes table keeps its
own route choice, and the bar narrows the pages on the chosen routes. The calls keep theirs with the stored settings.
The tally of a person's verdicts that stood beside a state left the bar: the "A person" facet says it, once (the viewer's
tip 5). The Why of a page row and a derived block's marking are in plain ink now, the colour left to the state (tip 6). The
chip bar, its tally component and the stored bar's default selection and scope, which no view used, are gone. Open with
the operator: where the API's state totals stand above the bar (SC1), and the calls' cards against the bar's count of the
listed calls (SC2). **Measured:** unit tests of each view's narrowing in the panel, the order, the address and the stored
calls; the browser checks that picked a toggle pick in the panel now, and a work's chapters keep their filter across a
reload. 375 unit tests, 78 checks in the browser (3 skipped on today's data), 1,462 Python tests.

**The overview as one corpus (the operator's O3.a, 19 Nov; first part).** The overview took 35 to 65 s a load in the
container (48.5 s measured), and stood the knowledge bases side by side in column pairs (the operator: "today there is only
one corpus"). It is now a headline summed in the API over the bases served, each figure's part per base in its card: the
works, the pages planned, those that passed with their share and the pages the search serves, from each base's shelf as
the core builds it, and the pages to look at and what the work cost, from each export, the cost's card with each provider's
part. Beneath it the latest runs of both bases in one table, newest first, each with its base's mark. A base the sums
leave out says why (under `--public-only` the licensed one), and so does a base whose shelf is not built. The tables of
counts by route, state, verdicts, category, why judged, reasons, model and the integrity of each reading file, and the
search's count per medium, are gone. Every count of a page they gave is the page list's filter by the same field, which a
test holds field by field; the costs per model and the search's count per medium have no such counterpart, and go (line 1:
the providers stay in the cost's card, and the shelf says per work what the search serves). Three costs were found on the
way. The integrity table stat-ed some 10,200 reading files on each load; integrity is now asked only through its filter.
Every page list asked each page's work title anew, each a stat of the export's index, 28,854 for the unfiltered list (114 s
in the container, 0.64 s natively); titles are resolved once per list, which the Issues use too. And the latest runs were
read whole from each pipeline database on every load (0.27 s a base natively); they are kept while the database, and its
write-ahead log, are unchanged. A run that recorded no end says so in line 1's words, "no end recorded", its meaning in its
card, never "failed" (D10, here because the overview's runs show it). **Measured natively, both bases:** the overview
1.0 s cold and 0.07 s warm, the unfiltered page list 0.45 s, the Issues 0.03 s. **Open:** the shelf's shares and history
(X1.a, the core's data first), and a way to choose the Pages filters in the view (P1, with the operator). 372 unit tests,
78 checks in the browser (3 skipped on today's data), 1,462 Python tests.

**The shelf's shares and the corpus's history in the overview (O3.a, second part, on line 1's X1.a, 19 Nov).** The
headline adds the pages read beside those planned and passed, each with its share of the planned pages, summed in the API
over the shelves of the bases served. Beneath it the corpus's history as the core keeps it (`shelf.history`), a line per
milestone line 1 records, newest first: its date, its name, and its pages planned, read, passed with their share, and
served, summed over the bases served, each base's part in the milestone's card. The lines taken over from the person's
file before 19 Nov hold both bases summed; they stand as kept, what they did not keep left empty and their card saying so,
and never under `--public-only`, as they hold licensed counts. **Found by looking at the screenshot:** under
`--public-only` the newest line's name named a licensed work, so the API gives no milestone's name there and the view says
it is withheld (81.a). 374 unit tests, 78 checks in the browser (3 skipped on today's data), 1,464 Python
tests.

**The sources list's figures and the lists' totals (the operator's B3.a, B4.a, SC1.a and SC2.a, 19 Nov).** A work read page
by page stood its states stacked in one cell, 6 to 20 lines high. Its pages and five states are figure columns now, ok, ok
unjudged, issue, blocked and decided by a person, each under its glyph and the core's word, right-aligned with its
heading, how many of an issue's pages are served all the same on a line beneath its figure; a work cut otherwise says how
in the same column as the pages, in the API's words, and leaves the figures empty. The rarer states, an automated
review's, a stopped work's and the pages not checked yet, stand in the work's card with their counts. The list sorts by
blocked or by issue, most first, a work without pages read last. The title and the id stand on a line each (B4.a), a
licensed copy's notes now in the card. The ladder of ranks was taken again with the figures, so every width keeps the
work's column at 8 rem at least: the work and its pages stay; then issue and blocked; then the knowledge base, ok and the
authors; then ok unjudged and decided by a person; the year, the format and the topic last (with the knowledge base a rung
earlier, the work's column kept 121 px at 34 rem). The Issues and a work's head carry one line of the API's totals above the
bar (SC1.a), each state once with its served tally, whatever the bar narrows; the calls keep their cards' counts of every
logged call beside the bar's count of the listed ones (SC2.a, as stage C left them). 377 unit tests, 78 checks in
the browser (3 skipped on today's data), 1,464 Python tests.

**Polish from the viewer's tips (Y1.a, stage D, 19 Nov; D1 to D11 agreed with line 1).** Every count is said with the noun
that agrees with it through one helper (`counted`, `noun`): "1 section by heading", "1 call", where a view wrote "1
sections" and "1 calls"; the helpers the views held each are merged into it. The runs tables, the Runs view's and the
overview's, rank their columns: the base and a run's note go first, then the start and the cost (measured with both bases:
the table ran 85 px past its box at 800 px, now 0). The costs keep the operator's rule of two significant digits rather
than fixed decimals per column; their headings already stood over their figures. The PDF page field has the border of a
control, a prototype's state the primary ink, the Runs view's headings sentence case. What the Prompts view holds is a
hint on demand, the core's words in its panel, where a paragraph stood on every visit. A count in the chapter table that
opens its pages wears a link's look, the accent's ink. The frame's head says once which clock every time is on, the
reader's own zone. A dotted underline stays the one sign of a card under the pointer, and each of the two that carry it
opens one. The API's `from_text_layer` is `from_fallback` now, as it means since H2.a. **Measured:** unit tests of the
helper and of each view's words, ranks, hint and clock; a browser check that the runs table fits its box at 800 and
1,400 px over an invented run as long as the longest real one, shown failing once with the ranks switched off (11 px).
The decision numbers in the Prompts text (147.a, 148.a, …) are the core's registry's words, which trace each version to its
decision, and stay as given (line 1). 381 unit tests, 79 checks in the browser (3 skipped on today's
data), 1,464 Python tests.

**The Pages view's facet bar (the operator's P1.a, 19 Nov).** With the overview's tables gone, the Pages view could drop a
filter but not choose one, so a count was reached only by its address. It now loads every page once, each with its words
in every field it is narrowed by (`filtered_by`: route, state, verdict, reasons, readers, judge, providers, category, why
judged, a person's and an automated review's standing), and the facet bar narrows them in the browser, counting as it goes
(Q4.a), the knowledge base among the facets and the states in the core's order. The choice stands in the address, as in the
Issues, so every link into the list (`?state=blocked`, `?person=accepted`) opens the pages it names. The integrity of a
reading file stays a filter the API answers from the disk, asked only when the address names it and never counted on a
load. A long list draws its first 500 pages and says how many there are, every page one click away. The unfiltered list,
10,224 pages with their words (10.3 MB), is kept while no export changes and built ahead at the app's start: 1.9 s to build
natively, then 0.1 s. **Measured, both bases:** before, in the container, `/api/pages` 1.6 s cold and 0.7 s warm (6.9 MB),
and the unfiltered view drew all 10,224 rows after 3.1 s; after, natively, the API 0.11 s warm and the view's first 500
pages after 1.1 s; the container after the merge is line 1's to measure. 384 unit tests, 79 checks in the browser
(3 skipped on today's data), 1,466 Python tests.

**Every PDF page in a work's list (the operator's V1.b, 20 Nov).** A work's page list showed the pages with a reading, so a
work read in part looked whole. It now shows every page of its PDF, and the record's Pages line is one sentence from the API:
"120 of 300 PDF pages read; the other 180 are served from the IDE's Markdown", split where more than one thing serves them
and saying how many of them a plan holds. A page without a reading stands in a state of its own, `not_read`, quiet, with its
own glyph and no status colour, since nothing is wrong with it; "planned" beside it where the rollout's plan or a session's
list holds it; its Why says what serves it; its number opens nothing, since it has no reading and no image. It counts as
every page does, so the states line, the routes (a level of its own, "not read", after the core's three), the chapters'
Pages and their own "not read" column, and the facet bar all hold it. **What serves such a page is the librarian's rule,
asked of its data:** a licensed work's page-numbered legacy Markdown where it has the page and nothing where it has not,
since the librarian never falls back to that work's text layer; any other PDF its text layer where the page has text, and
nothing on a page without. The first rule proposed, the text layer wherever no Markdown has the page, was measured against
the librarian's own pages and would have named the text layer for a legacy work's pages the Markdown leaves out; the rule
here matched every unread licensed page. A page's chapters come from the outline's ranges, as it has no text to place.
Built once per state of the export, the PDF, the legacy pages and the plans; the legacy pages take 15.8 s natively and are
built ahead at the app's start; none of it is read of the licensed base under --public-only. **Measured:** every work's list
natively, the free works 0.2 s cold and 0.1 s warm in all, the licensed ones 3.2 s and 0.7 s, in the main tree's layout;
the container after the merge is line 1's to measure. 387 unit tests, 80 checks in the browser (3 skipped on today's data), 1,475
Python tests.

**The coverage ladder (the operator's U1.a, 20 Nov).** Nowhere said how many pages were available at which refinement, so
every work and the corpus now show it in the same five levels: text served (the pages, or an HTML or EPUB work's sections,
the librarian serves text for), keyword search (of those, the ones search (BM25) finds), semantic search (the chunks in the
vector index and the PDF pages they cover; the licensed base says "not vectorised yet (#8)", never 0 of N), read (the pages
a vision reader read, and how many passed), checked (a reading the judge passed, or a person or an automated review settled;
an unjudged reading is not counted, as unchecked is said). Levels 1 to 4 are the core's shelf, level 5 the export's states
as every list counts them; a level a format does not reach says why ("not read page by page: cut by its headings").
**Sources:** one Coverage column of five meters in place of B3's Pages column and its five state columns; the levels' lines,
every state of the read pages with an issue's served tally, and why a file is held or not served stand in the meters' card,
on the pointer and on the keyboard's focus; the sorts by blocked and by issue stay. Every work opens: a licensed PDF the
export has no pages of opens its page list, every page unread. **A work's page:** the ladder in words and figures heads its
record, its read level V1.b's line, a details fold beneath (what serves the text by route, held, not served, passed
readings not served, planned, passed, when the shelf was built). **The overview:** the corpus's ladder, each level summed
over the bases served and each base's part in its card; read and checked open the Pages view on exactly their pages, the
others stand as figures, and they two are drawn against the PDF pages alone, as no section is read page by page. What each
level counts is a hint on demand, in the API's words. **Measured:** the works list 1.9 s cold with both bases natively; a
work's page list and the overview as before. 389 unit tests, 81 checks in the browser (3 skipped on today's
data), 1,488 Python tests.

**Every page reachable, each with its own ladder (the operator's V2.a, 20 Nov).** "Whatever refinement the material is at, it
should be reachable by link: the work, then the page, then the image." Every PDF page now has a page view, read or not. A page
no reader has read shows its state, what serves it and why, its own ladder, the text served and the PDF's own image, the one
the librarian's `page_image` gives (a scan's own pixels never upscaled, any other page rendered at 150 dpi), and nothing of a
reading, which it has not; its row in the page list opens it, and previous and next step through every page of the PDF. A
page's own ladder, beside a read page's record too: text layer (its characters, or none: a scan), text served (its reading,
the IDE's Markdown, the text layer or nothing, and why), keyword search (in search (BM25), or not and why: no text, too short,
mostly figures, a table), semantic search (its chunks, or "not vectorised yet (#8)"), reading and check. The text served is
the search's own page, folded until asked for; the page view never waits for the search to be built, and says so while it
is. HTML and EPUB sections climb the same ladder, born digital: no text layer to extract and no reading needed. A file the
provenance list holds back is shown on this machine like any other, image included, and says so; the librarian goes on
refusing its images to any model. **With it, after U1.a:** the legacy-only works the shelf lists stand in Sources, served
from the IDE's Markdown with no source file held here; the overview's read and served tiles are gone, as the ladder shows
both; level 5 says what it counts, "checked by the judge or a review"; each base's shelf is handed to its store by the app
alone, so an export a test invents never sees this machine's shelf. **Measured natively:** a free page's view 0.4 s, a held
scan's unread page 0.8 s warm with its image drawn once for the view and its image route both. 391 unit tests, 82
checks in the browser (3 skipped on today's data), 1,493 Python tests.

**Colour in the coverage meters where a look is called for, and cards that wait for the pointer (the operator's C1.b, 20 Nov).**
A meter stays quiet, one neutral fill, unless the API marks a level: the pages the judge found bad stand as a segment after a
work's or the corpus's checked pages, in the issue's role (`Rung.issues`); a work that serves no text at all, a held scan, has
its text-served track in the warning role (`Rung.warn`); a level not measured here, not vectorised yet (#8) or not read page
by page, is a hatched track in the border's ink, hatched since a dashed line is the annotation role's. The words stay the
card's. Measured with the dataviz validator: the issue's red beside the fill's grey stands 7.8 apart in the dark theme
(deutan) and 5.3 in the light one (protan), OKLab ΔE, below the 8 a colour may carry alone, so the segment carries a form
too, a gap of 2 px from the fill and a pixel more on each side than its track. A hover card opens once the pointer has rested
500 ms (`HOVER_DELAY`, one value for every card), so a pointer crossing a table opens nothing; the keyboard's focus opens it
at once. 395 unit tests, 83 checks in the browser (3 skipped on today's data), 1,493 Python tests.

**The private base in the ladders (issue #8, 20 Nov).** The private base has its own vector index now, local only, and the
semantic level says what it holds: a licensed work its chunks and the PDF pages they cover, a page its chunks by the work's
key, an EPUB section its chunks by `<work key>:<ordinal>`, the corpus both bases summed. A work the provenance list holds back
is never embedded and says "held back: never embedded"; a file the librarian serves not at all says "not served: never
embedded"; "not vectorised yet (#8)" stands only on a machine without the private index. 395 unit tests, 83 checks in the
browser (3 skipped on today's data), 1,501 Python tests.

**One row per work, a card that follows the colours, an issue line in words, a number and a share per level (the operator, 20
Nov).** A work served from its legacy text stood a second time as its stand-in file, which the librarian does not serve while
that text stands; the core now links a stand-in to its work (`stand_in_of`), and the list folds it into its work's row: the
work's ladder, the stand-in named in its card with why it is not served and held where it is, its title, authors and year from
the stand-in's catalog entry where the work had none, and its page list one click away on a line of the row. The coverage card
draws each level's line with the column's meter, the issues' segment, the warning outline and the hatch alike, so the eye finds
in the card the line a coloured bit in the column stands for. The issue line says what its tally means, in the API's words
(`LadderState.said`): "12 pages with judge findings · all 12 served: the findings lie only on blocks never quoted (133.b)", or
how many serve their fallback. Each level carries its number, 1 to 5, before its word wherever the levels stand in words (the
card, a work's ladder, the overview's, the legend), and its share beside its meter as a whole percentage, both the API's
(`Rung.number`, `Rung.share`; the operator's L1.a): the number says which line of the card a meter in the table's cell is, and
the cell keeps its five meters alone. A level not measured shows no share. The read pages' states are no level and have no
meter: in the card they stand apart beneath the five, under a thin rule and the caption "read pages by state", a step in. The
meters keep their one neutral ink; red, the warning outline and the hatch stay the only colours (F1.b). 398 unit tests, 83
checks in the browser (3 skipped on today's data), 1,504 Python tests.

**A level on two lines, and every card inside the window (the operator, 20 Nov).** The coverage card had grown cramped where a
state's long label beneath set the width of the levels' words, which then ran to six lines beside their meter. Each level now
takes two lines: its number, word, meter and share, then its words a step in beneath, across the card; the levels are a block of
their own, so their meters stand under each other as in the cell, and the states keep the card's own columns. A work's and the
corpus's full ladder does the same only where the record is narrow. And a hover card, any of them, stands wholly inside the
window: beneath its host, above it where the room beneath is short, shifted to keep within the window's sides, and where it fits
neither, on the side with more room, as tall as that room, scrolling inside; it is placed again as the page scrolls or the
window changes, and closes when its host leaves the window. It is placed by Floating UI, which the library's Reka UI already
brings for its own popovers. 403 unit tests, 84 checks in the browser (3 skipped on today's data), 1,504 Python tests.

**Level 3 is "semantic search" (the operator's C2.a, 20 Nov).** It was "semantic chunks", which read as the literature's
semantic chunking, cutting where the meaning changes. What the level counts is something else: the pieces in the vector index
that semantic (hybrid) searches, cut by the text's structure and then by the recursive character splitter, and the PDF pages
they cover. Named for what it serves, it pairs with level 2, keyword search, on a work's ladder, the corpus's and a page's
alike; its figures keep their words ("2,396 chunks over 592 of 629 PDF pages"), and its line in the legend says how its pieces
are cut. 403 unit tests, 84 checks in the browser (3 skipped on today's data), 1,504 Python tests.

**What does not change between calls is kept (line 1, 20 Nov).** The Sources list cost the same on every call, about a second in
the container, and a page's view half a second however often it was opened. Every cache is keyed by what would change it, a
file's stamp (its modification time and size): each work's rows and its readings in figures once per state of the export's
index, the shelf once per state of its file, a page's text layer once per state of its PDF, whether a fresh render shows the
pixels the reader was sent once per pair of images. And a file's stamp is looked at once a request (`stamps`): the list asked
the index for it twice for every work, 4 ms each through the container's mount of the Windows folder. The view's numbers are
exactly as before; a test counts, never times, that a second call reads and parses nothing again and that a file written anew is
read again. Measured on this machine, warm, a second call: the Sources list 0.21 s before and 0.02 s after, a page's view 0.08 s
and 0.01 s, a work's page list 0.06 s and 0.03 s, the overview 0.05 s and 0.01 s; in the container before, 1.04 s, 0.51 s, 0.12
s and 0.16 s. 1,508 Python tests.

**The views warm up after a start (line 1, 20 Nov).** Every merge restarts the container, and the first calls after it paid for
what every later call shares: 24 s for a work's first page list, 18 s more for its first page. The start's warm-up builds it in
the background, in the order a person meets the views: the Sources list and the overview, the legacy pages and the files not
served, each base's vector index by page, each work's pages without a reading, the Pages view, the licensed EPUBs' cuts, and
last the search index, which only a search needs. The view answers meanwhile; a call that needs a part still being built waits
for that part, at the cold figure at worst, and a step that fails is logged and the next goes on. The log's last line says
`warm-up done in N s`. Measured in the container after the warm-up (173 s), each route's first call: the Sources list 0.13 s, a
work's page list 0.04 s, a page's view 0.78 s (most of it its own image, which no other page shares), the overview 0.04 s. 1,523
Python tests.

**A work in its editions (the operator's E1.a, 20 Nov).** An edition is a level under its work, work › edition › page or
section, never a group of works: exactly one edition is served, the others are kept with all they have (their readings, their
chunks, their pages, their own record), and only the two searches skip them. Which edition is served changes only by a core
command on the operator's word, so the view shows and never chooses. In Sources a kept edition's row is folded into its served
edition's, which keeps its own catalog data and ladder and says beneath its id "2 editions · serves the 2nd edition, 2003 · 3rd
edition, 2009 kept", the kept one a link to its own record; the work's card holds the editions apart, each "● served" or "○
kept" with its label and format, and when and why the served one was chosen. Every edition's record, a PDF's page list or an
EPUB's view, names the editions in a bar, its own marked and the others links, and its trail says "Sources › <work> ›
<edition>"; a kept edition's ladder says so in neutral words ("kept: the 2nd edition, 2003 is served; opens by its own key",
"kept: not searched", its chunks "held back from the search"), never in the warning role. An EPUB's view gains the ladder a
PDF's record has. A file that looks like another edition and is linked with none stands with a line in the warning role,
"possible edition of <title>: not linked; the operator decides", a call to look. The overview's works figure names the kept
editions, and a hit or an opened page names its edition beside its title, as its citation does. 409 unit tests, 85 checks in the
browser (3 skipped on today's data), 1,530 Python tests.
