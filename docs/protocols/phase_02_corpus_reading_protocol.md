# Protocol: phase 2, reading the corpus in batches

The record of how this phase came about, mistakes included.

## 2026-11-02

- **A second line of work** started beside this one, a diagnostics frontend in its own git worktree. Its first run of the
  offline suite there failed 2 of 770 tests: the reading store's guard followed the worktree's link to the data folder into the
  main tree and refused it as "another git work tree". The guard now compares git's common directory, so every worktree of this
  repository counts as its own and any other repository is still refused (commit 82bb4bf, with a test on a real repository and
  worktree built in a temporary folder).
- **The corpus cell names works instead of listing pages** (commit 6ef019d). Its pages come from the PDFs themselves; the work
  cards come from the pilot's page list, so the user turn of a pilot page is unchanged.
- **Smoke test:** 4 of 4 readings ok on the standard API, 0.0845 USD against an estimate of 0.0843.
- **Dry run:** 1,645 requests, 7 skipped as already read (the pilot's recheck pages on the frozen prompt), estimate 24.78 USD. The
  spend guard refused it at its default cap of 5 USD, as designed. The operator approved a cap of 40 USD for the run.
- **A gap in a contract test:** the test that keeps private names out of tracked files read no `.js`, `.ts`, `.vue`, `.css` or
  `.html`, so a web frontend would never have been checked. Found while reviewing the second line's request to change shared
  files; the suffixes are in (commit ec7b03a), and the one tracked minified file, the vendored KaTeX, passes without a false hit.
- **Submitted:** 20 batches of 46 to 101 requests, 1,645 requests in all, estimate 24.78 USD. The packing splits by request count and
  by bytes; each pack took about a minute to upload. The manifests hold every batch id.
- **Mistake:** the submit command ran in the foreground behind `| tail`, hit the tool's 10-minute limit and was moved to the
  background. Nothing was submitted twice: the run continued in the same process.
- **The offline suite now takes 67–76 s,** not the 20 s noted for the RAG sprint's suite; 774 tests.
- **Collected:** 1,524 ok, 75 malformed, 44 blocked, 2 without a page; 23.46 USD against the estimate of 24.78; none cut off.
- **A collect stopped once:** Windows refused to rename a manifest (`PermissionError`, access denied), most likely a scanner or
  indexer holding the fresh file. Nothing was lost: the readings were stored, the batch already deleted at Anthropic, and the
  second run recorded it as gone and collected the rest. The store now tries such a rename up to three more times.
- **The filter blocked free pages too:** 44 of 1,645 (2.7 %), 41 in the accounting book and 3 in the Kelly article, against an
  expectation of none drawn from only 12 pages in the pilot. The blocked pages are long prose (277 to 1,108 words, median 599),
  which fits the guess that long verbatim output is the trigger. Counted from the PDFs alone: 30 have no table, image or
  drawing, 12 only a photo, 2 a table or many drawings. They keep their text layer; no structure pass (the operator, 2026-11-02).
- **Most format failures were the validator's mistake:** 45 of the 77 readings that failed had no error but "possible $...$
  math", and the cases were dollar amounts in prose followed on their line by an inline mark (`[1]{.fn}`, `[years]{.sup}`) or by
  an escaped `\$` in a table cell. The check now ignores both; real `$x^2$` still trips it. This is validator `page/1.1`, with
  prompt, vocabulary and keys unchanged, and the stored readings were checked again for free (`recheck`). It was changed after
  seeing results, so both numbers stand here: valid on the first attempt 1,524 of 1,601 unblocked pages (95.2 %) **→ now**
  1,566 (97.8 %); no reading that was ok became malformed.
- **One format retry** for the 33 pages still malformed, estimate 0.50 USD.

## 2026-11-03

- **The retry mended 10 of 33 pages** for 0.50 USD; 23 stay malformed, so a retry helps little where the validator's
  correction helped much. Standing: 1,576 of 1,601 unblocked pages valid (98.4 %), 23 malformed, 2 without a page, 44 blocked.
- **Mistake:** the first check-flow plan covered the corpus cell only and missed the 7 pages the pilot had already read under the
  frozen prompt, filed under the pilot's cell. Planned again with both cells: 1,652 pages, 1,583 past stage 1.
- **Stage 2:** 183 of 1,583 readings suspicious (11.6 %), within the gate of 25 %: accounting 100, finance 76, walk-forward 6,
  Kelly 1.
- **The judge's sample is kept once drawn,** so that pages a second reader adds later do not move it (commit a41baf8).
- **Judge submitted:** 254 requests in 3 batches (183 suspects, 71 sampled), estimate 2.15 USD.
- **The judge came back:** 254 verdicts for 1.70 USD. The random sample held 0 bad of 71, the suspects 15 bad of 183; 40 pages
  are in the bin. No work stopped.
- **A first, crude count over the licensed PDFs** (free, local, from the PDF objects: an image, more than 40 drawings, a math or
  a monospace font) flags more than half of their pages, well above the pilot's share. It overcounts: pages with almost no
  text layer (scans, a route of their own) count, a small logo counts as an image, and a monospace font for one identifier in
  prose counts as code. To be refined.
- **A free check decides which pages need the reader** (decision 64.a, `page_classes.py`). Researched first: the large
  pipelines route the same way (Docling runs a cheap layout pass and the expensive models only on formula, code and picture
  regions; Marker sends math to its vision model always; LlamaParse re-reads a page whose cheap parse holds a table or image).
  Measured against the free corpus's readings, whose classes the vision reader found (1,583 pages, 1,101 with structure):
  the first rules found 90.8 % of structure pages; adding glyphs drawn as small filled paths (OpenStax draws its formulas) and
  tables from text alignment raised that to 99.7 % but sent 447 of 482 text-only pages along. Tuned offline on the stored
  signals: recall 97.2 % (31 missed) costs 214 false alarms, recall 95.5 % (50 missed) 71. Text-alignment tables stay off; they
  fired on 300 text-only pages. Coloured boxes and drawn bullets are what rules from PDF objects cannot tell from structure.
- **The operator chose the 97 % rules** (decision 66.a): a structure page the rules miss costs more than a text-only page
  they send along, and a layout model (PP-DocLayout through ONNX) waits in the backlog. The recall was measured on textbooks,
  so a cheap model's check of a sample of the pages the rules call text-only guards it on other kinds of book.
- **A review found the check flow selecting readings by the cell label** a record carries: the 7 pages the pilot bought first
  fell out of a plan over the corpus cell, as they had in this protocol's first plan by hand. Readings are now recognised by what
  their keys hold (`vision_batches.readings_of`), so `check_run plan --cells FREE-SM` covers all 1,652 pages; re-planned, it
  found the same 183 suspects and the same 71 sampled pages, and all 254 judge requests already answered. The judge's sample
  is now kept in one file per mirror, so a plan over other cells, a second reader's for instance, keeps it too.
- **The free readings are tracked** (decision 72.a): `python -m backend.conversion.store.reading_export` writes the latest reading of
  every free page and its trace to `corpus/readings/`.
- **Decision 63.a:** a second reader through a modular adapter for free pages the provider blocked or that stayed malformed,
  every such page judged and its deviation from the declared default reader recorded; phase 4 takes it on.

## 2026-11-04

- **A browser update broke the judge's formula sheets:** after an Edge update, `msedge.exe --headless --screenshot` returned at
  once with exit code 0 and wrote no image. The sheet now uses the first installed browser that really writes a probe
  screenshot (Chrome here). Because the judge's key also hashes the sheets' pixels, the new browser would have given every
  judged reading a new key and bought its verdict again; verdicts are now found by the reading they judged. A dry run over the
  free corpus confirmed it: 0 new requests.
- **On the licensed mirror the judge's random sample is doubled** to 40 pages per work, stopping a work above 6 bad, the same
  share as 3 of 20 (decision 74.a).
- **A reader's refusal is a class of its own** (decision 75.a): an answer without a page file that declines the page in prose,
  naming copyright or verbatim transcription and offering a summary, is the reader itself refusing, as the provider's filter
  does. Such an answer is now classed `refused`: it keeps its text layer, gets no retry and no second reader, its summary is
  never used, and it is recorded with its own reason. Only an answer without a page file is ever classed so. It was decided
  after seeing results. The free corpus had one such answer as well, on a freely licensed page; it is refused now too, and its
  report and export were refreshed.
- **Decision numbers renumbered** (2026-11-04): the decisions of 3 and 4 November had reused numbers already taken by earlier
  ones (one "42.a" was both "no new chat frontend" and "a doubled judge sample"). They now run on from 64: 64.a the free check
  per page, 65.a stitching across pages, 66.a the 97 % rules, 67.a the cascade, 68.a the canary rollout, 69.a the self-healing
  demo, 70.a the review's fixes, 71.a one keyword index, 72.a the tracked free readings, 73.a the call log, 74.a the doubled
  licensed sample, 75.a the refused class, 76.a the spend cap, 77.a the HTTP transport. Only the numbers changed.
- **A gap in the check flow, found on a free page** (accounting, PDF page 19: an organisational chart and two tables, all three
  of them images; its text layer holds 105 characters, the captions and the running head). What stage 2 cannot check (tables
  printed as images, text in figures, formulas drawn as paths) it lists as `unverifiable`, and its docstring says that list goes
  to the judge. The check flow never reads it, so such a page reaches the judge only through the random sample. Counted
  offline: 1,029 free pages hold such a block, 861 of them unjudged. Page 19 itself was checked by hand: every number matches
  the image, and the ledger's balances and the bond table's columns add up. Decision 83 is open.
- **Decision 83.a** (the operator, 4 Nov): every page with a block stage 2 cannot check goes to the judge, beside the random sample,
  which alone can stop a work, as before. Stage 2's list of such blocks now reaches the check flow; a plan written before it
  has none. Sent: 861 free pages (spend guard's estimate 7.19 USD, about 4.45 USD expected at the measured 0.0052 USD a page).
- **A round of the rollout can be split in two** (decision 88.a). The stored order is cut again rather than planned anew, and
  the earlier rounds must come out byte for byte as they were, which the command checks before it writes anything. A round's
  difficulty span is now its lowest and highest score; it showed its first and last page's, which within a band of
  interleaved works need not be the two ends.

## 2026-11-05

- **The judge on every page stage 2 cannot check, collected** (decision 83.a): 861 free pages, 28 bad (3.3 %), 14 in each
  OpenStax book; 12 of them hold a wrong value, 11 a wrong word. These pages had been quoted without a second witness. The
  last four of its eleven batches waited about twenty hours in the provider's queue; the first seven came back within the hour.
  Cost 5.66 USD against an estimate of 7.19 and the 4.45 expected from the earlier mean of 0.0052 USD a page: a page with an
  image or a formula costs the judge more, about 0.0066 USD.
- **The second reader on the free pages** (decision 63.a): OpenAI's `gpt-6.1-terra` through OpenRouter read the 68 free pages
  the provider blocked, the reader declined or that stayed malformed: 52 valid, 16 malformed. The judge passed 46 of the 52, and
  those 46 now stand for their pages, each route saying "second reader … : anthropic blocked the page" or why else. 66 free
  pages are still served from their text layer.

## 2026-11-08

- **The rollout's issue-share gate allows for noise** (decision 109.a, the operator). It was written strictly ("does not
  climb"), so a rise well inside the noise failed it. A round's issue share may now rise by one standard error above the
  previous round's, computed from the previous share and the new round's unblocked pages (`rollout.issue_band`). A round's
  own record keeps the gate it was judged by.
- **The pages left malformed, looked at one by one** (decision 110.b, the operator): the flagged lines of every reading, some
  page images, the PDFs' own signals. None had lost or misread text. Six patterns: a validator rule stricter than the page (a
  list item continued from the page before needs no marker; a callout may explain a table; a paragraph may sit in a list
  item); the parser refusing a binding written without quotes or a brace in a quoted value; a tab as the leader of a contents
  entry; a label missing where nothing is lost (a decoration's kind, a table note's marker, a continued caption's binding); a
  page the PDF itself rotates, read sideways, its boxes outside the image; and one page given a wrong structure. The retry
  without a hint came back with exactly the same error on most of them.
- **The correction, decided by the operator** (111.a, 112.a, 113.a):
  - **Validator page/1.2:** what loses no text is a warning, as page/1 already said; the prompt and the reading keys are
    unchanged (`frozen_contract.json` keeps both old hashes). Under it, more than half of the licensed pages left malformed
    are valid, at no cost. In the free knowledge base 45 of 65 would be; not applied there yet, since it would change the
    index phase 6 measured.
  - **Pages rendered upright:** a page whose rotation lays horizontal text on its side is rendered and checked unrotated.
    Some rotated licensed pages, all in one book, are such; on the others the rotation sets vertical text upright and is
    kept. No free PDF has a rotated page, so no free key changes.
  - **A retry with a hint:** the format retry carries the check's own messages in the user turn (decision 54.a's hint). A page
    whose plain retry failed before gets one hinted attempt more.
  - **Mistake of mine in a test:** a test took back all its fakes with `monkeypatch.undo()`, and its next call reached the real
    stores. The spend guard stopped it before any batch, and one listing of the running batches went out, read only. It
    left four prompt files nobody referenced, deleted after checking that no record names them. The test now puts back the
    one function it changed.
- **Gates computed again under a new validator keep the old records beside them** (`rollout_gates_rNN_page1.1.json`), and
  the rounds are recomputed in order, so each round meets its predecessor with the same instrument.
- **The intake of new works** (decision 120.a, 8 Nov): new works join the licensed archive. `rollout plan` would cut every
  round anew and rewrite the earlier ones, so a new command, `rollout append`, plans only the works no round holds yet, by
  the same cascade and order, as rounds numbered after the last, at most 2,000 pages each; it writes no existing round file
  and refuses while a text-only page of a new work lacks the cheap model's check, since without it the structure the rules
  miss would be lost. Tests pin both, and that earlier rounds stay byte for byte.
- **Three public documents join the free corpus** (decision 121.b, 8 Nov): the Federal Reserve's and the OCC's 2011 guidance
  on model risk (SR 11-7, its attachment), the revised guidance of April 2026 that supersedes it (SR 26-2), and Regulation T
  (12 CFR part 220, the 2025 edition), 65 pages. The licence was read at each source: the Board's site says its information is
  in the public domain and asks to be cited, the Government Publishing Office quotes 17 U.S.C. §105. The Board no longer serves
  the SR 11-7 file, so it comes from the Internet Archive's copy of the Board's own file. They are read whole by the corpus cell
  through a new list in the page list (`corpus_works`), which leaves the mini pilot's frozen cells as they were; the dry run
  bought exactly the 65 new pages and none of the 1,652 read before. Found on the way: `acquire` wrote its manifest with CRLF
  on Windows; it writes LF now, and a test holds it.
- **The three documents read and judged** (8 Nov): 65 of 65 pages valid at once (0.88 USD), all 65 judged ok (0.41 USD).
  Stage 2 had flagged every page of SR 11-7: its text layer, written for screen readers, carries words no reader sees
  ("Page 3", "[Page Break]", "Footnote … End of Footnote", once "Fotnote") and lacks the printed running head. The judge, who
  sees the page, found the readings right; the witness was wrong, not the reader.
- **Loader 5, found on the build:** the chat's index took SR 11-7 as its title alone (10 tokens) and Regulation T not at all.
  SR 11-7's outline nests every chapter under "Contents", and a unit under a back-matter title went out with it; Regulation T
  has no outline. Now a "Contents" parent keeps its children (an index's or a reference list's do not), and a PDF without an
  outline is cut at the headings its readings found where every page stands on a reading, else page by page, so no text is
  dropped. The four PDFs indexed before have no such case and came out with the same sections and chunks; SR 11-7 now has 8
  sections and 103 chunks, Regulation T 45 and 178. The build re-embedded the PDFs for the new loader version: 0.022 USD.
- **The judge's issues, read again** (decision 133.b, the operator, 9 Nov). Of the pages the judge had found bad, many carried their
  findings only on blocks never quoted, a figure's description above all; their quotable text was what the judge passed. Such a
  reading is now served, and its route says so ("the judge's findings lie on blocks never quoted"): 5 free pages, and
  licensed ones. A finding on the page as a whole, or on a block the export cannot name, still keeps the text layer. Every
  other issue page is read once more, told the judge's own findings in the user turn beside the frozen prompt (54.a), as the
  format retry is told the format check's messages (113.a); each such re-read goes to the judge again, whatever stage 2 says.
  Free: 26 of 38 re-reads passed, and 7 of 19 pages malformed since the first reading passed their hinted retry. The free
  issues fell from 43 to 11.
- **The last intake, four public documents on cost and execution reporting** (decision 143.a, the operator, 9 Nov; features were sealed
  the same day, decision 142.a, with this one work as the named exception). The operator's question of the morning, how a spread fee
  and a negative fee are shown in a report, found only an accounting textbook's analogies. Two answers exist in public law:
  the EU's Delegated Regulation 2017/565 (Article 50 and Annex II: costs totalled as a cash amount and a percentage, payments
  received itemised separately, the spread a mark-up in the price) and the SEC's Rules 605 and 606 with the definitions of
  Rule 600 (spreads against the midpoint; fees and rebates netted). Both were taken, since the contrast between them is part
  of the answer. Found on the way: EUR-Lex and the eCFR refuse automated requests, so the EU text comes from the Publications
  Office's own repository and the CFR sections from govinfo, as Regulation T did; the EU's reuse decision 2011/833/EU was read
  there at its source (Articles 4 and 6). The operator's question whether a search must know "which country asks" became an issue
  for after the capstone; for now each subject sentence names its work's frame: whom it binds, which market, which price
  formation (decision 144.a).
