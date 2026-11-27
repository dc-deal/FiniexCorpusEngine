# Documentation

[The roadmap](roadmap.md) holds the plan. One chapter per phase, each with its plan and report; the protocols record how a phase came about, mistakes included.

One word changed on the way: a page a person should look at is an **issue**; until 5 Nov 2026 the chapters and protocols
called it the bin (decision 97.a), and they keep the old word where they record that time.

The diagnostics frontend, which makes every stage visible and traceable, has [its own chapter](diagnostics.md) ([protocol](protocols/diagnostics_protocol.md)).
The librarian's security, the course's MCP security points one by one with what is left open: [its own chapter](mcp_security.md).

| pipeline stage | chapter |
|---|---|
| indexing: conversion of the sources | [phase 1: reader format, checks and judge](phase_01_reader_format.md) ([protocol](protocols/phase_01_reader_format_protocol.md)) |
| indexing: conversion of the sources | [phase 2: reading the corpus in batches](phase_02_corpus_reading.md) ([protocol](protocols/phase_02_corpus_reading_protocol.md)) |
| retrieval: keyword search as a service | [phase 3: a keyword search server over MCP](phase_03_search_server.md) |
| indexing: conversion of the sources | [phase 4: local readers on a bench machine, measured as test readings in the Lab](phase_04_local_readers.md) ([protocol](protocols/phase_04_local_readers_protocol.md)) |
| indexing: verified pages into the index | [phase 5: verified pages into the chat's index, and a pipeline that heals itself](phase_05_verified_pages.md) ([protocol](protocols/phase_05_verified_pages_protocol.md)) |
| evaluation: retrieval quality, measured through the chat | [phase 6: retrieval quality, measured through the chat](phase_06_retrieval_quality.md) ([protocol](protocols/phase_06_retrieval_quality_protocol.md)) |
| evaluation: the report, out of sample and with RAGAS | [phase 7: the evaluation report](phase_07_evaluation.md) ([protocol](protocols/phase_07_evaluation_protocol.md)) |
