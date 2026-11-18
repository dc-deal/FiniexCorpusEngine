# Phase 2: reading the corpus in batches

## Plan

**What.** Every page of the free corpus's four PDFs is read on the frozen contract `page/1` (phase 1): 1,652 pages of the two
OpenStax books, the Kelly-criterion article and the walk-forward preprint. The reader is Sonnet with Markdown blocks at high
resolution, through the Message Batches API. Then the check flow of phase 1 runs on every reading: stage 1 the format, stage 2
the content against the PDF's text layer, stage 3 the judge on a random sample of 20 pages per work plus every suspicious page
**→ now** (decision 83.a, 4 Nov) and every page with a block stage 2 cannot check: a table printed as an image, text inside a
figure, a formula drawn as paths.
The HTML sources (the SRE book, Lefèvre, Kleppmann, the Wikipedia articles) need no reader: their markup already carries the
structure. New free sources from the shortlist follow once their licences are recorded in the catalog.

**Which technique.** As in phase 1: the nearest lesson is multi-representation indexing (rag_from_scratch part 12); the
conversion stage itself lies outside the course.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| Read only the pages with formulas, tables, figures or code | It needs a page classifier first, which costs days, and two routes per work make two kinds of trace. Reading every page costs about 25 USD |
| The standard API instead of batches | Twice the price, and nothing here needs an answer within the hour |
| Haiku as the reader | 70 % valid on the first attempt in the mini pilot, one raster table lost, useless as a judge (phase 1) |
| A list of 1,652 pages as the cell's page source | The PDF, fixed by its checksum in the manifest, already says which pages there are. The cell names its works and takes their cards from the pilot's list, so a page the pilot read under the frozen prompt keeps its key and is not bought twice |

**The cell.** `FREE-SM` in `src/backend/conversion/reading/reading_cells.py`. The dry run on 2026-11-02 planned 1,645 requests for an
estimated 24.78 USD; 7 pages were already read in the pilot's recheck.

## Gates, written on 2026-11-02, before any result of this run exists

- **Cost:** what the batches actually cost stays within 1.3 times the estimate (32.2 USD), the spend guard's own factor. Above that
  the next batch waits until the difference is explained.
- **Format:** at least 95 % of the readings are valid on the first attempt (the pilot: 20 of 20). The rest get one format retry
  (`--retry-malformed`), the only retry there is.
- **Blocked pages:** expected none on free pages (the pilot saw 0 on only 12 distinct pages, a thin base). Every block is counted; the
  page keeps its text-layer conversion and is never sent again.
- **Cut off at the token limit:** at most 1 % of the pages.
- **Stage 2:** at most 25 % of the readings suspicious (the pilot: 3 of 13 on readings gold shows clean). Above that the thresholds are
  calibrated before the judge runs.
- **Judge:** a work stops above 3 bad pages in its random sample of 20. These starting values meet a real run here for the first time.

## Report

**The reading run, 2026-11-02:** 1,645 requests in 20 batches, 23.46 USD against an estimate of 24.78.

| gate | result |
|---|---|
| cost within 1.3 times the estimate | 23.46 USD, 0.95 times the estimate |
| at least 95 % valid on the first attempt | 1,524 of 1,601 unblocked pages, 95.2 %; **97.8 %** under validator `page/1.1` |
| blocked pages: expected none | **44 (2.7 %)**, all in long prose; they keep their text layer |
| at most 1 % cut off | none |

- **The filter blocks freely licensed text too.** The pilot's "none on free pages" rested on 12 pages. The 44 pages are long
  prose; judged from the PDFs alone, 2 of them hold a table or a drawn figure, so the text layer loses almost nothing there.
- **Validator `page/1.1`:** most format failures were dollar amounts that the check for `$...$` math mistook for formulas when an
  inline mark or an escaped `\$` followed on the same line. The check was corrected after these results, the stored readings were
  checked again without a new reading, and both numbers are recorded. The pages still malformed get their one format retry.

**Stage 2 and the judge, 2026-11-03:**

