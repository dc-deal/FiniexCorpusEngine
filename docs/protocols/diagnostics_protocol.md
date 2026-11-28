# Protocol: the diagnostics frontend

The record of how the diagnostics frontend came about, mistakes included.

## 2026-11-02

- **A second line of work,** beside the core, in its own git worktree with its own branch; the git-ignored data is linked
  in. Its first offline run failed 2 of 770 tests: the reading store's guard followed the link into the main tree and refused it
  as another work tree. The guard was fixed in the core (commit 82bb4bf); afterwards 774 passed in the worktree.
- **The stack:** FastAPI with server-rendered HTML and HTMX was proposed first, for having no build step. The operator chose Vue, so the
  components and patterns of an existing Vue project could be reused. The reviewer still installs nothing but Python packages:
  the build is committed.
- **Decided with it:** the URL holds only the deep link to the thing on show (hash routing); everything else becomes stored
  settings. A `page/1` reading will be parsed on the server by the core's own parser and shown block by block, with a switch
  to the raw text. API types are generated, not written.
- **Mistake: TypeScript installed without a version.** npm took 7.0.2, which three of the tools do not support (their peer ranges
  stop below 7, below 6.1 and at 5.x). Pinned to 5.9.3. The first install had also nested packages so deep that git reported
  "Filename too long" (312 characters); a clean reinstall brought the longest path to 208.
- **Mistake: the first frame showed nothing.** The view showed its loading line only after a flag set in `onMounted`, so the
  first render had neither a loading line nor content, and a test caught it. The view now shows the loading line until the
  first answer or failure, and the flag is gone.
- **The real catalog broke the first model:** `year` is `null` for the Wikipedia set. `int | None` now.
- **knip reported the built bundle as an unused file;** `dist/` is ignored there.
- **Result:** pytest 786 passed, Vitest 20, ESLint and knip clean; the running process answered 200 for the page, its script,
  `/api/works` and `/docs`.

## 2026-11-03

- **Commits by line 2 itself** (the operator): for its own folders, and for a shared file only with an approved change that touches
  line 2's areas alone.
- **The duplicate uvicorn pin went:** the search server pins it now, and the diagnostics block keeps fastapi.
- **Planning V1 on tracked data:** the core began to track the free readings in `corpus/readings/` (decision 72.a, numbered
  38.a until the core renumbered its decisions on 2026-11-04 → now 72.a), so the
  views can work on a clone. The original was the open question: a fresh render of three tracked pages from three works was
  compared with the sha256 of the image each reader received, and all three matched byte for byte.

## 2026-11-04

- **Tables from the parser's cells,** not the model's HTML through a sanitiser: decided by line 1, to whom the operator left it.
- **Three gaps closed in the core on request:** the export now names each page's catalog id and route, and each finding of
  the judge with its block, severity and evidence.
- **Mistake: a test mounted page 2 with an answer for page 4.** The view dropped the answer as one for another page, which is
  what it should do; the test was wrong.
- **The contract test for imports turned red in this worktree only:** KaTeX's Python helper scripts in `node_modules` were
  read as project code. Reported to line 1, whose test it is.
- **V1 in main** (fast-forward 91d5ba5..3eddccc). The automatic permission check of the session refused the merge twice as a
  change to a shared resource; the operator allowed exactly that one command in the local settings.
- **A browser check (Playwright), on the operator's suggestion.** Its screenshots were the first look at the views at all: until then
  they had been tested in jsdom and over HTTP only. Three defects showed that no unit test could: a work's title repeated on
  every row of the bin, a wide table cut off at the window's edge, a marked block scrolled with its top above the edge.
- **Mistake: a misreading suspected without checking.** A table cell read "3,9%" where its neighbours have a point; the PDF's
  text layer has the comma too, so the reading is faithful. Checked before it went anywhere.
- **Mistake: a check that did not run.** A type error in the new browser spec stopped the build, and the browser check then
  ran against the previous build and failed for the wrong reason.
- **The block's box on the original,** the last step of V1, built with a look at each screenshot (the operator: "please with a visual check"). The frame is placed in percent of the image the reader received; the browser check measured it within
  2 px of the reader's box, and a block at the foot of the page brought its frame into the original's view.
- **`--public-only` (decision 81.a, the operator):** the review is recorded, so the app can be started without ever reading the
  licensed knowledge base. Built before the licensed export exists, so its views are gated from their first day; the test
  makes reading it raise, as the search server's does. The browser check now starts the app that way.
- **A fast-forward refused, correctly:** main moved between the check and the merge, and `--ff-only` stopped instead of
  merging. Rebased and merged again.
- **V1.1, the page at a glance, on the operator's request:** one line of what matters, the findings below it, the rest folded and
  remembered; a field to open a page by its number.
- **Data asked for, not built** (the operator: "At best you go by the data alone. If it is not there, then we ask"): the
  sentence of a blocked page's error and the printed page label, now in the core's export, and a work's outline, which line 1
  put to the operator as decision 84. The four PDFs' bookmarks had been read here first, to see whether an outline exists at all.
- **Mistake: the judge's word twice.** The verdict went into the line beside the reasons without a look at how the core builds
  them; the reasons already name a bad verdict, and the state `ok` already means judged ok. The screenshot showed it, the
  counts over the export confirmed it.
- **Mistake: the earlier scroll fix, carried over unchecked.** "Top first, at once" scrolled every scrolling ancestor, the
  window included; with the findings now above the panes, choosing one hid the page's title. Only the reading's column
  scrolls now.
- **V1.2, the operator's choices 1.a, 2.a, 3.a and 4.a:** the knowledge base as the first part of a work's address, the provider's
  sentence in the line and the lists, the printed number shown, the bin view renamed Issues while the state keeps the core's
  word. The operator's wish from the screenshot: a finding beneath the block it names.
- **The test client now serves the free knowledge base alone.** Built with the default switch, it would have read the
  licensed export on the operator's machine, and the catalog-order test would have failed there and passed on a clone.
- **A data check before a column:** some blocked pages have no sentence; every one was declined by the reader, not refused
  by the provider. Asked line 1 whether the export should carry one.
- **Mistake: a selector that counted twice.** The browser check counted the free marks on the sources list as 16 for 8
  works, because the row carries `data-kb` as well as its mark. The test was wrong, not the view.
- **An independent review before the merge,** two read-only agents (the project's limit without asking): one on
  correctness, one on the licensed gate. The gate held in all seven checks, with a positive control for the leak search.
  Six small defects and one hardening, all fixed. **Mistakes of mine among them:** the test of a differing image was lost
  when the page view's tests were rewritten, and the docs claimed every knowledge base came from a row's field while a
  work's page list repeated its address.
- **Line 1's answer on declined pages:** `error_message` stays the provider's own words; a sentence of ours there would pass
  for theirs, and the reader's refusal offers a summary that is never used (75.a). The API now marks a page served from its
  text layer by the core's own list of such routes, and the Error column shows the route where the provider said nothing.
- **V1.3, a work's pages by its own order** (the operator: 6.a, 7.a, and 5.a by "your recommendation for now"). Built against the
  outline's announced shape and checked against the licensed export by shape only; the free export carries none yet, so the
  browser check lays an invented outline over real free pages.
- **The operator asked to see an HTML work before the build:** the diagnostics showed only "This work has no page readings", since the
  export holds PDF readings alone. That led to the operator's wish for one diagnosis for every medium, the data from line 1 (8.a,
  10.a); PDF keeps priority (11.a).
