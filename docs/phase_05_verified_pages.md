# Phase 5: verified pages into the chat's index, and a pipeline that heals itself

## Plan

**What.** Until now the chat's index (Chroma for meaning, SQLite for facts, from the RAG sprint) is built from the PDFs' text
layer, which in the two OpenStax books has no formula where a formula is drawn as vector paths and no cell where a table is an
image. This phase builds the free PDFs' sections from the verified page readings of phase 2 instead, and makes the pipeline
able to find and repair a damaged reading on its own.

1. **Pages from readings.** A PDF page's text comes from its reading where the reading may be served (valid under today's
   validator, not an issue the judge found, its work not stopped); otherwise from the page's own text layer, as before. A reading
   becomes plain text a reader can quote: prose with inline formulas as `\( … \)`, displayed formulas as `\[ … \]`, tables as
   rows, code as it is printed. Page furniture and the reader's derived figure descriptions are left out. The outline cuts
   sections as before, so section titles and the evaluation's expected sources stay comparable.
2. **Stitching across pages** (decision 65.a). A sentence, a paragraph, a formula or a table can run over a page boundary. Where
   the reader marked a page's first block `cont=prev`, the two pages join without a paragraph break; between text-layer pages a
   join is made by rule (the first page ends without a closing stop or with a hyphen, the next begins in lower case), and a
   word hyphenated at the line's end is rejoined. A chunk that spans a boundary names both pages.
3. **Every chunk keeps its trace.** Each page carries the route that made its text and, for a reading, its key; a chunk carries
   those of the page it starts on and the page it ends on. A source's fingerprint includes the readings it was built from, so a
   corrected page re-indexes its source and nothing else.
4. **A pipeline database** (decision 51.a, the first part of 47): one SQLite file per mirror for what cannot be rebuilt. Here
   two tables: `runs` (every command that read, checked or judged, with its cost and batch ids) and `chosen_readings`, an
   append-only record of which reading stands for a page and why (latest attempt by default; a replay switches it).
5. **Integrity, gaps and replay** (decisions 54.a, 69.a). `integrity` checks every exported reading against the sha256 its trace
   records and every page of a work for a reading; `replay` shows one page's whole trace and, with `--reread`, reads it again as
   a new attempt over the standard API, checks it in stages 1 and 2, has the judge see it, chooses it, exports it and rebuilds
   its source in the index. That is the self-healing demo: a tampered reading is found by its hash and by the checks, a deleted
   one by the gap scan, and both are repaired by buying exactly one page.
6. **Both knowledge bases in one shape** (decision 80.a, added on 4 Nov). Every row of a page export names its knowledge base
   first, `free` or `licensed`, then its work and page, with the printed page label the reader found and the provider's own
   message where it blocked a page. The licensed export has the free one's shape but lies in a git-ignored folder, local only,
   and the export refuses any folder git would track. A clone has the free export alone, and the search server and the
   diagnostics app start with `--public-only` for the recorded review (decision 81.a).
7. **The source's own order** (decision 84.a, added on 4 Nov). The export carries each PDF's outline as the chat's loader cuts
   it: the same function places every outline entry and cuts the sections, over the same pages with the served readings in
   place, so a view can group a work's pages by chapter and section without a second ordering of its own. Each unit has its
   level, its parent and its first and last page; back matter is kept and marked as not indexed. Each page lists the units
   whose text lies on it, so a page where one section ends and the next begins appears under both.

8. **One quoted text per page** (decision 93.a, added on 5 Nov). The search, the chat and the diagnostics frontend quote a page
   from one function: its served reading, or its text layer as the chat's loader cleans it. The search ranks the same text
   without LaTeX commands.

