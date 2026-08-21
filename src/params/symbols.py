"""
The canonical symbol vocabulary that Basel-derived formulas are written against.

This module is the contract between the two halves of the project. Rule
extraction produces formulas; the bank connector produces numbers; they only
meet if both sides agree on a fixed set of names. Free-form formulas invented per
rule are not executable, so parameterisation is constrained to these symbols.

Four availability states, and the last is the interesting one:

  AVAILABLE    read directly from the FDIC quarterly series
  DERIVED      computed from available symbols
  CALLREPORT   not in the FDIC series, but filed on a Call Report schedule and
               obtainable from the FFIEC CDR bulk distribution (see
               `ingest.callreport`); resolved when a Call Report record is passed
               alongside the FDIC row
  UNAVAILABLE  the Basel rule needs it, and no public filing carries it

`UNAVAILABLE` symbols are declared here on purpose rather than omitted. A rule
that depends on one is not dropped — it is carried with an explicit,
machine-readable statement of what would have to be sourced to make it
computable, and from where. That coverage gap is a finding of the project, not
an error to hide.

All monetary symbols are in USD thousands, matching the FDIC series.
"""
from __future__ import annotations

from dataclasses import dataclass

AVAILABLE, DERIVED, UNAVAILABLE = "available", "derived", "unavailable"
CALLREPORT = "callreport"


@dataclass(frozen=True)
class Symbol:
    name: str
    description: str
    availability: str
    fdic_field: str | None = None
    formula: str | None = None            # for DERIVED
    call_report: str | None = None        # where an UNAVAILABLE/CALLREPORT one lives
    mdrm: tuple[str, ...] = ()            # MDRM codes, for CALLREPORT symbols
    unit: str = "usd_thousands"


def _a(n, d, f, unit="usd_thousands"): return Symbol(n, d, AVAILABLE, fdic_field=f, unit=unit)
def _d(n, d, formula, unit="usd_thousands"): return Symbol(n, d, DERIVED, formula=formula, unit=unit)
def _u(n, d, src, unit="usd_thousands"): return Symbol(n, d, UNAVAILABLE, call_report=src, unit=unit)
def _c(n, d, src, mdrm, unit="usd_thousands"):
    return Symbol(n, d, CALLREPORT, call_report=src, mdrm=mdrm, unit=unit)


