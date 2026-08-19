"""
The canonical symbol vocabulary that Basel-derived formulas are written against.

This module is the contract between the two halves of the project. Rule
extraction produces formulas; the bank connector produces numbers; they only
meet if both sides agree on a fixed set of names. Free-form formulas invented per
rule are not executable, so parameterisation is constrained to these symbols.

Three availability states, and the third is the interesting one:

  AVAILABLE    read directly from the FDIC quarterly series
  DERIVED      computed from available symbols
  UNAVAILABLE  the Basel rule needs it, and a small US bank's published
               quarterly filing does not contain it

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


@dataclass(frozen=True)
class Symbol:
    name: str
    description: str
    availability: str
    fdic_field: str | None = None
    formula: str | None = None            # for DERIVED
    call_report: str | None = None        # where an UNAVAILABLE one lives
    unit: str = "usd_thousands"


def _a(n, d, f, unit="usd_thousands"): return Symbol(n, d, AVAILABLE, fdic_field=f, unit=unit)
def _d(n, d, formula, unit="usd_thousands"): return Symbol(n, d, DERIVED, formula=formula, unit=unit)
def _u(n, d, src, unit="usd_thousands"): return Symbol(n, d, UNAVAILABLE, call_report=src, unit=unit)


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

    # ---- declared but NOT in the published series -------------------------
    _u("undrawn_credit_card_lines",
       "Unused commitments on credit card lines — the exposure Basel converts "
       "with a CCF, and the quantity the supervisor's worked example turns on",
       "Call Report Schedule RC-L, item RCFD/RCON 3815"),
    _u("undrawn_commitments_other",
       "Other unused commitments (HELOC, C&I, CRE)",
       "Call Report Schedule RC-L, items 1.a-1.e"),
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
    for k in (AVAILABLE, DERIVED, UNAVAILABLE)
}


def catalogue_markdown() -> str:
    """Human/agent-readable listing, used as the parameterisation prompt input."""
    rows = ["| symbol | availability | unit | source | description |",
            "| --- | --- | --- | --- | --- |"]
    for s in SYMBOLS.values():
        src = s.fdic_field or s.formula or s.call_report or ""
        rows.append(f"| `{s.name}` | {s.availability} | {s.unit} | {src} | {s.description} |")
    return "\n".join(rows)


if __name__ == "__main__":
    import sys
    if "--markdown" in sys.argv:
        print(catalogue_markdown())
    else:
        for k, v in BY_AVAILABILITY.items():
            print(f"{k:12} ({len(v)}): {', '.join(v)}\n")
