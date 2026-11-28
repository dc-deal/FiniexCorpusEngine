# Protocol: phase 4, local readers on a bench machine

The record of how this phase came about, mistakes included.

## 2026-11-26/27, the night

- **The machine.** ROCm 7.1.1 from the Ubuntu archive (109 packages, 0.95 GB) found the GPU as gfx1100, 25.75 GB. llama.cpp
  was built with HIP for gfx1100 in four minutes. PyTorch 2.15.0 has ROCm builds for Python 3.14, so no older Python was
  needed. The weights came at about 9.4 MB/s, 26.5 GB in all.
- **Only free pages.** The mini pilot's 20 pages, rendered by the pipeline's own renderer at the tier Sonnet got, with
  `page/1` and each page's user turn byte for byte.
- **Mistake in our script, not the model:** PaddleOCR-VL's first run failed on all 20 pages. Its card's line
  `image_processor.min_pixels` no longer exists in transformers 5.24.1, which keeps sizes in `size`, whose default is
  already the card's 1280·28·28. Fixed once, read again.
- **A gap in the night's chain:** that first run's smoke test passed although its one page had failed, because the script
  recorded the error and exited normally. A run whose every page fails now exits with an error, so the chain stops there.
- **A claim corrected:** the night's log said Qwen's boxes lie on a 0–1000 scale. Mostly true: on 5 of the 20 pages one box
  or more was written in pixels, the footer at a height up to 2,140. The import rescales only a box wholly on the scale and
  counts the others.
- **GLM-OCR in its text mode left a page's table out** (finance p. 298); it has a mode of its own for tables. A finding for
  the comparison, not something the converter repairs.

## 2026-11-27, the import

- **Test cells and the Lab.** Four test cells, nothing buys them; their readings are found by their label, since no
  pipeline cell asks their question (Qwen's system prompt is `page/1`, but its mode, `local`, is no pipeline cell's).
- **Checked:** 80 stored, a second import stored nothing; the free export lists the four beside the served reading on
  every page, the served one unchanged; the free shelf's counts are unchanged to the page.
- **Not repaired on purpose:** inline `$…$` stays as written. Turning it into `\( \)` would be a guess on finance pages,
  where most dollar signs are money.

## 2026-11-27, prompts and verdicts

- **The agents' prompts had no fixed text.** Of the 87 reader agents' prompts sent from 19 to 26 Nov, 2 lines stood in
  every one: each run's prompt had been written anew, with notes for that run. A template version per prompt
  would have been one version per call. All 145 agent prompts of those days were saved locally on 27 Nov, before the
  transcripts' cleanup; tying each to the readings and verdicts it made is the backfill still to do. **→ now** (the same
  day): done, see below. From now on code renders the prompt from a registered template (decision 22.a).
- **The prompts' authors from the transcripts:** the transcripts left reach back to 30 Oct and show who wrote
  `page/1`, `judge/1` to `judge/3`, `classcheck/1` and `correction/1`; for `page/2`, `page/3`, `judge/4` and
  `correction/2` they show nothing, and those origins stay null.
- **Mistake found by the first run:** the session judge named a page's folder by its work and page, so four test cells on
  the same 20 pages wanted one set of folders and three found it taken. A test reading's folder now carries its cell.
- **The judge's plan for test cells is its own.** The check flow's plan keeps one reading per page across the cells it is
  given and adds its keys to the pipeline's kept sample; the Lab's plan takes each test cell alone, judges every reading
  the parser can cut into blocks, malformed ones included, and leaves the sample alone. 79 requests: 20 per model, 19 for
  PaddleOCR-VL, whose looped page has no page to judge.

## 2026-11-27, a review and the backfill

- **An independent review of the three commits** (an agent given the code, not our conclusions) found five faults, each
  reproduced, and each now fixed with a test:
  - a promoted page was marked protected, but the commands that read pages again asked only the verdicts, so a re-read
    could replace the person's choice;
  - an accept naming a Lab reading served it past the promotion and its reason;
  - accepting a promoted reading undid the promotion;
  - a reading promoted again after a reset stayed discarded;
  - the view's "standing" counted notes, and so could differ from the verdict the page is served by.
  Smaller: the pipeline's own plan now refuses a test cell, and a time without a zone no longer stops an export.
