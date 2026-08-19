# Phase 1 schemas — Basel rule → analysable portfolio parameter

Two artefacts. A **Rule** is a faithful, citable restatement of regulatory text.
A **Parameter** is the machine-computable object a portfolio optimiser consumes.
Keeping them separate is deliberate: rules are *grounded in the document* and can
be audited against it verbatim; parameters are *engineering decisions* about how
to measure a rule against real bank data, and are allowed to be approximate — but
must say so.

## Rule

```json
{
  "rule_id":   "R-CRE20.68-retail-rw",
  "title":     "Risk weights for retail exposures",
  "statement": "One normalised sentence stating the obligation.",
  "quote":     "Verbatim span copied character-for-character from the source paragraph.",
  "source":    {"para_ids": ["CRE20.68"], "chapter": "CRE20", "standard": "CRE"},
  "obligation": "must | should | may | definition",
  "rule_class": ["credit_risk_rwa"],
  "products":   ["credit_card"],
  "applies_to": {
    "bank_sizes": ["small", "medium", "large"],
    "approach":   "SA | IRB | both | n/a",
    "note":       "Scope/proportionality caveats, if any."
  },
  "quantitative": true,
  "param_ids": ["P-rw-retail-transactor"]
}
```

`rule_class` ∈ `scope_definition`, `capital_adequacy`, `credit_risk_rwa`,
`credit_risk_mitigation`, `provisioning`, `liquidity`, `funding`, `leverage`,
`concentration`, `securitisation`, `issuance_underwriting`, `operational`,
`supervisory_review`, `disclosure`.

`products` ∈ `credit_card`, `revolving_retail`, `personal_loan`, `sme`,
`mortgage`, `corporate`, `sovereign`, `bank_exposure`, `securitisation`, `all`.

**Grounding rule (hard):** `quote` MUST appear verbatim in the concatenation of
`text + footnotes + faqs` of the cited paragraphs. This is checked in code, not
by judgement — see `src/rules/validate.py`. A rule that fails is rejected, not
repaired.

## Parameter

```json
{
  "param_id": "P-rw-retail-transactor",
  "name": "Risk weight — regulatory retail, transactor",
  "kind": "coefficient | ratio_requirement | limit | eligibility_test | input_definition",
  "value": 0.45,
  "unit": "risk_weight | ratio | currency | count | days",
  "operator": ">= | <= | == | n/a",
  "formula": "rwa_retail_transactor = ead_transactor * 0.45",
  "symbols": {"ead_transactor": "Exposure at default of transactor balances"},
  "inputs": [
    {
      "symbol": "ead_transactor",
      "description": "Credit-card balances of obligors repaying in full monthly",
      "fdic_field": "LNCRCD",
      "call_report": {"schedule": "RC-C Part I", "item": "RCON B538"},
      "availability": "exact | proxy | unavailable",
      "note": "Transactor/revolver split is not separately reported; proxy required."
    }
  ],
  "portfolio_lever": "credit_card_balances",
  "direction": "increases_rwa | decreases_rwa | increases_hqla | constrains_growth | none",
  "rule_ids": ["R-CRE20.68-retail-rw"],
  "us_overlay": "Divergence in the US implementation (12 CFR 217), if material."
}
```

`availability` is the honest-reporting field and the one that matters most for
this project: it records whether the quantity a Basel rule needs can actually be
read out of a small bank's public quarterly filing. `unavailable` inputs are not
failures — they are the finding.