- **V4, the search (the operator's 14.a),** while HTML and the free outline wait on line 1. Checked against the data first: the
  search's keys for the free PDFs are exactly the export's work names, and no legacy Markdown key matches a licensed export
  name, so linking a hit needs no mapping, and a legacy hit honestly gets no link to a vision reading of another text.
- **Mistake: a test that leaked into the next.** The search view's tests share one router, and the views of earlier tests,
  still mounted, answered the next test's address and used up its prepared answers. The tests now unmount after each.
- **A gap found by following a hit (the operator: "judge for yourself what fits"):** a page in the bin showed its rejected
  reading as if it were quoted. Weighed against two small conveniences (folded empty chapters, kept filters), this one was
  taken: the view now says when a reading is not what is quoted. Extracting the text layer here was turned down, as a third
  way beside the search's and the chat loader's own; the core's one function for a page's quoted text was asked of line 1.
  Line 1 confirmed the fault behind it: the search and the chat loader extract a text-layer page differently, so they can
  quote different words; one function for both comes in phase 5.

## 2026-11-05

- **Asked line 1 what to build next** (the operator). Line 1 ranked: a page's readings over time first (the self-healing demo), the
  way each page took second (to be exported), a runs view third, the second reader's side-by-side last. The operator chose the first
  (15.a). Built against the announced export shape, with an invented history in the browser check until the export lands.
- **Mistake of mine, found by line 1 before it broke main:** a readings test assumed the tracked export had no outline yet;
  line 1's refresh would have turned it red. Fixed, with two more tests of the same weakness and two browser checks that
  counted a work's pages in a list that now opens on its chapters; checked against both exports before line 1 committed.
- **A server error on the operator's screen:** the licensed export's newest round holds pages no check has reached (`check: null`);
  the API took every row to have a check. Every test runs public-only, so none could see it. Such a page is now `unchecked`.
- **V6, the overview** (the operator through line 1, "best as a new menu item"). The core renames the state `bin` to `issue`
  (97.a); both names are read until every export says `issue`.
- **Mistake: a boolean property** cast to false when not given turned every figure's link off; the unit test found it.
- **The overview redrawn as compact boxes** (the operator: "clumsy", titles labelled twice; chose 16.a): key figures on top, each
  value once with both bases' counts beside it, joined in the API.
- **Mistake: an edit landed in the main tree.** A byte-safe replacement through .NET took relative paths against .NET's own
  current directory, the main tree, not the worktree `Set-Location` had chosen. Three of line 2's files in the main tree were
  rewritten beside line 1's uncommitted work. Seen at once by `git status`; those three paths were moved to the worktree and
  restored with `git checkout --`, nothing of line 1's touched. The trap stands in the frontend-commands skill.
- **Which model did what** (the operator's 17.a), on the fields line 1 added the same day. Counted against the exports first: the
  readings' costs (free 25.11 USD) exceeded the cost tile (23.63), since the tile counted only the reading a page shows. The
  tile now says what was spent, the provider box's sum. The boxes stand in the two-column grid, not full width as offered:
  on a full-width line the numbers sat far from the model's name.
- **Mistake: headers aligned left over right-aligned numbers** in every box since 16.a; a more specific rule outweighed
  theirs. Seen in the screenshot of the new boxes, which have four number columns.
- **`bin` dropped:** both exports say `issue` since line 1's re-export.
- **The overview set in bands** (the operator's 18.a, "the boxes still come across somewhat disordered"): three causes named from
  the operator's screenshots, holes in a grid whose rows take their tallest box, no grouping, runs wrapping over several lines.
  Boxes paired by height by hand were weighed and dropped: the pairing breaks as soon as the data grows. The operator's terms: if
  this does not work, the overview stays as it is until a better idea comes.
- **V7, the text that is quoted** (the operator's 20.a), on line 1's `quoted_pages`. A data check first: the export had cut the
  free knowledge base's quoted text, not yet the licensed one's, and the function cuts a missing book on its first call,
  writing into the core's store. Decided here, as a technical detail: the core's function is called as line 1 meant it,
  but only when the quoted text is to be shown, through a route of its own, so a page view never waits a minute for it.
- **Mistake: two browser checks assumed a page opens on its reading.** A page quoted from its text layer now opens on the
  quoted text, so its table and its findings were not there to measure; both checks now choose the reading first.
- **Mistake: a test that needed a declined page in the real export.** Line 1 let a second reading stand for the free
  export's one declined page, and the test turned main red. It now invents the declined page, as the rule says a test
  should when the data may change under it.
- **V8, for the review demo (69.a):** asked line 1 for one page's integrity, each attempt's check and the choices of one
  run; all came the same day. Weighed first: the integrity scan of a whole export takes 0.5 s (free) and 1.1 s (licensed)
  on every page view, and a cache would miss the demo's live change, so one file is hashed per page instead.
- **Found while building:** a page whose reading file is gone would have ended in a server error, since the page view
  read the file unasked. It is now a state of the page.
- **Mistake: a screenshot that showed nothing.** Git Bash turned the address argument `#/free/sources/...` into
  `#C:/Program Files/Git/free/sources/...`, and the router knew no such address. The app was fine; the trap stands in the
  frontend-commands skill.

## 2026-11-06

- **Decisions through line 1:** for a time line 2's decisions went to line 1, which decides inside the
  approved plan and parks for the operator what changes money, scope or line 2's rules. Line 1 took 21.a (a Runs menu item with a page
  per run) and placed the calls view (19) inside the plan by decision 98.c. Both are listed for the operator to revise.
- **A data question before the runs view:** the free pipeline database listed rounds of the licensed base. Line 1 found a core bug
  (every batch run was recorded in both databases) and fixed it in 4729f55; the view reads `pipeline_db.runs` as it is.
- **Mistake: a route that would have matched only the letter d.** A path written as `'(\d+)'` in a JavaScript string loses its
  backslash; the other routes write `\d+`. Caught when reading the diff, before any test ran.
- **One browser check failed once, unexplained.** Right after a rebase that brought line 1's phase 6 and a full Python run,
  one of 22 checks failed; the next three runs passed in full. The report was cut off before its name, so which check it
  was is not known; a cold server under load is a guess, not a finding. Watched in the next runs.
- **V10, the chat (100.a),** after the demo parts as planned. Scouted first by two read-only agents (the core's turn contract,
  and the operator's first chatbot's patterns), before an estimate was given: about 9 h for the chat, about 13 h with the demo parts.
  The scouting found what the brief had not said: the turn travels two or three times in one response (line 1 then gave
  `turn_log.stored`), the cost left out the server's router (line 1 then priced it), a failed start left a server process
  behind (line 1 fixed it), and a thread id went into a file name unchecked (the route takes a UUID only).
- **Two holes closed in the ported sanitiser:** its allow-list kept `target`, `rel` and `align`, which its own URI rule then
  removed, and it let a protocol-relative `//host` link through. And a formula: `\(` is a Markdown escape, so formulas in an
  answer lost their backslashes; they now stay word for word, as code.
- **The single unexplained browser failure (→ now explained):** the details check reloaded before `toggle` had stored the
  choice; it now waits for the store.
- **Not done:** an independent review of the chat, and one live turn through the real agent; both spend, so both wait
  for the operator. The chat went into main without them, switched off in every test.
- **V11, the calls view** (19.a, inside the plan by 98.c, line 1). A junction for `logs/` in the worktree, after checking that
  no test writes the real call log through the default path. A first test built the app without `--public-only` and so would
  have read the licensed export on the operator's machine; it now reads the free knowledge base alone, as every test must.

## 2026-11-08

- **Core changes of the day checked against the views,** at line 1's request: nothing broke (the licensed rollout complete,
  validator page/1.2, rotated pages rendered upright by the core, attempt numbers up to 2).
- **V12, the shelf (129.a).** A data check before any code: the shelf's reason counts matched neither the check state nor
  the class for 21 works, so a filter on state would have opened more pages than counted. Asked line 1; a second count
  showed the reasons equal the text-layer routes for every work, and line 1 confirmed it holds by construction and pinned it
  with a test. The form of the view is put to the operator (22).
- **A gap found by the same check:** licensed search hits name their work by the server's key (`book_a`), the export by the
  file's stem, so licensed hits and licensed pages in the call log opened no page view. Mapped through the shelf.
- **Answered works in the call log (124.a), built before line 1's commit:** the public-only filter checked answered pages
  only, so a search over works that named a licensed work would have shown that name. Closed against the announced shape,
  with a test. **Mistake:** a local name `sources` hid the module of that name in the same function; the tests caught it.

## 2026-11-09

- **A fidelity check of the chat on a live turn (the operator, via line 1).** No turn log held line 1's run, so one turn ran through
  this view from the main tree (about 0.004 USD). The view lost and reordered nothing, and its links opened the right pages.
  It did not say whose words were whose, and it hid a near miss in a folded list: both mended. What the core returned (an
  answer by analogy, relevance below the floor in this run and above it in line 1's) went back to line 1.
- **The shelf view (22.a, the operator: "yes, shelf sounds good").** Its browser check first failed: the shelf, local and built
  from line 1's not yet committed free export, counted two free works differently from the tracked export in the worktree.
  Not the view's fault; the check now tests what is the view's (a reason opens the pages on its route).
- **Features sealed (142.a, via line 1).** The issue view walked in a headless browser before the operator's own walk on Wednesday:
  the overview's route row opens exactly the 11 pages the operator judges, and back keeps that list; the Issues view did not keep
  its choice, and five served-despite pages gave no reason. Both mended, and the Sources column renamed (the operator: "I will take your recommendations for now", 23.a, 24.a, 25.a). **First screenshots showed "Loading…":** taken before the view's own
  request ran, not a slow API (0.36 s for the issues, 0.03 s for the 11); the scripts now wait for the rows.
- **The last free work (143.a) and the spread-fee question, checked along (via line 1).** The four works show in every
  view. One live turn of the operator's question through the chat view (about 0.005 USD): both quotes and all ten passages shown in
  their order, every link on an existing page, relevance and floor in sight. What the core returned went back to line 1: the
  answer's own text repeats its quotes, gaps and follow-up, one of those quotes the word-for-word check had dropped; the
  answer is German against the generator's rule 7; the export gives PDF page 76 of the regulation no printed number though
  its reading holds "L 87/76"; the export's outline is flat (252 units), not the nested sections of loader 6. The view's
  own: a long chapter title wrapped below its marker (mended), and the dropped quote is shown nowhere (put to the operator).
- **The deck's three screens (the operator's OK for the English turn, via line 1).** One turn on a `--public-only` server from the
  main tree (about 0.004 USD), English, three quotes all kept, fidelity held again. The calls screen showed the pages a call
  answered running into each other once opened: mended, one page a line. **Mistake:** a process filter meant for this
  session's server also matched search servers of the main tree's venv, which may be line 1's; the permission check refused
  it, and the server was stopped by its own task instead.
- **The overview's tiles say what they count (the operator's 1.a, via line 1).** The banner's 15 works against the tile's 11 were
  both right. The served counts are taken as the banner takes them, not recounted, and a test reads the banner's own line.
  First wording for the time the index is still being built ("search index still being built") doubled the tiles' height in
  the browser check, which sees the overview before the index stands; shortened to "search index building".
- **Loader 7's nested outlines (line 1, main 959627a), checked in the chapter view.** The EU regulation's 111 roots stand
  at the top and every one of its 141 children inside its parent; Regulation T's 34 roots likewise; "ANNEX II > Costs and
  charges > Identified costs ..." opens down to PDF pages 75 and 76. A page stands under every unit whose text lies on it, so
  page 75 stands under all three: the export's `units`, shown as given. **The new browser check for a long title failed
  once:** that title now stands nested inside folded parents; the check opens them first, outermost first, and so tests the
  indented case.
- **A fine line between rows, every list (the operator, via line 1's new session).** One token and one shared rule replace eight
  per-view row borders and part the lists that had none. The search hits kept their spacing, now half above and half below
  the line. **The new browser check failed once:** it took the Kelly paper's second top-level chapter, but since loader 7
  that paper's chapters all stand under its title; it now takes the EU regulation's. Looked at in both themes.
- **Details lines and block boxes (the operator, via line 1's new session).** Two key-value lists exist (a page's details, a run's
  facts); both take the shared rule, extended to a list's pairs. The block box keeps the findings mark by drawing the edge
  as an inset shadow, so the box's 1px border and the 2px edge do not compete.
- **Three questions left as they are (the operator: "leave everything as it is for now").** A quote the check dropped is not shown in the chat
  view (26.c); a page with findings whose text comes from its text layer still opens on the quoted text, one click from its
  finding (27.c, 20.a stands); the chapter view does not say where its titles come from (28.c).
- **V13, the HTML works: an explicit exception to the feature seal 142.a (the operator's 6.a), named here as such.** Ordered through
  line_features, the operator's plan read before any code. A data check first: the index's heading paths, the s-labels as the search
  server gives them, every chunk found in its section. Built: the API, Sources' Structure column (4.a), the outline, the table
  and the chunk pane; the original's pane and the dropped headings wait for line 1's function. **Mistakes:** an invented test
  text that repeated one sentence placed a chunk at an earlier repeat (the test now uses a text without repeats, the limit
  stands in the docstring); a join of chunks on the section id, which has no index, took 15 s for SRE, now counted over the
  index's `chunks_by_source` in 0.24 s; a browser check of an unrelated view timed out once while the full test suite ran
  beside it.
- **The overview's browser check waits longer.** It failed twice in a row, also without load: the overview hashes every
  reading file on each call (69.a), 3.5 to 5 s measured, and as the first request it shares the machine with the search index
  being built. Its two checks now wait up to 20 s, the reason beside the constant.
- **V14, the check in stages, its judges and a person (146.a, 147.a; exceptions to 142.a named as such).** Display orders
  from line 1, the operator's review demo first. A data check on finance p. 5 before code: stage 2, the judge with its version, a void
  finding, three judgements of the shown reading. The page's details now give the stages one by one and a person; the
  history every judgement. **Mistakes:** a judgement line drawn as a flex box on the table cell itself lost the cell's span
  and wrapped narrow (now a box inside the cell); spaces at the start of conditional spans were dropped ("cannot checkb05"),
  now one joined string; the fixtures and one browser check that invents a page's history lacked the fields the API now
  always sends.
- **The prompts tab (148.a).** The core offers the judge's versions alone (`page_judge.judge_versions`), so the API reads the
  registry and the frozen contract by the core's own paths. **Found on the way:** judge/2 and judge/3 each change one long
  paragraph line, so a line diff showed the whole line removed and added; a word diff of replaced lines marks just the added
  sentence. **Mistake:** a test joined the diff's lines without line breaks.
- **V13's left pane and rule 5, with line 1's `strip_source` (78dd1b7).** Kept in memory per work, never written. A
  dropped heading is placed after the section it follows, under that section's top unit. **Found:** the sanitiser kept
  `id` but dropped `colspan`, `rowspan` and `data-image`, as DOMPurify tests unknown attributes' values against the URI rule;
  named inert, and a test pins all four. The invented-index tests now stub the stripping, since the real raw files do not
  match an invented index.

## 2026-11-10

- **Opened chapters are remembered (the operator: "when I unfold something, it should remember that").** A chapter opened, a page clicked,
  and on coming back all stood folded again. Kept in the browser per work under a key of its own (`openUnits.v1`), the
  chapter known by its first page and title, since the outline's ids are renumbered whenever the core cuts it anew; the
  HTML outline likewise. The opening a filter makes is not remembered. **Found on the way:** the runs' browser check timed
  out: 390 runs, the newest hundred judge and prototype runs that choose no reading, walked newest first at 0.16 s each; it
  now walks the oldest first, and counts the listed runs as "at least", since the core may start one meanwhile.
- **A page's readings, folded and ordered (the operator: "retries should fold open ... order them better", line 1's proposal,
  confirmed by the operator).** Each reading is one folding line, the one shown first and open, the earlier ones newest first; a
  folded line sums its judgements up ("4 judgements: judge/1 counts · 1 asked again · 2 prototypes"). Opened, its
  judgements stand in one table with aligned columns, the role (counts, asked again, prototype) a column of its own, the
  counting judgement first. **Found on the way:** the line's last fields fell into a grid row of their own under the 1ch
  marker column and broke "shown here" in two; they now share the last column.
- **The view's name from the config, and a menu in four groups (decision 149.c; the operator: "the menus are too big ... a burger menu and submenus with categories", through line 1).** `GET /api/app` serves `ui.title` and `ui.subtitle` of the app
  config; the header and the tab show them. The ten links became a menu button whose panel groups the views as the operator's
  order gave them; Overview and the view's own name stay in the header. **Found on the way:** a view that names itself
  from its address could lend its name to the next view, since it sees the new address a moment before it is removed; it
  now gives a name only when its name changes, kept with the address of that moment. The subtitle's leading space was
  dropped by the template, as once before in a conditional span; it now stands inside the interpolation. A first try to
  add the Python test through a one-line shell command broke on its quotes and changed nothing; the test went in through
  the editor.
- **The Reading History and the Lab (decision 150.a), and who said what in a finding (the operator on finance p. 5's b12: "error fixed - by what? was that the fix comment? what was the judge's message?").** The morning's ordering kept the
  experimental judgements in the history, receded; the operator chose instead to part them: the history keeps what the pipeline
  did, the Lab below holds a prototype's judgements and a judge asked again, folded. The finding's three parts now carry
  their names, since the struck kind, the void mark and the grey quote read as one voice: the judge found, code voided,
  the judge quoted. Nothing was fixed in the reading; it was right. **Found on the way:** a check of a whole line's text
  fails on the flex lines, since the spans stand without spaces between them in the page's text; the tests check each
  part.
- **A work's routes in a table (the operator: "is this route a faulty one?", line 1's spec).** The chips said each route as
  one long string; the table parts it into level, source, reader and why, the fallback marked. The API parts the strings
  where `served_readings.route_of` builds them, a test builds them with that function, so a change of wording in the core
  fails here rather than in the view. **Found on the way:** three browser checks counted every `tbody tr` of the work view
  and so counted the routes' rows as pages; they count `tr[data-page]` now. The fallback's glyph made its row taller
  than the others; it is drawn at the word's height.
- **Formulas typeset, paragraphs parted, the dashed line explained (the operator on Sharpe ratio, through line 1).** The sanitiser's
  list gained `data-tex` and `data-display`, both named inert as `data-image` was on 9 Nov (see above: DOMPurify tests an
  attribute it does not know against the URI rule), so "S_{a}" is not dropped. KaTeX typesets after the sanitiser, on its
  DOM fragment, so its own markup is not sanitised away. **Found on the way:** a first test that the LaTeX cannot ask for
  a link looked for "javascript:" anywhere in the result and found it, inert, in the `data-tex` value and in KaTeX's
  annotation; the test now asks whether anything became a link or a class.
- **The overview's first load (line 1 measured the operator's 22 s and proposed a stat cache and warming before the search).** Both
  taken. **Found on the way:** warming alone made it worse at first: five seconds after a start, while the search read its
  pages beside it, the overview took 8 s, since PyMuPDF holds the interpreter's lock while it reads a page's text layer.
  Measured where the time went (reading the pages 45 s, the index over them 4.9 s, pickling 57 MB 0.25 s) and moved the
  reading into a process of its own. A test that `--public-only` never reads the licensed base patched the core in this
  process; it now reads the pages here, with the same switch, and a test of its own shows the process reads them with the
  app's switch, and that the pages are read here where no process can be started. A measuring script without a
  `__main__` guard ran twice, once in the spawned process; the start command has its guard.
- **The prompts in tabs by part (the operator through line 1), and the dashed line's legend as a hint (the operator: "does the dashed note always show? ... rather show it as a hint").** The legend stood as a paragraph even over a section of one chunk; it is
  now an info mark, shown only where a chunk shares text. **Found on the way:** two layout faults in the new prompts
  table, both shown by its screenshot and not by any test: the automatic table layout grew to 3,575 px around an opened
  prompt (measured with a temporary browser script, then deleted), and a class name used twice made the diff's unchanged
  lines refuse to wrap. The browser check now asks that the page stays inside the window.
- **A description's frame and a grouped figure (the operator on accounting p. 305, through line 1).** Hovering the description drew
  no frame, as it has no box; it now borrows its figure's, dashed and labelled. The figure's T-accounts ran together in
  the readable mode; they now stand one box per container. **Seen on the way, for line 1:** the judge's finding on that
  description says "page shows twelve accounts"; the original and the reading show eleven.
- **The whole article (the operator, through line 1), and previous and next that jump (the operator: "a no-go in design").** Line 1
  proposed grouping an article's sections by raw file; the outline from the index already holds the articles at its top,
  stands without the raw files, and keeps a book in one file from becoming one scroll, so it groups them instead. The
  article view was first built with its neighbours after its title, the very fault the operator had just named in the section view;
  caught before it left the worktree, both now use one pager in boxes of a fixed width. **Found on the way:** a check of a
  control's place must be shown to fail: with the pager set back after the title for a moment, it failed by 22 px on the
  step from p. 9 to p. 10, then passed again with the pager first. A first draft of the check expected the title to start
  with "PDF page"; the title's text starts with a space.
- **Decision 159.a, step 1: three type sizes.** Line 1 estimated two to three hours for the four steps; line 2 said four to
  five, since each step runs the full gates and is looked at in screenshots, and line 1 passed that on. The rename ran as a
  byte-for-byte script over the sources, so no line ending changed. **Found on the way:** the type check passed at its first
  run, which proves nothing; it now injects a 19 px title at its end and must find it.
- **Step 2: the head line and the routes' one line.** The level totals are the API's, so the view sums nothing. **Seen on
  the way:** folding the routes would hide a route the shelf's link had chosen, and with it why the list is short; the
  line now says a route is chosen and lets it go.
- **Step 3: the chapters as a table, one grid for the page tables.** The page tables lined up only once nothing indented
  them: the depth moved from the tables' margin into the title's cell. The fold's mark moved into the title cell as well,
  since a `::before` on the row would have taken a column of the grid. The state columns follow the states the work has,
  so a state such as blocked keeps a column where it occurs. **Found on the way:** at 390 px the tables' first least width,
  52rem, left Reasons and Why about 6rem each and stacked a long why into a tall row; 64rem keeps them about 12rem.
- **Step 4: the other views.** A survey of every view at 1,280 and 390 px, by a temporary browser script since deleted,
  found eight views scrolling sideways at 390 px and the Issues repeating whole route strings. The tables were wrapped by a
  small script that moved each table's `v-if` to its new box and indented the table, so no line was retyped by hand; the
  last offender, the page view's Lab line, was found by listing the outermost elements past the window: its `width:
  max-content` stood outside any scroll box. The session paused in the middle of this step and
  resumed from the worktree as it stood. **Seen on the way:** one core test failed in this worktree's full run,
  `test_a_free_pdf_page_is_quoted_by_the_search_exactly_as_the_chat_cuts_it`, on Kelly p. 4 and p. 9: the index the
  worktree shares with the main tree by junction had been rebuilt by line 1's uncommitted PDF loader 8, while this branch
  still held the loader before it. It passed at step 3, and touches no file of this step.
- **Decisions 160 and 161.a: one content width, and a unit's pages under it.** Line 1 proposed the width tokens and a note
  column of about 18rem with the outside note on one line at 1,440 px; the first browser run found the note two lines
  high, as it stood at the body's size, and put it at meta. With the note at up to 28rem the chapter titles then wrapped
  ("Chapter 2 Corporate Structure and / Governance"), which the screenshot showed and no check had asked about; the
  note's column was narrowed to 21rem, its words shortened, and the check now holds the titles to one line too. For the
  indented blocks line 1 named the rule that settles the two wishes: the first column absorbs the indent, so the other
  columns keep their x. A browser check of the chapters with an invented outline lacked the new `own_pages`, and the view
  failed on it; the invented outline now counts its own pages as the API does.
- **The Sharpe check-along and decision 164.a.** The operator's question ran once through the chat view on a `--public-only`
  main-tree server (0.0041 USD); the view showed every quote and source as the API sent them. Three core findings went to
  line 1; one was withdrawn when line 1 showed the passage holds the 1966 formula the answer cites, the other two became
  decision 163. The "open in the article" idea, sent as a question, came back as 164.a with line 1's hint that the data
  might already hold it: it did, and the core needed nothing. **Found on the way:** the key test first asked a search page
  for `label`; the search's `Page` names its label `page`.
- **Human times (the operator on accounting p. 524, through line 1: "every time stated in the project must get a human date format").** One formatter on the browser's `Intl` and one `<time>` component; the API keeps ISO 8601. **Found on the
  way:** the formatter's own test first expected "13 h ago" for 23:30 UTC seen at 13:30 UTC the next day, which is 14
  hours; the test was wrong, not the code. Five view tests had pinned the old "11-05 08:52" against the real clock; they
  now ask for the `datetime` the API sent and for the formatter's words. Under a day's heading in the calls a time of an
  earlier day repeated the date the heading already says, so it says its clock alone there. The browser check passed at
  its first run, which proves nothing alone; it puts an ISO timestamp on the page at its end and must find it.
- **A page's readings numbered, and one sentence first (the operator on accounting p. 524, items 2 and 3).** Line 1 guessed p. 524's
  fourth reading was "read again (round or replay)"; the core's code showed it was decision 113.a's hinted retry, and the
  export did not say which kind a re-read was. Line 2 first inferred the kind from the reading before and told line 1,
  which then wrote `purpose`, `cell` and `retry_of` into every attempt of the export (86efdb2); the inference was dropped
  for the core's words. **Found on the way:** the inference first read the reading before by its class, which is today's
  validator's: a first reading malformed when it was retried may pass today, and six re-reads came out "read again"; it was
  turned to the core's attempt numbers before the core's words arrived. The real-data tests first opened every page of the
  export and so rendered every original, which ran past five minutes; they call the two functions on the rows now, and
  one page whole. A page no check had reached broke the sentence on its missing check; it says nothing more, as its state
  says all there is. Finance p. 229 and Reg NMS p. 4 serve their text layer while their first reading passes today's
  validator; passed to line 1.
- **A person's verdict beside the state (decision 166.a).** Line 1 asked that the API call the core's
  `human_standing` rather than re-implement it; it does, and adds only "noted" for a note alone, with the core's own
  test of `applies`. The state chips' counts needed a place after the count in the facet bar, which had only a slot for
  the value; it gained a second one. A person's glyph and word replace the emoji line 1 wrote, so the mark follows the
  icon registry's rule of one drawing per meaning and is never colour alone. **Found on the way:** the chip's tally first
  read "·  1 accepted" in the unit test, two spaces around the glyph, which the browser collapses; the test compares
  collapsed spaces. A new list field with an empty default is required in the generated types, so ten fixtures gained
  `people: []`.
- **What kind of page it is (decision 172.a).** Line 1 offered to sort the Issues' pages that are not content last; the
  API orders them so and marks each (`apart`), so the view only parts the list where the API says, and never decides what
  content is. A page no reading named the kind of, mostly a blocked one, counts with the content: nothing says it is not.
  **Found on the way:** the two lists of the Issues first stood in columns of their own widths, Reasons and Why at
  different x, which the screenshot showed and no check had asked about; the grouped table now has one fixed grid, and
  the check holds its columns within a pixel. The italic category sat lower than the marks beside it until it was set
  like them. A label's constant exported for the view and never imported failed knip; it stays in its module.
- **One voice a line, and what a category means (decisions 178.a, 177.a).** The operator first named the void line "user judgement";
  line 1 pointed out the void is the code's, so the person has a line of their own and the code's is "The code's ruling".
  Line 1 asked for the four labels in a browser check on finance p. 5; b12 has no person's verdict, so the check finds
  three there and the fourth on accounting p. 635, b08, where a person accepted the reading. The labels went bold in an
  addendum while the check was being written; it now asks each label's weight. **Found on the way:** a scripted edit of a
  test whose strings held escaped quotes missed its match and changed nothing; the test was edited by hand.
- **The analysis set apart (181.a, item 2), done first as line 1 asked, since it is small.** Its markup was wrapped in a
  section and the wrapped lines indented by a short script, so no line was retyped. Decisions 183 (the record zone in the
  standard width, the analysis alone wide) and 184 (a labelled page head) arrived meanwhile; line 1 placed them in 179's
  steps 1 and 2.
- **A judgement recalled on the page (181.a, item 1).** Line 1's addenda arrived while it was built: an unmistakable
  marking, then the operator's own viewer's convention (a chip with the way back, a dashed frame around what the overlay acts on),
  then the skills' new rule that the overlay is the annotation role, always dashed. A token of its own, first named
  "overlay", was dropped for that role; the name would also have collided with the popover's `--color-bg-overlay`.
  **Found on the way:** the validator showed the light annotation hue failing against the link blue under deutan (ΔE 6.0)
  and the dark one in the 6 to 8 band; a first light candidate passed against blue but stood 12.8 from error at normal
  vision, so the hue was searched against all roles at once. The browser check first expected the recall's id
  percent-encoded in the address; the hash router keeps its colons and slash, and the check now compares the decoded
  address. The store is read by path and only for a key that is one of the page's own readings, so no path the address
  names can leave it; a test tries one.
- **Decision 179, the audit and step 1a.** Line 1 approved the plan in its order, split step 3 into 3a and 3b, and folded
  decisions 183, 184, 186 and 188.a, the badge and title fixes, the chart labels and the viewer's rules into the steps;
  step 1 was split again into 1a (the fold) and 1b (the grid folds and the two zones), so each lands green. **Found on the
  way:** the fold first asked the settings store on every mount, and the chat turn's tests, which mount without a store,
  failed; only a remembered fold asks it now. A test that compared the page's HTML for `class="history"` broke once the
  root carried the fold's class too; it compares the two folds' order in the document instead.
- **Step 1b.** The readings' fold first kept the mark inside the grid, as the chapters do; a plain fold with the grid as
  its title keeps the columns aligned as well, since every reading's mark has one width, and lets the general indent
  check see it, so only the chapters keep the mark in the title cell. **Found on the way:** the width check first measured
  a zone of the page the browser had just left, still in the document while the next view came in, and read it as 0 px
  wide; it now waits for the view's own analysis and measures inside the view. Two counter-probes broke each other: a
  style injected to show the page-title check failing still held when the type-scale probe ran after it, and is removed
  after use. The fold check's counter-probe clicked a fold the first pass had left open and remembered, and so closed it;
  it now opens it directly. The check that a reload keeps the history open passed alone and failed in the full run:
  the fold says its toggle after the click returns, and the reload came first; it now waits until the choice is kept.
- **188.a, a person's correction and assessment, taken ahead of step 2 at line 1's request while the operator looked at p. 94.**
  The core added the fields in 879233b; the API's model took them without a change in its reading, and the fold of the
  finding voices shows them. **Found on the way:** a unit test compared the assessment's whole line and found its label
  and words run together, the known trap of flex spans without a space between them in the page's text; it compares each
  part.
- **190.a, the printed words in attributes.** **Found on the way:** the template's own line breaks between the term, the
  separator and the body became spaces: two after the colon, and a leading one in a body that keeps its line breaks
  (`pre-line`), which an older test of a grouped figure caught; the bodies are written without gaps between their nodes.
- **Step 2a.** **Found on the way:** the findings line's jump first carried `data-block`, the attribute a reading's block
  is found by, so a test looking for block b02 found the button; it carries `data-jump`. The new record first flowed its
  lines side by side under the old head line's flex rule, and the old findings line's grey small type held, which the
  screenshot showed; the record is a column now and the old rules are gone.
- **Two checks that hung on a real page's state (after line 1's ff9a57b).** The operator accepted finance p. 119 in the walk, and a
  Python test and a browser check had taken it as "a standing finding on a page served from its text layer". The test now
  builds that case from an invented row; the browser check picks such a page from the Issues when it runs, by its state,
  not by its number. On the page it then chose, a tall block below the page's grown record (184) showed its start but not
  half of itself in a 720 px window; the check asked a share of the block where its intent was the block's start in view
  with the window unmoved, and now asks exactly that.
- **Step 2c and 194.a, taken ahead of 2b,** as the operator was looking at figures in the readable mode. **Found on the way:** an
  edit script passed through a Bash heredoc lost its backslashes, the known trap of `rules/machine.md`, and a `split('\n')`
  became a line break inside a string; the type check caught it and the line was set with the editor. A first try handed
  the fold a hover through an attribute it does not take; explanations wait for 2b's hint registry.
  The guard that a block reaches the view only as segments, cells, LaTeX, code or text listed the block's fields and
  failed on the new `decorative`, which is the API's reason, not the model's text; it lists it now. The three browser
  walks that open every fold took a list once and clicked through it while opening a fold drew the view again, and one
  clicked a row that was gone; a shared helper looks the next closed fold up anew after each click. Two browser checks now
  skip on today's data: no page of its work is declined any more, and the calls list (as before) has no answered page here.
- **Step 2b, part one,** split from the hint registry and the hover card so that the walk's new fields land first. No reset
  exists in the data yet; the tests invent one.
  The routes' browser check began to skip once the walk moved finance's last pages off its fallback route; it picks a work
  that has one from the Issues when it runs, so it checks the fallback row again rather than skipping it.
- **Step 2b, part two.** Line 1 noted that part one named the page's protection 189.b; it is decision 191.a with the reset
  (189.b is the rule that a wrong block always gets its correction). The labels in code, tests and this chapter were set
  right in this commit; part one's commit message keeps the wrong number. **Found on the way:** the overlap hint's old
  button left two imports unused, which the type check refused; a card fixed to the window was chosen over one placed in
  its cell after a table's scroll box was seen to cut anything absolutely placed inside it.
- **Step 3a.** The shared rules stand unscoped in the table component, by its class, since the cells are the views' own
  and reach it through its slots; a view's own rule for the table element itself would not reach it, so the routes' margin
  went to the box around it. The grouped list's work row kept its rule beneath it, which the parted-rows check asks for.
- **Step 3b.** The eleven tables were moved by a script written to a file, after two heredoc edits had lost their
  backslashes earlier in the day; it removed a table's own rule for the table element, which no longer reaches the
  element the library draws, and kept its width as the table's `wide` option. **Found on the way:** the script's pattern for
  a class took `class="{ paid }"` out of the overview box's `:class="{ paid }"` and left a bare colon; the type checker
  crashed on it without naming the file, and a compile of each changed component found it. Four scroll boxes under a
  condition were left by the script, which matched only an unconditioned box, and were unwrapped by a second one.

## 2026-11-11

- **Checked along on judge/4's verdicts** (line 1, for the operator's choice of the active judge). The first look found no judge/4
  in the page JSON at all: the tracked export had been written before judge/4's batches were collected. That was the
  core's, sent back, and line 1 wrote the export again (c89ff5c). Before it landed, the view was checked against a copy of
  the export in the scratchpad with the core's own judgements of each reading put in, the store only read, so the check
  did not wait. Accounting p. 69: judge/4's one flag on the clean calibration pages judged the mini pilot's reading, a
  reading the page's history does not list; line 1 had told the operator the served reading lacked the title, and the served one
  has it as its own heading block, so the omission is the pilot reading's alone, and the calibration judgement stays out of
  the page (line 1 agreed and corrected its protocol). **The view's own two faults:** the rows gave the findings' count
  without their severity; and a person's assessment, rating judge/1's finding, stood unnamed under a recalled judge/4's
  finding. On p. 119 that read as the person calling judge/4's finding a false alarm, where the person's own note says the
  grid finding, which is judge/4's, is right. The judge named is derived in the API, never in the view: the counting
  judgement on the verdict's reading, the latest stored before the verdict was given. Both verdicts were given before
  judge/4 judged (19:58 and 20:41 against 22:46 on 10 Nov), so the person cannot have meant it. Recording the judge
  with the assessment would be the core's, so it is left to line 1 to propose; the API would then read it instead.
  **Found on the way:** the scratch check's first run called the recall with the title it does not take and stopped after
  the first page; its second read the person's verdicts by a field the block does not have and showed none.
- **The page's head and one text size** (the operator, on finance p. 119: best practice for the best overview; then "I prefer everything uniform", and "do it as you recommend for now"). Proposed as seven findings with options; the operator
  took the recommended bundle of the head (each thing once, aligned columns, 100 characters a line, a person's verdict
  before a state it overrules) and asked for the sizes to be looked at. The second pane's share stays open. **Measured
  before deciding:** a browser walk of 17 views listed every visible text's font and size; the font was already one, form
  controls included, and the sizes the three of 159.a, so one size was taken, the one most text already had. The size
  declarations went by a script written to a file, which also removed the rules left empty, and their comments where a
  comment stood only for that rule; the diff was read for each. **Found on the way:** the aligned values moved by 7 px from
  a page with a person's line to one without, as the label column took the widest label present; it now takes the
  longest the record can show. In the grid the labels sat 3 px below their values until the line aligned by baseline.
  An invented page served from its text layer showed "Why: a person rejected the reading" under a sentence saying just
  that; a person's why now gives only their note. The receding state's reasons kept their bright ink, set by the list
  itself; the line's rule now reaches them.
- **211.a, a page a person settled leaves the issues** (line 1, from the operator). Line 1's rule named a current verdict, by the
  page's protection, and the latest one for the split. The view takes the rule the page's own person mark follows (the
  core's standing accept or reject on the reading shown, else an applying note): the same on today's export, and apart
  only where a verdict stands on another reading of the page, which then settles nothing, so the head, the row and the
  count never disagree. The record's line was named "State:"; on a settled page it would have read as the person's, so it
  is "Check:" now, everywhere. **Found on the way:** the Issues' check of the aligned columns measured every list's
  header, the folded one's at x 0; it opens the fold and asks for three. The check of a narrowed list took the first
  row's check state as the facet's value, which for a settled page is no longer what the facet lists it by.
  The fold of settled pages indented its table, so its columns stood 40 px off the open lists'; the columns check found
  it, and the fold is flat. The check of a served issue's why began to skip, as every such page is settled today; it
  takes a settled one, in its fold, where no open one is. And the prompts' check, unrelated: it took the first version
  with one before it, now line 1's reader prototype page/2, a rewrite whose diff has added and removed lines and no word
  replaced in a line, so nothing to mark; the view was right, and the check now picks a version that changed words.
- **206.a, step 1** (line 1, from the operator; the core's 205.a waits on it). The segment's kinds widened first, since a reading
  with an `fn` segment would fail the API's model before the view could draw it. The link to the note is the API's: it
  knows every block of the page, the view knows one segment. The card sits around the raised marker, not inside it, so its
  text keeps the one size rather than the superscript's.
- **204.a** (line 1, from the operator). The table's drawing moved out of the reading's blocks into `ReadingTable`, used by the
  reading and by a correction alike, under "unify as you go". **Found on the way:** the build stopped on a type the
  view's type module did not name yet (`Cell`), and the browser check of the new table ran against the old build and
  failed, as it should; with the type named, it passed.
- **210.a** (line 1, from the operator; taken before 202.a, since the export already listed page/2's readings and they stood in the
  history). The reading keeps its number among all the page's readings, so a recall's line and the Lab name it as the
  export orders it; the history's count is of the pipeline's readings. **Found on the way:** the operator's look at finance's work
  page showed "decided by a person" running into "Note"; the chapters' columns were fixed at 7rem. A first control of the
  new heading check, run by stashing the change, proved nothing, as the stash took the check with it; the check now puts
  the old widths back itself and must see the overrun.
  The check of accounting p. 524's readings expected every attempt in the history, page/2's too; it takes the pipeline's.
- **202.a and a verdict's one look** (line 1, from the operator; and the operator on the history of finance p. 119: "all the displays would need one clear line", change only with high confidence). Taken: a person's verdict in one look, as
  certain; proposed, not built: the Lab drawn as the history is, by reading, at 70 % confidence. The rules first stood
  in rows of their own after all the Lab's judgements; a judgement and its rules now come from one loop, so the rules
  stand right beneath it. **Found on the way:** the unit test of a rule's line read its parts run together, the known
  trap of flex spans without spaces; it compares the parts.
- **203.a** (line 1, from the operator; under "unify as you go"). Three named places, and a fourth found: the assessment's tooltip
  repeated the note that now stands beneath the verdict, so it went rather than moving. The dashed overlap's tooltip went
  too: its figures are the count's card, its meaning the view's hint.
- **Checked along: the demo views** (line 1, for the deck's screenshots in `_INTERNAL/deck_shots/`, light theme set in
  the browser alone, as the app's theme is dark by its page and has no switch). One claim of line 1's did not hold and was
  the data's, not the view's: accounting "issue 9" was before validator page/1.3; the view says 3, and the Issues agree.
- **208.b, the conversion in folders by concern** (line 1; the operator: "internet is back, to all lines"). Line 1 rewrote the
  imports of this API's five modules and its tests itself and held them while it worked; line 2 waited, then took main
  as it was. One thing was the view's own: a run's command is said without the module path all of them share, and a run
  started since reads "python -m backend.conversion.checks.check_run …" where the pipeline database keeps the earlier
  "python -m backend.conversion.check_run …". The path to drop now takes an optional concern folder, named one by one, so
  both read "check_run …" and a folder the conversion does not have is not taken for one.
- **The head's findings, flagged** (the operator via line 1, 12 Nov, on accounting p. 524). Both flag and colour, as beneath the
  block: one look for one kind of thing, the rule the operator is deciding as line 2's question (3). Line 1 named finance p. 94 as
  "one minor under an ok outcome"; that is judge/4's, seen when it is recalled, while the head shows the page's standing
  judgement, judge/1's major; the minor case is tested with an invented page.
- **219.a, a work's head on the page head's grid** (the operator, via line 1; formerly line 2's question 1). The facet bar became
  labelled lines everywhere it stands, not only on the work page, as one kind of thing gets one look; the Issues and the
  calls changed with it. **Found on the way:** a line of toggles centred its label between two wrapped rows, and set by
  baseline it sat 3px low beside the toggles' padding; it now stands at the top, set down by the toggle's own padding and
  border. Measuring that showed every labelled line with a value that begins with a glyph 3px off, on the page's head
  too, since 11 Nov; the lines stand at their top now, and a check measures the words' line boxes. A scratch server run
  outside the harness's background tasks was stopped by its port.
  **Found by the full browser run:** at 390 px the work page and the Issues scrolled sideways, the bucket's toggle
  (361 px) wider than the value column; a toggle's parts now wrap inside it. The voices' check met a block with a
  person's correction and assessment (line 1's 217.a on accounting p. 635) and knew neither voice; it reads them from
  the API now. The timestamps' walk ran past 180 s: it hung on a click in the Issues, held by a hover card a row had
  opened under the resting pointer (since 203.a gave rows their cards), and the calls' log has grown past 300 folds
  (24 s to open). A card now lets the pointer through, and the walk opens the first 60 folds of a view, each kind among
  them, said in the check.
- **213.b, a person's verdict from the page view** (the operator via line 1, 12 Nov: "this really is the last proper feature before the freeze"; the switch 223.a, the correction 224.b). Line 1 built the core's `from_view` and the export
  queue first; line 2 the route, the dialog and its checks. The view addresses a work by its id, the core by the export's
  folder name (`openstax-accounting`, not the source id); the API maps one to the other from the page's own row, and a
  test pins it. Two of line 2's own tests broke and were told apart from a fault: the start switch's test replaced
  `create_app` with a function that knew no `allow_verdicts`, and the block's field list lacked the new `body`.
  **Found on the way, for the deck's shot:** accounting p. 524's b11, a table the reader marked unreadable, carries a
  person's correction as a table, and the page showed it as HTML source: the rule from 204.a asked the block for cells of
  its own, which an unreadable table has none of. It asks for the block's class now. The deck's shot was taken from a
  scratch server started with `--allow-verdicts --public-only --no-chat` as a background task, every verdict request
  aborted in the browser, and the server stopped after it; nothing was sent. The correction's field ran its one-line HTML
  out of sight to the right; it wraps at the field's edge now, the text unchanged. knip found two type names exported for
  nothing, and they went.
  **Line 1 ran it once end to end** on copies of the export and the pipeline database (the real ones untouched, 31
  verdicts before and after): recorded, the export finished after 53 s without error, and the page showed the note on
  reloading. The dialog had promised "about 40 s", measured on an idle machine; it says "about a minute" now, which holds
  on a busy laptop too.
- **227.a, every page opens on its reading** (the operator via line 1, 12 Nov, optics). The one exception kept is not a choice: a
  page without a reading has only the quoted text to show, and opening it on "readable" would leave the pane empty.
  Accounting p. 360 is such a page (blocked), p. 398 a text-layer page with a reading. Every browser check that clicked
  "readable" on a text-layer page first still does so harmlessly; the two that pinned "quoted" now pin "readable".
  **Found by the full browser run, twice, and not alone or in the first six:** 219.a's check of the work head failed
  at its control, which widened the label column on the grid elements themselves; the work view draws its head again when
  the work's pages arrive anew, and Vue sets the grid's own width back on it. The control is a style rule now, and the
  check measures from the head's edge once the head stands, so a scrollbar still coming does not count either.
- **229.a and two faults on accounting p. 398** (the operator via line 1, 12 Nov, right after the first real verdict from the
  dialog: verdict 32, export run 231; route, export and reload all worked). The text correction was not lost in the API,
  which served it; the view drew a person's correction only beneath a block's findings, and b04 had none. The break was
  lost in the core's table parser, on purpose: its quoted text needs a table one line a row. So the break could not be
  drawn from what the API gave; the API now reads a cell again with the same parser, the break held by a private-use
  character, and keeps the first parse wherever the second would differ in shape. The core is untouched. Which correction
  stands is the API's choice now (latest applying, not archived), so the view and the dialog cannot pick differently; the
  dialog's own rule went. The struck-through reader's text of 188.a went with it: the reading now stands whole beneath
  the correction, muted, which is what 229.a asked. Found while checking p. 524: under a correction over an unreadable
  table the reading's label named nothing, and now says the reading holds no text there. Line 1 added "not served yet"
  to the correction's line so "correction first" cannot be read as what the search quotes. Verdict 32 lives in the main
  tree's export, not yet in the worktree's tracked copy, so p. 398's b04 is tested with an invented block of its shape.
- **228.a, the validator's errors on their blocks, and the raw text numbered** (the operator via line 1, 12 Nov, after 229.a).
  The validator's errors are strings; parting them in the view would have computed in the UI, so the API parts them by
  the validator's own two forms and keeps the string whole where neither fits. Who looked is the same choice as which
  correction stands (`latest_standing`, one function for both). The validator's line numbers were checked against the
  raw text before anything was built: p. 398's line 26 is b04's fence, p. 338's line 86 the refused attributes, so the
  gutter counts from the file's first line. The gutter is a pseudo-element, so neither the text nor a selection holds a
  number; a browser check selects the whole raw text and compares. A Python script through a Bash heredoc turned two
  escaped newlines into line breaks in the page view (the trap the machine rules name; it struck this entry too); found
  in the source and mended with the editor.
- **A parting dot at a line's start, again** (seen on p. 398's b04 while checking 229.a). The operator had asked on 11 Nov that a
  wrapped line never begin with the dot that parts two fields; the note had moved to a line of its own then, but the
  verdict's line itself was a flex row whose items each began with their dot, so a long reason pushed "· maintainer" to
  the next line's start. The person's line, in the lists and beneath a finding, is one run of text now, each dot bound to
  the word before it by a no-break space: a line breaks after a dot, never before one. The validator's error on a block
  had the same fault for its "show raw"; that and who looked stand on an indented line beneath the error now, as a
  finding's evidence does.
- **225.a, a chapter's count opens its pages** (the operator via line 1, 12 Nov, "only if it fits before the freeze"). Line 1's
  example, chapter 6's red 1 to p. 398, no longer held by the evening: the operator's verdict 32 had moved p. 398 from issue to
  decided by a person. Leaving that count a figure would have made the example unreachable, so the decided count opens
  its pages too (`OPENED_BY_A_COUNT`); said to line 1 with the commit. The units to open are found as the filter's are,
  from each page's units upward (one function for both now, `withAbove`), and the open-units store opens them, so they
  stay open on coming back, as the reader's own opening does.
- **Stage 3 in labelled lines** (the operator via line 1, 16 Nov, about two hours before the review; markup only). Stages 1 and 2
  stay one line each, as line 1 asked; they read as single facts beside stage 3's three and were left alone.
  The full browser run then failed twice. One was this change's: a check that the head has no "Why:" looked over the
  whole page and found stage 3's; it looks at the head now. The other was the data's: the call log, grown since 12 Nov,
  lists a call answered with a work first, whose link opens the work, and the check took the first link for a page's; it
  takes the first page's link now, and skips, as before, where no listed call names a page.
- **Which search is which, said where it is chosen** (the operator via line 1, 16 Nov, an hour before the review; text only). The operator
  typed a question into Search and expected the chat's hybrid search. The menu now says "Chat · hybrid search" and
  "Keyword search · no model" (the operator: "search without LLMs"); the search page's heading follows, and its note says it is the
  MCP server's keyword tool with no model at all, neither embeddings nor a language model, and sends a question in words
  to the Chat by a link; the Chat's first screen says its answers come through the librarian's hybrid search and every
  quote is checked word for word. The label is the route's, so the header and the tab say the same.
  **→ now**, the same day, the operator's naming rule: `search` is called search (BM25), `semantic_search` semantic (hybrid). The
  menu says "Chat · semantic (hybrid)" and "Search · BM25, no model", the search page's heading follows, and both lines
  say BM25 and semantic (hybrid) where they said keywords and hybrid search.
- **Ready for a public repository** (line 1's handoff, 16 Nov evening, after the operator's 263.a to 267.a). Line 2's
  share, delivered as a patch on the import commit rather than as a commit, since that commit is redone: a Host check on
  every route, the licence notices of the bundle, the operator named by role with their quotes translated, a licensed
  work's key and the licensed shelf's counts replaced. The handle went by a script that capitalises at a sentence's
  start, across line breaks and comment markers, and lists every case for a look; the quotes by a table of each German
  phrase and its English, matched across wrapped lines, longest first, so a short quote inside a longer one is not
  translated twice. **Mistake:** the new test of the chat's own Host check imported `starlette` directly, which
  `requirements.txt` does not declare; the contract test that every import is declared caught it, and FastAPI's own
  `Request` took its place. **Found on the way:** the test client's default host, `testserver`, is refused like any
  foreign name, so every test client now names 127.0.0.1; the rebuilt bundle differs from the old only in the scoped style
  ids Vue hashes from each component's source, comments included.
- **A.a: why, cost, the raw error's block and the box's stroke** (line 1's handoff, 18 Nov, the operator's A.a). The
  worktree first moved onto the new main: every junction to the data removed with `rmdir` but `.claude`, the main tree's
  folders named in a git-ignored `configs/app_config.local.json` instead (285.a). With it six of line 1's tests failed,
  each assuming the data lay inside the repository; line 1 fixed them (f282e80). Then the four tasks. **Found on the way:**
  the page's row wrote 0.0 for a reading read in a session, where its attempt wrote None; the API takes the attempt's
  own, and line 1 makes the row's None too. The export writes `format_errors: null` for a reading that passed, which the
  model takes as none. Three browser checks went red after the change and were the checks' own: two computed the
  expected figure with `toFixed`, one invented a history in the API's old shape, which threw in the view; they now take
  the formatter and the current shape. **The box:** line 1 measured the reader's boxes against the text layer (median 1 px
  off); the view put each frame on its bbox to 0.03 px, measured in the browser over 65 blocks, so nothing was shifted.
  A screenshot showed what was: the stroke inside the box lay on the first and last glyphs. **Mistake:** a screenshot
  script given `/free/...` from Git Bash found no page, its path rewritten into Git's own folder, as this file warned on
  5 Nov; run from PowerShell it worked.
- **page/1.4's exact line and an automated review** (line 1's handoff of 18 Nov, after d58533f and 505b7fd). One
  question went to line 1 before building: where a page a delegated review settled is listed. The answer, Q.a: its own
  bucket, as the core serves the page by the review but nothing a person decided may count as a person's. **Found on
  the way:** two browser checks went red with the change and were the checks' own: one counted the Issues' grids as a
  fixed three, the other expected "show raw" at the block's opening line, where accounting p. 398's error now names its
  fault's own line (29, the block opening at 26); and at 390 px the Issues scrolled sideways by 15 px, since a state's
  mark keeps its words on one line and "decided by an automated review" alone was wider than the column. Inside a facet
  toggle the state's words now wrap.
- **N1.a, the licensed catalog in the sources list** (line 1's handoff, 18 Nov). The free view shows no catalog notes
  today, so "notes where the free view shows its notes" became a line under the title wherever the API gives notes, which
  only the licensed catalog does; the free catalog's notes are working notes and stay out of the view. No screenshot of
  the licensed rows was taken: a screenshot takes the free mirror only, and the unit test draws the row from invented
  entries. **Found the same evening:** three tests pinned live free pages that the second reader then read (accounting
  p. 360, Kelly's blocked pages): they now invent a blocked page, or take any free page in the state they need and skip
  without one.
- **O1.a and two findings of the operator's** (18 Nov). The table's cut licence column had a cause the operator could
  not see: the table scrolled in its box, but the box's scroll bar sat at the end of a list of 100 rows. Measured in the
  browser with the licensed rows (sizes only, no text): 1,612 px of table in a 1,408 px box. For "issue 9" line 1
  proposed a state of its own; a state is the core's word, so the view keeps it and says beside it how many of its pages
  are served, a count the API makes as it makes a person's tally. **Mistake:** the served count read `row['route']`, and
  a test's minimal rows have none; a row without a route now counts as not served.
- **P1.a, the licensed EPUB works** (line 1's handoff, 18 Nov). **Mistake caught by the suite:** the app tests over the
  invented licensed export listed the real licensed EPUBs of this machine, since `epub_works.epubs` reads the archive
  wherever the licensed base is served; an autouse fixture now hands those tests no EPUB, and the EPUB tests hand in the
  core's invented one. **Not looked at:** the view's pages with licensed text or images, by screenshot or by reading
  them, as anything of an EPUB must not reach a model provider; the browser check measured sizes and load states only.
  **Found on the way:** one image the core marks inline stands taller than six lines, a picture inside a paragraph; it
  keeps its size, since capping inline images would shrink formulas.
- **The sources table, again** (the operator's second look at 2,000 px, 18 Nov). The fit of the same day had given its
  narrow columns widths in `ch` that ignored the cells' right padding, and the state marks and the knowledge base's mark
  never wrap: so the structure cell ran into the authors (29 cells, up to 256 px of content in 179), the knowledge base
  touched the structure, and "trading_finance" and "edition" split mid-word. **Mistake:** the first check measured only
  the table against the window, not a cell against its neighbour. Now each fixed column is its longest word plus the gap
  (`calc(<n>ch + var(--space-md))`), a state's words wrap inside the structure cell, and only the work, authors and
  publisher may split a word longer than a line, which the ids alone are. The browser check now holds every cell's
  content inside its box and every word of a fixed column whole, over two invented rows; shown red on the table as it was.
- **H2.a, the fallback the export names** (line 1, 19 Nov, ahead of Y1.a's first merge). A licensed scan whose page is
  served by the IDE's legacy Markdown read "fallback · text layer" and "the PDF's text layer is served instead": the view
  took every route that serves no reading for a text layer. It now asks the core's `FALLBACK_ROUTES`
  (`NOT_SERVED_ROUTES`, renamed from `TEXT_LAYER_ROUTES`, since five places read it as "no reading served"), names a
  route's source by its own head, and words the sentence and the findings' outcome by the row's `fallback`. The API field
  `from_text_layer` keeps its name until stage D and now means "served by a fallback". Tested with invented rows, one per
  fallback and one of an export written before the field. Y1.a's stage A waited in a stash meanwhile, as both touch
  `readings.py`.
- **Y1.a stage A, the sources list's facet bar, series and F5** (line 1's handoff of the operator's Y1.a, 19 Nov). The
  operator chose three merges (Q1.a): A the bar, the series and F5 on the sources list; B the viewer's ranked list for it;
  C the issues, a work's pages and the calls on the new bar. Mid-stage the operator set the rule for all three: "we orient
  on the viewer, we do not imitate it". **Taken** from the FiniexViewer: the bar with its filter functions, the overflow
  row with its fit, the stored bar state and its tests, their lessons kept (a facet that cannot narrow stays disabled
  rather than gone; nothing a pick changes moves the bar). **Left out:** the viewer's translation marker `t()`, a
  convention this app does not have, and the overflow row's end group, which no row here uses; and every browser
  tooltip, which this app replaced by its hint and card (decision 179). **Added:** one slot for a value's look (Q3.a), so a
  state keeps its glyph, word and colour in the panel. The old chip bar stays, renamed `ChipFacetBar`, for the three views
  stage C moves. The counts beside the values are the browser's (Q4.a), an exception to "the UI computes nothing" the
  operator made for a facet's counts and "N of M" alone. **Mistakes:** the browser check first counted every work while
  the series stood closed, and so missed its three parts; it counts once the series is open. The check shown failing on
  purpose first failed for another reason: it clicked the knowledge base, which `--public-only` rightly disables, and
  timed out; it was run again on the format facet, and then failed where it should. A sort by title by default moved rows
  that five unit tests read by their place; they now find a row by its work. A test name lost its escaped quote through a
  shell heredoc, the trap `.claude/rules/machine.md` names; the scripts went into files after it. **Between:** H2.a
  (line 1's, the fallback a page names) merged first; stage A waited in a stash, as both touch `readings.py`, and came
  back onto the new main with only the built `dist/` in conflict, which a fresh build replaced.
- **Y1.a stage B, first part: ranks and the card** (line 1 agreed B1.a and B2, 19 Nov; B3 and B4 with the operator).
  Before choosing, a probe in Chrome settled whether a real `<table>` with a fixed layout can give up columns by a
  container query: it can, the hidden `col` returns its width to the others. So the ranks went into the library's data
  table rather than a second, list-shaped component beside it (the viewer's `RecordList` needs its subgrid because each
  of its rows is a button; ours hold links). **Mistakes:** (1) a series' heading kept its one cell spanning seven columns;
  on a phone's table, which keeps two, the browser drew five more columns for it and the work's column shrank to a
  letter, "WorkStructure" in the head. The first fit check did not see it: it measured the body's cells only and knew no
  floor for the work's column. It now measures the head too and holds the work's column to 8 rem, shown failing on the
  spanning heading put back. (2) The fit check counted a row's open hover card, fixed over the page, as text running out
  of its cell: the pointer from the series' click stood on a row after the window narrowed. The check now skips a card
  and moves the pointer away. (3) It first measured a cell that ends in an ellipsis by its clipped text instead of its
  box. The first was the view's, the other two the check's; all three were found before the report.
- **Y1.a stage C: the other lists on the bar** (line 1 agreed what moves and decided C3.a, 19 Nov; SC1 and SC2 with the
  operator). Measured first: the calls list 500 of 1,266 logged calls, so the bar counts the listed ones while the cards
  count all; the Issues hold 176 rows. **Kept from our own rules against the viewer's:** a facet the DATA cannot fill (a
  second knowledge base, a person's verdict) still stays away, while the bar disables one the SELECTION leaves empty: the
  viewer's lesson is about a bar that changes shape while it is used, which a data-given facet never does. **Added to the
  viewer's bar:** a facet's own order, as the core orders its states. **Found by the browser check:** a work's chapters
  check expected every page after a reload; with the choice now in the address the filter stays, which is the operator's
  F5 wish, so the check now expects it and clears it with the bar. **Removed:** the chip bar and its test, the person tally
  (its only use was beside a state), and the stored bar's default selection and scope.
- **O3.a, the overview as one corpus, first part** (the operator decided O3.a, 19 Nov; line 1's handoff). Measured first,
  in the container: the overview 48.5 s, the unfiltered page list 113.7 s for 10,224 rows, a filtered one 0.3 s. A profile
  natively found the page list's time in 28,854 stats of the export's index, one per page's title; the overview's in the
  integrity of every reading file, and once that was gone, in reading every run of each pipeline database. **The check
  line 1 asked for**, each removed row against a Pages filter, is a test now, field by field; two kinds of row had no
  filter (the costs per model and the search's media), named to line 1, which let them go. **A gap named, not built:** the
  Pages view can drop a filter but not choose one, so without the tables a count is reached only by its address (P1, with
  the operator). **Mistakes:** a test that cleared the export counts through a function's `__globals__`, written so in a
  hurry, became a plain module access before the report; a heredoc lost an escaped quote in a test name a second time,
  the trap `.claude/rules/machine.md` names, and the test files were written with the editor after it.
- **O3.a, second part: the shelf's shares and the history** (on line 1's X1.a, 19 Nov). Built on the core's fields
  as line 1 named them; the corpus's shares are summed in the API from both bases' totals, passed and read of planned.
  **Found by looking:** the first screenshot of the overview under `--public-only` showed the newest milestone's name,
  which named a licensed work: the names are line 1's free text and may name anything. The API now gives no name under
  `--public-only`, which a test holds, and the view says the name is withheld; line 1 was told, so its names can stay
  as they are. **Before this part:** X1.a's float shares in the shelf's totals made `/api/shelf` answer 500 (the model
  read them as integers); line 2's browser checks found it, and line 1 put the one-line fix on main the same hour.
- **B3.a, B4.a, SC1.a, SC2.a** (the operator, 19 Nov). Interrupted once by the operator's account switch: the work stayed
  uncommitted in the worktree and its state was written to line 2's roadmap, then picked up from there. **The ladder:** the
  agreed B2 ranks did not hold with five figure columns more; worked out with the columns' real widths, padding included, the
  knowledge base moved a rung later and the year and format to the last. **Mistakes:** the totals test first picked a value
  the bar rightly disables, where every page is in one state; the bar's browser check scrolled to 700 px, which the shorter
  rows no longer reach, and now takes its place from the page's height; and a test name lost its escaped quote through a
  heredoc a third time, so test text is written with the editor tool only from now on.
- **Y1.a stage D, the polish** (agreed with line 1, 19 Nov; D8.a, D9.a and D11.a its choices). **D2 changed on
  measuring:** the viewer's "one precision per figure column" would have undone the operator's two-significant-digit rule of
  18 Nov, and the headings already stood over their figures; what the viewer saw at 800 px was the runs table overflowing,
  85 px, which ranks fix. **A check that could not go red:** the first runs check passed with the ranks switched off, as
  the free base's runs are short; measured with both bases natively, the overflow came from a long unbroken word in a
  licensed run's command, so the check now adds an invented run as long and was shown failing on it. **Found:** the
  decision numbers the viewer saw on the Prompts view are the core's registry's text, which line 1 keeps: they trace each
  prompt version to its decision.
- **P1.a, the Pages view's facet bar** (the operator, 19 Nov). Measured first: the field words added 3.4 MB and 0.8 s
  natively to a list of 10,224 pages; they stay plain words, readable, rather than numbers into a vocabulary, and the whole
  unfiltered list is kept per export state instead. Drawing every page took 147,000 elements, so the list draws its first
  500. **A probe that lied:** a timing script given the view's address on the command line saw only the page's empty shell
  for five minutes, on the old and the new build alike; the address had not survived the shell, and with it written into
  the script both views drew at once. The bar's counts now stand in English figures ("1,822"), as every count here does.
- **V1.b, every PDF page in a work's list** (the operator, 20 Nov). **A rule changed on measuring:** the handoff said every
  unread page that no Markdown has is served from the text layer; asked of the librarian's own pages (183.7 s to build every
  licensed page), a legacy work's pages the Markdown leaves out are served by nothing, since `with_readings` never falls back
  to that work's text layer, and a text-layer page without text by nothing too. The rule here follows the librarian, and the
  measurement matched it page for page. **Found:** in the worktree a licensed PDF is not found, since `data_paths.locate`
  resolves the export's `_sources/…` against the repository root and not the originals the local configuration names
  (285.a); a licensed page's image has the same gap there. A first fix took the archive by the file's name, against the
  rule that a PDF is the export's `pdf`; a test with an invented licensed work caught it, it was undone, and the question
  went to line 1. The figures were measured in the main tree's layout. Asking for the legacy pages before the PDF was found
  had the tests build the real ones; they are now handed in by `licensed_readings` alone, as the catalog is. The "planned" word first
  stood beside the state mark and sat 2 px below its word, so it moved into the mark's own line, and a browser check holds it
  there (shown failing once at 2 px), as it holds the quiet ink (shown failing once in a status colour). The example figures
  of the handoff were replaced by invented ones in every tracked file, as a count of the licensed collection never stands
  in one (251.a).
- **U1.a, the coverage ladder** (the operator, 20 Nov). **Against B3:** the Pages column and the five state columns
  (ok, ok unjudged, issue, blocked, decided by a person) became one Coverage column; the rarer states left the work's card for
  the coverage card, which holds every state; an issue's served tally (18 Nov) moved there with it; the ranks are now the
  work and its coverage, then the knowledge base and the authors, then year, format and topic. **What serves an unread page,
  refined on measuring:** a file the licensed shelf says the librarian serves not at all now says "nothing served" with the
  shelf's why on every page, and a work whose legacy Markdown names no PDF page is served by that Markdown whole; asked of
  the shelf, a held PDF of such a work had claimed the text layer on nearly every page, where the shelf counts the legacy
  Markdown. **Found:** a lock taken twice hung a probe for ten minutes (the shelf's map asked for the legacy pages inside the
  guard that builds them); the ladder's words held to one line ran the work's record 10 px past a phone's window, shown by
  V1.b's check, and now wrap; the corpus's read level stood against the sections too and showed a corpus read through as
  read in part. **Open with line 1:** the legacy-only works the shelf lists stand in no Sources row, though the corpus
  counts them; an EPUB the librarian does not serve has no section view to open (V2.a); the overview's tiles repeat two of
  the ladder's figures.
- **V2.a, every page reachable** (the operator, 20 Nov), with U1.a's follow-ups (line 1's answers). **Found:** an export a
  test invented read this machine's licensed shelf through `shelf.load`, so the new legacy-only rows put real work keys in a
  failing test's output; each base's shelf is now handed to its store, as the catalog and the legacy pages are. A page's
  image was drawn twice, for its view and its image route (0.6 s each for a scan's page), and is now kept for both. The page's
  own ladder, held to one line per level, left its words 12 characters at 390 px, and a size container without a width folded
  to nothing and hid the text served's fold (a browser check timed out on it); both are fixed and measured. Why search (BM25)
  leaves a page out follows the branches of the core's `page_index.is_structural`, whose constants it takes; a `structural_why`
  in the core would serve both, and is line 1's to decide. The image check was shown failing once, its image refused.
- **C1.b, colour in the meters and a hover delay** (the operator, 20 Nov). Only existing roles: the issue's (error), the
  warning's, the border's ink for the hatching. **Measured first:** the issue's red against the meter's grey fell below the
  colour-blind floor in both themes (dark 7.8 deutan, light 5.3 protan), so the segment got a gap and a taller form before it
  was drawn. The delay is one value, 500 ms on the pointer and none on the keyboard's focus; the unit suite sets it to 0 in
  its setup and one test holds the 500 ms itself, with the timers faked. The browser check reads the colours as drawn against
  the role tokens and the card's wait, and was shown failing once with the segment greyed.
- **One rule for why the search leaves a page out** (line 1, 20 Nov). A page's keyword level now says the core's
  `page_index.structural_why`, which the ranking itself follows (0b8be5e), and line 2's copy of its branches is gone; a page
  the core would rank that the search leaves out all the same says "left out of the ranking", the one case the rule does not
  name. The words changed in one place: "mostly figures", where the copy had said "as a contents page or an index" beside it.
- **The private base in the ladders** (#8, line 1, 20 Nov). Each base's index read apart (`page_ladder.semantic_detail` per
  base, cached per state of its database); whether the private index exists asked of the core alone
  (`retrieval.licensed_index_built`), so every test sets it rather than reading this machine's. Measured over the private base:
  every read PDF counts its chunks, the held works say they were never embedded, and the files the librarian does not serve
  say so too, where they had first said "not in the vector index".
- **One row per work, the card's meters, the issue words, the levels' numbers** (the operator, 20 Nov). **Changed against the
  ask:** the stand-in's page list was to stay reachable from the card, but the card holds data only and lets the pointer through
  (12 Nov: a card left open took a click meant beneath it), so a link there could not be clicked; it stands on a line of the
  work's row instead, the card naming the file and why. **Found:** the fold ran before the legacy-only works were listed, so it
  folded nothing; it now runs after them. The card's value is the view's to draw through a slot of the library's card, its rows
  typed by the view, so the card stays one component. The issue line counts pages, not findings: "12 pages with judge findings".
  The browser check reads the card's segment colour against the issue role and was shown failing once greyed. **The level's
  number and share (L1.a):** computed fields on the rung itself rather than set in `coverage_ladder.py`, so `with_coverage`,
  which replaces the read level's count on a copy, can never serve the share of the count it replaced; a level some but not all
  of the whole reaches is held between 1 and 99 %, so 999 of 1,000 pages never reads as done. The card's rows take a group, a
  caption and an indent from the library's card (`CardRow`), a rule wherever the group changes, and its label is the view's to
  draw as its value is. **Found:** two browser checks counted the open card's meters with the cell's and read a level's share
  with its words; they now look at the cell's meters and the line's words alone. A third, skipped today, still expected the
  issue line's old figure and takes its words now. A browser check holds the card's five meters under each other and its shares'
  right edges in one line; it was shown failing once with the share column given its content's width.
- **A level on two lines, every card inside the window** (the operator, 20 Nov: "teils platzproblem", "tooltips immer im Bild").
  **Found:** the card's levels shared the card's two columns with the states beneath, so the longest state's label set the width
  of the levels' words; the levels now stand in a lead of the card's own (`HoverCard`'s `lead` slot), their words spanning a
  last column that takes what is left, so their length never widens the word's column. The card's `label` and `value` slots of
  the morning went with it, nothing else drawing through them. **Placement by Floating UI** (`@floating-ui/dom`, now a direct
  dependency at the version Reka UI already installs, 0 advisories): `flip` with `bestFit`, `shift`, `size` and `hide`, and
  `autoUpdate` while the card is open, in place of the hand-made rule of 11 Nov, which flipped only where the room above was
  enough and never placed again; a first own rule written this afternoon was dropped for it before it shipped. **Decided:** a
  card that scrolls is the one card that takes the pointer; it waits 300 ms after the pointer leaves its host
  (`HOVER_DELAY.crossMs`), so the pointer can cross the gap into it, and closes when the pointer leaves it; the keyboard reaches
  it by Tab from its host. Every other card still lets the pointer through and closes at once. The unit suite holds what the
  card asks of Floating UI and does with its answer (jsdom draws nothing); the browser holds where it stands. The new browser
  checks were shown failing: against the merged build the card stayed put while its host scrolled and a narrow ladder kept its
  figures beside its meter; on the new build a level's words held to eight characters ran to five lines, and a card without its
  height bound ran out of a 260 px window. **Asked by line 1, answered:** the folded legacy work's title was never a link: a
  work served from the IDE's Markdown alone has no view here (bb2cf9e, "with no view"); its stand-in's page list is the link on
  its row.
- **Level 3 renamed "semantic search"** (C2.a, 20 Nov). The word changed in the `Level` and `PageLevel` literals, so the schema
  and the generated types with it; no deep link and no Pages filter keys on a level's word (only read and checked carry a
  filter, by state), and no stored setting does. The chapter's earlier paragraphs that name the level take the new word. Beyond
  the ask, the level's legend line now says how its pieces are cut, in line 1's words, since the name alone no longer says
  chunks.
- **Repeat work out of the requests** (line 1, 20 Nov: the Sources list, a work's page and a page's view slower again).
  **Found:** line 1's profile of the list counted an EPUB parsed on every call; it was the background cut every process makes
  once after a start (29 s natively), still running in the calls that followed the start, and taking the interpreter from them;
  each EPUB's cut was kept by its file's stamp already and was never made twice. What the calls did repeat: the export index's
  stamp asked twice for every work, each work's rows sorted out of all of them and counted again, the shelf's store opened (a
  git call) and its file read, and on a page's view the whole PDF opened to count one page's characters (0.37 s of 0.86 s in the
  container) and the image sent compared with a fresh render. **Built:** `stamps.stamp` (modification time and size) looked at
  once a request through a plain ASGI middleware and a context variable, which a sync route's worker thread inherits; outside a
  request every call looks again. The shelf is kept by its file's stamp and the loader that read it, so a test that hands in its
  own `shelf.load` is never answered with the shelf read before (found when the full suite failed one such test in its order and
  passed it alone). The PDF the page view read last stays open from its bytes, not its file, so no handle locks the file on
  Windows. **Shown failing:** with the caches set aside, the counting tests failed on every work's readings counted again and
  the index's stamp asked ten times a call. The container's figures after the merge are measured once line 1 has restarted it.
- **The start's warm-up, in the order a person meets the views** (line 1, 20 Nov). **Found:** a work's first page after its page
  list took 18 s because the first page of a base reads that base's vector index by page whole (`semantic_detail`, 6 s of its
  own in the container), which every page shares and the old warm-up left out, with the EPUB cut a list had started running
  beside it; the old warm-up also left out each work's pages without a reading (1.3 s for a work's first list once all else was
  warm) and cut the EPUBs only after the search index, 136 s in the container. **Built:** `app.warm_steps` names the steps in
  order and `app.run_warm` runs them one after another, each in a request's span of stamps, a failing one logged and passed;
  while it runs, a list's own call to cut the EPUBs ahead leaves them to it (`epub_works.held`). It starts once every route
  stands, so it calls the Sources list and the overview as a request would. **Measured** in a throwaway container from the
  image, the main tree mounted and the worktree's source read-only over it: a measuring script fed on stdin made the search's
  process pool fail to start its workers and build in one process (130 to 190 s), so it runs as a file. During the warm-up every
  call answered 200, the page list at 10.9 s while it built the legacy pages itself; after it, each first call under a second.
- **A work in its editions** (E1.a, 20 Nov). The view reads the core's shelf rows alone (`work_editions`): a family from
  whichever of its rows carries it, an edition's row by its key as its work key, its source id or its file's stem, and from the
  row where its record opens (an EPUB by its librarian's key, a PDF by its source id). **Found and sent to line 1:** the served
  row of one family carried no family, its work key a legacy work's and so not the edition's key; line 1 matched rows by work
  key or stem (245b2c5), and the view, which finds a row by any of the three, never depended on it. The fold runs after the
  stand-ins', so a work stands once over both. A kept edition's words are the ladder's (`coverage_ladder.kept_words`); the
  warning outline of a kept file that serves no text went with them, a decided case. **Built for one look:** the edition's mark
  and word (● served, ○ kept) are the same in the card and in the bar; the bar and the trail are components of their own, used
  by the page list and the EPUB view alike, and a kept edition's route is one function (`edition_route`). The card's rows took a
  key of index and label, since two kept editions are both "○ kept". **Beyond the ask:** the EPUB view now shows the ladder a
  PDF's record shows, so a kept EPUB's record can say it is kept. **Not changed:** a page's and a section's own ladders on a
  kept edition still say why the keyword search leaves them out in the search's words. The browser check gives the API's
  answers, invented, the fold held by the API's tests; it was shown failing with the possible edition's line greyed.
- **A kept edition's page and section ladders** (line 1, 20 Nov: free hits keep their year; a kept edition's pages say "kept"
  for consistency with its record). `page_ladder.kept_of` reads the served edition's words from the work's shelf row
  (`work_editions.served_named`), through one lookup of the row that `held_of` now shares (`shelf_row`); `keyword` takes it
  before every other case, so a kept page never reads "not built" or the search's reason for leaving it out. No model changed,
  so the schema and the built UI stand as they were.
- **A page's coverage in one line, "as served", its chunks** (the operator, 21 Nov; W4). `PageRung.short` gives each level's
  shortest words and `PageLadder.served_by` what serves the page in its reading's place, so the line and the fold are the API's
  words; the fold is `PageLadderLines`' own, so a page's and a section's ladders fold alike in all four views. `Block.served` is
  the core's `block_text` for a block `quotable_text` keeps. `page_chunks` reads each base's index read-only, as `html_works`
  does: the page's chunks by `pdf_page` and `pdf_page_end`, each placed in its section's text by `html_works.placed`, the page
  found in that section by its whole text or, where a heading starts a section mid page (free finance p. 470), by where the two
  meet over at least sixteen characters, each case checked word for word. **Found:** a first anchor of sixty characters missed a
  page's beginning that ended a section in fewer; the mode's head counted the chunk run on from the page before beside those
  that begin on the page, so it said four where the ladder said three, and now says the ladder's count, the run-on chunk on its
  own line. **Found by a browser check:** with the coverage folded the record is shorter, the original's pane (85 % of the
  window) reached past the window's foot, and the frame of a block low on Kelly p. 7 stood there, out of the window and beyond
  the pane's own scroll; the pane is now as tall as the window shows beneath its top, measured as the window scrolls. The quoted
  tab's store and client went with it; its API route stays. The browser check of the mode was shown failing with the greying
  undone.
- **The verdict panel, ✦ fill with AI** (V1.a, W2.a, F1.a, 21 Nov). `VerdictPanel` takes the inline form's fields, rules
  (`verdict_rules`) and route unchanged; only where it stands changed, and the inline form is gone. It asks before a change is
  lost inside itself, never in a browser dialog, so it can be tested and answered by keyboard. The route `POST
  /api/verdict/propose` is guarded as the verdict's (this machine's host and pages, `--allow-verdicts`) and takes the judge's
  findings on the block from the page's own data, void ones left out, never from the browser; the core's `Refused` answers 409
  with its reason; the form says before any ask whether a version is active (`VerdictForm.propose`). The word diff is difflib's
  matcher over words and the spaces between them, in the API. **Changed on the way:** the first version proposed the correction
  alone and had a "use" step; F1.a made it fill the whole form, and the step went. "Give a verdict" opens on the page as a
  whole, as line 1 asked; the block of the first finding is a ⚖ away. **Found by the browser check:** measured while it slid in,
  the panel stood past the window's edge, so the check waits for it to arrive; the lines' value column took up to 100 characters
  and ran past the panel's edge, and now takes what the panel leaves. The layout check holds the page's boxes and height unmoved
  and a point left of the panel the page's own; it was shown failing with the panel set in the page's flow (the page grew from
  1,180 to 1,881 px). The guard over licensed text in tracked files reads every tracked file and so fails on the inline form's
  file until its deletion is committed; its own check, run over every tracked file still there and every new one, found none
  over its harmless run.
- **H1.a's fixed rows, chunk first, the BM25 wording** (21 Nov). `FoldSection` takes a `label` (the row's label in the record's
  one column, `RecordRows`, 17 characters: "Reading History:" in bold) and `plain` (the same row with nothing to fold open, its
  mark's place kept empty), so the record's rows are the one fold of every view and no component of their own; `LabelledLines`
  stays for the lines inside a fold. The API adds `PageDetail.check_said`, `said_of`'s sentence in the Check line's words, None
  where a person's verdict settled the page, whose mark in the same line says it; `said` stays for the API's other readers. The
  route's hover card went: its parts fold open beneath its line. A section's record says none in every row but its coverage: the
  API holds no check, route or reading of a section. `page_chunks` answers in groups: each chunk placed by its text as before;
  each quoted block a span of the page's quoted text, a chunk holding of it what the two spans share; a run shared where another
  placed chunk holds it too; the quoted text no placed chunk holds listed apart, every quoted block where the page has no chunk.
  `readings.counted_as` groups thousands now and serves both modules. The keyword level's words while the search is built and
  the served text's why are two constants now (`NOT_BUILT`, `SERVED_WAITS`). **Found on the way:** the readable view's raw text
  stood beneath it whenever "as served" was off, since the raw `<pre>`'s `v-else` had come to hang on the paragraph that said
  where the last chunk ran on (W4); the paragraph went, and a browser check holds the readable view alone, its control the raw
  text found on "raw". **Found by the browser checks:** the new check of the rows' places failed on its first run, the Lab and
  the Details 8 px lower on a read page, where the history and the Lab kept the margin they had as sections of their own; a
  row's fold set its content at its line's x, not one step right of it as every fold's (179); a label column of 17 characters
  left a work's coverage too little at 390 px and the page scrolled sideways, so a narrow record sets each label above its line
  (a container query on `RecordRows`); and the longer "BM25 being built after a start" put the folded coverage's words whole
  beneath its marks, 14 px below the row's label, since marks and words were flex items; they are one run of text now. **Shown
  failing:** the rows' places with the Lab's row taken out; the never-quoted block with an answer that put the description into
  a chunk; a row's words set 6 px below its label's. Measured on three free pages: the chunks route 27 to 47 ms; finance p. 469
  four chunks, fifteen blocks, none cut by a border; a page served from its text layer places none of its chunks in its reading,
  and offers no "as served".
- **The Librarian in place of the chat** (L1.a, 21 Nov). `librarian.py` holds the page's one session (`LibrarianService`: opened
  under a lock on the first call; a librarian found down asked again no sooner than 5 s on; a call that fails on its way closes
  the session, so the next opens it anew). `tool_of` parts an input schema into typed fields (an optional argument's `anyOf`
  with null, an enum a choice, an array a list), the view's own defaults beside the server's (`VIEW_DEFAULTS`: the router off)
  and the fields it folds (`FOLDED`). `cost_of` takes the description's own words for cost and time, a fixed list of phrases in
  the order the description says them, "free" not where it names the free base. `shaped` gives each tool's parts beside the
  answer as it came, the image's pixels replaced there by their size; a page image is drawn from png or jpeg and base64 alone; a
  `view_url` becomes this view's route (the part after its '#', a page, section or article route alone), so a link opens here
  whatever address the server names. The guard moved into `local_only` (the chat's host check, the verdict's origin check),
  which the verdict routes and the call both take. The view: `LibrarianView`, `SchemaForm` with `SchemaField`, `LibrarianAnswer`
  with `HitCards`, `LibrarianWorks` and `ContentsTree`; `librarian_form.ts` turns a form into arguments, the address and back: a
  value the server takes by default is left out, a field whose form starts other than the server would is always sent, the
  router either way, so the address opens its form as it was. Gone: the chat's route, service and models (`chat.py`), `GET
  /api/search` and its models, `ChatView`, `ChatTurn`, `ChatServerAnswer`, the chat's and the search's stores, `SearchView`,
  `render_markdown` and the `markdown-it` package, which only the chat's Markdown used. **Found on the way:** the core's
  `SearchClient` leaves its thread's loop running where a session fails to open, so each attempt on a librarian that is down
  would leave one behind; the service asks again no sooner than 5 s on, and line 1 was told. Checked against the running
  librarian with the free tools before the gates: every answer shaped without an error, the server's own error for 0 hits among
  them. **Shown failing:** the tabs under the pointer with a line set before them; the router passed through ticked (true)
  beside unticked (false); the call made once for its address and once more on F5, none for a tab alone. Never the real
  librarian in a test: a fake client in pytest, mocks in Vitest, the browser's own fixtures in the browser check, whose app
  starts with `--no-librarian`.
- **The search tools' names in the view** (21 Nov, line 1 on the standing rule). `LibrarianTool.label`, from `librarian.LABELS`,
  gives a tab its words; the name stays the code name, which the tab's head shows and the address carries. The changed browser
  check was shown failing against the build before it (the tabs said `search` and `semantic_search`).
- **The running mark, the toast, the export followed** (21 Nov, the operator on cloud patterns; E1.a). `RunningMark` (a ring
  that turns, still under reduced motion, its words counting up) and `use_elapsed` (the seconds from a start, so a panel opened
  again counts on): the library had a moving line for a view that loads, none for a control that runs. The proposal still out is
  kept in the verdict store by its block (`propose`, `proposing`), not in the panel, so a close does not drop it and a panel
  opened again waits on the same call. The toast: `toast_store` (each time held while pointed at or focused, run on from where
  it stood) and `AppToasts`, the app's one place for a "done", a polite status. The export is followed by one poll in the
  verdict store (`follow`, every 2 s while one runs or waits), which the header's `ExportBadge`, the page's reload and the
  toast's line all read; `followExport` waits on it by a watch. A verdict waits where the pipeline database holds it and the
  export does not (`verdicts.waiting_in`, by page, time, verdict and block, the core's `human_verdicts` read through its public
  function); `ExportStatus` takes the core's `started_at` and `expected_seconds` and the waiting verdicts, `PageDetail.waiting`
  a page's own. **Found by the browser checks:** the toast at the window's very top covered the header's hourglass it points a
  person to, so it stands beneath the header (`--frame-header-height`, measured); the frame now asks for the verdict form once
  on every view, so a check's mocks go in before the app first loads; and loading the form moved a base's `finished` from 0 to
  its count, which read as an export ended, so the page watches the base's own status, unknown until loaded. **Shown failing:**
  the mark turning beside still under reduced motion; a toast gone with the pointer away beside one held; both checks failed on
  their first runs over the faults above. On the way, the check that the coverage's fold stays open over a reload waits for the
  store before it reloads, as the details' check does: it reloaded once before `toggle` had stored the choice.
- **The free catalog's series** (22 Nov, line 1). `CatalogSource` takes `series` as `Work` has it (`readings.Series`); pydantic
  left the free catalog's key out silently, so `/api/works` answered 200 with no series for a free work. A test holds an
  invented entry with a series and one without. Seen in the browser: the facet lists the three, their parts under each heading
  in order. Four Sources checks took the free list as flat, or the invented series as the only one: they open every series first
  (`openSeries`, the first closed heading each time) or name the invented series' heading; one measured the bar while opening
  the last heading had scrolled the page, and now measures it from the top.
- **A free PDF not read yet, gzip, the warm-up split** (8.a, 9.a, 22 Nov). The free store takes the free catalog
  (`free_catalog`, `readings.FREE_CATALOG`, which `sources.CATALOG` now names): `free_entries` lists its PDFs the export has no
  pages of (`files[0].path`), and `entry_work` builds a work from one, its search key the shelf's, so `pages`, `unread_page`,
  the image and `warm_unread` serve it as a licensed entry's; `app.free_work` sets `page_list` and "not read page by page". No
  core change: the catalog names each PDF. Measured for 9.a first: the list 0.084 s warm in the server, 0.18 s in the browser
  for 298 KB, drawn in 20 ms (84 rows, 2,470 nodes); the first call after a start 2.08 s (the plain list 0.8 s, coverage 1.0 s,
  readings 0.25 s), the overview 6.6 s; not the garbage collector (tested with the search index in memory, unchanged by
  `gc.freeze()`). So no virtualisation and no second call for coverage (line 1's choice (b)): `warm_steps` takes the Sources
  list and the overview as two steps, and `GZipMiddleware` (level 6; Starlette leaves PNG and JPEG alone) packs the list's 298
  KB to 28 KB. The browser check of 8.a takes the free data's own PDF without readings and was shown failing with a list that
  opened nothing (`page_list` false); an older test meant only licensed works where it said no work is "not read".
- **The search index from the index database** (issue #10, part E, 22 Nov). `search_hits.build_service` hands over to
  `search_server.build_service(public_only, read=read_pages)`: the database where `database.librarian_reads` says so, else
  files, read in a process of their own as before (`read_pages` looked up at the call, so a test's reader reaches it). The view
  reads only `by_page`, `works` and `ranked_pages()`, never `index.pages`, which the database's index holds as a dict.
  `Search.ready()` calls `refresh()` (one generation query) at most every `REFRESH_SECONDS` (5) for a service with a
  `database_url`, with an injectable clock for the test; a failure is printed once and the index loaded last serves on. The gate
  ran before the switch, in a throwaway container on the compose network over the main tree's data with this branch's code:
  works by key and eight fields, every page key, every page's fields, its text by digest and its keyword rung, and twenty
  searches. The page keys and the hits held; three differences were the database's and went to line 1 (an edition kept after the
  last write still ranked there, some text-layer pages with other text, the legacy pages' paths absolute on the importing host).
  The view takes the database all the same: it is what the librarian serves, and a re-import reaches the view through
  `refresh()` without a restart. Warm-up measured one after the other in a throwaway container: the search step 202.3 s to 2.2
  s, the whole 472 s to 265 s.
- **The free plan** (line 1's FIX note, 22 Nov). `unread_pages.free_planned_pages` wraps the core's
  `reading_cells.free_planned_pages`, kept once per stamp of the corpus cell's page list and of the session's free list (the
  free PDFs are unmodified copies, so their stamps are not asked), and `knowledge_bases` hands it to the free store as
  `planned`, as `licensed_readings` hands the licensed store its own. The docstrings that said a free PDF is read whole now say
  which free pages are planned. Gate: the Sources view, from the list to a FIX volume's page list (`fix_latest_ep284_trade`),
  against the running service and this branch on port 8031: "every one of them is planned" and all 124 rows marked planned
  before; the line ending at the text layer and no row planned after. Tests: the wrapper asked once per state of its two lists;
  an invented NoDerivatives PDF with no page planned beside a work read whole whose every unread page is; and on the real data
  (markers `corpus` and `readings`) the FIX volume with none planned and an OpenStax page in the plan.
- **The text layers kept on disk** (line 1's 1.d, 22 Nov). `unread_pages.TextLayers` keeps, per file, the PDF's stamp
  (`stamps.stamp`: modified in nanoseconds and size, the same natively and through the container's mount), its page count and
  the pages asked so far with and without a text layer; a question about a page it does not know opens the PDF and adds it,
  outside the lock. It is written whole through `<name>.<pid>.part` and `os.replace` after each PDF that taught something new,
  and a damaged file is built anew. `unread_rows` takes it as `layers` and asks only where the text layer may serve (no legacy
  Markdown, served at all); without one it asks the PDF as before. `knowledge_bases(keep_text_layers=warm_search)` gives each
  base its file (`text_layers_file`: the free and the licensed working folders), so only the start command's app reads or writes
  them; the 8.a test's stand-in for `knowledge_bases` took the new keyword. Checked against `diskcache` and `joblib.Memory`,
  which key by arguments and cannot tell that a PDF changed nor add later pages to an entry. Tests: kept and read back with the
  PDF closed to it, a page not asked before added, a changed PDF and a damaged file asked anew; a work's unread rows the same
  from kept layers as from the PDF; only the start command's app keeps them. Measured one run after the other in a throwaway
  container: the licensed step 187.8 s, 209.1 s building, 0.9 s after; the free 30.8 s and 1.2 s; the whole from 265 s to 61 s.
  The run that built the files shared the host with a search assembled from files (the database's address left out of that run),
  so its whole is not compared; two later runs, the files complete, took 62 s and 61 s.
- **A page without a reading, its image at a read page's size** (the operator, 23 Nov). `UnreadPage` moves out of `RecordZone`
  to stand where `AnalysisSection` stands, in the wide container, and takes `width: calc((100% - var(--space-md)) / 2)` with
  `margin-inline: auto`: one of `.side-by-side`'s two columns, the same breakpoint (900 px) giving the whole width; `box-sizing:
  border-box` keeps its border inside that width. Measured before, on the running service: a read page's image column 936 px at
  2,560 px and 676 px at 1,400 px; an unread page's image at its own 836 px either way, at the record's left edge, or as wide as
  the record (1,240 px for a FIX page at 1,400 px). After: the column's widths, off centre by 0.0 px, on both example pages and
  a free unread page. The browser check reads a free read page's `.original` column and a free unread page's image at 1,400 and
  2,560 px, its width no more than the column's and no less than nine tenths of it, its centre within a pixel of the content's;
  shown failing first on the old build (1,240 px against a 676 px column). A blocked or refused page has a reading row (`read`),
  so the Analysis pane shows its image already; no full-size view, since none exists for an image anywhere in the view.
- **A book's companion code** (#12, the operator's 3.a, 23 Nov). `code_works` builds a code work (`toc` joined with
  `code_catalog(work, hits=CATALOG_HITS)` by page; `categories` the core's, the most first; each folder's count) and a file
  (`open_page`, its record, its neighbours and their names) from the view's search service alone; the routes
  `/api/{knowledge_base}/code/{work}` and `/files/{label:path}` answer 404 before building anything for a base this app does not
  serve. Sources: `CatalogEntry` takes `code_language` and `companion_of`, a code entry leaves the unread rows, and `with_code`
  folds a `CodePart` into the book's row, the book found by the key the search names it by through the shelf's row or the
  export's `work` (the catalog's `companion_of` is a work key, a row's id a source id: the first test, with the source id,
  listed the book twice); a book not listed keeps the code as a row of its own. Librarian: `code_catalog` after `search_works`
  in `TOOL_ORDER`, `VIEW_ROUTE` takes `/code/` and `?lines=a-b`, `CodeCatalog` of `CatalogUnit`s, and `kind`, `code_language`
  and `lines` on a hit and an opened page; `kind` itself came with the tool's schema. Frontend: the raw reading's numbered
  `<pre>` became `NumberedText` (221.a, one look), its classes `numbered-text`, `numbered-line` and `data-mark`, the checks'
  selectors moved with them; `CodeUnitTable` for the code work's folds and the catalog's answer, `CodeWorkView`, `CodePageView`,
  `code_store`, `recordRoute` beside `editionRoute`; the routes `#/:kb(licensed)/code/:work` and `/:label`, the label one
  encoded segment as the librarian's `view_url` gives it. `PagerLinks`' empty place stood 10 px lower than a box with a word (no
  line of its own, centred in the row), in every pager; it takes a zero-width character now, found by the new check on a code
  work's last file. The three new browser checks run over an invented code work the API is mocked with (the checks' server is
  --public-only) and were shown failing: the pager on the old `PagerLinks`, the range scrolled to line 1, the Sources part
  hidden. Python tests over the core's own service built from invented files and an invented catalog; the real EPUBs kept out of
  the Sources test. Looked at on the real data in a throwaway container: the code folded under its book, every file with a
  catalog entry, a file's range marked and in view, `code_catalog` on the Librarian page opening its files here; screenshots of
  invented code only.
