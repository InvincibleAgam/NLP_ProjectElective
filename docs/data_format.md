# What is in `bank_filings_2023_2025/`, and how to read it

## The key point first

A Call Report is **not a document**. It is a structured filing: a bank submits
roughly 1,700–2,000 numbered fields to the FFIEC each quarter. There is no
original PDF that was converted into this JSON. The facsimile PDF that FFIEC's
viewer produces is *generated from these same fields* — a rendering, not the
source.

So the JSON is one step closer to the filing than a PDF would be, and it is what
the FFIEC itself distributes for analysis.

## One file per bank per quarter

```
bank_filings_2023_2025/1391778_comenity-bank/
    call_report_2023-03-31.json   ┐
    …                             ├ 12 quarters, 2023-03-31 … 2025-12-31
    call_report_2025-12-31.json   ┘
    trends.csv                    14 headline metrics × 12 quarters
    summary.md                    readable view: annual + quarterly
```

The folder name is `<RSSD>_<bank name>`. **RSSD** is the Federal Reserve's
permanent identifier for the institution — it survives name changes, mergers and
charter conversions, which is why the twelve quarters join cleanly.

## Structure of one JSON file

```jsonc
{
  "institution":        { "rssd": "1391778", "cert": "27499",
                          "name": "COMENITY BANK", "city": "WILMINGTON", "state": "DE" },
  "report_date":        "2025-12-31",
  "report":             "FFIEC Call Report (FFIEC 031/041/051)",
  "is_fiscal_year_end": true,          // the 31 Dec filing is the annual one
  "source":             "FFIEC CDR Public Data Distribution, bulk single-period download",
  "schedules_filed":    ["RC", "RCCI", "RCL", "RCRI", "RI", …],   // 38 for this bank
  "field_count":        1746,
  "fields":             { "RCON2170": "7760444", … }              // the filing itself
}
```

Everything above `fields` is provenance. `fields` is the filing.

## `fields` — a flat map of MDRM code → value as filed

```jsonc
"RCON2170": "7760444",     // total assets                       $7.76bn
"RCONB538": "6756180",     // credit-card loans                  $6.76bn
"RCON3815": "37768445",    // unused credit-card line commitments $37.77bn
"RCOAP859": "1054628",     // common equity tier 1 capital        $1.05bn
"RCOAA223": "6979457",     // risk-weighted assets                $6.98bn
"RIAD4340":  "375496",     // net income, year to date            $375m
"RCFDK663":     "CONF"     // suppressed by the filer as confidential
```

**All amounts are in thousands of US dollars.**

### The MDRM code

`MDRM` is the Micro Data Reference Manual — the Fed/FFIEC's field dictionary.
Every code is 8 characters: a 4-character prefix and a 4-character item number.

    RCON  3815
    ────  ────
    what form and basis        which line item

The **item number** (`3815`, `B538`, `P859`) identifies the concept and is stable
across banks and across time. `RCON3815` means "unused commitments: credit-card
lines" in every bank's filing in every quarter. That stability is exactly what a
PDF would not give you, and it is what makes a 50-bank × 12-quarter panel
possible at all.

The **prefix** says which form the item came from and on what consolidation
basis. In this dataset:

| prefix | count* | meaning |
| --- | ---: | --- |
| `RCON` | 1,310 | Report of Condition — **domestic offices only** |
| `RCFD` | 161 | Report of Condition — **fully consolidated** (domestic + foreign) |
| `RIAD` | 171 | Report of Income — **year-to-date flows** |
| `RCOA` | 49 | Schedule RC-R, regulatory capital — domestic basis |
| `RCFA` | — | Schedule RC-R, regulatory capital — consolidated basis |
| `TEXT` | 50 | free-text fields (narrative, contact details) |
| `RSSD` | 5 | identifiers |

\* for Comenity Bank, 2025-12-31.

## Three things that will bite you if you skip them

**1. `RCON` vs `RCFD` — always coalesce.** A bank with foreign offices reports on
`RCFD`/`RCFA`; a domestic-only bank on `RCON`/`RCOA`. The same concept therefore
appears under two possible codes, and any given bank populates only one. Reading
`RCON2170` alone silently drops every internationally-active filer. The code in
`src/params/symbols.py` handles this by declaring both and taking whichever the
bank actually used.

**2. `RIAD` items are cumulative within the calendar year, and reset each Q1.**
They are flows, not stocks. Comenity's `RIAD4340` (net income):

| 2023-03-31 | 2023-06-30 | 2023-09-30 | 2023-12-31 | 2024-03-31 |
| ---: | ---: | ---: | ---: | ---: |
| $130m | $228m | $358m | $447m | **$90m** ← reset |

So the December figure is the full year, and a single quarter's income is the
difference between consecutive filings — except Q1, which is already the quarter.
Balance-sheet items (`RCON`/`RCFD`) are point-in-time and need no such treatment.

**3. Values are strings on purpose.** A field the bank suppressed as confidential
carries the literal `"CONF"`, not a number. Parsing the file with automatic
numeric coercion turns "the bank withheld this" into `0`, which is a silent and
material error — it reads as "the bank has none of this". Treat `CONF` and
absence as *missing*, never as zero.

## Where the numbers live

The schedules relevant to a credit-card portfolio:

| schedule | code in filenames | what it holds |
| --- | --- | --- |
| RC | `RC` | balance sheet — assets, deposits, equity |
| RC-C Part I | `RCCI` | loans by category — `B538` credit cards, `B539` other revolving |
| **RC-L** | `RCL` | **off-balance-sheet — `3815` unused credit-card lines** |
| RC-R Part I | `RCRI` | regulatory capital — `P859` CET1, `A223` RWA |
| RC-R Part II | `RCRII` | risk-weighted assets by risk-weight category |
| RC-N | `RCN` | past-due and nonaccrual, by loan type |
| RI | `RI` | income statement |
| RI-B Part I | `RIBI` | charge-offs and recoveries — `B514`/`B515` on credit cards |

RC-L item 3815 is the one that matters most here: it is the exposure Basel
converts with a credit conversion factor, it is several times larger than the
drawn card book for these banks, and it is **not published in the FDIC series**
that most small-bank analysis starts from.

## Caveat on the bulk files

The FFIEC bulk distribution truncates the human-readable captions to about 36
characters, which is why row 2 of the raw `.txt` files shows things like
`UNUSED COMMITMEN WEIGHT CATEGORY`. The codes are unaffected. For full official
captions and line-item numbers, consult the FFIEC MDRM dictionary or the blank
form for FFIEC 031/041/051.
