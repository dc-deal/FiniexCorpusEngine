# Phase 4: local readers on a bench machine, measured as test readings in the Lab

Issue #17 (and #6, whose reader this is). The view's side is issue #18.

## Plan

**What.** A page reader that runs on our own hardware: no provider's filter, no API cost, and a night's run that needs nobody
awake. A second machine with a 24 GB GPU (an AMD RX 7900 XTX, ROCm) joined the app park as the bench machine. Four open
models are compared on the same pages, and the best one becomes a reader of its own, for the pages no provider will read
and for runs the API budget cannot carry.

**Technique.** A bake-off against publisher gold (the mini pilot's 20 free pages, 13 with exact truth from the publisher's
own web edition, phase 1), every reading also judged by the pipeline's judge. The models:

| model | size | way in | prompt |
|---|---|---|---|
| Qwen3-VL-30B-A3B-Instruct, Q4_K_M | 19.6 GB | llama.cpp's server (HIP for gfx1100) | `page/1`, byte for byte as Sonnet got it |
| PaddleOCR-VL-1.6 | 0.9 B | transformers on PyTorch for ROCm | its vendor's `OCR:` |
| MinerU2.5-Pro (2605) | 1.2 B | mineru-vl-utils, two-step extraction | the package's own |
| GLM-OCR | 0.9 B | transformers on PyTorch for ROCm | its vendor's `Text Recognition:` |

**Test readings, the Lab.** A reading made beside the pipeline is a test reading. It is stored like any reading, with its key,
image, prompts, parameters, seconds and GPU memory, and it stands in the Lab: never chosen, checked or served, so nothing a
client sees changes. A test cell is a cell nothing buys (`reading_cells.TEST_READING_CELLS`); its readings are imported
(`backend.conversion.reading.local_reader`) and found by their cell's label. The export lists them beside the pipeline,
marked `prototype` and `test_reading`, as it lists a reader prototype's (phase 2).

**Into page/1 by code, never by hand.** Qwen answers in `page/1`. Its boxes lie on its own 0–1000 scale, mostly: a box
wholly on that scale is rescaled to the image's pixels, any other is kept as written, and the record counts both. The
document models answer in Markdown, and a converter (`markdown-to-page1/1`) makes `page/1` blocks of it: display formulas,
HTML and pipe tables, headings and paragraphs. Each block gets a box over the whole page, since these models give none, and
the front matter they cannot know is filled and named as filled. Dollar signs stay text: on a finance page `$` is money, so
`$…$` is never turned into math by guess. The model's own answer is kept beside the reading, by its sha256. A reading's key
covers the image, the prompts, the parameters, the model's answer and the converter, so an import run twice stores nothing
new.

**Every prompt traced to its origin.** Every version in `prompt_versions.json` names who wrote it: a person, a model or a
vendor, on which day, from which source, and how that is known. The past is filled in only with what is certain: the
session transcripts left on 27 Nov show who wrote most prompt files; where they show nothing, the origin stays null
and says so. An origin that names a model as an author is kept on this machine only, and the registry says so. The local models' own prompts are registered as their vendors' (`OCR:`, `Text Recognition:`); MinerU's
are its package's and were not copied, so its entry has no file. The prompts that start a Claude Code session's agents were
written anew for each run until 26 Nov; from now on they are rendered by code from a registered template
(`judge-agent/1`, `reader-agent/1`) with the run's details, kept by their sha256, and every request and verdict names the
prompt that asked for it. An agent whose prompt is lost points at an entry without text that keeps what is still known.

**What a person's verdict answered.** A person's verdict records the judge's record it answered; one given before that
was recorded is assigned the judgement that counted on its reading when it was given, marked as derived. The export says
which verdict stands: the latest counting judgement of the served reading, and of a person's verdicts the latest on each
block. Every reason has a short label beside its sentence.

**Promote.** A person makes a Lab reading the page's reading (`human_verdict promote`, and the view's button): a reason
from a fixed list (`better`, `served wrong`, `only one`, `other` with a note), appended to `promotions` and never changed.
The export pins the promoted reading as it pins a reading a person accepted, the later of the two acts standing; the page is
protected, its route says "promoted from the Lab by a person", and the person's act stands over the judge's finding, as an
accept does. Only a valid `page/1` reading of that page's Lab can be promoted, and only by a person, never by a session on
the operator's delegation.

**Gates, written before any score:**
- Every test reading is listed in the Lab and in no page's choice: the free shelf's counts stay exactly as they were.
- The images the models read are the images the pipeline read (sha256 equal on every page).
- The report sets each model beside the default reader on the same pages: publisher gold (formulas exact, table cells,
  words), the judge's verdicts, seconds per page, GPU memory, and how many answers needed no repair to fit `page/1`.

## Report

**The night of 26–27 Nov 2026** (the bench machine, 80 minutes from the first package to the last page; each model alone on
the GPU, one page at a time, greedy decoding):

| model | pages | seconds per page, median (range) | GPU memory | stopped by |
|---|---|---|---|---|
| Qwen3-VL-30B-A3B Q4_K_M | 20 / 20 | 17.3 (13.0–29.1) | 23.1 GiB, with a 32k context | 20 stop |
| MinerU2.5-Pro | 20 / 20 | 13.6 (5.9–34.4) | 2.5 GiB at peak | the two-step extraction |
| GLM-OCR | 20 / 20 | 10.0 (4.6–36.2) | 3.0 GiB at peak | 20 stop |
| PaddleOCR-VL-1.6 | 20 / 20 | 17.9 (6.4–221.0) | 1.9 GiB at peak | 19 stop, 1 at its token limit |

PaddleOCR-VL's 221 seconds are one page whose table row of fifteen equal coupons it kept writing until its limit (672 times);
greedy decoding without a repetition limit allows that. The three document models ran through plain transformers; their
cards recommend vLLM, so these speeds are a floor, not their best.

**Imported (27 Nov):** 80 test readings, 20 per model, found again by a second import as already stored. The images are the
pipeline's (20 of 20 equal), and the free shelf's counts are unchanged (1,822 read, 1,814 passed, 4,096 served, 1,779 from
readings). How many answers fit `page/1` without repair:

| model | valid | malformed | why |
|---|---|---|---|
| MinerU2.5-Pro | 19 | 1 | a `\times` outside math |
| PaddleOCR-VL-1.6 | 15 | 4, and 1 truncated | formulas written without math delimiters |
| Qwen3-VL-30B-A3B | 12 | 8 | inline math as `$…$`, although `page/1` asks for `\( \)` |
| GLM-OCR | 11 | 9 | inline math as `$…$`, and dollar signs inside formulas |

Qwen was given the rule and did not keep it; the document models were never given it. Their answers are stored as they
came, and the count is a measurement of its own: how much repair a model needs before its output fits the contract.

**Next:** the judge on the 80 readings, the gold scores, and the comparison report, once the view shows readings and their
verdicts in one form (#18).