SYMBOLS: dict[str, Symbol] = {s.name: s for s in [
    # ---- portfolio composition -------------------------------------------
    _a("total_assets", "Total assets", "ASSET"),
    _a("gross_loans", "Total loans and leases, gross", "LNLSGR"),
    _a("net_loans", "Total loans and leases, net of allowance", "LNLSNET"),
    _a("credit_card_balances", "Credit card loans to individuals (drawn balances)", "LNCRCD"),
    _a("auto_loans", "Automobile loans", "LNAUTO"),
    _a("other_consumer_loans", "Other loans to individuals", "LNCONOTH"),
    _a("ci_loans", "Commercial and industrial loans", "LNCI"),
    _a("ag_loans", "Agricultural production loans", "LNAG"),
    _a("re_construction", "Construction and land development loans", "LNRECONS"),
    _a("re_resi_1_4", "1-4 family residential real estate loans", "LNRERES"),
    _a("re_multifamily", "Multifamily residential real estate loans", "LNREMULT"),
    _a("re_nonresidential", "Nonfarm nonresidential real estate loans", "LNRENRES"),
    _a("securities_total", "Total investment securities", "SC"),
    _a("securities_ust", "US Treasury and agency securities", "SCUS"),
    _a("securities_muni", "State and municipal obligations", "SCMUNI"),
    _a("cash_and_due", "Cash and balances due from depository institutions", "CHBAL"),

    # ---- funding ----------------------------------------------------------
    _a("deposits_total", "Total deposits", "DEP"),
    _a("deposits_domestic", "Domestic office deposits", "DEPDOM"),
    _a("deposits_insured", "Estimated insured deposits", "DEPINS"),
    _a("deposits_uninsured", "Estimated uninsured deposits", "DEPUNINS"),
    _a("repo_funding", "Federal funds purchased and repurchase agreements", "FREPP"),

    # ---- capital and RWA --------------------------------------------------
    _a("cet1_capital", "Common equity tier 1 capital", "RBCT1C"),
    _a("tier1_capital", "Tier 1 capital", "RBCT1J"),
    _a("tier2_capital", "Tier 2 capital", "RBCT2"),
    _a("total_rwa", "Total risk-weighted assets", "RWAJT"),
    _a("total_equity", "Total equity capital", "EQTOT"),
    _d("total_capital", "Total regulatory capital", "tier1_capital + tier2_capital"),
    _d("cet1_ratio", "CET1 capital ratio", "cet1_capital / total_rwa", unit="ratio"),
    _d("tier1_ratio", "Tier 1 capital ratio", "tier1_capital / total_rwa", unit="ratio"),
    _d("total_capital_ratio", "Total capital ratio", "total_capital / total_rwa", unit="ratio"),
    _a("leverage_ratio_reported", "Tier 1 leverage ratio as reported", "RBC1AAJ", unit="percent"),
    _a("cet1_ratio_reported", "CET1 ratio as reported", "RBCT1CER", unit="percent"),

    # ---- credit quality ---------------------------------------------------
    _a("allowance_credit_losses", "Allowance for loan and lease losses", "LNATRES"),
    _a("net_chargeoffs_ytd", "Net charge-offs, year to date", "NTLNLS"),
    _a("noncurrent_loans", "Noncurrent loans and leases", "NCLNLS"),
    _a("nonaccrual_assets", "Nonaccrual assets", "NAASSET"),
    _a("provision_expense", "Provision for credit losses", "ELNATR"),

    # ---- performance ------------------------------------------------------
    _a("roa", "Return on assets", "ROA", unit="percent"),
    _a("roe", "Return on equity", "ROE", unit="percent"),
    _a("nim", "Net interest margin", "NIMY", unit="percent"),
    _a("efficiency_ratio", "Efficiency ratio", "EEFFR", unit="percent"),
    _a("interest_income", "Total interest income", "INTINC"),

    # ---- derived portfolio shape -----------------------------------------
    _d("credit_card_share", "Credit cards as a share of gross loans",
       "credit_card_balances / gross_loans", unit="ratio"),
    _d("loan_to_asset", "Gross loans as a share of total assets",
       "gross_loans / total_assets", unit="ratio"),
    _d("liquid_assets", "Cash plus securities — a coarse liquidity proxy",
       "cash_and_due + securities_total"),
    _d("nco_rate", "Annualised net charge-off rate on gross loans",
       "net_chargeoffs_ytd / gross_loans", unit="ratio"),
    _d("coverage_ratio", "Allowance over noncurrent loans",
       "allowance_credit_losses / noncurrent_loans", unit="ratio"),
    _d("total_card_exposure", "Drawn card balances plus committed undrawn lines",
       "credit_card_balances + undrawn_credit_card_lines"),
    _d("card_line_utilisation", "Drawn share of total committed card lines",
       "credit_card_balances / (credit_card_balances + undrawn_credit_card_lines)",
       unit="ratio"),

    # ---- filed on a Call Report schedule, absent from the FDIC series ------
    _c("undrawn_credit_card_lines",
       "Unused commitments on credit card lines — the exposure Basel converts "
       "with a CCF, and the quantity the supervisor's worked example turns on. "
       "For small card banks it routinely exceeds the drawn book several times "
       "over, and it is absent from the FDIC series.",
       "Call Report Schedule RC-L, item 3815", ("RCFD3815", "RCON3815")),
    _c("undrawn_commitments_other",
       "Other unused revolving commitments (HELOC and similar)",
       "Call Report Schedule RC-L, item 3814", ("RCFD3814", "RCON3814")),
    _c("credit_card_loans_cr", "Credit-card loans as filed on Schedule RC-C",
       "Call Report Schedule RC-C Part I, item B538", ("RCFDB538", "RCONB538")),
    _c("other_revolving_plans", "Other revolving credit plan loans",
       "Call Report Schedule RC-C Part I, item B539", ("RCFDB539", "RCONB539")),

    # ---- declared but NOT in any public filing ----------------------------
    _u("credit_card_transactor_balances",
       "Balances of obligors who repay in full each cycle — determines the "
       "45% vs 75% Basel retail risk weight",
       "not collected by any US regulatory report; requires issuer-internal data"),
    _u("credit_card_revolver_balances",
       "Balances of obligors carrying a balance",
       "not collected by any US regulatory report; requires issuer-internal data"),
    _u("credit_card_accounts",
       "Number of open card accounts — the supervisor's 'how many cards issued'",
       "not in FDIC series; partially in FR Y-14M for large filers only"),
    _u("hqla", "High-quality liquid assets as defined for the LCR",
       "FR 2052a; only banks above the $100bn LCR threshold report it"),
    _u("net_cash_outflows_30d", "Total net 30-day stressed cash outflows",
       "FR 2052a; LCR filers only"),
    _u("available_stable_funding", "ASF for the NSFR", "FR 2052a; NSFR filers only"),
    _u("required_stable_funding", "RSF for the NSFR", "FR 2052a; NSFR filers only"),
    _u("pd_qrre", "IRB probability of default for QRRE",
       "bank-internal IRB model; not published"),
    _u("lgd_qrre", "IRB loss given default for QRRE",
       "bank-internal IRB model; not published"),
    _u("largest_exposure", "Largest single-counterparty exposure",
       "not published for banks below the large-exposure reporting threshold"),
]}

BY_AVAILABILITY = {
    k: [s.name for s in SYMBOLS.values() if s.availability == k]
    for k in (AVAILABLE, DERIVED, CALLREPORT, UNAVAILABLE)
}


def catalogue_markdown() -> str:
    """Human/agent-readable listing, used as the parameterisation prompt input."""
    rows = ["| symbol | availability | unit | source | description |",
            "| --- | --- | --- | --- | --- |"]
    for s in SYMBOLS.values():
        src = s.fdic_field or s.formula or "/".join(s.mdrm) or s.call_report or ""
        rows.append(f"| `{s.name}` | {s.availability} | {s.unit} | {src} | {s.description} |")
    return "\n".join(rows)


if __name__ == "__main__":
    import sys
    if "--markdown" in sys.argv:
        print(catalogue_markdown())
    else:
        for k, v in BY_AVAILABILITY.items():
            print(f"{k:12} ({len(v)}): {', '.join(v)}\n")