**Which technique.** Indexing with a second representation of each page (multi-representation indexing, rag_from_scratch
part 12: the page image is read into a structured text that the index stores beside the original); the splitting stays the
course's `RecursiveCharacterTextSplitter` (lesson 3). Replay and the content hashes are outside the course: engineering for
traceability, which the project's own requirements ask for.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| Keep the text layer and append each page's formulas as extra chunks | Two representations of one page drift apart, and a quote could join a sentence from one to a formula from the other |
| Chunk each page on its own | Sections are what the evaluation's expected sources name, and a page boundary would cut sentences the stitching joins |
| A full schema now, every table of 51.a | Tickets come after the capstone (62.b), chunk rows can wait for the index: two tables serve the replay and the trace |
| Repair a tampered reading from a backup | The demo shows the pipeline at work: a page is bought, checked and chosen as on the first day, and both versions stay |

## Gates, written on 2026-11-04, before any code of this phase exists

- **Nothing lost:** every formula, table and code block of a served reading reaches a chunk (100 %), and no page outside the
  back matter and the pages before the first outline entry is missing from its sections.
- **Stitching:** every join the reader marked `cont=prev` is made; on text-layer joins the words of the joined sentence appear in
  order in the two pages' text layers (at least 98 % of joins).
- **Trace:** every chunk resolves to its page's row in `corpus/readings/index.json` or to its text-layer route; a test pins it.
- **Retrieval does not get worse:** recall@5 on the tuning questions within the run-to-run noise of the RAG sprint's 0.48 or
  better (a paired difference whose 95 % interval includes 0 or lies above it). One build and one evaluation run on OpenRouter,
  estimated under 0.15 USD.
- **Self-healing:** a tampered reading is flagged by its hash and by stage 2; a deleted one by the gap scan; one replay repairs
  each, buys exactly one page, and leaves every other page's key unchanged.

## Report

**Done on 5 Nov.** The free PDFs' sections come from their verified readings, stitched across pages; every page is quoted from
one text by the search, the chat and the diagnostics frontend; the pipeline records every run and every chosen reading; and a
damaged reading is found and repaired by buying that one page again. The gates as written on 4 Nov, each with what was measured:

| gate | measured | |
|---|---|---|
| nothing lost | every formula, table and code block of a served reading reached a chunk (2,115 of 2,115). 54 pages after each first outline entry reach no section: 20 are back matter, the other 34 hold no quotable text (contents pages, one blank page, pages with only a running head or a page number) | passed |
| stitching | every join the reader marked is made, pinned by tests. The rule for joins between text-layer pages agrees with the reader's own marks on about 70 % of them, so a reader's mark decides wherever a reading is served. The measure as written (the joined sentence's words in order in both text layers, at least 98 %) was not run; 112 of 1,652 free pages are served from their text layer, so few joins depend on the rule | partly |
| trace | every chunk names the route of its first and last page and, for a reading, its key; none without a route | passed |
| retrieval does not get worse | section recall@5 of the chosen pipeline (router rewrite, step-back, BM25 on keywords) 0.47 over three runs (range 0.38 to 0.57), against 0.48 in the RAG sprint; paired by question over the 17 questions both runs scored, a difference of -0.012 with a 95 % bootstrap interval of [-0.074, +0.048], which includes 0. The two runs are weeks apart, and the router varies between sessions | passed |
| self-healing | case (a) run live on accounting PDF page 19: a number changed by hand was found by the integrity scan, `replay reread` bought one new reading for 0.058 USD, the judge passed it, it was chosen and exported, and a second scan was clean. Case (b), a deleted reading, is found by the same scan (a test) and repaired by the same command; its live run is left for the rehearsal of the review | partly |

**Added on the way, each a decision of its own:** the judge on every page stage 2 cannot check (83.a: 861 pages, 28 bad, 12 with
a wrong value); each PDF's outline in the export (84.a); a second reader through OpenRouter for pages the default reader could not
give (63.a: free, 52 of 68 valid, judged); one quoted text per page (93.a); the pipeline database (47.a); the word "issue" for
what was the bin (97.a). The index has 8,548 chunks, built for 0.029 USD; the measurement cost 0.060 USD.

**Next (decision 98.c):** the chat's retrieval chain becomes a tool of the MCP server, and the chat its client, so there is one
retrieval and the chat is its control tool. Phase 6 measures through it.
