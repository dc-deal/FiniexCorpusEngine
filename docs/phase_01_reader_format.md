# Phase 1: reader format, checks and judge

## Plan

**What.** A vision model reads one page image and writes a page file: verbatim text, formulas as LaTeX, tables as HTML,
figures with their printed labels and a description marked as derived. Three stages check each reading before it may be quoted:

1. **Format (code):** the file parses against contract `page/1`. One retry, then a bin for a person.
2. **Content (code):** the words against the PDF's own text layer, which the reader never saw, so it is an independent witness;
   formulas through KaTeX, code through `ast.parse` and its indentation against the layer, tables as a grid.
3. **Judge (a model):** on a sample per work and on everything suspicious, it sees the page image, the reading and the formulas
   rendered. Outcomes: ok, the bin, or the work stopped. A person stays the final judge.

**Which technique.** The nearest lesson is multi-representation indexing (rag_from_scratch part 12): one source, several
representations. The conversion stage itself lies outside the course, because the course's loaders take the text layer as it is, and in
the free corpus that layer has no formula where the formula is drawn as vector paths and no cell where a table is an image.

**Why this beat the alternatives.**

| alternative | why not |
|---|---|
| The text layer alone | It loses exactly the content that needs quoting: drawn formulas, raster tables, figure text, code indentation |
| Docling's or Marker's own conversion | They need local models and a GPU for the hard pages, and their output has no independent check |
| DocTags, DocLang or HTML as the reader's format | More tokens, every body needs escaping, and no field for a page's printed number or an uncertain reading |
| Correcting the reader's output by hand to make gold | Gold anchored on the model; plausible errors survive. The publisher's own markup does not depend on any model |

**The structures lean on DoclingDocument** (`docling-core`, which needs no torch: 39 packages, measured 2026-10-30). Every class of the
contract names the Docling label it becomes (`contract_vocab.json`), and a test holds the mapping, so the real model can come later.

## Gates, written on 2026-10-30, before any reading exists

The mini pilot reads 20 free pages with four cells: Haiku and Sonnet, each with Markdown blocks and with JSON through structured
outputs. 14 pages have publisher gold (MathML, tables, prose); 6 more cover boxes, figures and console code. Budget: at most 1 USD for
the readings, at most 1 USD for the judge. With 20 pages only large differences count, and every rate is shown with its n.

**Format: Markdown or JSON, on the same pages.** Markdown is the default, for its raw bodies, its fewer tokens and because a cut-off
answer keeps its closed blocks. JSON wins only if one of these holds, and it has no silent corruption (a control character in a body,
such as the TAB a lost escape leaves in `\text`):

- Markdown's valid share on the first attempt is below 90 % while JSON's is at least 97 %.
- JSON's formula exact or table-cell exact rate is at least 5 percentage points above Markdown's, paired on the same pages.

**Model.** Sonnet reads the structure pages (formulas, tables, figures, code), as already decided. The pilot answers whether Haiku
suffices anywhere: only if it stays within 3 points of Sonnet on the class in question.

**Reader targets (proposed in the design, with these n unproven):** formula exact against gold at least 0.9, KaTeX render 100 %, table
cells exact at least 0.95, printed label 100 %, prose 1 - normalised edit distance at least 0.98. If no cell reaches a target, the
prompt is revised once, with a new prompt hash, and measured again within the same budget. If it still fails, a person decides.

**Stage 2.** Reproduces the design's 8 of 10 planted errors on the example page. On readings that gold shows to be right, at most
10 % of pages are suspicious; above that the thresholds are calibrated before the format is frozen.

**Judge.** The cheapest model that catches at least 80 % of planted errors in formulas and tables, the classes stage 2 cannot check, with
false alarms on at most 10 % of clean pages. If no model reaches this, the judge runs on but its bin no longer stops a work, and
a person decides what it means. The starting values, 20 pages per work and a stop above 3 bad, are checked against these rates.

**Freeze.** The winner's prompt, vocabulary and validator are frozen by their hashes as `page/1`. Batches of phase 2 run only on the
frozen contract.

## Report

**Decided by the gates:** Markdown blocks; Sonnet reads structure pages and judges. `page/1` is frozen by its hashes
(`src/backend/conversion/frozen_contract.json`, held by a contract test). The mini pilot cost 1.51 USD: 1.02 for readings, 2 cents over
their budget, and 0.49 for the judge.

**Readings, on 20 free pages, 14 of them with publisher gold:**