- **Read, judged, served** (9 Nov): 105 pages by the corpus cell, 101 valid at once, the 4 malformed mended by the hinted
  retry (1.66 and 0.07 USD); 81 pages judged (0.53 USD), every work's sample clean, 2 issues; the two re-read with the
  judge's findings (0.03 USD): EU p. 76 passed its new judgement (0.007 USD), Rule 600 p. 4 came back malformed and keeps its
  text layer. 104 of the 105 pages are served from a checked reading.
- **Loader 6, found on the build:** the EU regulation's outline is one bookmark, its title, so the chat's index would have
  held its 83 pages as one section, and no hit could name Article 50. An outline of one entry now counts as none, and where
  the readings' headings make the outline, a heading with no text of its own becomes the parent of the next one, since the
  readings carry no levels. No PDF with bookmarks changed; the EU regulation has 111 sections, Regulation T 34 instead of
  45. The rebuild re-embedded the PDFs for the new loader version: 0.023 USD.
- **Loader 7, found by line 2's check the same evening:** the views' outline of the EU regulation was still flat, 252 units
  of level 1, because the fold acted on the chat's sections only. The outline now nests a heading with no text of its own
  over the next unit, as the sections do: 111 roots, as the chat has 111 sections. The chat's sections did not change; the
  rebuild for the new version cost 0.024 USD. Also found there, left as they are: the re-read of EU p. 76 wrote no printed
  label in its front matter, though its page header says L 87/76, so its citations say p. 76.
