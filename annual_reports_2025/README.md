# Year-end 2025 regulatory filings — 50 small US banks with a credit-card business

50 banks, each with the full Call Report they filed for **31 December 2025**.

```
<RSSD>_<name>/
    call_report_2025-12-31.json   every field the bank filed, keyed by MDRM code
    summary.md                    a one-page readable view
INDEX.csv                         all 50 with headline card figures
```

## What these are, and a naming caveat

Banks do not file an "annual report" with the FFIEC. They file a **Call Report**
(FFIEC 031/041/051) every quarter, and the 31 December filing is the
fiscal-year-end one. That is what is collected here — the regulatory annual
filing, not a glossy shareholder annual report. Where a shareholder report
exists it is filed with the SEC, not the FFIEC, and most banks this size do not
produce one.

## Provenance

Source: **FFIEC Central Data Repository, Public Data Distribution**, bulk
single-period download for cycle 12/31/2025 (`FFIEC CDR Call Bulk All Schedules
12312025.zip`, 48 tab-delimited schedule files). Public domain.

**Not** from `www.ffiec.gov/npw`, which was the site originally suggested. NPW
refuses automated clients outright — every request returns HTTP 403 from a WAF,
for curl and for every other non-browser agent tried. NPW is in any case a
directory of institutions and ownership hierarchies; the filings themselves are
served by CDR, and CDR's bulk distribution is the route FFIEC publishes for
programmatic access.

Regenerate with `src/ingest/callreport.py` (see its docstring for the CDR form
flow).

## Selection

Small banks — **total assets under $10bn**, the community bank leverage ratio
threshold in 12 CFR 217.12 — that reported either credit-card loans (Schedule
RC-C item B538) or unused credit-card line commitments (Schedule RC-L item 3815),
ranked by total card exposure and cut at 50. 245 small banks report some card
balance, so this is the top of a much larger pool, not the whole of it.

## Why item 3815 is the point

The FDIC's published series — the one most analysis of small banks starts from —
does **not** carry unused credit-card commitments. That absence matters more than
it sounds, because for this population the undrawn book dwarfs the drawn one:

| bank | assets | card loans drawn | **unused card lines** | utilisation |
| --- | ---: | ---: | ---: | ---: |
| Comenity Bank | $7.8bn | $6.8bn | **$37.8bn** | 15% |
| John Deere Financial | $3.4bn | $0.5bn | **$33.5bn** | 2% |
| Credit First NA | $0.04bn | $0.0bn | **$11.4bn** | 0% |
| WEX Bank | $8.5bn | $0.0bn | **$8.9bn** | 0% |
| Credit One Bank | $2.0bn | $1.7bn | **$8.1bn** | 17% |

Across all 50: **$128.6bn of undrawn card commitments**, against far smaller
balance sheets.

## The worked example, run on this data

Basel III applies a **10% credit conversion factor** to commitments that are
unconditionally cancellable at any time without notice (**CRE20.100**) — which is
what a credit-card line is — and then the regulatory-retail risk weight of 75%
(**CRE20.68**). Converting each bank's item 3815 on that basis:

| bank | CET1 now | + RWA from undrawn lines | CET1 after | change |
| --- | ---: | ---: | ---: | ---: |
| Comenity Bank | 15.1% | $2.8bn | 10.7% | −4.4pp |
| TCM Bank | 20.9% | $0.2bn | 14.0% | −6.9pp |
| RBC Bank (Georgia) | 41.1% | $0.2bn | 37.0% | −4.1pp |
| 1st Financial Bank USA | 21.0% | $0.1bn | 18.8% | −2.2pp |
| Credit First NA | 387.7% | $0.9bn | 4.3% | −383pp |

Credit First is an outlier worth understanding rather than averaging away: $39m
of assets against $11.4bn of committed lines means it originates and sells
almost everything it writes, so its reported ratios describe very little of the
risk it arranges.

**The divergence to raise with the supervisor.** Basel's 10% CCF on
unconditionally cancellable commitments is part of the finalised standard. The
current US rule, 12 CFR 217.33, assigns **0%** to them. So under the rules these
banks actually report against, the whole $128.6bn attracts no capital at all, and
the columns above are what Basel would require rather than what any US supervisor
is asking for today. That gap is the most interesting thing in this dataset and
is a good candidate for the scenario work.

## Caveats

- Fields marked `CONF` were suppressed by the filer as confidential.
- Banks with foreign offices report on `RCFD*` codes, domestic-only on `RCON*`.
  The summaries coalesce the two; the JSON keeps both as filed.
- Stride Bank reports $0 in item 3815 despite a $2.2bn card book — it appears to
  service rather than commit the lines. Worth confirming before using it.
- One-quarter snapshot. `src/ingest/fdic.py` provides the 12-quarter panel.
