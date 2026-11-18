# Phase 6 protocol: retrieval quality, measured through the chat

How phase 6 came about, mistakes included. The chapter with its plan, gates and report:
[phase_06_retrieval_quality.md](../phase_06_retrieval_quality.md).

## 2026-11-06

- **Where the new questions come from.** The coding sessions of a project that consumes this knowledge base wrote them from
  the needs in their own open and closed issues: 30 development questions and 10 held-out ones, in one pass. They were not
  written by the operator, nor by the pipeline's author, who would tend to pick what the pipeline handles well.
  - The authors confirmed each expected source by reading its page on the search server, in the free knowledge base. They
    did not call `semantic_search`, which spends money and is what will be measured.
  - They recorded at which rank the keyword search found the page (`found_by_search`), kept every miss, and reworded no
    question to rank better.
  - The style mix follows the one their own benchmark measured: keywords, question, section paraphrase, short phrase and
    title words, about 20, 25, 30, 10 and 15 %. Title words serve as the canary: if they fail, the instrument is suspect.
- **The fresh held-out set is committed before any change of phase 6.** It is
  `evaluation/eval_questions_holdout_2026-11-06.json`. The RAG sprint's set was read on 2026-10-01 and is spent. A held-out
  set is now read once by mechanism, not by intention:
  - `evaluation/holdout_ledger.json` records every reading, written by the evaluation command before it measures anything;
  - `retrieval_eval`, `pipeline_eval` and `answer_eval` refuse a second reading of the same file without `--again "the
    reason"`, and the ledger keeps that reason beside the first reading;
  - the RAG sprint's reading is the ledger's first entry, written by hand.
- **How a delivered page became an expected source.** The search server names pages, while the evaluation matches a chunk by
  its document and its indexed section. So each page was mapped to what the index holds for it:
  - a PDF page to its outline unit, since the server shows the heading at the page's top and the chunks carry the unit, for
    example "Sharpe Ratio" on Finance 2e PDF p. 471 becomes "15.4 Applications in Performance Measurement";
  - an HTML section to its anchor, and a Wikipedia section to its article and anchor.

  Eleven PDF sources named a heading below the outline. Five pages hold two units; there the authors' note decided.
- **Mistake caught by a test the same hour:** the spent set and the fresh one both used the ids h01 to h10. The new contract
  test, which asks that the two sets share no id, failed at once. The fresh set's ids are now hc01 to hc10, and each keeps
  the id it was delivered under.
- **Two gaps the questions found before any measurement:**
  - The Kelly paper's PDF p. 14 holds a results table above the heading "Data Availability Statement". The chat's loader
    files the page under that back-matter unit and leaves it out of the index, so the table cannot be found. A held-out
    question (hc03) expects it, and the expected source stays, so the measurement counts the gap.
  - The SRE book's section path carries a footnote marker ("Motivation for Error Budgets 14"). Matching goes by anchor and is
    not affected; the marker is noise in a citation.
- **Two findings of the questions' authors, as hypotheses for this phase:**
  - A question typed the way a developer types it pushes the defining section down the keyword ranking, in several works. That
    is the gap the router's rewrite and the vector search are meant to close, and this phase measures it.
  - The OpenStax books' exercise pages ("Multiple Choice", "Review Questions", "Thought Provokers", "Exercise Set",
    "Solution") repeat a chapter's vocabulary without explaining anything, and they outrank the explanation. In one question
    they hold ranks 1 to 3 and the answer comes fifth. A change that acts on every question alike would demote them.
- **The free index was rebuilt with its model unchanged** (decision 103.a, the operator). The 46 pages the second reader gave were
  chosen after the index of 5 Nov had been built, so for them the chat quoted the text layer while the search quoted the
  reading. Only the two OpenStax books were indexed again, for 0.020 USD; all 46 pages are now in the index, with 234 chunks.
  Seen on the way: the HTML sources' chunks carry no route, while their pages on the server do.
