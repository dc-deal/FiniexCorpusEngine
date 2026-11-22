# Roadmap

**Goal:** a small Google Books for trading knowledge: every answer with a verbatim quote and its page,
verified rather than guessed. The depth goes into conversion and retrieval. A search server over the
Model Context Protocol is the main interface; the diagnostics view's chat shows a question, an answer and the
quote with its page (a Streamlit demo did until 17 Nov 2026).

**Dates:** feature-ready 12–13 Nov 2026; review by 18 Nov (the course deadline includes it).

**What goes first:** if time runs short, cut in this order: tracing, the comparison
of embedding models, multi-representation indexing. Stitching across pages is not on that list: without it a verbatim quote
could end in the middle of a sentence.

| phase | what | when |
|---|---|---|
| 0 | Clean the repository and its history; first push to the course repository | 30–31 Oct |
| 1 | Reader format, verification checks and judge; mini pilot on free pages; freeze the format | 31 Oct – 2 Nov |
| 2 | Read the free corpus and its new sources in batches; the licensed works through the same pipeline and gates | 2–8 Nov |
| 3 | MCP search server: BM25, page access, coverage test over every work | 2–5 Nov |
| 4 | Local conversion bench and scans; modular reader adapters and a second reader for free pages the provider blocked | parallel |
| 5 | Bring verified formulas, tables, figures, scans and code into the free pipeline | 5–9 Nov |
| 6 | Retrieval quality: more questions, a fresh held-out set committed before tuning, measured stages | 8–11 Nov |
| 7 | Evaluation report: RAGAS, the held-out run, tracing if time allows | 11–12 Nov |
| 8 | Adapt the Streamlit demo; README, ethics, docs, presentation | 12–15 Nov |

Review 16–18 Nov. One chapter per phase follows in `docs/phase_NN_<what>.md`, each with its plan and report.

**Phase 1 is done:** [its chapter](phase_01_reader_format.md) holds the gates and the measurements; `page/1` is frozen.
**Phase 2 is done:** the free corpus is read and judged ([its chapter](phase_02_corpus_reading.md)), three public documents
added (8 Nov); the licensed works went through the same gates (by 9 Nov).
**Phase 3 is done:** [the search server](phase_03_search_server.md) over MCP, with its gates.
**Phase 5 is done:** [its chapter](phase_05_verified_pages.md): verified pages in the index, one quoted text per page, a pipeline
that repairs a damaged reading; retrieval holds (recall@5 0.47 against 0.48). **One retrieval in the MCP server stands** (5 Nov):
the chat is the [search server](phase_03_search_server.md)'s client, its loop capped. **Phase 6 has started** (6 Nov,
[its chapter](phase_06_retrieval_quality.md)): 60 development questions and a fresh held-out set of 10, committed before any
change; a baseline through the chat; each change kept or dropped by a paired comparison, question by question. **Phase 6 is
done** (9 Nov): three hypotheses measured, two kept, and the intake of three documents holds. **Phase 7 is done** (9 Nov,
[its chapter](phase_07_evaluation.md)): the held-out set read once, 7 of 10 behaviours, and a RAGAS report, faithfulness 0.94
on the development set and 0.97 on the held-out answers. Phase 4's scans and local model, and tracing, move after the
capstone.
**Since 10 Nov:** a person walked the judge's issues page by page, and four judge versions were measured against the
person's verdicts; a reader prompt built from those findings was measured as a prototype ([phase 2's chapter](phase_02_corpus_reading.md));
the conversion code was put into folders by concern. **Phase 8 is under way** (12 Nov): the demo rehearsed, the README and
the presentation brought up to date.
**Since 22 Nov (issue #10):** the index can live in PostgreSQL with pgvector, in Docker: the keyword ranking in SQL, the
semantic search's vectors in pgvector, a changed page served without a restart; each half gated against the files
before it was switched on ([phase 3](phase_03_search_server.md)). Still open: the view reading the database (E) and a
backup of the vectors before Chroma is retired.
