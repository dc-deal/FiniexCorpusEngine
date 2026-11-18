# Phase 7: the evaluation report, out of sample and with RAGAS

## Plan

**What.** Two measurements of the finished system. First, the fresh held-out set (`evaluation/eval_questions_holdout_2026-11-06.json`,
ten questions written by the consuming project's coding sessions and committed before phase 6 changed anything) read once, the
chat's way, after the last change to the free index. Second, a RAGAS report on the last development run and on the held-out run.

**Which technique.** The held-out set is the RAG sprint's guard against tuning on the test (lesson 3: a set measured once, at the
end). RAGAS is the evaluation the course teaches (sprint 3, lessons 3 and 4): faithfulness at 0.8 is the first target, context
metrics below 0.7 point at retrieval. Four of its metrics: **faithfulness** (does every claim of the answer follow from the
passages?), **answer relevancy** (does the answer address the question?), **context precision** (are the passages that matter
ranked first?) and **context recall** (do the passages hold what the expected answer needs?).

**Why this way.**
- **RAGAS in its own environment** (decision 136.a): RAGAS 0.4.3 pins `openai` below 2 and needs `langchain-community` 0.3; the
  app runs on `openai` 3 and `langchain-openai` 1.6, and `pip install ragas --dry-run` would have downgraded both. So
  `requirements-eval.txt` installs RAGAS into `.venv-eval`, and `backend.evaluation.ragas_report` imports nothing of the app:
  it reads an answer record, the questions' expected answers and the passages' texts from the index's SQLite file. DeepEval
  would have installed into the app's environment, with four pytest plugins and its own telemetry beside the offline test
  guarantee, and the course teaches RAGAS.
- **The judge is not the generator:** the chat answers with `gpt-5-mini`; RAGAS judges with `gpt-4.1-mini`, so no model grades
  its own words. Both through OpenRouter; the embeddings are the index's own model.
- **Answer relevancy asks one generated question per answer:** RAGAS asks three by default, and OpenRouter returns one
  generation per call; it warned and went on with one, so the report asks for one and says so.
- **Before the held-out run, its authors checked it against the three documents added in phase 6** (SR 11-7, SR 26-2,
  Regulation T): no label changes. They named three questions the new documents expose to a false positive or a displaced
  source: hc09 (a market impact model, where every model-risk passage says "model"), hc01 (monitoring, where SR 11-7 has
  "ongoing monitoring") and hc10 (documenting a number for a later check, where SR 11-7 requires documenting a model). The
  set itself stayed unread on our side until its one run.
- **Tracing is cut** (decision 138.a): the roadmap named it first to go if time ran short; the reviewer of the agents sprint
  asked for tracing *or* a RAGAS or DeepEval report, and the RAGAS report is here.

## Report

### The held-out set, read once (9 Nov, `answers_phase7-holdout`, 0.069 USD on the key)

Through the search server, live routing, as a user would ask; the ledger (`evaluation/holdout_ledger.json`) holds the reading
and its commit.

**After the reading, the free index changed once more** (decision 143.a, 9 Nov): four public documents on cost and execution
reporting joined it, measured in phase 6 against the development set (holds; 47 of 60 behaviours). The held-out numbers
below are those of the index before them; the set is spent and is not read again.

**The development set gained a question after the runs** (decision 151.a, 10 Nov): q31, the operator's question on the Sharpe
ratio's history in five parts, one of which no source answers ("where was it founded"). Every number here and in phase 6
is of the 60 questions before it; q31 is measured from the next run on (10 Nov, `answers_phase6-baseline-61`: answered
with three verified quotes, "where it was founded" named as a gap).

| measure | held-out (10) | the last development run (60) |
|---|---:|---:|
| correct behaviour | 7 of 10 | 44 of 60 |
| answers with a verified quote | 7 of 7 | 47 of 48 |
| section recall@5 | 0.417 (8 scored) | 0.582 (44 scored) |
| document recall@5 | 0.708 | 0.856 |
| first expected section in the top 5 | 0.625 | 0.841 |

**The three misses, each a different cause:**
- **hc01**, "how do i know if my monitoring is actually catching real problems": the router declined it as off topic, though
  the SRE book answers it. A wrong routing decision, the router's.
- **hc03**, "how often should i rebalance": the search server did not answer in time, and the chat said so. An operational
  failure, not a judgement on quality; it counts as a miss all the same.
- **hc09**, "market impact model": answered where nothing was expected. The best passage lay at a relevance of 0.504, just above
  the floor of 0.495, and the answer built on the walk-forward paper's mention of Kyle (1985). The authors' label, written
  before the run, names that paper and rules it out: it is not a model of market impact.

**The authors' warning held for hc10:** it counts as answered, but SR 11-7 took four of the first five places, as they said it
might; the expected accounting section lost its rank.

### RAGAS (9 Nov, `ragas_phase6-judge-rereads`, `ragas_phase7-holdout`)

Scored on the questions the chat answered from passages; declines, clarifications and "nothing found" have no answer to judge.

| metric | development (42 answered) | held-out (7 answered) | the course's mark |
|---|---:|---:|---:|
| faithfulness | **0.941** | **0.970** | 0.8 |
| answer relevancy | 0.587 | 0.611 | – |
| context precision | 0.633 | 0.749 | 0.7 |
| context recall | 0.679 | 0.809 | 0.7 |

Cost: about 0.3 USD for the development run (the key had not booked it when the run ended) and 0.076 USD for the held-out run.

**What the numbers say.**
- **Where the chat answers, it stays with its sources.** Faithfulness is above the course's first target in both sets: the
  generator answers from the passages, and the quotes are checked word for word in code.
- **Retrieval is the weaker stage, and the questions' style decides how weak.** On the development set the context metrics lie
  around 0.65, below the course's 0.7; the colloquial questions of the RAG sprint ("where do i start when i build a trading
  bot?") score 0 on several, the precise questions of the consuming project mostly above 0.9. The held-out questions are of the
  second kind, and there both context metrics pass.
- **Answer relevancy is low by construction here.** RAGAS sets an answer it finds noncommittal to 0; the chat's honest partial
  answers ("the passages do not say ...") are exactly that (i18 and i30 on the development set). A chat that guessed would
  score higher.
- **RAGAS and our section recall can disagree, and both are right.** On hc10 RAGAS finds the SR 11-7 passages relevant to the
  expected answer (precision 0.92, recall 1.0), while section recall counts only the expected accounting section: RAGAS judges
  meaning, section recall counts the exact place a citation should point to.
- **The judge is a model:** the numbers carry its noise and its taste; they compare runs, they are not a truth.

**What it means for the next step.** The misses are not in the reading or the quoting, which the whole project was built to make
trustworthy, but in the decision whether to answer: a router that declines an in-scope question, a relevance floor that a
near miss crosses (hc09 here, the spread-fee question of 9 Nov in two runs at 0.503 and 0.451), and a server call that timed out.
They are the candidates for after the capstone, measured first: the router's plan, the floor, and a retry for a search that
failed in passing.

**Tool choice, measured on 12 Nov through the search server** (`tool_eval`, the report `evaluation/results/tools_phase8-review_2026-11-12.md` in the local data folder):
the course's three questions for a tool call, on 13 cases written for this measurement: the right tool in **13 of 13**, the
right arguments in **6 of 6** where a calculation was due, and no calculation where none belongs (a request to explain, an
off-topic question, an attempt to read the instructions, a calculation asked for without its numbers); a follow-up
("open the full text of source 1") opens the page the previous answer cited. 0.03 USD.