- **A second reading of ten development questions.** One reviewing agent read the pages and searched the free corpus
  offline. Result: 1 confirmed, 8 adjusted, 1 rejected.
  - Three claims that something is missing from the corpus were wrong. The SRE book's cron chapter covers a duplicated
    write (i03). Wikipedia covers slippage and implementation shortfall (i12), and comparing a backtest with live trading
    (i19, which had been marked "nothing found"). The authors' searches had missed whole chapters and subsections.
  - Six questions had a better or a further source, for example Finance 2e 4.1 "Cash versus Accrual Accounting" for the
    question of when a transaction is recorded.
  - Each amended entry says what changed and why. The other twenty are unchanged.
- **Mistake of mine, found by that second reading:** the mapper took a PDF page's printed number from the first chunk on the
  page, which can start on the page before. Five of seven checked numbers were one too low. They now come from the page's
  own reading. The held-out set, committed the same morning, was corrected before any reading; no printed number is used
  for matching.
- **The baseline was measured and committed before any change:** 60 questions, 0.157 USD. The instrument check passed, 3 of
  4 title-word questions. The record was 2.6 MB, because every passage was stored twice with its citation twice. It is now
  written compactly, each passage once with its citation raw. The baseline's record was compacted after the run with the
  same function, after checking that all 60 questions re-score exactly as they did at run time.
- **The plan's gates were committed before the baseline** (the operator: "ok"), after two lessons from the consuming project went in:
  report every change per question, since one point on sixty questions can be one borderline question moved by statistics;
  and a miss is a measurement, never a reason to drop a question.
- **The held-out set's three riskiest labels were read a second time** (decision 104.a, the operator). Each label's specific claim
  held, but each search had missed material a careful answer would use. hc07 needs two more sources. hc08 and hc09 are
  partial rather than "nothing found", by the dataset's own definitions. Whether to amend them is decision 105.
- **The measurement goes through the chat** (decision 102.a, the operator): `answer_eval --through-server` answers every question the
  chat's way, through the search server's `semantic_search`. It scores retrieval from the passages the model was given
  (hit@5, recall@5, reciprocal rank) beside behaviour and verified quotes, by style and by expected work.
- **Each change is compared question by question** (`compare_runs`): the paired difference in section recall@5 and in the
  reciprocal rank with a 95 % bootstrap interval, the behaviours before and after, and every question whose first expected
  section moved. Each record keeps a digest of every expected section's indexed text, so a move tells whether the text
  itself changed or only the statistics around it.
- **The router is taken out of the comparison.** `--frozen-plans` reads the baseline's router plan for every question from its
  record and routes nothing. Without it, two runs of the same configuration differ by the router alone, which the RAG sprint
  measured at 0.07 recall@5 between sessions.
- **The instrument, replayed before the first change** (`answers_phase6-baseline-replay`, 0.133 USD): the baseline's
  configuration and its frozen plans once more. Retrieval came back identical, with no question moved. Two behaviours still
  changed, both by the generator: q10 failed to generate, and i30 was answered where "nothing found" was expected.
  **→ now** (the same night, found while attributing hypothesis 2): the scores came back identical and no question moved, but
  the passages were the same in 59 of 60 questions only. In i15 the last three differed, since a query's embeddings are
  computed afresh in every run. "Identical" said more than was measured. And its cost is 0.122 USD by token counts: the key
  had not booked the run when it ended, and the 0.133 USD above has no record behind it.
- **Mistake in a gate I wrote, found by that replay:** the gate allowed correct behaviours to fall by one question, so the
  comparator called a run without any change "dropped". The slack is now two, the noise one replay measured; the chapter marks
  the change **→ now**. No hypothesis was rescued by it: the first held under both, and the change came before the loader fix
  was measured. The operator approved the gates as written, so the operator confirms or reverts the change.