- **`diagnostics` by the view's default** (#14, 23 Nov). `VIEW_DEFAULTS['semantic_search']` takes `diagnostics: True` beside
  `router: False`: the field keeps the server's own default (`false`) as `server_default`, and the form starts ticked, since the
  page's `HitCard`s draw the snippet a compact answer leaves out; the candidate lists and the citation stand only in the raw
  answer. `WorkRow.pages_kept` and its words in `LibrarianWorks` beside "kept for". `corpus` (semantic_search, works), `kind`
  (works) and `under` (toc) came through the schema-built forms with no code. Tests: the form's default and the server's beside
  it, a kept edition's pages in the shaped answer and in the table. Checked against the running librarian in a throwaway
  container: the field ticked, 10 of 10 hits with a snippet with it, none without, the answer's characters halved.
- **Every work names its language** (#11, 23 Nov). `language` on `CatalogSource` (the free catalog), `CatalogEntry` (the
  licensed one) and `sources.Work`; `CATALOG_FIELDS` takes it, so a licensed row and a stand-in's fill carry it with the rest.
  The heads: `WorkPages`, `HtmlWork` and `EpubWork` take it from the catalog (`language_of`, the free catalog by id or the
  licensed one by the work's id; an EPUB by its file), `CodeWork` from the search service's work. One `LanguageMark` beside
  every `KnowledgeBaseMark` that stands for a work, the code with a card, and the `language` facet after the knowledge base's.
  No name table: the code is what the catalog writes, and a name would be a list of the view's own. Tests over invented catalogs
  in English and German and a work that names none: the rows, a head, the facet's counts and its filtering; the browser check
  said one free work was German, a moment, and was shown failing on the build before (`language` absent). On the real data every
  row names one, and every kind of head says it.
- **#15 on the Librarian page and the ladder** (23 Nov). `CallHead` takes `keywords_said` and `keywords_missing` (from
  `keywords_covered`), `per_page_said` and `generation_said` (`index_generation`); `HitCard` `more_on_page_said` and
  `keywords_found`; `WorkRow.kept_because`; `Contents.other_matches`; `CodeCatalog.match`. The new fields default to None, so an
  answer without them, and every test fixture written before, stays as it was; the generated types made a field with a list
  default required, which the first build refused. The words are the API's ("+2 more passages on this page", "2 of 3 keywords on
  the hits: none holds …"); the per_page switch came with the schema and keeps the server's default, as a client gets it.
  `page_ladder.keyword` asks `page_index.contents_why(page.words)` after `structural_why` and before its fallback. Checked
  against the running librarian: every shaped part equal to the raw answer it came from (keywords on each hit, the head's
  coverage, the generation, the passages counted, the catalog's match, the kept editions' reasons, the contents' other matches),
  and per_page false showing none of the per-page words. Over the real index, the ladder's reasons for every unranked page: "a
  table of contents" where the fallback stood before, which no page gives any more.
- **A page's form, #18** (27 Nov). `page_form.py` builds `PageForm` (readings, lab, verdicts, their counts; each row's kind,
  result, verdict words, recall, `show_why_not` and card rows) from the parsed attempts and people by their fields alone, so it
  needs no import of `readings`; `PageDetail.form` carries it. `PageForm.vue` replaces the Reading History and Lab folds and
  their helpers in `PageView` (`readingOf`, the history's and the Lab's words, their CSS). `recall()` takes a reading key
  alone. `VerdictRequest.answers_judgement`, `Option.short`, `VerdictForm.promote_reasons`, `POST /api/verdict/promote`;
  `PromptVersion.origin`, read from `page_judge.prompt_origins()`. What went wrong on the way: the generated types made every
  new field with a default required, which broke every fixture written before, so the new optional fields default to None; a
  judgement's state followed its verdict word, so an ok with a minor finding showed in the error role, now its outcome; the Lab
  said "counts" until the core's export set `counts` false there, after which `judge_role` reads `counts` alone; the recall's
  head called a test reading a prototype (`read_by`); a reading no judge had judged could not be shown until every reading row
  had its own show; decision 25 first counted only findings that were not void, so judge/2 on finance p. 5, whose one finding
  is void, came out greyed, though its recall draws that finding beneath b12: the browser check found it, and a void finding
  now counts. Main's unpushed history was rewritten under the worktree mid-phase (line 1); `git reset --mixed main`, and the
  core's nine files taken from main, none of them line 2's. The tests left the old folds: six tests of the history and Lab
  and three of the readings over time went, replaced by `page_form.test.ts`; the browser checks read the API's form. The full
  browser run found two more: the prompts check counted no tab for the versions without text (now it does), and the runs table
  ran 35 px past its box at 800 px, not from #18 but from today's data: a free run's command held a work's key of 62
  characters with no place to break, so `.command` takes `overflow-wrap: anywhere` in the runs view and in the overview.