- **Still open, a design question:** a reset of a promoted page serves the pipeline's reading the person had replaced,
  not the text layer. An accepted page behaved the same way before this work.
- **The backfill, and a mistake in it:** the first pass tied only 1,005 of 2,322 session readings. The batch files a
  reader's prompt names had been reused by later runs, so they listed other pages. The first pass also read only the
  sessions' own transcripts, not the agents' own, and took an agent's kind from how its prompt began, which the first
  nights' prompts did not match. Each agent's own transcript names the prompt it was started with and every folder it
  wrote into. Taken from there, 2,293 of the 2,322 session readings and all 1,334 session verdicts are tied to the exact
  prompt that made them. 29 readings and 57 calibration verdicts point at the entry without text.
- **The reader agents too:** `night_run batch` now writes each batch's agent prompt from `reader-agent/1` beside the
  batch file (`batch_NN.prompt.md`); every page of the batch names it, and the reading stored from it keeps it. A
  licensed run's note is added by code, a run's own note with `--notes`.

## 2026-11-28, the pages looked at, and the verdict

- **The operator looked at the test readings in the Lab** (#18's form, page by page, each reading with its judgement
  beneath). On finance p. 343 MinerU's formula showed "(11.26)" drawn into the fraction. Nobody had flagged it: not the
  validator, not the converter, not the judge, and gold only as a low score (1 of 5 formulas exact) that nobody had
  opened. The cause was ours: MinerU wrote `\tag{11.26}`, LaTeX's own place for an equation number, and the converter
  passed it into the formula instead of `label=`. The served readings never held one; the default reader writes `label=`.
- **Why the judge missed it:** the number is printed and stands in the reading, only in the wrong field. That is form,
  not content, and form belongs to a check by code, which runs on every reading and before any model. Hence validator
  `page/1.5` (49.a), not a line in the judge's prompt.
- **Not imported again (48.b):** with the verdict below, a fairer MinerU score changes no decision; the gap is written into
  the report as a limit of the measurement.
- **The verdict (50.a):** none of the four is strong enough for the pipeline. MinerU, nearest on formulas and tables,
  loses currency signs; the two small document models lose tables; Qwen breaks the format and fills the GPU. The
  bake-off is parked until stronger local readers exist.
- **A mistake of ours, found the same day:** asked whether a larger GPU would help, we compared the night's numbers with
  OmniDocBench v1.6, where PaddleOCR-VL-1.6 scores 96.34 and the leaders are all small (0.8 to 1.2B). PaddleOCR-VL had
  found 21 of 224 table cells here. The night had given PaddleOCR-VL and GLM-OCR the whole page with a single OCR prompt;
  both are built as a layout model that cuts the page into regions, each then read with its own task prompt (text,
  table, formula). They never got their table prompt, and the boxes the layout stage gives were never there to keep.
  MinerU, the one model run in its own pipeline, came out best. The verdict above is therefore unfair to those two; the
  report says so, and a second measurement in their own pipelines is the operator's to decide.
- **The second measurement (51), the same afternoon, cut to save the week's tokens:** an independent review of the plan
  first (an agent given the code and the vendor's sources, not our conclusions). Its three critical findings held where
  we could check them: the vendor ships the whole pipeline without PaddlePaddle on the GPU; that pipeline strips every
  `$` from a block with math (seen in the installed code); the night had shown the page at 868×1120 and our importer had
  turned tables into prose. On the machine: Python 3.13 through uv (PaddlePaddle has no 3.14 wheels), OpenCV's headless
  build (no libGL on the server; the run script answers PaddleX's check for the desktop build's name). Table cells rose
  from 21 to 221 of 224, the default reader's own count. The review of the finished script (56.a), the judge on 17 more
  pages and the view wait until the tokens are back.