- **Features sealed, and the exceptions named on purpose** (decision 142.a, the operator, 9 Nov: from now on quality, presentation, docs
  and tests). Named exceptions: the last free work (143.a, above); a person's verdict on a page, versioned judge instructions
  with prototypes, and a prompts tab in the diagnostics view (146.a, 147.a, 148.a, below); a view of the HTML works' sections
  in the diagnostics UI with a stripped original beside the indexed text (the operator's 5.a, coordinated by a side session, recorded
  in the diagnostics protocol). Each came from using the system: the operator walked the issues as the person who keeps the corpus.
- **A person's verdict** (decision 146.a). The operator opened finance p. 5, an issue: the judge had called "Carlyse" in a list of
  sponsors a wrong word, and its own evidence read "printed 'Carlyse' ... written 'Carlyse'". A person's verdict is now kept
  for ever beside the judge's: `human_verdict give accept|reject|note`, a reason from a fixed list, the block, a tag such as
  `name_list` and a note, appended to the pipeline database and carried by the export, so a clone serves alike. The served
  route follows a person over any model. The tag stays in the person's verdict, never as a new attribute of the reading's
  contract: the reader was right, the judge was not.
- **A finding that names no difference is void** (146.a). Code voids a wrong-word or wrong-value finding whose evidence says
  identical, quotes one string as printed and written, or quotes strings that all stand as whole words both in the judged
  block and in the PDF's text layer; the person still sees it, marked. Audited before it acted, without a model: 13 free
  findings voided, every one a judge error (two more, minor and in tables, do not stand in the layer and stay) (accounting p. 820 among them, where the judge took "$2,467." against "$2,467.48" though
  the page prints both, in two sentences); some licensed findings the reading's text alone would have voided did not stand
  in the text layer, so the layer became the rule's second witness and those stay issues. A first version matched
  inside words ("$2,467." in "$2,467.48") and was corrected before it acted. Free issues served from the text layer fell from
  11 to 6; finance p. 5 and accounting pp. 156, 580, 657 and 706 serve their readings, and their route says why.
