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

### FIX Latest as of EP284: Introduction

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-introduction/>

### FIX Latest as of EP284: Infrastructure

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-infrastructure/>

### FIX Latest as of EP284: Pre-Trade

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-pre-trade/>

### FIX Latest as of EP284: Trade

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-trade/>

### FIX Latest as of EP284: Order State Changes

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-order-state-changes/>

### FIX Latest as of EP284: Post-Trade

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2023
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-latest-specification-post-trade/>

### FIX Session Layer: Technical Standard (Errata, November 2020)

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2020
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-session-layer-technical-standard/>

### FIX Session Layer: Test Cases (version 1.0, June 2020)

- **Authors:** FIX Global Technical Committee
- **Publisher:** FIX Protocol Limited (FIX Trading Community), 2020
- **Licence:** CC BY-ND 4.0, stated at <https://creativecommons.org/licenses/by-nd/4.0/>, checked 2026-11-22
- **Source:** <https://fixtrading.org/packages/fix-session-layer-test-cases/>

### Commission Delegated Regulation (EU) 2017/589: organisational requirements of investment firms engaged in algorithmic trading (RTS 6)

- **Authors:** European Commission
- **Publisher:** Publications Office of the European Union (Official Journal of the European Union, L 87, 31.3.2017), 2017
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-22
- **Source:** <http://data.europa.eu/eli/reg_del/2017/589/oj>

### ESMA Decision (EU) 2018/796: temporary restriction of contracts for differences for retail clients

- **Authors:** European Securities and Markets Authority
- **Publisher:** Publications Office of the European Union (Official Journal of the European Union, L 136, 1.6.2018), 2018
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-22
- **Source:** <http://data.europa.eu/eli/dec/2018/796/oj>

### Trading and Arbitrage in Cryptocurrency Markets (accepted manuscript)

- **Authors:** Igor Makarov, Antoinette Schoar
- **Publisher:** LSE Research Online (accepted version of Journal of Financial Economics 135(2), 2020, 293-319), 2020
- **Licence:** [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/), stated at <https://creativecommons.org/licenses/by-nc-nd/4.0/>, checked 2026-11-22
- **Source:** <https://researchonline.lse.ac.uk/id/eprint/100409/>

### Commission Delegated Directive (EU) 2017/593: safeguarding of client financial instruments and funds (MiFID II)

- **Authors:** European Commission
- **Publisher:** Publications Office of the European Union (Official Journal of the European Union, L 87, 31.3.2017), 2017
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-22
- **Source:** <http://data.europa.eu/eli/dir_del/2017/593/oj>

### Regulation (EU) 2023/1114 on markets in crypto-assets (MiCA)

- **Authors:** European Parliament and Council of the European Union
- **Publisher:** Publications Office of the European Union (Official Journal of the European Union, L 150, 9.6.2023), 2023
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-22
- **Source:** <http://data.europa.eu/eli/reg/2023/1114/oj>

### Directive 97/9/EC on investor-compensation schemes

- **Authors:** European Parliament and Council of the European Union
- **Publisher:** Office for Official Publications of the European Communities (Official Journal of the European Communities, L 84, 26.3.1997), 1997
- **Licence:** Reuse authorised, source acknowledged (Commission Decision 2011/833/EU), stated at <http://publications.europa.eu/resource/celex/32011D0833>, checked 2026-11-22
- **Source:** <http://data.europa.eu/eli/dir/1997/9/oj>

### Triennial Central Bank Survey: OTC foreign exchange turnover in April 2022

- **Authors:** Bank for International Settlements, Monetary and Economic Department
- **Publisher:** Bank for International Settlements, 2022
- **Licence:** BIS terms: download and redistribution for non-commercial purposes, the BIS cited as the source, stated at <https://www.bis.org/terms_conditions.htm>, checked 2026-11-22
- **Source:** <https://www.bis.org/statistics/rpfx22.htm>

### The global foreign exchange market in a higher-volatility environment (BIS Quarterly Review, December 2022)

- **Authors:** Mathias Drehmann, Vladyslav Sushko
- **Publisher:** Bank for International Settlements (BIS Quarterly Review, December 2022, pp. 33-48), 2022
- **Licence:** BIS terms: download and redistribution for non-commercial purposes, the BIS cited as the source, stated at <https://www.bis.org/terms_conditions.htm>, checked 2026-11-22
- **Source:** <https://www.bis.org/publ/qtrpdf/r_qt2212.htm>

### Momentum effects in the cryptocurrency market after one-day abnormal returns

- **Authors:** Guglielmo Maria Caporale, Alex Plastun
- **Publisher:** Springer (Financial Markets and Portfolio Management 34(3), 2020, 251-266), 2020
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), stated at <https://creativecommons.org/licenses/by/4.0/>, checked 2026-11-23
- **Source:** <https://doi.org/10.1007/s11408-020-00357-1>

### When Do Stop-Loss Rules Stop Losses? (original manuscript)

- **Authors:** Kathryn M. Kaminski, Andrew W. Lo
- **Publisher:** MIT Open Access Articles (original manuscript of Journal of Financial Markets 18, 2014, 234-254), 2014
- **Licence:** [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/), stated at <https://creativecommons.org/licenses/by-nc-nd/4.0/>, checked 2026-11-23
- **Source:** <https://hdl.handle.net/1721.1/114876>

### Intraday Bitcoin price shocks: when bad news is good news

- **Authors:** José Luis Miralles-Quirós, María Mar Miralles-Quirós
- **Publisher:** Taylor & Francis (Journal of Applied Economics 25(1), 2022, 1294-1313), 2022
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), stated at <https://creativecommons.org/licenses/by/4.0/>, checked 2026-11-23
- **Source:** <https://doi.org/10.1080/15140326.2022.2151253>

### Non-Parametric Statistic for Testing Cumulative Abnormal Stock Returns

- **Authors:** Seppo Pynnönen
- **Publisher:** MDPI (Journal of Risk and Financial Management 15(4), 149, 2022), 2022
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), stated at <https://creativecommons.org/licenses/by/4.0/>, checked 2026-11-23
- **Source:** <https://doi.org/10.3390/jrfm15040149>

## Non-commercial works

The code may be used commercially under its MIT licence; these works may not. Their licences forbid commercial use, so
a commercial use of this project leaves them out:

- Principles of Finance 2e
- Principles of Accounting, Volume 1: Financial Accounting
- Site Reliability Engineering
- Trading and Arbitrage in Cryptocurrency Markets (accepted manuscript)
- When Do Stop-Loss Rules Stop Losses? (original manuscript)

## For rights holders

If you hold rights in a work listed here and see a problem with how it is used, please open an issue in this
repository. The material concerned is taken out while the question is open.

## Libraries

The built interface bundles libraries under their own licences, listed in
`src/frontend/diagnostics/dist/THIRD_PARTY_NOTICES.md`; KaTeX, vendored for the page checks, carries its licence in
`src/backend/conversion/vendor/katex.LICENSE`.
