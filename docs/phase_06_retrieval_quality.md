# Phase 6: retrieval quality, measured through the chat

## Plan

**What.** Measure the chat's whole path, the way a user and a coding session meet it since decision 98.c: the search server
routes the question and searches (`semantic_search`), and the chat answers and keeps only the quotes it finds word for word
(`chat_turn.search_turn`). Then change the pipeline only with changes that act on every question alike, each kept or dropped
by a paired before-and-after number on the development set. The held-out set is read once, at the end.

**The questions.**
- **Development set:** the RAG sprint's 30 questions (the operator's), and 30 from the coding sessions of a project that consumes
  this knowledge base, written from its real needs on 2026-11-06. Of the 60, those with expected sources are scored on
  retrieval; all are scored on behaviour.
- **Held-out set:** 10 more questions from the same authors, committed before any change (`eval_questions_holdout_2026-11-06.json`).
  It is read once by mechanism: the ledger refuses a second reading without a stated reason.
- **Styles,** after the authors' own measured mix: keywords, question, section paraphrase, short phrase and title words.
  Every number is also given per style and per expected work.

**Which technique.** Retrieval evaluation as the course's RAG lessons teach it: recall@k and the reciprocal rank of the
first expected section, at the section and the document level (lesson 2), with paired comparisons rather than totals.
Answer quality by a judge model (RAGAS) is phase 7.

**Hypotheses, each a change that acts on every question alike:**

| hypothesis | change | where it came from |
|---|---|---|
| exercise pages crowd out explanations | demote or leave out the OpenStax review and exercise sections in the chat's index | the questions' authors: in one question exercise pages hold ranks 1 to 3, and the answer comes fifth |
| a table above a back-matter heading is lost | the loader keeps a page's text above the first back-matter heading under the unit before it | the Kelly paper's results table, PDF p. 14 |
| the relevance floor was set before the verified pages | recalibrate it on the development set | a floor is not comparable after a change of the converter (lesson of a neighbouring project) |
| developer phrasing pushes the answer down | none to build first: the router's rewrite and the vector search exist for this; the per-style numbers show whether they close the gap | the questions' authors, and their twelve query pairs |

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| measure in process, as phases 4 and 5 did | the chat no longer searches in process; a number from another path would not be the chat's |
| tune on the held-out set too | then it measures nothing; it is read once, at the end |
| a judge model for every answer now | phase 7; this phase needs retrieval numbers that cost almost nothing to repeat |

## Gates, written before the baseline is measured

- **Baseline first.** One run on the development set through the chat, its results committed, before any change.
- **The instrument check.** Title-word questions name their own topic; if fewer than 3 of the 4 find their section within
  the first 5 passages, the instrument is suspect, and no other number is read until it is understood.
- **A change stays** only when, on the development set, the paired difference in section recall@5 is not negative and its
  95 % interval's lower bound lies above −0.05, while correct behaviours fall by at most one question and the share of
  answers with a verified quote does not fall. A lower bound above 0 is reported as an improvement; otherwise as "holds".
  **→ now** (6 Nov, after the replay below): correct behaviours may fall by at most **two** questions. A replay with the
  baseline's own plans and the same index scored retrieval identically and still moved two behaviours, both on identical
  passages, by the generator alone, so a slack of one counted noise as harm.
  **→ now** (8 Nov, decision 116.a, written and committed before the run it first judges): behaviours and verified quotes are
  judged only on the questions whose passages the change altered (other chunks, or the same in another order), each allowed
  to fall by at most two, and quotes by count, not share. Run C showed why: the two answers that lost their quotes had been
  given identical passages, and a question newly answered without a quote lowers a share though nothing got worse.
- **Per question, not only in total.** Each change reports the questions whose first expected section moved, and whether
  that section's text itself changed. A consuming project measured why: a change right on its face came back a point lower
  at rank 1 because a shift in the keyword statistics moved two questions that sat on the rank boundary, while their
  expected sections stayed byte for byte the same. On sixty questions one point can be one borderline question.
- **A miss is a measurement, not a reject.** No question leaves the sets because the pipeline misses it; the Kelly table
  (hc03) was found only because its miss was kept.
- **No change aimed at one question.** A change that helps one question by name is not made.
- **The held-out set,** read once with the final configuration, is reported as it comes, beside the development numbers.
- **Cost:** at most 2 USD for the phase's measurements; every run states its cost.

