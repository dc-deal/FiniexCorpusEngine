# Protocol: phase 5, verified pages into the chat's index

The record of how this phase came about, mistakes included.

## 2026-11-04

- **Plan and gates first** (commit 5a86c5e), before any code of the phase.
- **Pages from readings, stitched across pages** (commit 6ca700f). Measured offline, before any build that spends:
  - every formula, table and code block of a served reading reached a chunk (2,115 of 2,115);
  - no chunk without a route; 1,295 chunks span a page boundary; a dry run of the build makes 8,567 chunks.
  - The join rule for text-layer pages, checked against the reader's own `cont=prev` marks, finds about 70 % of the joins the
    reader marked. A reader's mark therefore decides wherever a reading is served, and the rule only between text-layer pages.
  - Pages missing from the sections although they lie after the first outline entry: 29 in the finance book (among them
    pages 2 to 13), 23 in the accounting book (among them 494, 602, 650 and 794), pages 14 and 15 of the Kelly article. Not
    examined yet.
- **Mistake in a test:** the first fixture for a chunk that spans a page boundary did not span one. A stitched fixture
  replaced it.
- **The free knowledge base alone** (decision 81.a): the search server starts with `--public-only` (commit cd06a80), the
  diagnostics app likewise (commit d40c640), so the recorded review cannot show a licensed page.
- **The knowledge base is the first key of every export row** (decision 80.a), and the licensed readings have an export of their
  own, in the same shape, local only. Free rows gained three keys (`knowledge_base`, `printed_label`, `error_message`) and the
  index a list of its works; 1,652 of 1,652 rows are otherwise unchanged.
- **Mistake caught before the commit:** the first version read every check report that covers a cell. An older report of 3 Nov
  over two cells at once, read after the current one, put one free page (accounting, PDF page 747) back from `blocked`
  (refused) into the bin. Found by comparing the new export with the tracked one row by row. Each cell's own report is read
  now, and a test pins it (commit 70fa19d).
- **The source's own order** (decision 84.a): the diagnostics frontend asked for a unit to group a work's pages by, for every
  medium. The PDF loader now cuts its sections and the outline from one function, so the two cannot disagree. Checked before
  the commit on all four free PDFs: the old and the new code give identical sections (18, 44, 301 and 307), and the pages
  with indexed units are exactly the pages the sections touch. The outline has 24, 44, 304 and 309 units. Cutting the
  accounting book takes 55 s, so the export keeps each outline in the store under a key of the loader's version, the PDF's
  bytes and each page's route and text, and cuts only a PDF whose inputs changed.
- **Seen in the outline,** the finance book's 29 pages missing from the sections after its first outline entry:
  - its trailing "Blank Page" entry points to page 2 and, sorted into reading order, covers pages 2 to 6 as back matter;
  - "Contents" follows on page 7, and its pages 8 to 14 hold no quotable text, since the reader classes contents lines as
    contents entries, which are never quoted;
  - the other 16 are nine single pages through the book (78, 112, 140, 174, 290, 360, 454, 536, 566) and the last seven
    (623 to 629), still to be examined.