- **Hypothesis 1, the exercise sections demoted: kept** (`answers_phase6-exercises-demoted`, 0.131 USD, the baseline's plans).
  - The list of ten section titles reaches the two OpenStax books only: 816 of 3,336 chunks in Accounting, 219 of 2,385 in
    Finance 2e. The other six works are untouched.
  - Before, the model was given 10 exercise passages in 6 questions; after, none. Section recall@5 did not move, since only one
    exercise passage had sat in the first five, below the expected section.
  - Behaviour against the baseline 45 → 46, against the replay 43 → 46; answers with a verified quote 49 of 49 → 50 of 50.
  - So the chat's retrieval, vectors fused with BM25 on the router's keywords, rarely let exercise pages crowd out an
    explanation. The questions' authors saw that in the page-level keyword search, which ranks pages, not chunks.
  - **→ now:** the cost is 0.119 USD by token counts, unbooked like the replay's; the 0.131 USD above has no record behind it.
- **Hypothesis 3, the relevance floor: no change, measured from the baseline's record without a run.** All answerable questions
  but i03 have a best similarity of 0.508 or more; all questions expected to find nothing but two borderline ones lie at
  0.474 or less; the floor of 0.495 sits in that gap. i03 (0.467) cannot be told from i18 (0.474) by any floor.
  **→ now** (the review the same night): the two are not borderline. i20 (0.542) and q27 (0.616) lie far above any floor, so
  no floor catches them. 0.495 lies inside the gap from 0.474 to 0.508, not in its middle (0.491). No floor makes fewer than
  three errors on the 49 questions with a similarity, and 0.495 makes three, so the verdict stands. "All answerable questions"
  means the 42 of 43 that have a similarity; q23 was routed as harmful and searched nothing.
- **Hypothesis 2's cause, found before the fix.** The loader looks for each outline heading on its page in the outline's own
  spelling. The Kelly paper's PDF p. 14 sets "DATA AVAILABILITY STATEMENT" in capitals, so the heading was not found, the unit
  was taken to start at the top of the page, and the results table above it went out of the index with the back matter.
  Measured before changing the loader, across every free PDF: a case-insensitive search at the start of a line, used only
  where the exact spelling is not found, moves 5 outline entries, all in the Kelly paper.
- **Hypothesis 2, the fix: loader 4.** The title finder keeps the outline's own spelling first, so every heading found before
  is found where it was. Only where that spelling is not on the page does it look in any case at the start of a line. Two tests
  fail on loader 3 and pass on loader 4; the slow tests over whole books pass.
- **Only the Kelly paper was embedded again** (`build --source`, the same model, 0.000374 USD). Under loader 4 the other three
  PDFs give the stored chunks byte for byte, ids and texts: Finance 2e 2,385, Accounting 3,336, the walk-forward paper 106.
  Embedding them too would only have added the embedding service's own noise to the comparison.
- **The Kelly paper's index under loader 4:** 92 chunks became 100.
  - PDF p. 14's text above "DATA AVAILABILITY STATEMENT", Table 9 with the sensitivity analysis and the end of the discussion,
    lay under "4. Discussion", the unit before the heading.
  - "2. MATERIALS AND METHODS" on p. 2 and "3. RESULTS" on p. 6 stand in capitals too. Under loader 3 the end of the
    introduction lay under "2. Materials and Methods", and "2.3. Monte Carlo Simulations" was empty: "3. Results" was placed at
    2.3's own heading, so 2.3's text is cited as "3. Results" in the index as it stands. Loader 4 gives each unit its own text.
  - The free export changed in four pages, 2, 6, 14 and 15 (on p. 15 two back-matter headings were found), and in the last
    page of two units, "1. Introduction" and "4. Discussion"; nowhere else.
- **Its reach in the licensed knowledge base,** which uses the outline only for page labels and the local export: some
  outline entries move, in a few of the works that have an outline.
  - Nearly all are headings alone on their line, most of them in capitals; a few carry a short tail such as a page number.
  - A few move only because the entry before them on the page moved.
  - One is a line that goes on after the title's words, perhaps a heading run into its paragraph. Counted by code, without
    printing a title or a line.
- **No development question expects a Kelly section whose text moved.** So on the development set the fix can act only through
  the Kelly paper's re-cut chunks competing for a place (100 instead of 92; 10 carry text the index did not hold, 24 ids name
  other text than before) and through the keyword statistics every chunk shares. The question it was found by is in the
  held-out set (hc03). Its second expected source
  names the back-matter unit the old cut gave PDF p. 14, which is never indexed: a label that cannot be met by any retrieval.
  Whether to amend it before the held-out reading is decision 107, for the operator.