| measure | result |
|---|---|
| stage 2 suspicious | 183 of 1,583 readings (11.6 %), within the gate of 25 % |
| judge, random sample (20 per work, 11 for the article) | **0 bad of 71**; no work stopped |
| judge, the 183 suspects | 15 bad (8 %); the other 168 were stage 2's false alarms |
| the bin, for a person | 40 pages: 23 malformed after their retry, 15 the judge found bad, 2 without a page |
| judge cost | 1.70 USD against an estimate of 2.15 |

| state of a page | pages |
|---|---|
| ok, judged | 239 |
| ok, not judged (passed stages 1 and 2, outside the sample) | 1,329 |
| bin | 40 |
| blocked by the provider, text layer kept | 44 |

**→ now, the judge on every page stage 2 cannot check** (decision 83.a, 2026-11-05): 861 pages that had been quoted unjudged,
each with a table printed as an image, text in a figure or a formula drawn as paths. The judge found **28 bad (3.3 %)**, 14 in each
book; among their findings 12 wrong values and 11 wrong words, 4 omissions and 3 inventions. Judge cost 5.66 USD against an
estimate of 7.19. The states now:

| state of a page | pages |
|---|---|
| ok, judged | 1,072 |
| ok, not judged (passed stages 1 and 2, holds no block stage 2 cannot check, outside the sample) | 468 |
| issue (a person looks; called the bin until 97.a) | 67 (43 the judge found bad, 23 malformed after their retry, 1 without a page) |
| blocked by the provider or declined by the reader, text layer kept | 45 |

- **0 of 71 in the sample** bounds the share of bad readings among the unjudged ones at about 4 % (95 %, rule of three); the
  sample is small, so that is a bound, not a rate.
- **Stage 2 is a cautious net:** it sends twelve times more pages to the judge than the judge finds bad. That is its job, since
  a missed error costs more than a judged page; its precision is worth tuning once the issues have been read by a person.
- **What the judge named:** omissions 44, a wrong word 4, a wrong value 2, a structure error 1, an invention 1 (findings, several
  can sit on one page; minor ones leave a page ok).