- **The missing pages examined, all four free PDFs** (54 pages after each first outline entry): 20 lie in back matter
  (index, contents, references, a data statement, "Blank Page"; the finance book's last seven pages are its index). The other
  34 hold no quotable text at all: the contents pages 8 to 14 of both OpenStax books, whose lines the reader classes as
  contents entries, one blank page, and 19 pages without a quotable block (the four looked at hold only a running head, a
  footer or a page number). No page with quotable text is missing, so the gate "nothing lost" holds, read as "no page with
  quotable text".
- **A citation that landed one section early** (decision 91.a, found by the diagnostics frontend): a heading without an id of
  its own takes the id of its enclosing section, and where it is not that section's first heading, its link opened the heading
  before it. Counted on the four free HTML sources: one such heading, SRE's "DevOps or SRE?" (397 SRE headings take their
  section's id, but as its first heading, which is their own place). Its link now carries a text fragment to the heading itself;
  the HTML loader's version went to 3, so the HTML sources are indexed again with the next build.
- **The pipeline database** (decision 47.a, taken by line 1 on the operator's word "at your own discretion"): one SQLite file per
  knowledge base, git-ignored, with two tables. `runs` holds every command that reads, checks, judges, exports, plans or
  builds; a run measures its own cost per provider from the ledger and its batches from the manifests, and names the commit,
  whether the tree was clean, and a hash of `src/backend`. `chosen_readings` is append-only, held so by triggers in the
  database itself; without a row the latest attempt stands. The export serves a chosen reading, and a reading off the default
  says so in its route ("second reader (model, …): anthropic blocked the page").
- **The second reader** (decision 63.a) reads through OpenRouter's OpenAI-compatible endpoint with the frozen prompt; its cost
  leaves the Claude spend guard, and every page of its cell goes to the judge. 68 free pages wait for it: 44 blocked by the
  provider's filter, 23 malformed after the format retry, 1 declined by the reader.

## 2026-11-05

- **The free export carries the outline** (84.a; 24, 44, 309 and 304 units in the four PDFs, 1,610 pages under a unit), each
  page's attempts, and the choice that stands for it.
- **Integrity scan and replay** (decision 69.a), first run end to end on free accounting PDF page 19, a page of two tables
  printed as images. One number in its tracked reading was changed by hand (96,384 to 96,385). `integrity` found the reading no
  longer matching its recorded sha256. `replay reread` read the page again as a new attempt over the standard API: valid,
  stage 2 clean, judged ok, chosen in the pipeline database, and the export written again; 0.058 USD. A second scan was clean,
  and the file holds 96,384 again, now from the new reading. The earlier reading stays in the store; both stand in the trace.
- **Mistake in the second reader's stop rule:** where every page of a cell is judged, a work was stopped above 6 bad pages,
  a count meant for a sample of 40. One work of a cell judged in full had more than six of its pages judged bad, though
  less than 15 % of them, and was stopped, so readings the judge had passed were not chosen. Decision 74.a defines the stop
  as a share ("the same share as 3 of 20"), and a cell judged in full now stops on that share, 15 %. Found in the choice's
  own count of stopped pages; a test pins it.
- **"bin" becomes "issue"** (decision 97.a, the operator): a page a person should look at is an issue, in the states, reasons, reports,
  rollout gates (`issue_share`), exports and docs. The judge's own answer never held the word: the model answers ok, bad or
  unsure, and our code made the outcome "bin"; it now makes it "issue", and records stored before keep theirs, read as an issue.
  Reports and protocols written before keep the old word where they record that time.
- **The export says which model did what, through which provider** (for the operator's overview): each attempt carries its provider,
  the upstream that served a second reading, and its cost; each verdict the judge's model, mode and cost.
- **One quoted text per page** (decision 93.a, found by the diagnostics frontend): the search took a text-layer page's words
  raw from `get_text()`, running heads and loose table numbers included, while the chat cut the same page cleaned and with
  tables as rows, so a "verbatim" quote of one was not found in the other. Now one function gives every reader a page's text
  (`reading_export.quoted_pages`): the served reading as quotable text, or the text layer as the chat's loader cleans it. The
  export writes it beside each PDF's outline; the search quotes it and ranks it without LaTeX commands, a view of the same
  text rather than a second extraction. A test pins search and chat to the same text on a tracked PDF. The search's coverage
  gate after the change: free 8 of 8 works within the first 6 (7 at rank 1), licensed every work, as before.
- **Decision 98.c** (the operator): one retrieval, in the MCP server; the chat becomes its client and its control tool. Order: the free
  index rebuilt (90.a), the chat's retrieval chain as a server tool, the chat as an MCP client with every tool.
- **The chat as the server's client, done** (98.c, with 94.a and 95.a decided by line 1 on the operator's "at your own discretion"). The
  chat's own `open_section` is gone: a source opens through the server's `open_page`. The loop cap was tested with LangChain's
  real middlewares and a fake model that asks for a position size without end; the test pins the words the middlewares end a run
  with, since the turn is marked from them. Three mistakes, all found by the first live run and none by the offline tests, which
  built their passages by hand: an HTML passage named by its anchor rather than the label `open_page` takes; 44 short sections
  the server could rank no more and therefore not open; and a page image's description overwritten by its pixels in the client.
  The first `semantic_search` of the second live run took 46 s against 9.9 s in the first; building the chain cold takes about
  4.6 s here, so the rest was the provider's latency (the router's median was 3.4 s and its maximum 15 s on 5 Nov). Observed
  once, not yet measured.
- **The server's console names its callers** (decision 99.a, the operator): the question shortened to one line, the client, and a line
  per new client. Measured first with a probe server over stdio, HTTP and in process, in both protocol eras of `mcp` 2.3.0: the
  client's name and version always arrive; a session id only over HTTP with the 2025-11-25 handshake, since a 2026-07-28 request
  is a connection of its own; and the SDK's `ctx.session` is built anew for every request, so it cannot identify a client. So a
  client is its session where it has one, else its name and version, and a contract test keeps these facts. Found on the way:
  the question and the client's name now reach the terminal, so a client could send an escape sequence into it; every such
  value is printed without control characters, with a test.
- **An independent review of 99.a** (two read-only reviewers, each finding shown with a probe) confirmed the core of it, then
  found five weaknesses, all fixed with tests:
  - a session header that a 2026-07-28 client sends was counted as a session, although the SDK checks it only for the
    handshake era, so a forged one gave a client line per call;
  - a lone surrogate in a client's name made the record unwritable as UTF-8 and failed a search that had succeeded, and a
    line separator split the record (the call log is ASCII JSON now, and a log that cannot be written no longer fails the
    call);
  - stderr through a pipe was cp1252, so a host reading UTF-8 saw U+FFFD for an umlaut (it is UTF-8 now);
  - the width was counted in characters, so a CJK question wrapped (it counts terminal columns now);
  - no test covered stdio, the chat's own transport, or the call log being git-ignored.

  One claim of the review was wrong: the turn logs did have a test that keeps them out of git.
- **Found by the same review, older than 99.a:** the search server's call log lies in the chat's log folder, and the chat
  treated it as a past conversation:
  - it listed the call log as one;
  - it counted the call log's records as turns;
  - it let the call log be opened, and then appended a whole turn to it, page text included, in a log meant to hold none;
  - it let the call log be deleted.

  Since the chat starts its server itself, every question of the chat wrote there. The chat now reads and deletes only files
  named as it names conversations. Its turn log is ASCII JSON and is split at line feeds only, for the reasons the call log is.
- **Two mistakes of mine in 98.c, found by line 2** while it read the chat's contract for its chat view (decision 100.a):
  - A turn's cost had lost its router: since 98.c the router runs in the search server, and `usd` priced only the
    generator. A test even pinned the loss (`'router' not in turn['usage']`), and a comment claimed the server reported
    its cost, which it did not. A declined question had lost its cost the same way. `semantic_search` now reports its
    router's model and tokens, and the chat prices them as before, declines included. The query embeddings stay
    uncounted, about 0.000002 USD a question.
  - The chat started its search server before reading the model prices, so a missing network left one server process
    running per retried start. The server now starts last and is closed when a later step fails.
- **Reads for line 2's review-demo views and its chat route** (its requests, 5 Nov):
  - the pages one run chose (`pipeline_db.choices`);
  - one page's integrity, checked by the same function the scan uses (`integrity.page_state`);
  - each attempt's check in brief in the export, `{state, verdict, outcome}`, or null where none ran. The free export was
    re-exported, and no other field of its 1,652 rows changed.
  - a turn in the log's own shape (`turn_log.stored`, with the pixels where an interface shows them);
  - a conversation id refused when it could name a file outside the log folder.
- **Mistake, found by line 2 while building its runs view:** the batch runner recorded every run in both knowledge bases'
  databases, so the free one listed runs of licensed cells. A run is now recorded in the bases its cells read: a cell whose
  page list lies with the licensed mirror is licensed. `collect` stays in both, since it stores both mirrors' results. The
  database is append-only by design, so those rows stay as written, and reading a base's runs leaves out those that named
  only the other base's cells: free 30 runs instead of 35.
- **Mistake:** the free export with the second reader's 46 pages was committed (a56b543) without the suite being run. One
  test of the diagnostics frontend expected a declined page in the real export; the only one, accounting PDF page 747, now
  stands with a judged second reading. The frontend's test is being made independent of the real data; the core runs the
  whole suite before every commit that changes tracked data.

## 2026-11-06

- **Mistake, found by the first client:** the search server's chapter claimed parity with the predecessor ("the same scores
  to 1e-9") without saying that it stopped holding on 3 Nov. The client ran two queries on both engines, found the scores
  1.6 to 2.9 % higher on the server with the same pages and order, and guessed the cause: the single index over both
  knowledge bases (decision 71.a) ranks on both bases' statistics.
  - Confirmed here: on an index of the licensed works alone, the port gives the predecessor's scores (40.37 against 40.4).
  - Over 72 queries (the client's two, trading terms and the coverage probes), the shared index moves scores by −14 to
    +4 %. Rank 1 stays the same in all 72 queries, the six pages in 69, and their order in 55. The shifts lie at ranks 3
    to 6, where a term is common in the other base.
  - The phase 6 baseline is not affected: it runs through the chat, whose server serves the free knowledge base alone.