- **Judge versions, prototype first** (decision 147.a). `prompt_versions.json` names every version of the reader's and the
  judge's instructions and its state; a new version is frozen beside the active one, runs only on chosen pages, is filed
  under a cell of its own, and is never counted until the operator makes it active after its gate. judge/2 adds one sentence on proper
  names; run live on finance p. 5 it still called "Carlyse" wrong, quoting "Carlyse Ciocca" and "Carlyse", both as the
  reading writes them. judge/3 adds to that the rule that a finding needs printed and written to differ and a second look at
  the block before reporting a word; live on p. 5 it said ok, without findings (one run, not yet a measurement). judge/1, asked
  again on the same reading, made the same error, so the case can be shown live. Both prototypes run on judge/1's calibration
  set made again (56 of 57 entries with exactly the views judge/1 saw; one view differs since the validator of 8 Nov) and on
  the 16 free pages judge/1 called bad: 1.28 USD estimated, in batches.
- **Pages no check had reached, some of them served by mistake.** The diagnostics view showed them "not yet checked":
  readings judged ok later, but their cell's check report planned only each page's latest reading, so none held them. A
  reading with no check state counted as servable, so pages of a work a check had stopped were served from those readings.
  Now a reading no check reached is never served, and the export gives a chosen reading the state of its own counted verdict
  and its cell's stop: those pages are stopped and keep the text they had; the others stand as judged.