## Report

**The baseline, 2026-11-06** (`evaluation/results/answers_phase6-baseline_2026-11-06.json` and `.md`):
- one run over the 60 development questions, through the chat's path, the router and the generator as configured;
- 0.157 USD measured on the key, a median of 24 s per turn.

| measure | result |
|---|---|
| behaviour correct (answer, not found, clarify, the two declines) | 45 of 60: the RAG sprint's questions 20 of 30, the consuming project's 25 of 30 |
| an expected section among the passages given to the model | 38 of 44 |
| a verified quote from an expected section | 32 of 44 |
| quotes proposed, then kept after the word-for-word check | 141, then 134 |
| answers with at least one verified quote | 49 of 49 |
| partial answers that name what is missing | 5 of 8 |
| section: hit@5, recall@5, reciprocal rank | 0.84, 0.58, 0.60 |
| document: hit@5, recall@5, reciprocal rank | 0.93, 0.86, 0.88 |

**The instrument check passes:** 3 of the 4 title-word questions find their section within the first 5 passages. "time
value of money" does not; a summary page outranks the explanation, as the questions' authors had seen.

**By style** (section recall@5, questions with expected sources):

| style | questions | recall@5 |
|---|---|---|
| section paraphrase | 8 | 0.75 |
| keywords | 3 | 0.78 |
| title words | 4 | 0.63 |
| short phrase | 2 | 0.50 |
| question | 8 | 0.48 |
| the RAG sprint's, not labelled | 19 | 0.52 |

The developer's own phrasing ("question") is the weakest style. One question shows why: "is it safe to resend an order if
i never got a confirmation back" was answered "nothing found", while the SRE book's chapter on cron answers it in its own
vocabulary ("idempotent", "double launch").

**By work** (section recall@5):

| work | questions | recall@5 |
|---|---|---|
| SRE book | 10 | 0.73 |
| Wikipedia | 16 | 0.62 |
| Accounting | 3 | 0.58 |
| Kelly paper | 2 | 0.50 |
| Finance 2e | 8 | 0.49 |
| walk-forward paper | 4 | 0.38 |
| Lefèvre | 1 | 0.20 |

**The 15 behaviour misses:**
- Eight are the router's: clarify against answer (q12 to q14, q18, q26, q27, i28) and declines confused (q23, q25, q30).
- Two are "nothing found" where an answer exists (q21, i03).
- Three were answered where the authors expected "nothing found" (i18, i20, i29). Whether they should count is decision
  105: i20 used the SRE book's client-side throttling and named the gap, while i18 stretched a consensus protocol's sequence
  numbers onto an order protocol.

**Not comparable to phase 5's 0.47:** that number came from a measurement in process over the RAG sprint's 17 questions,
on the first 5 passages of the search itself. This one is taken on the passages the chat gave the model, through the
server. The phase's changes are measured against this baseline.

**The instrument, replayed** (`answers_phase6-baseline-replay`): every question routed by the baseline's own plan
(`--frozen-plans`), so the router's variance is out of the comparison and no routing is paid for.
- Retrieval scored identically: a recall@5 difference of exactly 0, and no question's first expected section moved. The
  passages were the same in 59 of 60 questions; in i15 the last three differed, since a query's embeddings are computed
  afresh in every run.
- Two behaviours changed, both by the generator: q10 failed to generate, and i30 was answered where "nothing found" was
  expected. That is the noise floor of a run, and the gate's slack now follows it.
- 0.122 USD by token counts; the key had not booked it when the run ended, as for runs B and C below.

**Hypothesis 1, exercise sections demoted** (run B, `answers_phase6-exercises-demoted`: the baseline's plans, the textbooks'
exercise sections listed in `retrieval.demote_sections`; 0.119 USD by token counts). **Verdict: holds, kept.**
- The model was given 10 exercise passages in 6 questions before, and none after.
- Section recall@5 did not move: +0.000 [+0.000, +0.000]. Only one exercise passage had sat in the first five, and that
  question's expected section stood above it.
- Behaviour: 45 of 60 against the baseline, 46 after; against the replay, 43 then 46. q21 had held three exercise passages
  and is now answered, as expected.

The chat's retrieval, vectors fused with BM25 on the router's keywords, rarely ranked exercise pages high. The page-level
keyword search (`search`), where the questions' authors saw them crowd out explanations, ranks whole pages and is not touched
by this change; whether to demote them there too is left open.

