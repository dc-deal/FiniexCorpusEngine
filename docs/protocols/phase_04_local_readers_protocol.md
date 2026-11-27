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
