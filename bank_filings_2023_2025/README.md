# Call Report filings 2023–2025 — 50 small US banks with a credit-card business

50 banks × **12 consecutive quarters**, 31 March 2023 to 31 December 2025. Every
bank filed in every quarter, so the panel is complete with no gaps.

```
<RSSD>_<name>/
    call_report_2023-03-31.json  …  call_report_2025-12-31.json   12 filings,
                                    every field as filed, keyed by MDRM code
    trends.csv                    14 headline metrics × 12 quarters
    summary.md                    annual comparison + quarterly series
INDEX.csv                         all 50 banks, latest-quarter figures
```

## What these are, and a naming caveat

Banks do not file an "annual report" with the FFIEC. They file a **Call Report**
(FFIEC 031/041/051) every quarter, and the **31 December** filing is the
fiscal-year-end one. So the three annual reports for each bank are the
`2023-12-31`, `2024-12-31` and `2025-12-31` files; the other nine quarters show
how the bank moved between them. Income and charge-off items are year-to-date, so
the December figures are full-year.

Where a shareholder-facing annual report exists it is filed with the SEC, not the
FFIEC, and most banks this size do not produce one.

## Provenance

Source: **FFIEC Central Data Repository, Public Data Distribution**, bulk
single-period downloads for the twelve cycles covering 2023–2025. Public domain.

**Not** from `www.ffiec.gov/npw`, which was the site originally suggested. NPW
refuses automated clients outright — every request returns HTTP 403 from a WAF,
for curl and for every other non-browser agent tried. NPW is in any case a
directory of institutions and ownership hierarchies; the filings themselves are
served by CDR, and CDR's bulk distribution is the route FFIEC publishes for
programmatic access.

Reproduce with `scripts/fetch_callreport.py` (one cycle per run, `--list` shows
what is offered) then `src/ingest/callreport.py`.

## Selection

Small banks — **total assets under $10bn**, the community bank leverage ratio
threshold in 12 CFR 217.12 — that reported credit-card loans (Schedule RC-C item
B538) or unused credit-card line commitments (Schedule RC-L item 3815), ranked by
total card exposure at 2025-12-31 and cut at 50. 245 small banks report some card
balance, so this is the top of a much larger pool.

The cohort is fixed on the latest quarter and tracked backwards, so it is a
survivor set: banks that left the population before 2025 are not here.

## What three years of data shows

Aggregated across all 50, at each fiscal year-end:

| | 2023 | 2024 | 2025 |
| --- | ---: | ---: | ---: |
| Total assets | $203.1bn | $211.7bn | $230.1bn |
| Credit-card loans drawn | $17.7bn | $17.5bn | $21.4bn |
| **Unused card line commitments** | **$131.5bn** | **$127.2bn** | **$128.6bn** |
| Risk-weighted assets | $144.8bn | $149.7bn | $160.9bn |
| **Line utilisation** | **11.9%** | **12.1%** | **14.3%** |
| Aggregate CET1 ratio | 16.4% | 16.4% | 16.7% |

Two things stand out.

**Committed capacity is flat while drawdown is rising.** These banks did not
extend more credit over three years — the committed book went $131.5bn → $128.6bn
— but customers drew more of what was already available, taking utilisation from
11.9% to 14.3%. Rising utilisation against static lines is a consumer-stress
signal, and it is invisible in balances alone: drawn card loans grew 21% over the
period, which read on its own looks like healthy origination.

**The sector is splitting.** Comenity pulled $14.2bn of committed lines (−27%)
while Merrick added $2.1bn (+93%), First Bank & Trust $2.7bn (+46%) and Credit
One $1.7bn (+26%). Retrenchment and aggressive growth are happening side by side
in the same size tier, which makes the benchmark-and-redistribute question sharper
rather than academic — there are real strategies to compare.

## Why item 3815 is the point

The FDIC's published series — where most small-bank analysis starts — does **not**
carry unused credit-card commitments. For this population the undrawn book dwarfs
the drawn one, so that omission hides most of the exposure:

| bank | assets | drawn | **unused card lines** | utilisation |
| --- | ---: | ---: | ---: | ---: |
| Comenity Bank | $7.8bn | $6.8bn | **$37.8bn** | 15% |
| John Deere Financial | $3.4bn | $0.5bn | **$33.5bn** | 2% |
| Credit First NA | $0.04bn | $0.0bn | **$11.4bn** | 0% |
| WEX Bank | $8.5bn | $0.0bn | **$8.9bn** | 0% |
| Credit One Bank | $2.0bn | $1.7bn | **$8.1bn** | 17% |

Basel applies a **10% credit conversion factor** to commitments that are
unconditionally cancellable at any time without notice (**CRE20.100**) — which is
what a card line is — then the 75% regulatory-retail risk weight (**CRE20.68**).
Two figures follow, and they answer different questions. Converting the undrawn
lines alone, holding the rest of the book at current treatment, takes Comenity's
2025 CET1 ratio from 15.1% to **10.7%** — that isolates the exposure nobody
currently counts. A full Basel restatement, which also moves the drawn balances
from the US flat 100% to 75%, lands at **13.0%** — that is what Basel would
actually require. Because the transactor split is unobservable (CRE20.66), the
honest output is a band: 21.2% if every account were a transactor (45%), 13.0% at
the 75% central case, 9.8% if the book failed the regulatory-retail criteria
(100%).

**The divergence to raise with the supervisor.** Basel's 10% CCF is part of the
finalised standard. The current US rule, 12 CFR 217.33, assigns **0%** to
unconditionally cancellable commitments. Under the rules these banks actually
report against, the whole $128.6bn attracts no capital at all. That gap is the
most interesting thing in this dataset and a natural subject for the scenario
work.

## Caveats

- Fields marked `CONF` were suppressed by the filer as confidential.
- Banks with foreign offices report on `RCFD`/`RCFA` codes, domestic-only banks on
  `RCON`/`RCOA`. Summaries coalesce the two; the JSON keeps them as filed.
- Stride Bank reports $0 in item 3815 despite a $2.2bn card book — it appears to
  service rather than commit the lines. Worth confirming before using it.
- Credit First NA is a genuine outlier ($39m of assets against $11.4bn of
  committed lines) rather than a data error: it originates and sells almost
  everything it writes, so its reported ratios describe very little of the risk it
  arranges. Understand it; do not average it away.