| measure | Haiku, Markdown | Haiku, JSON | Sonnet, Markdown | Sonnet, JSON |
|---|---|---|---|---|
| valid on the first attempt | 14/20 | 14/20 | 20/20 | 19/20 |
| USD per page (batch) | 0.00076 | 0.00114 | 0.01628 | 0.02091 |
| output tokens per page | 1,893 | 2,702 | 1,907 | 2,551 |
| silent corruption (control characters) | 0 | 0 | 0 | 0 |
| formulas exact, against the publisher's MathML | 109/112 | 108/112 | 112/112 | 112/112 |
| table cells exact | 224/224 | 221/224 | 221/224 | 221/224 |
| values of raster tables found | 2/18 | 18/18 | 18/18 | 18/18 |
| prose, 1 - normalised edit distance | 0.999 | 0.997 | 0.999 | 1.000 |
| printed page number | 14/14 | 14/14 | 14/14 | 14/14 |
| furniture kept out of the body | 30/30 | 30/30 | 30/30 | 30/30 |

- **Format.** JSON cleared neither gate: its valid share is not above Markdown's, and no content rate is 5 points higher. It costs 28 % more on Sonnet. Its
  constrained decoding did remove silent corruption, which never occurred in Markdown either, since bodies there are raw.
- **Model.** Haiku stays within 3 points of Sonnet on formulas, tables and prose on these pages, at a twentieth of the price. Its valid share is
  70 %, it lost one raster table, and figures and code have no gold here, so Sonnet stays for structure pages as decided.
- **The three table cells** that differ in every Sonnet reading lie on one page, in a row the gold itself lacks.
- **The validator was relaxed after the first run,** on the evidence: most invalid readings had every word intact. The first run's valid shares were
  60, 35, 85 and 90 %. The protocol records this, because it was done after seeing results.

**Stage 2** reproduces the design's result on the example page: 8 of 10 planted errors caught, and the two it misses are the classes without a text layer.
Planted on Sonnet's readings:

| group | caught by stage 2 |
|---|---|
| prose, 8 kinds | 147/154, 85-100 % per kind |
| caption numbers | 11/11 |
| code | 3/3 |
| formula label | 13/13 |
| formula body (drawn as paths) | 1/29 |
| table cell, table row | 3/8, 8/10 |
| a label inside a figure | 0/1 |

On Sonnet's Markdown readings gold shows clean, it raised 3 of 13: a table title really left out, a ragged table whose place in the print nobody has compared by eye, and one
lone digit, probably from a subscript, the one clear false alarm.

**Judge,** on 8 clean readings and 49 planted errors, the same set for each model, blind to stage 2:

| | clean pages sent to the bin | planted errors sent to the bin | USD per page |
|---|---|---|---|
| Haiku | 8/8, after a sharper prompt 6/8 | 48/49, then 49/49 | 0.0004 |
| Sonnet | 0/8 | 48/49 | 0.0077 |

Haiku raises an alarm on nearly everything, so its detection rate means nothing, which only the clean control could show. Sonnet caught all 18 formula and table errors.
Its one miss was a mistake of the planting: spaces added to a blank line, which changes nothing. Stage 2 and the judge complement each other as designed: stage 2 is free
and covers text, the judge covers what the text layer lacks.

**What these numbers do not show.** 14 gold pages from free, born-digital books: no scans, and no licensed pages. 0 of 8 false
alarms has an upper bound of about 31 %, and 18 of 18 a lower bound of about 85 % (95 %). The planted errors are plausible but mine, not the reader's own; Sonnet reading and Sonnet judging may
share a blind spot, which planted errors cannot measure. Formula exactness rests on a comparator that agreed with the gold on all its formulas and caught all mutations,
without a person reading every pair. Figures and code have no publisher gold here. The starting values of the check flow, 20 pages per work and a stop above 3 bad,
have not met a real run.

**The validator after the freeze.** The prompt and the vocabulary stay frozen; the validator changed four times, each a version of its
own in `frozen_contract.json` with the hash it replaced and why, and each time the stored readings were checked again for free before
the change counted (`vision_batches recheck`). Page/1.1 to 1.3 stopped failing readings that lose no text. **Page/1.4 (18 Nov 2026)** lets a
page print a backslash as text: a table head such as `rate&#92;term`, rows by rate and columns by term, failed every reader, because
the check for a stray LaTeX command outside math read the text after markdown-it and html.parser had decoded `&#92;` and `\\` alike.
It now reads the source as written, so the entity passes and a bare or escaped backslash before letters still fails (a reader that
escapes LaTeX twice writes `\\frac`). The format check's messages also name the page line a fault stands on, beside the block's
opening line: `block b04 (line 26): LaTeX command outside math on line 28: \HL`.