- **Decisions 26 and 27.a** (27 Nov). `page_form.shown_verdicts` (with `judgement_standing_for`, `judge_row`, `person_row`)
  replaces `verdict_rows`; `ShownVerdicts` (said, recalled, count, rows) is `PageForm.verdicts` and `Recalled.verdicts`.
  `VerdictRow` loses `in_lab` (the caption names the reading) and gains `recall`, and its `standing_said` reads standing,
  replaced or not counted. On the served reading a person's standing is the core's; on a recalled one it is the latest per
  block over that reading's own verdicts (the core's rule, #17), since the export's `standing` is relative to the served
  reading. `AnalysisSection` gains a `lead` slot for the way back; the page head's recall chip and its CSS went. What went
  wrong: the new browser check first measured the way back while the recall was still loading, the heading's words the
  placeholder in every round, so the way back held its place for no reason; it now waits for the recall's own words and
  counts that they varied.
- **Decision 30.a** (27 Nov). `reload_standing.ts` (`navigationType`, `standingOnReload`, `returnStandingOnReload`), set on
  the router once; `AppButton` takes a fourth shape, `overlay` (dashed in the annotation role, the weight of normal text in a
  heading); the icon `show-standing` (↺). The way back is an `AppButton` now, pushing the standing address. The new browser
  check was written first and shown failing on the build before, in both halves (the way back a link with no border; the
  recall surviving F5, run apart in a throwaway spec). It then found the compact button making the analysis head line 6 px
  taller (20.4 to 26.4), so the image and the reading moved as a recall began: the button's padding and border now reach
  into the space around the line (`margin-block`), and the check holds the panes' offset within a pixel, shown red at 6 px
  before the fix. In the full run the check counted the Verdicts tab's frame before the recall had come (the way back
  stands from the address alone, the tab's frame from the recall's answer); it passed alone and failed among the others,
  and now waits for the recall's own words before it counts, as the way back's check does. A full run also found an older
  check racing its image: "every page opens, read or not" read an unread page's `naturalWidth` as soon as the frame stood,
  before the image had arrived, and now waits for it to be drawn.
