# Basel III → small-bank credit portfolio analysis

Phase 1 of the project described in `docs/requirements_from_meeting.md`: take the
Basel Framework, extract the rules that govern a **credit-card / credit
portfolio**, and turn them into **parameters that can actually be computed from a
small US bank's published quarterly filing**.

The test of "analysable" here is literal. Every extracted parameter is executed
against real FDIC quarterly data, and either produces a number or reports exactly
which unpublished input blocked it.

## Pipeline

```
BIS consolidated Basel Framework (PDF, 1,982 pp)
        │  src/ingest/parse_basel.py + src/ingest/pdf_lines.py
        ▼
data/basel/paragraphs.jsonl        3,682 paragraphs, each with its real citation
        │                          (CRE20.68, LCR40.x …), heading path, footnotes
        │  src/rag/corpus.py       BM25 + latent-semantic retrieval, RRF-fused
        ▼
outputs/rules/rules.json           atomic rules, classified, each carrying a
        │                          verbatim quote checked by exact substring match
        │  src/rules/validate.py
        ▼
outputs/rules/parameters.json      formulas over a fixed symbol vocabulary
        │  src/params/symbols.py   38 available · 9 derived · 12 declared-unavailable
        │  src/params/evaluate.py  ast-walked arithmetic, no eval()
        ▼
outputs/phase1/                    coverage.csv · compliance.json · rulebook.json
                                   evaluated against FDIC quarterly filings
                                   src/ingest/fdic.py, src/analysis/portfolio.py
```

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. fetch the source documents, then parse the framework (~3 min, cached after)
./scripts/fetch_basel.sh
.venv/bin/python src/ingest/parse_basel.py data/basel/BaselFramework.pdf \
        data/basel/paragraphs.jsonl

# 2. pull 12 quarters for every US bank over $1bn (~10 min, cached)
.venv/bin/python src/ingest/fdic.py --latest 20260331 --quarters 12 \
        --min-assets 1000000

# 3. query the corpus
.venv/bin/python src/rag/corpus.py --search "undrawn credit card commitments" -k 8
.venv/bin/python src/rag/corpus.py --ids CRE20.65,CRE20.68

# 4. bank size tiers and portfolio composition
.venv/bin/python src/analysis/portfolio.py --tier small

# 5. end to end
.venv/bin/python run_phase1.py
```

## Three design decisions worth defending

**Grounding is mechanical, not judged.** Every rule carries a `quote` that must
appear character-for-character in the paragraph it cites. `src/rules/validate.py`
checks this with an exact substring match after whitespace/typography
normalisation only. No model is asked whether a quote is faithful, so no model can
be wrong about it. Rules that fail are dropped, not repaired.

**Formulas are written against a closed vocabulary.** `src/params/symbols.py`
fixes the set of names a formula may use and binds each to a specific FDIC field
or a derivation. This is what makes extracted parameters executable rather than
decorative — a free-form formula naming `EAD_transactor` cannot be run against
anything.

**Unmeasurable is a result, not a failure.** Twelve symbols the Basel rules need
are declared but marked `unavailable`, each with the report that does carry it.
The most important is `undrawn_credit_card_lines` — Call Report Schedule RC-L
item 3815 — which is the quantity the supervisor's own worked example turns on
and which the FDIC series does not publish. Parameters depending on it are
emitted, flagged, and reported in `coverage.csv` rather than silently dropped or
quietly proxied.

## Findings that change the brief

- **22% of small US banks (195 of 887 over $1bn) report no risk-weighted assets
  at all.** They have elected the community bank leverage ratio under 12 CFR
  217.12, which switches off the entire risk-based capital apparatus. Basel
  risk-weight rules are not merely hard to check for these banks — they are
  inapplicable. Credit One Bank, a 100%-credit-card small bank, is one of them.
- **Basel and the US implementation diverge on exactly the rules that matter most
  here.** Basel assigns 45% / 75% risk weights to regulatory retail split by
  transactor status; 12 CFR 217 assigns a flat 100% to most retail and does not
  recognise the transactor split. Applying Basel literally to Call Report data
  will not reproduce any US bank's reported ratios.
- **The transactor/revolver split is not collected by any US regulatory report.**
  It is the hinge of Basel's retail risk weighting and it is unobservable from
  outside the issuer.
- **30 small banks have a material credit-card book**, three of them effectively
  monolines (Credit One 100%, Comenity 100%, Merrick 71%). That is a workable
  peer group for the benchmark-and-redistribute phase.

## Layout

| path | what it is |
| --- | --- |
| `docs/requirements_from_meeting.md` | the brief as stated in the supervisor meeting |
| `docs/rule_schema.md` | rule and parameter field semantics |
| `src/ingest/pdf_lines.py` | BIS PDF line reconstruction (see its docstring) |
| `src/ingest/parse_basel.py` | framework → cited paragraphs |
| `src/ingest/fdic.py` | FDIC quarterly connector + size tiering |
| `src/rag/corpus.py` | hybrid retrieval over the corpus |
| `src/rules/validate.py` | schema + verbatim-grounding gate |
| `src/params/symbols.py` | the closed symbol vocabulary |
| `src/params/evaluate.py` | safe formula execution |
| `src/analysis/portfolio.py` | tiering, composition, peer groups |
| `run_phase1.py` | the whole thing |
| `scripts/fetch_basel.sh` | downloads the BIS source documents |

## What is not in this repository, and why

- **The meeting recording and its raw transcript.** They capture identifiable
  people speaking in a private meeting. `docs/requirements_from_meeting.md`
  carries the derived brief instead.
- **The Basel PDFs and `paragraphs.jsonl`.** The BIS reserves copyright in the
  Basel Framework and permits brief excerpts only, so the full document and its
  complete text extraction are not redistributed. `scripts/fetch_basel.sh` plus
  the parser reproduce both in about three minutes.
- **The FDIC quarterly panel.** Public domain but large and reproducible —
  `src/ingest/fdic.py` rebuilds it.