- **What the view showed of a check is now complete:** each attempt keeps the verdict it was judged with (the first reading of
  finance p. 5 had said "not checked"), and a check plan keeps stage 2 in full (each finding with its block and detail, each
  block it could not check with why, recall and precision), so the view can show the three stages one by one.
- **The operator's walk as the person who judges, 10 Nov** (the 16 free pages judge/1 called bad, one by one against the page image):
  accounting p. 156 accepted (b06 reads as printed; both judge versions that called it an omission say so in their own
  evidence), p. 305 accepted (judge/1 counted twelve T-accounts in Figure 5.16; the page holds eleven, as the reading's
  description says; judge/2 and judge/3 said ok). The judge had the figure's text with its eleven groups beside the image
  and did not count from it. An accept for the reason `other` now names the person's note in the route, not "another
  reason, said in the note". The tally per judge version against the person grows with the walk and decides judge/3.
- **A person's manual parts, beside the reading, never in it** (decision 188.a, 10 Nov, finance p. 94). The reader's
  description of Figure 3.12 has blue overtaking red "around 2000"; all three judge versions called it wrong and read the
  crossing as 2006-2007; the axis says chained 2012 dollars, and the lines cross about 2012, where real and nominal GDP are
  equal by definition. The judges' verdict was right for a wrong reason: they only catch a misread value larger than their
  own misreading, a blind spot reader and judge share as one model. The operator wanted both corrections marked as manual. Editing the
  reading was ruled out: its hash would no longer match and the integrity check would call it tampering. A person's verdict
  may now carry a correction (the block's text as the person says it reads) and an assessment of the judge's finding (right,
  right for a wrong reason, false alarm, missed), appended like every verdict; a database made before gains the two columns
  on first use. The export and the view show them as a person's; nothing served changes before the capstone.
- **A glossary entry's term reached neither the judge nor the index** (decision 190.a, 10 Nov, finance pp. 136 and 562). The
  contract puts the defined term in an attribute (`::: {#b19 .glossary_entry term="accrual-basis accounting"}`), the
  definition in the body. The judge's view passed a fixed list of attributes without `term`, so it saw seven definitions
  alone and called each term missing; both pages served their text layer for that. The quotable text read the body only, so
  934 definitions on 68 free pages stood in the index without the words they define. A glossary entry now reads "term:
  definition" (PDF loader 9), the judge's view carries `term`, `key` and `target`, and a person accepted both pages, rating
  the judge's findings a false alarm caused by our view.
- **A page a person checked is protected, and a person may reset it** (decision 191.a, the operator, 10 Nov: "pages a human
  corrected must be protected from a re-render, they are valuable; a human, a real member of staff has looked them over";
  "there must also be a reset option … a human must trigger it"). A verdict applied only to the reading it
  was given on, so any re-read would have dropped a person's work without a word. Now every command that reads a page again
  (`replay reread`, `vision_batches submit --retry-malformed/--retry-issues`, `second_reader read`) skips or refuses a page
  with a person's verdict unless `--over-a-person "<reason>"` is given; the reading a person accepted stays the page's
  reading; and `human_verdict reset --reason` archives the page's verdicts, discards its reading (the page serves its text
  layer until a new reading stands) and lifts the protection. Resets go to their own append-only table, every reset with its
  reason; a person's acts are stamped to the microsecond so a verdict right after a reset sorts after it.

