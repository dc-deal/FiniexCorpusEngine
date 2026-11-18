# Protocol: phase 1, reader format, checks and judge

The record of how this phase came about, mistakes included.

## 2026-10-30

- **`docling-core` without torch:** a dry-run install lists 39 packages, none of them torch, transformers, onnxruntime or tokenizers;
  with the pinned requirements only 10 packages are new, and `pip check` is clean. So it can be used directly.
- **Image limit:** on the free token-counting endpoint, `transformations: {"oversized_image": "error"}` on the image block is accepted, and a
  3000 x 4000 image then gets a 400 instead of a silent downscale. Placed inside `source` it is rejected. The JSON schema is accepted
  with effort and thinking set, on Haiku and Sonnet.
- **Formula sheet:** KaTeX's MathML, rendered natively by headless Edge, gives a crisp image without downloading fonts or CSS.
- **Repository layout:** all code moved under `src/backend` and `src/frontend`, with an editable install through `pyproject.toml`.
  241 offline and 5 slow tests stayed green. The local course-material folder was renamed so the ignore rule for leading underscores covers it.
- **Mistakes:** a Python edit through a Bash heredoc lost the backslashes in a test file, the known trap: scripts go to a file first. A stray
  `cat` waited on standard input and held up a command for two minutes. The attribute parser returns the index of the closing brace,
  not the length, so the first version reported "text after the attributes" on every block; a test caught it.
- **Gates** were written into the chapter before any reading of the new contract existed.
- **A parallel run stopped early:** eight agents building the modules stopped after 41 minutes. Three had written most of
  their modules, which were complete enough to pass 675 tests; five had not started. The rest was written directly.
- **First mini pilot (80 readings, 0.78 USD):** the content was far better than the format check suggested. Valid on the first attempt:
  Haiku 60 % and 35 %, Sonnet 85 % and 90 %. Most failures had every word intact: a stray `level` attribute on headings (12), an invented
  span class such as `.link` (8), `<strong>` in a table cell (3). These became warnings. A ragged table became a stage 2 suspect, since its
  text is there and only its place is in doubt. **→ now** Sonnet 100 % and 95 %, Haiku 70 % and 70 %, on the same stored readings. The
  change was made after seeing results, so both numbers are recorded here.
- **Stage 2 raised false alarms on right readings:** 18–50 % of the readings gold shows clean. Causes: the layer glues a symbol to a word
  (`y-intercept` against `\(y\)-intercept`), a tag like `LO` printed as a picture, table cells drawn as paths. **→ now** 0–25 %, and of the
  remaining cases on Sonnet's Markdown readings two of three are real: a table title left out, a ragged table. Planted prose errors are
  still caught at 85–100 %.
- **The reader's bare `$` inside `\( \)`** cost four inline formulas on one page, in the first run and again after the prompt said
  otherwise. Inside math a `$` can only be a dollar sign, so it is repaired at parsing. **→ now** Sonnet's Markdown: 112 of 112 formulas exact.
- **Three table cells differ in every Sonnet reading:** Finance p. 393. The gold lacks that row (its header row holds only math), so these
  are the gold's gaps, not reading errors. Not compared with the page by eye.
- **The prompt recheck** came to 0.1564 USD against an estimate of 0.1339, so the readings cost 1.02 USD against a budget of 1 USD.
- **A mistake of mine:** a chained command committed with 46 tests red, because a list built at import time ignored the tests' cells. Fixed in
  the next commit. Commit commands now run only after a separate look at the test result.
- **Haiku as judge failed the control:** it sent 8 of 8 clean pages to the bin while catching nearly every planted error, so its detection
  rate means nothing. With a sharper prompt: 6 of 8, and findings such as "printed 0.6875, written 0.6875". The clean control is the reason
  this was seen at all.
- **Sonnet as judge:** 0 of 8 clean pages to the bin, 48 of 49 planted errors. The miss is a no-op: the planted-error plan was made before a mutator that added
  spaces to a blank line was fixed. The format was frozen by hashes the same evening.
- **Open after this phase:** the reviews by independent agents planned for this phase did not run. The modules were checked
  by tests, by the planted errors and by reading the results, not by a second reader.