**Hypothesis 3, the relevance floor: holds, no change, measured without a run.**
- Of the 42 answerable questions with a similarity, all but i03 (0.467) reach 0.508 or more.
- Five of the seven questions expected to find nothing lie at 0.474 or less. Two lie far above any floor, i20 at 0.542 and
  q27 at 0.616, so no floor can catch them.
- 0.495 lies inside the gap between 0.474 and 0.508. No floor makes fewer than three errors on these 49 questions, and 0.495
  makes three.
- i03 cannot be separated from i18 at 0.474 by any floor: its problem is retrieval, not the floor.

**Hypothesis 2, headings in capitals found by the loader** (run C, `answers_phase6-capital-headings`: the baseline's plans, the
exercise sections demoted as kept; 0.124 USD by token counts). **Verdict: dropped by the gate.** The change waits on its own
branch, `phase6-loader-capitals`, for a decision.
- **The cause:** the loader looks for each outline heading in the outline's own spelling. The Kelly paper sets "DATA
  AVAILABILITY STATEMENT" in capitals, so the heading was not found, and PDF p. 14's text above it went out of the index
  with the back matter.
- **The fix** finds such a heading in any case at the start of a line, wherever the outline's spelling is not on the page.
  - In the free PDFs it moves 5 outline entries, all in the Kelly paper, whose 92 chunks become 100.
  - The other three PDFs give the same chunks byte for byte.
- **Against run B,** the same configuration before the fix:
  - Section recall@5 +0.000 [+0.000, +0.000], and no expected section moved.
  - Behaviour 46 → 45, within the slack.
  - Answers with a verified quote 50 of 50 → 49 of 51. The share fell, so by the gate the change does not stay.
- **Per question:** the two answers without a quote, q07 and i20, were given exactly the same passages as in run B. The five
  questions whose passages the fix altered in text (q14, q15, q19, i11, i23) lost neither a quote nor a behaviour. As far as
  one run can tell, the fall is the generator's. The gate allows for no such noise on quotes, and none is added after the fact.
- **What the development set can show:** no development question expects a Kelly section whose text the fix moves, so it can
  show harm, not gain. The question the gap was found by is in the held-out set.
- **A review of the fix** found two defects to mend before any merge, and one more defect in the loader as it stands. The
  protocol has them.

**Hypothesis 2, measured again: kept** (run D, `answers_phase6-loader4-page12`, 0.122 USD measured on the key).
- Loader 4 came back with the review's two defects mended: a heading in capitals counts only as a line of its own, and a
  heading that stands above the previous entry is found where the page prints it.
- In the same rebuild the validator page/1.2 let two free pages stand on a checked reading instead of their text layer.
- Judged by the rule written before this run: section recall@5 against run B +0.000 [+0.000, +0.000], and no expected
  section moved. Passages changed in 7 questions, all with a Kelly passage; among them correct behaviours 6 → 6, verified
  quotes 7 → 7. On identical passages the generator moved q21 and i29 (a failed generation), which the rule does not count.
- An outside confirmation: the held-out question hc03 was delivered with the section "DISCUSSION" for PDF p. 14. Loader 4
  files that page's text under "4. Discussion"; the old cut had put it under the back-matter unit.

**The generator's noise, from the four runs:** on identical passages it changed the behaviour or the quote status of two to three
questions in every comparison: q10 and i30 in the replay against the baseline, q27 and i30 in run B against the baseline, and
q07, q27 and i20 in run C against run B.

**The intake of three documents, measured against run D: the gate says dropped** **→ now: holds, measured again the chat's
way (see the correction below); the numbers in this paragraph are those of the mismeasured run** (`answers_phase6-regulation-intake`, 8 Nov,
0.154 USD measured on the key; decision 121.b added SR 11-7, SR 26-2 and Regulation T to the free index, and loader 5 cut them).
Section recall@5 fell by 0.059 [−0.131, +0.008]; correct behaviours rose from 45 to 47 and verified quotes from 48 to 49.
- **The new documents are not what moved:** a passage of theirs is among the first five of three questions only (q09, q18,
  i26), none of them scored for recall. Eight scored questions fell (q06, q11, q12, i05, i06, i12, i15, i27) and two rose
  (q15, i17); in every one that fell, the expected section lost its rank to another chunk of the old sources.
