# Phase 7 protocol: how the evaluation report came about

- **9 Nov, RAGAS would not install beside the app.** `pip install ragas --dry-run` in the app's environment would have downgraded
  `openai` from 3.19 to 1.109 and `langchain-openai` from 1.6 to 1.1, and pulled `langchain-community`, archived since June.
  DeepEval 4.3.3 would have installed cleanly, but with four pytest plugins and its own telemetry. Decision 136.a (the operator): RAGAS
  in an environment of its own, `.venv-eval` from `requirements-eval.txt`, the report reading the app's records and index files
  without importing the app. A contract test checks the report's imports against `requirements-eval.txt`, as the app's are
  checked against `requirements.txt`.
- **The newest `langchain-community` broke RAGAS 0.4.3 on import:** it asks for `chat_models.vertexai`, which 0.4.2 removed. Pinned
  to 0.3.31 in the evaluation environment, where the app's stack does not apply.
- **A smoke run on three answers** (0.022 USD) worked; RAGAS warned that its LangChain wrappers are deprecated in favour of
  `llm_factory` (they work, and take the course's `ChatOpenAI` with a `base_url` as it is), and that the judge returned one
  generation where answer relevancy asked for three. The report now asks for one.
- **The held-out set's authors were asked first** (through the operator, 8 Nov evening) whether the three documents added in phase 6
  change any label; they answered no, named three questions newly exposed (hc09, hc01, hc10) and noted they had not read SR
  26-2 itself, judging it by its subject. The set stayed unread here.
- **The free index was frozen before the run:** the last change (decision 133.b) measured "holds" against the intake run; no
  change to the free index or the chat followed. The held-out set was then read once (9 Nov, commit b4d1d9a in the ledger),
  through the server, routed live.
- **What the run showed was predicted in part:** hc09 was answered where nothing was expected, the trap its authors named; hc10
  lost its expected section to SR 11-7, as they said it might. hc01 and hc03 were not predicted: a routing decision and a
  server call that did not answer in time.
- **The development run's RAGAS cost was not booked** on the key when the report was written; the held-out run's was (0.076 USD).
  At the smoke run's rate, about 0.3 USD.
- **Tracing cut** (decision 138.a, on the operator's "at your own discretion"): first on the roadmap's list to go; named on the
  presentation's last slide instead.
- **10 Nov, a question from the diagnostics view joined the development set** (decision 151.a): the operator asked the chat about the
  Sharpe ratio's history, construction, inventor and timeline, and where it was founded. Server and chat answered four parts
  with three verified quotes and named the fifth a gap; the router had guessed "1966 Journal of Finance" as a search word,
  which the answer did not use. It became q31, verbatim, `answer_partial`, its sources located the same day and unconfirmed
  until the operator checks them. Not the held-out set: its answer had been seen. `compare_runs` calls two runs over different sets
  "not comparable" on purpose, so a later gate first needs a new baseline over the 61.