- **judge/4, a judge on another model that also proposes rules for the reader** (decisions 195.a and 197.a, the operator, 10 Nov:
  "do we also get the valuable improvements of the reader prompt? … clear format rules … gathered in one shared store, so
  that we don't have so many duplicates"). The walk showed reader and judge sharing a blind spot as one model
  (p. 94), and judge/1 calling 12 of 14 fair pages wrongly bad (judge/2: 4, judge/3: 5). judge/4 is judge/2's instructions on
  Opus 5.5 at the project's Opus setting (effort low), plus a section asking for at most three rules per page for the reader:
  a format rule, a class or an attribute of the vocabulary, each naming the block that asked for it. Its answer has a schema
  of its own and a larger output budget (3,000 tokens); every key made before stays the same, by a test. `check_run
  reader-rules` gathers the proposals of a version and merges those that say the same: a class or an attribute by name and
  value, a format rule by the set of its words without the small ones ("never" and "not" count, so a rule and its opposite stay
  apart). Nothing is applied: the list is where a reader prompt page/2 would start, again as a measured prototype. Submitted
  in batches the night of 10 Nov: the calibration set (56 views, made again from Sonnet's judge/1 set with `judge-replan
  --from-model`) and the 16 free pages of the walk.
- **judge/4 measured, 11 Nov** (all answered; about 0.014 USD a page, 1.8 times Sonnet's 0.0078). *Against the person*
  (the walk's 16 free pages): it agrees on 13 of the 14 pages a person accepted (judge/2 10, judge/3 9, judge/1 none);
  on the fourteenth, finance p. 119, it names the very defect the person corrected (the header's operator columns have no
  cells in the body, so Debit and Credit shift against the accounts) but grades it
  major where the person found the values right. judge/2 and judge/3 judged pp. 136 and 562 on the view without the
  glossary term (190.a); without those two pages: judge/4 11 of 12, judge/2 10, judge/3 8. On the two pages whose reading is
  wrong it names accounting p. 969's index number (655 printed, 489 written) and, as the first judge, finance p. 94's crossing
  at about 2012, but grades that minor, so its verdict there is ok. *Calibration* (judge/1's set: 48 planted, 8 clean): a
  finding on the planted block in 45 of 48, as judge/2; 47 of 48 to an issue (a dropped figure label found and graded minor);
  1 of 8 clean pages flagged, accounting p. 69, where the reading lacks the table's title "Types of Business Structures",
  printed above Table 2.1 and present in the text layer: a true omission all earlier judges and the set's own label missed.
  The set is measured too. **→ now** (11 Nov, found by line 2's check-along): the omission is the mini pilot's reading's
  (cell MP-SM), the one the calibration set holds; the page's served reading (MP2-SM) has the title as its own heading block,
  so no served page is wrong and no correction is due. The judgement stays out of the page's history in the view, since it
  judged a pilot reading the page does not serve. *Rules for the reader:* 26 proposals, each on a page with a finding;
  merging by words joined none, so they were grouped by hand into nine themes: table grids (7), chart values read against
  their axis (6), counts in a description only as
  drawn (4), list markers and kinds (3), exact signs and names (2), a table's printed title (1), a toc entry's level (1), a
  chapter opener's picture as decoration (1), matched math delimiters (1). Three of the six candidates the walk had named
  came back unprompted (operator columns, chart axes, chapter art). Two need new vocabulary (a list kind for letters),
  that is a contract change; the rest are rules of use. judge/4 stays a prototype until the operator decides.
- **Reader prompt page/2 as a prototype; its gates, written before the run** (decision 207.a, the operator, 11 Nov: "let's do
  that"). page/2 is page/1's rules unchanged plus a section of eight: table grids with operator columns, T-accounts as
  tables, a table's printed title, legible images of tables read, chart values read against the axis, counts only as
  counted, a photo's own text left out, index numbers digit by digit; each from a reader error the walk confirmed or a rule
  judge/4 proposed. The contract stays page/1. The reader got a version as the judge has one (`system_prompt(form,
  version)`, page/1's bytes and keys unchanged); its readings lie in two cells no knowledge base names, so none is served.
  Free pages only. The baseline is each page's reading served today. Gates: (1) the mini pilot's 20 pages, 14 with
  publisher gold: every page valid, and formulas exact, table cells exact and pages clean against gold each no fewer than
  page/1's; (2) the walk's six reader errors, each checked by code against what the person recorded, at least four fixed:
  finance p. 94 (the chart's crossing named between 2008 and 2016, not about 2000), p. 119 (every row of a table of equal
  width), p. 387 (no text read from the chapter opener's photo), accounting p. 305 (the eleven T-accounts as eleven tables),
  p. 524 (the three journal boxes read, none unreadable), p. 969 (accumulated depletion 655); accounting p. 69 keeps its
  table title. judge/4 judges every page/2 reading, reported, not gated; cost within 1.3 times the estimate.
- **page/2 measured, 11 Nov: every gate holds.** 26 pages read, 25 valid, 0.42 USD (0.40 estimated); judge/4 on the 25,
  0.37 USD. *Gold:* both 20 of 20 valid and 112 of 112 formulas exact; table cells exact 221 to **224** of 224 (finance p.
  393: 15 to 18 of 18), pages clean against gold 13 to **14** of 14. Nothing was lost. *The walk:* four of six fixed by
  content: accounting p. 305's eleven T-accounts are eleven tables (debit and credit apart, where page/1 wrote one grouped
  figure), p. 524's three journal boxes are read ("Petty Cash 150 / Cash 150", page/1: unreadable), p. 969 reads 655,
  finance p. 387 reads no text from its opener's photo (page/1: 57 lines). Finance p. 119 half: the operators have their
  own columns and empty body cells, so the body is the right 17 wide, but the account headers got no colspan of 2, so the
  head is 13 and 11 wide. Finance p. 94 not: the axes are now read ("0 to 24,000 in ticks of 4,000"), yet the crossing is
  "about 2000 to 2005". p. 69 keeps its title. *p. 524 stays malformed for another reason:* its answer options A, B and D
  are a marker alone above their journal table, so three list items have empty bodies, which the validator refuses; page/1's
  reading failed for the same, and the page serves its text layer, where the boxes, being images, are missing. That is a
  question of the contract (an option whose content is a table), not of the reader; counted strictly, three of six fixed.
  *judge/4 on page/2:* 24 ok and one issue, p. 119, rightly (headers 13 wide, body 17); p. 524 not judged (malformed). On
  p. 94 it said ok without a finding, where on 10 Nov it had read 2012: one run is not a measurement. *The lesson:* the
  rules changed how the model writes (structure, discipline, legible images), not what it sees: a chart's crossing is a
  matter of perception, which Opus had and Sonnet has not. page/2 stays a prototype until the operator decides; activating it means
  reading the free corpus again (about 1,800 pages, about 21 USD) with the pages a person checked kept.
- **Validator page/1.3: a list item whose content is the block after it** (decision 212.a, the operator, 11 Nov). Of the free
  corpus's 21 issue pages, 9 accounting pages were malformed, 8 of them for one reason: a numbered answer or an option
  ("7.", "A.") whose whole content is the journal table printed right below it, written as a list item with its marker and
  an empty body, then the table (p. 961 even bound it with `in=`). The validator refused the empty body, so the pages served
  their text layer, which lacks the tables where they are images (p. 524). Such an item is now a warning when a table,
  figure, formula or listing follows it or binds to it; nothing is lost, as page/1.2 made what loses no text. Checked again
  for free: 7 pages valid (524, 550, 578, 958, 961, 965, 966); 338 (an attribute) and 398 (HTML in prose) stay malformed.
  Stage 2 and the active judge on the 5 that needed it, 0.04 USD estimated.
- **A footnote marker and a superscript read apart from the number before them** (decision 205.a, the operator, 11 Nov, from
  the operator's look at fed SR 11-7 p. 5). The marker was right (`[4]{.fn}`, footnote b10 `marker="4"`), but the quotable text ran it
  into the word before: "processes.4"; next to a number it made a wrong one: "Consumer Price Index, 1947–2020[2]{.fn}" read
  "1947–20202" in the index and in any quote, "variance is 12.5[2]{.sup}" read "12.52" (7 markers and 4 superscripts next to
  a digit, 302 markers on 197 free pages). The inline segments now keep a footnote marker, a superscript and a subscript as
  their own kind, and the quotable text reads them "[2]" and "^2" (an ordinal's "nd" and a subscript stay as printed); PDF
  loader 10. The view shows them raised, the marker linked to its footnote (206.a, line 2).
- **A reader prototype's readings in the export** (decision 210.a): page/2's readings stand in a page's history as attempts,
  `prototype: true`, purpose "a reader prototype (page/2), never served", never in its choice, check states or route, so
  line 2 can show accounting p. 305 before and after.
- **The export checks each reading once per run** (decision 214.a, the operator, 11 Nov: "technically this is less critical,
  since the result must not change"). Profiled, the free export took 69 s, 55 of them parsing and validating stored
  readings, each about three times (choosing the standing reading, listing the attempts, the row). A reading is immutable
  and the validator cannot change within a process, so `check_reading` keeps its answer by everything it depends on, the
  text's hash included, and hands out a copy. 69 s to 41 s, and the export is byte for byte the same (no line of
  `corpus/readings` changed). The row's own parse is a different call (without the page's expected size) and stays. What
  makes a page renderable on its own (a cache across runs keyed by reading and validator hash, an export of one page that
  marks its work or PDF when a stop or a section boundary moves) waits for the buttons after the capstone (214.b, 213).
- **`conversion/` in folders by concern** (decision 208.b, the operator, 11 Nov: "units that belong to the same group of topics belong
  in a subfolder of their own", as a rule for the whole code). The 27 modules of one folder now sit in six: `contract/`
  (the page contract and its vocabulary), `reading/` (requests, cells, the batch runner, the second reader, the rollout, the
  replay, page rendering, the page classes), `checks/` (the check flow and run, stage 2, integrity, KaTeX, a person's
  verdict), `judge/` (the judge, formula sheets, planted errors), `measurement/` (the mini pilot, publisher gold, scoring,
  the reader prototype), `store/` (the reading store, the pipeline database, the export, the served readings); prompts,
  their registry, the frozen contract and the vendored KaTeX stay at its root. Moved with `git mv`; imports, dotted names,
  commands and links rewritten by one script; seven paths relative to a module's own file went one level up. A test that
  looked for direct clients in `conversion/*.py` would have checked one folder only after the move; it walks the whole tree
  now. No behaviour changed: the suite is green, every command runs under its new name, no link points nowhere.
- **A person's verdict from the page view, the last feature before the freeze** (decisions 213.b, 223.a, 224.b, the operator,
  12 Nov: "this really is the last real feature before the freeze"). The core's part:
  `human_verdict.from_view` records a verdict (accept, reject or note, its reason, a block or the whole page, a note, a
  correction, an assessment of the judge) as its own run, given by the maintainer like one from the command line, and asks
  `export_queue.ExportQueue` for the export: one at a time in the view's own process, a request while one runs makes
  exactly one more run after it, and a failed export is said in the status while the verdict stays recorded.
  `human_verdict.record` answers a wrong input with a ValueError the view can show; the command line's `give` is unchanged.
  The export now writes its files whole or not at all (a temporary file, then a replace), so a view reading during a
  background export never sees half a file; the export's output is byte for byte the same. The write route, the start
  switch `--allow-verdicts` (off by default, so a reviewer's clone stays read-only) and the dialog are line 2's.
- **213.b run end to end once, on copies, and a guard it showed was missing** (12 Nov). The view's verdict route lives in
  line 2's app (57dc07e); its tests stub the write by design. Run once for real against copies of the export and the
  pipeline database (the app pointed at them, the real ones untouched: 31 verdicts before and after): the verdict was
  recorded, the export ran in the background and finished after 53 s, and the page then showed the verdict. Thinking it
  through for a reviewer's clone showed a sharp edge: the clone holds the export but not the store, so an export run there
  (by hand or after a verdict) would write an empty index and delete every reading text as stale. Today it stops by chance,
  on the untracked accounting PDF, which `acquire` would fetch. The export now refuses outright when the store holds fewer
  than half the pages the export it would replace already has, and says why.