- **One of the eight is the generator:** in i05 the chat declined the question and called no search at all, so its recall
  went from 1 to 0 with no retrieval behind it. Without the two questions where a run retrieved nothing, the difference is
  −0.039 [−0.097, +0.020].
- **What is left has two possible causes, not yet separated:** the keyword side's statistics over an index 3.6 % larger
  (its idf and mean length move for every term the new chunks hold), and the re-embedding of the four PDFs that the loader's
  new version triggered, whose texts are unchanged. A run on the same index without the three documents would tell them
  apart. The gate's rule holds: the growth waits until a person has looked.

**Correction: the intake holds** (`answers_phase6-intake-with-three`, 9 Nov, 0.135 USD measured on the key). The run above, and
an isolating run after it (decision 131.b), left out `--through-server`: the evaluation then answered in process, routed every
question live, and ignored `--frozen-plans` without a word, so 53 of 60 plans differed from the baseline's and the comparison
measured the router's variance, not the documents. Measured through the server with the frozen plans (60 of 60 plans the
baseline's), the intake against run D: section recall@5 +0.000 [+0.000, +0.000], reciprocal rank +0.011 [+0.000, +0.034],
correct behaviours 45 → 44 (q08: the generator stopped at its output limit), verified quotes 48 of 48 → 48 of 48; the passages
of 16 questions changed. The gate's verdict: holds. The isolating run was not repeated, since no drop is left to explain.
`answer_eval` now refuses `--frozen-plans` without `--through-server`, before anything is spent.

**The judge's issues read again, measured against the intake run: holds** (`answers_phase6-judge-rereads`, 9 Nov, 0.175 USD on
the key; decision 133.b brought 36 free pages from their text layer onto a checked reading). Through the server with the
frozen plans (60 of 60): section recall@5 +0.000 [+0.000, +0.000], reciprocal rank +0.000, correct behaviours 44 → 44,
verified quotes 48 → 47 of 48 (q03: the generator failed, on passages that did not change); the passages of 7 questions
changed.

**The cost-disclosure rules, measured against the re-reads run: holds** (`answers_phase6-cost-rules`, 9 Nov, 0.122 USD on the
key; decision 143.a). Four public documents joined the free corpus for a question the corpus could only answer by analogy, how a
spread and a negative fee are shown in a report: Commission Delegated Regulation (EU) 2017/565 and Regulation NMS Rules 600,
605 and 606, 105 pages, each read, checked and judged like the rest. Loader 6 came with them: the EU regulation's outline is
one bookmark, its title, and made its 83 pages one section, so an outline of one entry now counts as none; and where the
readings' headings make the outline, a heading with no text of its own becomes the parent of the next ("Article 50 >
Information on costs and associated charges"), since the readings carry no heading levels. PDFs with bookmarks keep their
sections exactly; Regulation T went from 45 sections to 34. Through the server with the frozen plans (60 of 60): section
recall@5 +0.011 [-0.015, +0.045], reciprocal rank +0.011 [-0.005, +0.030], correct behaviours 44 → 47 (q03 and i21 had
failed in the run before, i03 now answers from the new rules), verified quotes 47 of 48 → 51 of 51; the passages of 24
questions changed. The new works stand among the first five passages of 8 questions and are quoted in 5, where they fit:
the swap and overnight questions (q21, i26) quote Annex II's ongoing charges, which name swap fees; i12 quotes Rule 600's
"executed outside the quote". One is a label question for the set's authors, left as it is here: i30 (price-time priority,
labelled "not found") was answered before and is now answered from Rule 600's ranking of bids and offers by price, size and
time. The spread-fee question itself, asked as on the morning of 9 Nov, now quotes Annex II's "mark ups embedded in the
transaction price" and Rule 606's "net execution rebate or fee … (cents per 100 shares, specified to four decimal
places)", where it had quoted an accounting textbook's card fees; Article 50, which says "a cash amount and … a percentage"
and "itemised separately", was not among its ten passages, and no rule names the sign a negative fee is printed with, which
the answer says.