- **Run C, loader 4 against run B** (`answers_phase6-capital-headings`, 0.124 USD by token counts, unbooked like the replay's
  and run B's): section recall@5 +0.000 [+0.000, +0.000], no expected section moved, behaviour 46 → 45. But answers with a
  verified quote fell from 50 of 50 to 49 of 51, and the gate asks that the share does not fall. **So the change does not stay.**
- **Why it fell, question by question:** q07 and i20 lost their quotes (3 to 0 each), and q27 went from "nothing found" to
  clarify. All three were given exactly the same passages as in run B. The five questions whose passages the fix altered in
  text (q14, q15, q19, i11, i23) lost neither a quote nor a behaviour. As far as one run can tell, the fall is the generator's:
  the replay and run B each moved two questions on identical passages too.
  - **Mistake of mine, found by the review:** I first listed q28 among the questions the fix altered. Its ten passages were the
    same in both runs, reordered by the drift of the query embeddings, and it kept two of its three quotes.
- **I did not change the gate after this result.** I had widened the behaviour slack after a run without any change. Widening
  the quote rule right after a hypothesis failed it would be rescue after the fact. So the fix went to its own branch,
  `phase6-loader-capitals` (one commit, the code, its tests and the free export), and main went back to loader 3: the Kelly paper
  embedded again with it (92 chunks, the ids run B used, 0.000341 USD), and both exports rewritten. The free export equals its
  committed state byte for byte. Whether the fix goes in, and by which rule, is decision 108, for the operator.
- **An independent review of the night's work** (two read-only reviewers, one on the code, one on every claim against the
  records; nothing spent on the API) returned 17 findings, 16 of them with evidence. Fixed here:
  - `compare_runs` called two records "holds" that it could not compare: no shared question, no retrieval scores, or a new run
    that lost questions. It now says "not comparable" and names the questions found in one record only.
  - The slack of two had no test that failed at one or zero; a test now holds that two lost behaviours pass and three do not.
  - Nothing tied the chat's `retrieval.k` to the server's bound of 50 hits; a config test does now.
  - Claims above, marked **→ now** where they had been committed: the replay's "identical", the runs' costs, the floor's
    "borderline" questions, q28, the reach of the re-cut chunks, and the pages the export changed.
- **Left for decision 108, from the same review, on the branch's fix:**
  - On the Kelly paper's PDF p. 15 the outline's order differs from the page's. A back-matter heading found by the new rule
    raises the floor for the next entry, whose heading stands above it, so the reference list falls under "Author
    Contributions". All three units are back matter, so the index is not touched, but the export's units for that page are wrong.
  - The rule takes any line that begins with the title's words, with no word boundary after the last one: "Discussion" would
    match a line "discussions of risk follow". Not seen in any measured PDF, where no heading found before moved.
  - The share rule for quotes has no allowance for noise, and a question newly answered without a quote lowers the share
    even when the behaviour improves.
- **Left open, without evidence:** the bound of 50 hits stands in the tools' descriptions, not in their input schemas, so a
  client's model sees no maximum; the chat's server tools return directly, so a refused number ends the turn instead of
  being retried. Whether the chat's agent ever asks for more than 50 is not measured.

## 2026-11-08

- **The operator's decisions on the phase's open questions** (116.a, one bundle): the behaviour slack stays at two (106.a); the gate
  judges behaviours and quotes on the questions whose passages a change altered (written and committed before run D); the
  loader fix comes back with the review's two defects mended, measured together with the free pages page/1.2 makes valid
  (108.a, 115.a), in one rebuild and one run; the held-out labels are amended before the reading (105.a, 107.a).