**A person judges the judge, 10–11 November: prompt and context engineering, measured.** judge/1 had sent 16 free pages to
the issues. A person walked all 16 against the page image and recorded a verdict on each (decisions 146.a and 188.a):
14 readings were right, 2 wrong (accounting p. 969, an index number; finance p. 94, a chart's description). Three new judge
versions were tried as prototypes: frozen and hashed beside the active one, run on chosen pages, never served (147.a).

| version | what changed | agrees with the person on the 14 right pages | the 2 wrong pages | calibration: planted errors caught, clean pages flagged | USD per page |
|---|---|---|---|---|---|
| judge/1, active | | 0 (these are the pages it called bad) | both called bad | 48 of 49, 0 of 8 (phase 1) | 0.0078 |
| judge/2 | the prompt: one sentence on proper names | 10 | both called bad, p. 94 for a wrong reason | 48 of 48, 0 of 8 | 0.0078 |
| judge/3 | judge/2, plus: a finding needs printed and written to differ | 9 | both called bad, p. 94 for a wrong reason | 48 of 48, 0 of 8 | 0.0078 |
| judge/4 | judge/2's prompt on another model (Opus 5.5), proposing rules for the reader | **13** | p. 969 bad; p. 94's error named right but graded minor | 47 of 48, 1 of 8 (a true omission) | 0.014 |

- **Context before prompt.** On finance pp. 136 and 562 every judge was wrong for one reason: its view of the reading lacked
  each glossary entry's term (decision 190.a), so it called the terms missing. No prompt could have fixed that; the view
  did. Without those two pages: judge/4 11 of 12, judge/2 10, judge/3 8.
- **A second model breaks a blind spot the first shares with itself.** Reader and judge were one model. On p. 94 the reader
  put a chart's crossing at 2000; judges 1 to 3 objected, but read it as 2006–2007. The axis is in chained 2012 dollars, so
  real and nominal GDP meet at 2012 by definition. judge/4, on another model, read 2012.
- **The instrument is measured too.** The one clean calibration page judge/4 flagged holds a real omission: the pilot reading
  the set keeps lacks the table title of accounting p. 69. The served reading has it. No earlier judge found it.
- **The new weakness is severity.** judge/4 finds the right block, but grades it differently from the person: p. 119's
  table grid major, though every value is right; p. 94's chart minor, though the description is wrong.
- **Rules for the reader, proposed and not applied.** judge/4 proposed 26 rules, merged into nine themes (table
  grids, values read against a chart's axis, counts in a description only as drawn, list markers, ...). Three are what the
  person's walk had named before. A reader prompt built from them is the next prototype, measured the same way.
- **Where it stands:** judge/1 stays active and judge/4 a prototype until a person decides, so nothing served changes. Every
  version's verdict is in `corpus/readings/index.json`, per attempt; the walk and the runs are in the protocol.

**A person's verdict and a delegated review, kept apart (18 November).** From 17 November a Claude Code session reviewed
judge issues on the operator's delegation, recording its clear verdicts (confidence 0.9 or above) through the same command a
person uses, its giver named `<model> session, delegated by the operator (<day>)`. Such a verdict decides what is served as a
person's does, but it is never called one: the route says "an automated review (delegated by the operator) accepted the
reading", the export marks each verdict `by_a_person`, and only a person's verdict protects a page from being read again
(decision 191.a). The operator's reason: a person who signs a verdict takes the responsibility for it, as with a contract.

**A direct reading, for the hard cases only (decision 280.a, 17–18 November).** Once the API credit ends, a page whose reading
stayed malformed after its format retry may be read in a Claude Code session, as its own route (`direct_reader`: cell
`*-DIRECT-OPUS`, the deviation "read in a Claude Code session (280.a)"), stored, checked and judged like any reading; its cost is
not measurable by an API ledger and says so. A page a provider's filter blocked or a reader refused is never read this way,
since that would pass the same model's safeguard by another door. A reader that answered with prose instead of a page counts
as having refused: every such answer read on 18 November declined the page as a published book's text, so `no_page` in a page's
history keeps it out too; the second reader of another company takes such a page as it takes a refused one (63.a). A page the
session read stays in the cell's list whatever came of it, so the cell's report keeps
its check; a served page that left the list would have lost its state and fallen back to its text layer, as the second
reader's chosen pages once did.

**The loop closed once: a reader prompt built from the judge's and the person's findings, measured, 11 November.** page/2
is page/1's rules unchanged plus eight (table grids with operator columns, T-accounts as tables, a table's printed title,
legible images of tables read, chart values read against the axis, counts only as counted, a photo's own text left out,
index numbers digit by digit). It read 26 free pages as a prototype, never served, against the reading each page serves
today; the gates were written before the run (protocol).

| measure | page/1, served today | page/2 |
|---|---|---|
| mini pilot's 20 pages valid | 20 | 20 |
| formulas exact against publisher gold | 112 of 112 | 112 of 112 |
| table cells exact against publisher gold | 221 of 224 | **224 of 224** |
| pages clean against gold | 13 of 14 | **14 of 14** |
| the walk's six reader errors fixed, checked by code | 0 | **4** (T-accounts, image tables, an index number, a photo's text); 1 half (a table grid); 1 not (a chart's crossing) |
| judge/4 on the readings | | 24 ok, 1 issue (the half-fixed grid), 1 malformed for an unrelated reason |

- **Rules change how a model writes, not what it sees.** Structure, discipline and legible images improved; the chart's
  crossing on finance p. 94 did not: the reader now reads the axes and still puts the crossing at 2000–2005. That is
  perception, and a stronger model, not a longer prompt, is the lever there.
- **A judge's single answer is not a measurement either:** judge/4 read p. 94 right once and passed page/2's wrong
  description the next time.
- page/2 stays a prototype; serving it means reading the free corpus again (about 21 USD), which waits for a person's
  decision. Run it with `python -m backend.conversion.measurement.reader_prototype report`.