- **Decisions 29.d, 31.a to 39.a** (27 Nov).
  - `page_form`:
    - `judge_word` (the result that counts, and `overruled`);
    - `finding_reason`, `finding_blocks`;
    - `STRUCK`;
    - `moment`, `superseded_at`, `then_of`, `at_then`, `latest_per_block`;
    - `TRIAL`;
    - `reading_row(trials=)`;
    - `shown_verdicts(judgement=)` in three branches: the standing view, a trial, and as then.
  - `ShownVerdicts` takes `said_at`, `why_not` and a `count` that may be None. `VerdictRow` takes `recalled`, `overruled`,
    `judge_said`, and `standing_said` standing, recalled or counted then. `FormVerdict` takes `overruled`, and
    `HoverRow` takes `at`.
  - `readings`:
    - `reading_said` and the new `recall_said`;
    - the recall cuts the people on its reading to the moment before it builds its blocks, a verdict archived only
      later taken as not archived, and hands the parsed judgement to `shown_verdicts`;
    - `FindingsAt.said` is "struck by code".
  - The view:
    - `CardRow.at` and `HoverCard` say a time;
    - `PageForm` keeps its folds per tab, since a pipeline reading stands in Readings and in the Lab;
    - the greyed Verdicts tab is a disabled button in a card, and a trial's recall moves the view to the Lab;
    - `FindingList`'s and the errors view's "void" words are "struck".
  - What went wrong:
    - The recall's line called the served reading "served before": the export's attempt carries no `shown`, so the
      recall now takes it from the parsed attempt.
    - The new browser check's recall links were looked for by their encoded id, while the router keeps the colons and
      the slash as they are.
    - The way back's check saw a move of 77 px as its recalls crossed tabs: the form above is as tall as its tab, which
      moves the whole analysis. The check now measures the way back within the analysis, where it is meant to hold.