- **The held-out set amended, unread** (105.a): hc07 keeps answer_partial and gains Lefevre XII, the fullest first-person
  account, as its first source, and the SRE book's trading halt by a separate team; hc08 and hc09 become answer_partial, since
  the SRE cron chapter treats an operation that must not take effect twice, and the walk-forward paper models a simulated
  order's cost and names what it leaves out. Each entry says so in `amended`. hc03 waits for run D's verdict on the loader.
  The ledger still holds the RAG sprint's reading alone.
- **The development set keeps its labels for now:** i20 and i30 follow the older convention ("nothing found" where the corpus
  covers a neighbouring topic). Changing them during the phase would score run D against run B under two conventions. They are
  aligned when phase 7 begins, and every phase 6 record is scored again with `answer_eval.score`, which calls no model, so the
  development and held-out numbers are reported under one convention.
- **Run D, loader 4 and page/1.2 on the free pages, against run B: holds, so loader 4 stays** (0.122 USD measured).
  - The free export changed in two pages that now stand on a reading, in the Kelly paper's four outline pages, and in the
    validator named on every row. The four free PDFs were embedded again (0.021 USD), since every page's route names the
    validator; the HTML sources were not.
  - Passages changed in 7 questions, all with a Kelly passage. Embedding the three unchanged PDFs again changed no other
    question's passages. Among the 7: behaviours 6 → 6, verified quotes 7 → 7. q21 and i29 moved on identical passages.
  - **I had told the operator "45 free pages would become valid".** True of the readings, but only 2 pages changed what stands for
    them: the second reader had already covered the others.
- **Mistake of mine, found by the questions' authors** (decision 107.a): they had delivered hc03's second source as PDF p. 14,
  section "DISCUSSION". My mapper of 6 Nov wrote the back-matter unit the old loader put at the page's top, "Data
  Availability Statement", which is never indexed. Restored as "4. Discussion", the unit loader 4 files that text under.
- **The authors' answer on 105, for the operator:** a neighbouring topic is "not found", never "partial". "Partial" means a source that
  answers part of the asked question; otherwise the middle state empties the outer two. That reverses the reading behind
  105.a for hc08 and hc09; hc07 stays partial by their own example.
- **105 settled by the authors' rule** (105.c, the operator): "partial" needs a source that answers part of the asked question; a
  neighbouring topic is "not found", or the middle state empties the outer two. hc08 and hc09 are back to answer_not_found, the
  material the second reading found named and ruled out in their expected answers. hc07 stays answer_partial with its two
  added sources, as the authors' own example of a partial answer. The development set's i20 and i30 already follow that rule,
  so the re-scoring planned for phase 7 is not needed. The held-out set is still unread.
- **Mistake of mine, 8 and 9 Nov: two runs measured with the wrong instrument.** The intake of decision 121.b was measured with
  `answer_eval --frozen-plans` but without `--through-server`. Without the server the evaluation answers in process and routes
  live, and it ignored the frozen plans without a word, so the run compared the router's variance against run D: recall@5
  −0.059, the gate's verdict "dropped". An isolating run (131.b, the index without the three documents) was made the same way
  and seemed to blame a re-embedding of unchanged texts (−0.086). Found by comparing the records' router plans with the
  baseline's: 7 and 6 of 60 equal, against 60 of 60 in every run before, and the turns lacked their `retrieval` stamp. The
  isolating run's records were deleted, the first run's record stays as the trace of the mistake. Measured again the chat's
  way, the intake holds (recall@5 +0.000). `answer_eval` now refuses `--frozen-plans` without `--through-server`, with a test.
  Cost of the mistake: 0.31 USD on the key and an evening's wrong conclusion, which reached the operator as decision 131
  before it was corrected.
