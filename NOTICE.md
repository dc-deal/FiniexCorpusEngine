# Notice

FiniexCorpusEngine's code is MIT-licensed ([LICENSE](LICENSE)). It is built to read the works listed below, and none
of them is part of this repository:

- **Not uploaded here.** `python -m backend.ingestion.acquire` downloads each work from the place named below, under
  the licence named below, into the data folder `_data/corpus/raw/`. A contributor gets the same files the same way.
- **What the project does with them:** it reads each work page by page into a local search index, checks every page's
  reading against the original, and answers with a verbatim quote, its page and its licence. Its checked readings and
  measurements are kept in a local data folder, never in any repository.
- **Where excerpts appear here, they keep their work's licence:** the screenshots in `docs/images/` (the README's
  section "What it looks like" names the works) and the page transcriptions in `tests/fixtures/page_contract/` (its
  README does).
- **A work under a NoDerivatives licence is never transformed,** only quoted word for word with its source.

This file is written from `corpus/catalog.json` by `python -m backend.ingestion.notice`; do not edit it by hand.

## The works

### Principles of Finance 2e

- **Authors:** Julie Dahlquist, Rainford Knight
- **Publisher:** OpenStax, 2026
- **Licence:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), stated at <https://openstax.org/books/principles-finance-2e/pages/preface>, checked 2026-09-28
- **Source:** <https://openstax.org/books/principles-finance-2e/pages/preface>

### Principles of Accounting, Volume 1: Financial Accounting

- **Authors:** Mitchell Franklin, Patty Graybeal, Dixon Cooper
- **Publisher:** OpenStax, 2019
- **Licence:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), stated at <https://openstax.org/books/principles-financial-accounting/pages/preface>, checked 2026-09-28
- **Source:** <https://openstax.org/books/principles-financial-accounting/pages/preface>

### Wikipedia articles on trading and risk

- **Authors:** Wikipedia contributors
- **Publisher:** Wikimedia Foundation
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), stated at <https://en.wikipedia.org/wiki/Wikipedia:Copyrights>, checked 2026-09-29
- **Source:** <https://en.wikipedia.org/>

### Reminiscences of a Stock Operator

- **Authors:** Edwin Lefèvre
- **Publisher:** George H. Doran, 1923
- **Licence:** Public domain in the USA, stated at <https://www.gutenberg.org/ebooks/60979>, checked 2026-09-28
- **Source:** <https://www.gutenberg.org/ebooks/60979>

### Site Reliability Engineering

- **Authors:** Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Richard Murphy (eds.)
- **Publisher:** O'Reilly / Google, 2017
- **Licence:** [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/), stated at <https://sre.google/sre-book/table-of-contents/>, checked 2026-09-28
- **Source:** <https://sre.google/sre-book/table-of-contents/>

### Accounting for Computer Scientists

- **Authors:** Martin Kleppmann
- **Publisher:** martin.kleppmann.com, 2011
- **Licence:** [CC BY 3.0 Unported](https://creativecommons.org/licenses/by/3.0/), stated at <https://martin.kleppmann.com/2011/03/07/accounting-for-computer-scientists.html>, checked 2026-09-28
- **Source:** <https://martin.kleppmann.com/2011/03/07/accounting-for-computer-scientists.html>

### Practical Implementation of the Kelly Criterion: Optimal Growth Rate, Number of Trades, and Rebalancing Frequency for Equity Portfolios

- **Authors:** Andrea Carta, Claudio Conversano
- **Publisher:** Frontiers in Applied Mathematics and Statistics, 2020
- **Licence:** CC BY, stated at <https://www.frontiersin.org/journals/applied-mathematics-and-statistics/articles/10.3389/fams.2020.577050/pdf>, checked 2026-09-28
- **Source:** <https://www.frontiersin.org/journals/applied-mathematics-and-statistics/articles/10.3389/fams.2020.577050/full>

### Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals

- **Authors:** Gagan Deep, Akash Deep, William Lamptey
- **Publisher:** arXiv, 2025
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), stated at <https://arxiv.org/abs/2512.12924>, checked 2026-09-28
- **Source:** <https://arxiv.org/abs/2512.12924>

### Supervisory Guidance on Model Risk Management (SR Letter 11-7, Attachment)

- **Authors:** Board of Governors of the Federal Reserve System; Office of the Comptroller of the Currency
- **Publisher:** Board of Governors of the Federal Reserve System, 2011
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.federalreserve.gov/disclaimer.htm>, checked 2026-11-08
- **Source:** <https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm>

### Revised Guidance on Model Risk Management (SR Letter 26-2)

- **Authors:** Board of Governors of the Federal Reserve System; Office of the Comptroller of the Currency; Federal Deposit Insurance Corporation
- **Publisher:** Board of Governors of the Federal Reserve System, 2026
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.federalreserve.gov/disclaimer.htm>, checked 2026-11-08
- **Source:** <https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm>

### Regulation T: Credit by Brokers and Dealers (12 CFR Part 220)

- **Authors:** Board of Governors of the Federal Reserve System
- **Publisher:** U.S. Government Publishing Office (Code of Federal Regulations), 2025
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.govinfo.gov/about/policies>, checked 2026-11-08
- **Source:** <https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol3/pdf/CFR-2025-title12-vol3-part220.pdf>

### Commission Delegated Regulation (EU) 2017/565: organisational requirements and operating conditions for investment firms (MiFID II)

- **Authors:** European Commission
- **Publisher:** Publications Office of the European Union (Official Journal of the European Union, L 87, 31.3.2017), 2017
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-09
- **Source:** <http://data.europa.eu/eli/reg_del/2017/565/oj>

### Regulation NMS, Rule 600: NMS security designation and definitions (17 CFR 242.600)

- **Authors:** U.S. Securities and Exchange Commission
- **Publisher:** U.S. Government Publishing Office (Code of Federal Regulations), 2025
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.govinfo.gov/about/policies>, checked 2026-11-09
- **Source:** <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol5/pdf/CFR-2025-title17-vol5-sec242-600.pdf>

### Regulation NMS, Rule 605: Disclosure of order execution information (17 CFR 242.605)

- **Authors:** U.S. Securities and Exchange Commission
- **Publisher:** U.S. Government Publishing Office (Code of Federal Regulations), 2025
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.govinfo.gov/about/policies>, checked 2026-11-09
- **Source:** <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol5/pdf/CFR-2025-title17-vol5-sec242-605.pdf>

### Regulation NMS, Rule 606: Disclosure of order routing information (17 CFR 242.606)

- **Authors:** U.S. Securities and Exchange Commission
- **Publisher:** U.S. Government Publishing Office (Code of Federal Regulations), 2025
- **Licence:** Public domain (U.S. Government work, 17 U.S.C. §105), stated at <https://www.govinfo.gov/about/policies>, checked 2026-11-09
- **Source:** <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol5/pdf/CFR-2025-title17-vol5-sec242-606.pdf>

## Non-commercial works

The code may be used commercially under its MIT licence; these works may not. Their licences forbid commercial use, so
a commercial use of this project leaves them out:

- Principles of Finance 2e
- Principles of Accounting, Volume 1: Financial Accounting
- Site Reliability Engineering

## For rights holders

If you hold rights in a work listed here and see a problem with how it is used, please open an issue in this
repository. The material concerned is taken out while the question is open.

## Libraries

The built interface bundles libraries under their own licences, listed in
`src/frontend/diagnostics/dist/THIRD_PARTY_NOTICES.md`; KaTeX, vendored for the page checks, carries its licence in
`src/backend/conversion/vendor/katex.LICENSE`.