- **Decisions 41.a and 42.a** (27 Nov). `FormReading.served_said` ("served" on the served reading) and
  `FormReading.show_why_not` from `reading_why_not` (the first judge beneath it with an active show, newest first, by its
  version); the view's greyed reading show is `show-reading-off`, a disabled link in a card, as decision 25's. Three older
  browser checks clicked reading 1's show, greyed now: the recall check reaches that reading by its address instead,
  which a recall keeps; the way back's check takes every active way in, a judge's on reading 1 among them, its fold
  opened first; the Lab reading check takes only a reading whose show is active.
- **Decision 43.a** (27 Nov). `PageView.showBlock` scrolls the analysis into view (`block: 'start'`, as the recall does),
  then the block in its column (`scrollToBlock`), then the frame in the image pane (`boxIntoPane`, now its own function and
  called on every click, not only on a new frame), and sets `flashing` for 900 ms. The attribute `data-flash` is taken
  away, a layout forced (`offsetWidth`) and set again, so a second click restarts the animation. `ReadingBlocks` takes
  `flash`. The keyframes `block-flash` are a box-shadow in the accent (scoped by the build, so the check matches the
  name's start); with reduced motion the frame's `outline-width` is 4 px and the reading's edge 5 px for the moment. The
  browser check was written first and red on the build before. Its first measure, the analysis's top within 40 px, could
  not hold on finance p. 5, where the page ends 91 px short of the analysis for show as for a block link. It now accepts
  the window as far as the page goes. The full run then found the older check of the head's findings line asserting the
  window still (the rule of 4 Nov); 43.a names every `data-jump`, so that check now asserts the window at the analysis,
  marked → now. The same full run had one Python test red for a moment, a section of the private search index (the
  ladder's keyword rung), green on its rerun and in the full rerun: the index on this machine was being written.
- **Decisions 45.a and 46.a** (28 Nov).
  - `readings.with_replaced`, after `with_corrections`, in the page and in the recall: a block's people newest first, as
    copies, `replaced_said` "replaced" on every one that applies and stands no more (`latest_standing` gives the one that
    does).
  - `FindingList`'s verdict head is label, moment (`HumanTime`), "replaced" where said. The note, the correction and the
    assessment are indented a step beneath.
  - `page_form.changed_since` (a verdict given, or archived, after the moment, on that reading) and `SAME_AS_NOW`, set by
    `reading_row` on the served reading's standing judgement where decision 25 leaves its show active.
  - What went wrong: two Python tests built their cases wrongly.
    - One picked the last row of a fold that now runs newest first.
    - The older decision 25 test meant "a judge with findings keeps its show" on a page with no person, where 46.a now
      greys it; it now gives that page a later verdict.
  - Free pages whose standing judge's moment is now: two among the free pages with findings (accounting p. 360, finance
    p. 229). None among the free issues, each of which a person has judged.
  - Two older browser checks held a person's label beneath a block to "A person's verdict:"; they take its moment now.
- **Decision 47.a** (28 Nov).
  - `FormVerdict.verdict_said` is one word, and `FormVerdict.reason_said` is the judge's `finding_reason` or the person's
    reason.
  - `result_of` returns the reading's word and its reason; `FormReading.reason_said` holds the reason.
  - `PageForm` gains a Reason column (colspans 8), with widths 8 · 8 · 11 · 7 · 11 · 7.5 · rest · 7 rem.
  - The first parting gave Reason 176 px at 1280 px, so "wrong word, struck by code" wrapped. A probe then found a time of
    13 characters ("12 Nov, 12:49") wrapping at 7rem. Both were measured by the rows' heights; a count of text rects per
    cell had been fooled by the icons.