- **10 Nov, text as a browser shows it (decision 155.a) and a figure's lines (156.a), both from the operator's look at the views.** In
  the HTML view the operator saw "the Sortino ratio , which" and "( m − d ) ÷ σ ,": the loader read every element's edge as a space
  (BeautifulSoup's `get_text(' ')`), so every Wikipedia quote carried such spaces. On accounting p. 305 the eleven T-accounts
  the reader had written line by line, group by group, reached the index as one run ("… Bal. 5,500 Common Stock 70,000 …").
- **Checked before any change, by a probe in the session:** the new reading patched in, every section's text compared with
  today's. The words were the same in every section (only whitespace moved). The first reading took 1,235 spaces beside punctuation,
  as meant, but 225 places joined two words: a footnote mark or an exponent fused with its neighbour ("Sloss6Edited", "1.16" for
  1.1 to the 6th), and SRE's nine stray `</br>` (html.parser drops them; a browser reads a line break). With superscript and
  subscript kept as edges and `</br>` read as `<br>`, 1,230 spaces went and 15 joins remained, each as a browser shows it ("/ˈɑːrbɪtrɑːʒ/",
  "1/Nth", "1,000P", and SRE's own "USENIXConfiguration", whose markup has no space). Formulas got the delimiters a PDF
  page's reading writes (\( \), \[ \]); the chat's typesetting now unwraps a delimited formula line, which PDF quotes
  needed already. The T-accounts' alternative, a table, was checked too: the 21 the reader had written as tables put all
  dates in one cell and all amounts in the next, so the index lost which amount belongs to which date; the lines keep the
  pairs. A table with one row per entry needs a reader rule and a re-read, after the capstone (157.a).
- **Two runs lost to the network before the measurement.** The before-run stopped at its first key read with a connection
  reset by the remote host, then again after 25 of 61 questions in the generator. `answer_eval` now goes on when the key
  cannot be read before a run, and asks a question again (up to twice) when the connection drops before its answer, never
  after one. About 0.15 USD lost.
- **The gate holds** (`answers_phase6-text-as-shown` against `answers_phase6-baseline-61`, both through the server, the
  baseline's plans frozen): recall@5 +0.000, behaviours 46 → 46, on the 25 altered questions 21 → 22 behaviours and 23 → 24
  verified quotes. Every source was indexed again (both loaders' versions are part of every fingerprint), 0.031 USD; the free
  and licensed exports were written again first, because the quoted text of a PDF page is kept by the loader's version. Fewer
  quotes were dropped (12 → 6), but the drops moved on questions whose passages did not change, so that is the generator's
  variance and is not claimed.
- **10 Nov, the generator's own sections (decision 163.a, the operator: "correct it where confidence is high, judge for yourself").** Found by
  line 2's check-along of the operator's Sharpe question; a third finding of that check (a formula attributed to passage [2]) was not a
  fault: the History passage ends with that formula. Before changing the rules, the answers of the two runs that day were
  counted for an own gaps section (6 and 4), an own follow-up section (2 and 1) and an offered action (0 and 0). A code filter
  that cuts such sections out of the answer was weighed and left: the model titles them differently each time.
- **10 Nov evening, the gate after the walk's first fixes holds** (`answers_phase6-glossary-terms`): only q02 and q06 saw
  other passages, so the 934 glossary definitions now carrying their terms did not crowd out the explanatory sections the
  questions expect, the risk named before the run (exercise sections had done so in phase 6).

- **11 Nov, the gate after PDF loader 10 and validator page/1.3 holds** (`answers_phase6-markers-validator`, against
  `phase6-glossary-terms`, router plans frozen, through the server): section recall@5 +0.000, no expected section moved,
  only i23 saw other passages; the rebuild cost 0.024 USD, the run 0.12 USD. Behaviour 46 → 44, every change on a question
  whose passages did not change, so the generator's variance: q21 and q24 answer → not found, and i15 an error. i15's
  generator ran on to 34,468 characters until the output limit stopped it (`LengthFinishReasonError`), with retrieval at
  recall 1.0; the chat answered "The answer could not be generated this time. Please ask again.", as it should. A loop of
  the generator is a known problem that can show in a demo; asking again is the answer today.
