# Phase 3: a keyword search server over the Model Context Protocol

## Plan

**What.** A search server that any MCP client can call without a chat model: a coding session in another project asks, the
server answers with cited pages in a machine-readable form. Three tools, a fourth since 4 Nov, a fifth since 5 Nov, and two
for the shelf since 8 Nov:

| tool | what it returns |
|---|---|
| `search(query, corpus, hits, work)` | up to `hits` pages (1 to 50, since 6 Nov), best first: knowledge base, work, printed and PDF page, section, file and line, a 250-character snippet, licence, route; or `state: "nothing found"` |
| `open_page(work, page, printed)` | one page in full, with its file and line range; since 10 Nov (decision 175.a), with `printed=true` the page whose printed number is `page`, as an index entry or a "see p. 291" names it, both numbers in the answer (accounting's printed 655 is PDF page 669) |
| `works()` | every work the server knows: key, title, knowledge base, licence, route, page count, and since 8 Nov a sentence on what the work is for (decision 124.a) |
| `search_works(query, corpus, hits)` | since 8 Nov (124.a), which works hold a subject: the page ranking of `search` summed per work over its best five pages, each work with its subject sentence, how many pages hold a query word and how many hold every one, and its best three sections; `pages_with_every_term` 0 says no page holds all the words |
| `toc(work, depth)` | since 8 Nov (124.a), a work's table of contents with the page labels `open_page` takes: its PDF's bookmarks, else its headings or HTML sections; entries deeper than `depth` (1 to 6) are counted, not sent |
| `semantic_search(question, hits)` | since 5 Nov (decision 98.c), the chat's retrieval chain as a tool: a router decides whether to search and rewrites the question into a search query, a broader concept query and keywords; passages close in meaning and the best keyword matches are fused. Up to `hits` passages (1 to 50), shaped like `search`, each with its full passage text, for a client that verifies quotes word for word, and the router's model and tokens under `usage`, so a client can price the call (the query embeddings, about 0.000002 USD a question, are not counted) |
| `page_image(work, page)` | on request only, the page's image: a scan's own embedded pixels, never upscaled, or a 150 dpi render of a born-digital page, with a line saying which, the stored format, pixels, dpi and bytes; or why there is none (decision 92.a) |

The ranking is Okapi BM25 over **one document per printed page**, because a citation needs a page. It is ported unchanged from a
predecessor search tool that was calibrated over the licensed works: K1 1.5, B 0.75, idf `log(1 + (N - n + 0.5) /
(n + 0.5))`, a tokenizer that keeps identifiers (`dry_run` also yields `dry` and `run`) and strips possessives, no stemming, no
stopwords; pages that are mostly an image, a table of contents or an index are dropped, and so is a back index. The server
builds the index once at start and scores a query through postings, which gives the same numbers as scoring every page.

**Sources.** The free mirror, which is what a reviewer runs: the four PDFs from the page readings of phase 2 (the latest valid
reading of a page, its text layer where the reading was blocked or stayed malformed), the HTML sources by section. A second,
private index of licensed works is built the same way on the machine that holds them and never leaves it (decision 39.a).

**Which technique.** Keyword retrieval with BM25 (the RAG sprint, lesson 2, where it fused with vector search); an MCP server
with the official `mcp` package, as in the course's workshop (`MCPServer`, stdio transport). Retrieval stays callable without a
chat model, a stage of its own.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| `rank-bm25`, the course's BM25 | Its idf has another form, so it would move a ranking that was calibrated and measured; checked, not taken |
| SQLite FTS5 with `bm25()` | Persistent and fast to start, the target: it replaces the port once it holds the same gate on the same probes |
| The chat pipeline's vector search | It exists already; exact terms and identifiers are where keyword search wins, and the server must run without an API key |
| One document per section | A section has no page to cite; the predecessor measured pages |

## Gates, written on 2026-11-03, before any code of this phase exists

- **Parity:** on the same pages and queries, the port's scores equal the predecessor's to 1e-9, and its order is the same.
- **Coverage:** for every work, a probe built from its middle third (the predecessor's rule) finds the work within the top 6. The
  predecessor reached every one of its works; the port reaches at least the same. The free works are probed the same way.
- **Latency:** a query on a warm server answers in under 1 second; the start-up time is measured and stated.
- **Answer states:** a search either finds pages or says `"nothing found"`, never an empty answer without a state.

## Report

**The port and the server, 2026-11-03:** `src/backend/search/page_index.py` (the BM25), `coverage_gate.py` (the gate),
`search_server.py` (the tools and the MCP server, `mcp` 2.3.0 over stdio).

| gate | result |
|---|---|
| parity with the predecessor | the same scores to 1e-9 and the same order on five queries over the same works. **→ now** (6 Nov, found by the first client): this holds for the port on one knowledge base's index. The server's single index over both (decision 71.a) ranks on both bases' statistics: over 72 queries scores move by −14 to +4 %, rank 1 stays the same in all 72, the six pages in 69, their order in 55 |
| coverage, private works | every work reached within the top 6, as the predecessor |
| coverage, free works | 8 of 8 reached (four PDFs, four HTML sources), 7 at rank 1 (`coverage_gate --free`) |
| latency, warm | median 4 ms, at most 32 ms over twelve queries; after the review's fixes, over one shared index of both knowledge bases, median 13 ms, at most 47 ms |
| answer states | every search answers `found`, `nothing found`, or `error` for an unknown corpus or work; `open_page` likewise. **→ now** (6 Nov, decision 96.a): also `error` for `hits` outside 1 to 50, in both search tools |

- **One index for both knowledge bases** (decision 71.a, 2026-11-03, replacing the fusion of two indexes in 39.a): raw BM25
  scores from two separately built indexes are not comparable, and RRF would force a mix even when only one base holds the
  answer. A search over one base is the same ranking with the other filtered out, and every hit names its base.
- **The free knowledge base on a clone** (decision 72.a): the latest reading of every free PDF page is tracked in
  `corpus/readings/` with its trace in `index.json` (1,652 pages, 1,608 reading texts, 12 MB, licences in its README), so a
  clone serves the checked readings without buying them. Of the 2,157 free pages the server indexes, 1,353 come from readings,
  723 from the HTML sources by section, and 81 from the text layer, each saying why: 43 blocked by the provider, 23 malformed
  after their retry, 14 in the judge's bin, 1 without a page.
- **Every hit says how its text was made** (`route`), the section in effect, its page label, the PDF page only where it is
  known (a numbered marker or a reading; never for an unnumbered marker or a work converted from an EPUB), its printed number,
  and its file with the line range or the PDF page. Readings are indexed as their words, never their markup.
- **Every tool call is logged** (decision 73.a): a line on stderr with the tool, the query's length, the state, the number of
  hits and the time, and a record in the git-ignored `logs/search_server.jsonl` with the query, the pages that answered and the
  time; never a snippet or a page. The queries are real questions from real callers, the raw material of later evaluation sets.
  **→ now** (decision 99.a, 5 Nov): the line names the client and ends with what was asked, a question in quotes shortened to
  one line of at most 60 characters (or to the terminal's width), a page as its work and label; a line `+ <client> <version>`
  comes before a new client's first call. The record gains `client`, `client_version` and `session`; a session exists only
  where the SDK issued one (HTTP with a handshake-era protocol), since a 2026-07-28 request is a connection of its own. What a
  client sends is printed without its control characters, so an escape sequence in a question cannot rewrite the operator's
  terminal; the width is counted in terminal columns, so a CJK question stays on its line; stderr is UTF-8 even through the
  pipe an MCP host reads; and the call log is ASCII JSON, so no text a client sends can fail a call or split a record.
- **Start-up:** about 32 seconds on this machine: 11 s for the free knowledge base, 15 s for the private works' legacy Markdown,
  6 s to index. A cache of the built pages would cut it.
- **What "nothing found" means:** no query term occurs on any page. A query with one common word finds pages with that word,
  as the predecessor did; the terms a hit lacks are listed with it, so the caller can tell a weak hit from a strong one.
- **An independent review** of the day's core commits (four reviewers, each finding then attacked by a skeptic) confirmed nine
  findings, among them an empty free knowledge base on a fresh clone, markup indexed as words, readings from the judge's bin
  served as citable text, and scores mixed across two indexes; all are fixed here, each with a test.
- **Two transports:** stdio, which an MCP host starts as a subprocess, and streamable HTTP with `--http PORT`, for clients
  that run in containers. Over HTTP the server binds to 127.0.0.1 only, accepts `host.docker.internal` as a Host header (the
  package's DNS-rebinding guard rejects unknown hosts), and answers 401 to any request without the shared token from `.env`.
  Checked on 2026-11-03 from a throwaway container: 401 without the token, and an MCP `initialize` with it answered 200.
- **A switch for a recorded session** (decision 81.a, 2026-11-04): `--public-only` serves the free knowledge base alone; the
  licensed one is not even read, so no licensed title, hit or page can appear. A test pins that it is never read.
- **The page's image, asked for by the first client** (decision 92.a, 4 Nov). A coding session in another project needed to
  check a sentence on a scanned page before quoting it, and the page's text could not settle it. A fourth tool gives the page
  itself, on request only, so a hit stays cheap and textual. A scan comes with its own pixels: rendering it at a higher
  resolution only invents pixels, and the client had measured that a 300 dpi render of a 100 dpi scan reads worse than the
  scan. JPEG and PNG go out as stored; JPEG 2000 and the fax formats as a PNG of the same pixels, since clients and vision
  models take PNG, JPEG, GIF and WebP only. The answer states what it is (native or rendered, stored format, pixels, dpi,
  bytes), so a 7 KB scan can be told from a clean page before a vision call is spent; a work whose first file is not held,
  an HTML source, a work counted by its text rather than PDF pages, and a file the provenance list holds back get a reason
  instead.
  Measured on the client's page: 667 x 928 pixels, 100 dpi, 7,341 bytes as JPEG 2000, as the client had found by hand.
- **What a server says when it starts** (4 Nov): its commit and whether uncommitted changes run with it, a hash of the code,
  where it listens, its knowledge bases with their pages and works (or that `--public-only` left the licensed one unread),
  the routes its texts come by, and its tools; on stderr, since stdout belongs to the protocol under stdio.
- **The chat is the server's client** (decision 98.c, 5 Nov): there is one retrieval. The chat starts its own server over stdio
  with `--public-only` and gets every tool the server lists, through the official SDK's `mcp.Client`. Its knowledge answers take
  their passages from `semantic_search`; a page, a page image, exact hits and the list of works are the server's answers, shown as
  they came. Its two calculations stay in the chat, since they are no retrieval. The agent's loop is capped by LangChain's own
  middlewares (decision 94.a): 5 model calls and 4 tool calls per message, after which the run ends and the turn says so. Its
  chat model has a timeout of 120 s and no hidden retries (decision 95.a; LangChain's defaults are no timeout and two retries).
- **A bound on hits** (decision 96.a, 6 Nov): both search tools take 1 to 50 hits and answer any other number with
  `state: "error"`; `semantic_search` refuses before its router is built or called, so a refused call costs nothing. Before,
  `search` had no upper bound, and one call asking for every page would have flooded the calling model's context. A page hit
  is about 790 characters (the median over five queries on the free knowledge base), so 50 are about 40,000; a passage of
  `semantic_search` carries up to 1,000 characters of text besides. The chat and the evaluation ask for 10. The server
  enforces the bound itself rather than through the input schema, so a refusal comes in the tools' own states, as for an
  unknown corpus or work, and the tool descriptions name it, which a test keeps in step.
- **Found by the first live run of the chat as a client**, each fixed with a test: a passage from an HTML source was named by
  its anchor (`Definition`), while `search` and `open_page` call the same section `s9`, so the chat's "open source 1" found
  nothing; the passage now carries the server's label, and a test over the real index checks every HTML passage against the
  pages the server opens. Then 44 of 767 such sections still did not open, because the server left short sections and tables
  out of its pages along with its ranking; it now keeps them for `open_page` and leaves them out of the ranking alone, so the
  BM25 statistics are those of before. And the client put a page image's pixels under the key that already held the server's
  description of them (native or rendered, dpi, bytes), which was lost; the pixels have a key of their own now. Two live turns
  cost 0.003 USD: an answer with three verified quotes, and its first source opened.
- **The licensed knowledge base serves its checked readings** (decision 125.a, 8 Nov). Until now it served only the legacy
  Markdown of the licensed works, so their checked readings reached no search. Now both bases go through one function
  per PDF page (`pdf_work_pages`): a page's reading where the free corpus's rule lets it be served (valid under today's
  validator, not an issue the judge found, its work not stopped), else its text layer. A licensed work with legacy Markdown
  keeps it page by page and gets each servable reading in place of the legacy page of the same PDF page, the legacy section
  kept, since its headings run through the whole work; a reading of a page the legacy text had left out (a table, a short
  page) joins it. A work without legacy Markdown is served like a free PDF, from its readings and its text layer, and its
  page images open. A file the provenance list holds back stays out, and so does a stand-in file beside the legacy text of
  its work, since two copies of one book would compete for every hit. Matching is by the PDF page alone, and only where the
  legacy marker names it: a legacy text whose markers carry no number stands whole. On the machine that holds it, the
  licensed base now serves pages from checked readings, from legacy Markdown and from the text layer of the new works; a
  warm start reads it in 37 s (the first start cut the new works' pages once, 208 s). The free base is unchanged: its
  function was moved, not altered, and its tests pass as before.
- **The shelf** (decision 129.a, 8 Nov): `python -m backend.search.shelf` writes, per knowledge base, one row per work into
  its store's reports (`shelf.json`, never into the repository): its pages, the pages the cascade planned for the reader,
  how many readings passed and why the others did not, what the search serves of it by route, why a passed reading is not
  served, and the files the server serves not at all, with the reason. It counts from the very pages the server builds, so
  the two cannot disagree, and a passed reading it cannot account for is kept as `unexplained` rather than hidden (none on
  8 Nov). The diagnostics frontend shows it and computes nothing. **Since 19 Nov (X1.a)** each base's totals carry their
  shares of the planned pages (`share_read`, `share_passed`), and `--milestone NAME` adds a row to the corpus's history
  (`data_paths.SHELF_HISTORY`, each base's figures apart, so a view of the free base alone never shows the other's); the view
  shows both, in place of the table a person's file used to hold.
- **The library tools** (decision 124.a, 8 Nov), from a request of the server's first outside consumer: five of seven
  subjects it wanted books for were already on the shelf, and finding that out took four searches and several greps, because
  the passage ranking answers *where is this sentence* and the shelf question is *do we own a book about X*. The top hit for
  one such subject was a glossary page of the book that is entirely about it. Three additions, none of them a model call:
  `works` carries one sentence per work on what it is for (for the free works in `corpus/catalog.json`); `search_works` sums
  the page scores per work over its best five pages, the passage-to-document aggregation retrieval papers call SumP, so a
  work about a subject outranks one strong page elsewhere, and it counts the pages that hold every query word, which makes
  "we own nothing on this" as cheap to establish as the opposite; `toc` gives a work's contents to descend into. The server's
  MCP instructions now say to start with `works`. **The chat keeps exactly the five server tools it was measured with:** it
  took every tool the server listed, so two new tools would have changed the prompt run D was measured on; it now names its
  tools, and a new one reaches it only after its own measurement. The descriptions of the five are unchanged, and a `works`
  answer reaches the user as it came, never the model, so nothing the chat was measured with moves.
- **Two kinds of licensed work now serve their checked readings too** (decisions 126.a and 127.a, line 1 on the operator's "at your own
  discretion", 8 Nov). A legacy text whose markers carry no number is named by its PDF pages through an offset
  measured per work and kept as data beside the knowledge base: word overlap between each checked reading and the legacy
  pages around its number put the match at ordinal = PDF page + 1 on nearly every reading, never at another offset, because
  each file opens with one marker more than its PDF has pages, for a header note that is never served. Their pages are now
  labelled like every other work's, open as images, and take their readings page by page. Before, every such reading stood
  unused and the labels were off by one against the PDF. A work whose first file is not held is now served whole from its
  stand-in file, its readings and text layer: the legacy text's page numbers pointed at a file nobody holds, and they drift
  against the stand-in by 12 to 60 pages, so no page could be matched. The numbered legacy works were checked the same way
  first: their marker N holds PDF page N in nearly every matched reading, so decision 125.a's matching by number stands on
  a measurement.
- **10 Nov, a printed page number opens its page** (decision 175.a, the operator, from the index page accounting p. 969). The numbers
  in a book's index, and a "see p. 291" in its text, are printed numbers, while `open_page` took the page label, which for a
  PDF is the PDF page: asked for 655, it opened PDF page 655, fourteen pages before the one that prints 655, without a word.
  `open_page(work, page, printed=true)` now opens the page that prints the number and names both; where one number stands on
  several pages, the first opens and the answer says which others hold it. Resolving references inside the text (pages,
  chapters, figures, links, internal or external) is a feature for after the capstone, noted in the backlog; this is its
  foundation: every page of a reading already carries its printed number.
- **A link to check a hit** (decision 226.a, the operator, 12 Nov: "can the MCP results also show the shareable link into the
  frontend?"). Every page hit of `search`, `open_page` and `semantic_search` carries `view_url`, where a person sees
  the page in the diagnostics view with its image, its reading and every check: a PDF page as
  `http://127.0.0.1:8001/#/free/sources/<work>/page/<pdf page>`, an HTML section as `…/#/free/html/<work>/s9`. The work is
  named by the view's own id, the catalog's, which is not the key the search uses (`openstax-accounting` is
  `openstax_principles_of_accounting_v1` there). A legacy text without a reading has no page in the view and no link. The
  view's address is `DIAGNOSTICS_VIEW_URL` where it runs elsewhere (a server the chat starts inherits it), or
  `--view-url`; the field is new, so a client that does not know it loses nothing.
- **EPUBs, by section** (decision 123.a, after the submission; the operator, 18 Nov). An EPUB is born-digital XHTML in a zip,
  so it needs no reader, no judge and no API call: `backend.ingestion.clean_sections.epub_sections` reads the container, the
  package's reading order (spine) and the navigation's chapter names with the standard library, and cuts each document at its
  headings with the HTML route's own walker, so both formats read text alike; a publisher's paragraphs set as `<div>` are read
  as paragraphs. Hits name their section as an HTML source's do (`s12`, with the heading path). An EPUB serves its work in
  place of the legacy text made from it; a stand-in EPUB stays beside the legacy text of its work. An image stays where it
  stands as the mark `⟦image⟧` and is listed with its file: in several books the formulas are images whose alt text says
  nothing, so a route of text alone would lose them without a word; the ranking leaves the mark out (`Page.index_text`).
  Measured on the private shelf: the loader keeps 96 to 100 % of each book's words, and where a legacy text exists the two
  hold the same words to within 1 to 4 %, the legacy text's surplus being markup and image paths. Reading the formula images
  is a later step, and only for files that may go to a provider.
- **What stands in a reading's place is named as served** (H2.a, the operator, 19 Nov). A page whose reading may not be served
  said "text layer" in the export, though a licensed work with page-numbered legacy Markdown serves that page's legacy text
  (decision 125.a above); for a scanned work, which has no text layer at all, the route claimed a text that does not exist.
  The export now asks the server's own rule (`search_server.legacy_fallback_pages`) and names each row's `fallback`: the
  legacy Markdown, the text layer, or none where the reading is served. The route keeps its reason under the new source
  (`legacy markdown: the judge found the reading bad, a person looks at it`), and `served_readings.FALLBACK_ROUTES` holds
  every route that serves no reading.
- **The private knowledge base gets the semantic search** (issue #8, the operator's S2.a, 20 Nov). Its pages come by four
  routes, so its vector index is built from the librarian's own pages (`backend.ingestion.licensed_index`): the very text
  the keyword search serves, each page a section with its PDF page, route and reading key, split by the free index's
  splitter (1,000 characters, 200 overlap) and stored in the free index's format, in its own folder under the private
  working data, refused wherever git would track it. A work whose file the provenance list holds back stays out whole, its
  earlier Markdown and EPUB sections included, since an embedding sends text to a provider. `semantic_search` runs the same
  chain over both indexes and fuses the two by rank (reciprocal rank fusion, k = 60, as 39.a fuses two indexes), every hit
  naming its knowledge base; a server that does not give the private base out (`--public-only`, so the chat and every
  measurement) or a machine without the index searches the free index alone, exactly as before.