**A judge's finding that names no difference is void, measured against the cost-rules run: holds** (`answers_phase6-void-rule`,
9 Nov; the key had not booked its cost when it ended; decision 146.a). Code voids a wrong-word or wrong-value finding whose
evidence quotes no difference, checked against the reading's block and the PDF's text layer; five free pages the judge had
sent to their text layer serve their readings again (finance p. 5, accounting pp. 156, 580, 657, 706). Through the server
with the frozen plans (60 of 60): section recall@5 +0.000 [+0.000, +0.000], reciprocal rank -0.004 [-0.011, +0.000], verified
quotes 51 of 51 → 51 of 51; the passages of 5 questions changed, and among them correct behaviours 5 → 5. Over all 60, correct
behaviours 47 → 45 (q24 and q27), both on questions whose passages did not change: the generator's own variance, which the
gate's rule of 116.a leaves out. A first run of this measurement answered all 60 questions and then lost its results to a
connection reset while reading the key's usage; `answer_eval` now writes its results whether the key can be read or not.

**HTML text as a browser shows it, and a figure's lines, measured against a new baseline over 61 questions: holds**
(`answers_phase6-text-as-shown`, 10 Nov, 0.125 USD measured on the key; decisions 155.a and 156.a, both from the operator's look at
the diagnostics views). The HTML loader (version 4) read every element's edge as a space, so a quote said "the Sortino ratio
, which" and "( m − d ) ÷ σ ,"; it now joins an inline element to its neighbours as written, keeps a space only where a
browser breaks the line or sets a superscript or subscript apart, reads a stray `</br>` as a line break, and writes a formula
in \( \) or \[ \] as a PDF page's reading does. Measured before the change: every section's words unchanged, 1,230 spaces
gone beside punctuation, 15 words joined, each as a browser shows it. The PDF loader (version 8) keeps a figure's lines and
its groups apart, where eleven T-accounts had read as one run ("… Bal. 5,500 Common Stock 70,000 …"). The baseline is
`answers_phase6-baseline-61`: the void-rule run's plans for the 60 questions it held, q31 routed live, 46 of 61 behaviours
correct. Through the server with the baseline's plans (61 of 61): section recall@5 +0.000 [+0.000, +0.000], reciprocal rank
-0.004 [-0.013, +0.004]; the passages of 25 questions changed, and among them correct behaviours 21 → 22 and verified quotes
23 → 24. Over all 61, behaviours 46 → 46; i17 ended in an error, its generator stopping at the output limit on passages that
did not change. Quotes the verification dropped went 12 → 6, but the questions whose drops changed are mostly not the
altered ones: the generator's variance, not a measured effect.

**The generator keeps gaps and the follow-up out of its answer, measured against the text-as-shown run: holds**
(`answers_phase6-generator-sections`, 10 Nov, 0.120 USD measured on the key; decision 163.a). Line 2's check of the operator's Sharpe
question found the answer writing its own "Gaps" and "Follow up" sections above the same two fields, and a follow-up offering
"I can fetch it if you want", which the system cannot do. Two sentences joined the generator's rules: gaps and the follow-up
are shown below the answer and are never written into it; a follow-up asks the user and never offers an action, since the
model cannot search or fetch beyond the passages. Counted in the answers by the same pattern before and after: an own gaps
section 4 → 1 of about 45 answers (q31 still wrote one), an own follow-up section 1 → 0, an offered action 0 → 0 (the offer had
come in a live turn, not in a run). The passages did not change (the same index, the plans frozen): section recall@5 +0.000,
behaviours 46 → 47, answers with a verified quote 52 of 52 → 51 of 52 (q11 answered without one this time, within the
generator's variance).

**A glossary entry with its term, and the pages a person reviewed, measured against the generator-rules run: holds**
(`answers_phase6-glossary-terms`, 10 Nov, 0.120 USD measured on the key; decisions 190.a, 167.a, 174.a, 189.b and the
person's verdicts of the walk). The term a glossary entry defines stood only in the reading's attribute, so 934 definitions
on 68 free pages reached the index without the words they define; they now read "term: definition" (PDF loader 9). The
same rebuild serves the readings a person accepted where the judge's findings had sent pages to their text layer (accounting
p. 635's four exercise tables, finance p. 119's Figure 4.4, the glossaries of finance pp. 136 and 562) and finance p. 229's
first reading, which a failed re-read had displaced. Through the server with the frozen plans (61 of 61): section recall@5
+0.000, reciprocal rank +0.000; the passages of 2 questions changed (q02, q06), both still correct and quoted. Over all 61,
behaviours 47 → 46 (q26 and q29, on passages that did not change: the generator's variance).
