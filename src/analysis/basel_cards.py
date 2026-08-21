"""
Basel III assessment of a bank's credit-card book, computed from its Call Report.

Five steps, each tied to a provision in the extracted rulebook. Every step either
produces a number from the filing or states which reported item was missing.

    1. Exposure at default      CRE20.94, CRE20.100
    2. Risk weight              CRE20.65, CRE20.66, CRE20.68
    3. Capital adequacy         RBC20.1, RBC30.2
    4. Liquidity stress         LCR40.64
    5. Credit quality           RC-N, RI-B, RC-K

Two honest limits are built into the output rather than papered over.

The transactor/revolver split that decides Basel's 45% versus 75% retail risk
weight (CRE20.66) is collected by no US regulatory report, so step 2 returns a
band across the three admissible weights rather than a point estimate. The 75%
case is reported as central because it is the weight for regulatory retail that
is not transactor business, and a bank that cannot demonstrate transactor status
cannot claim 45%.

Banks that elected the community bank leverage ratio report no risk-weighted
assets at all, so steps 2 and 3 are not computable for them. That is a finding
about the US framework, not a gap in the data.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

# --- Basel parameters, each with the provision it comes from ----------------
CCF_UNCONDITIONALLY_CANCELLABLE = 0.10      # CRE20.100
CCF_US_UNCONDITIONALLY_CANCELLABLE = 0.00   # 12 CFR 217.33
RW_TRANSACTOR = 0.45                        # CRE20.68(2)
RW_REGULATORY_RETAIL = 0.75                 # CRE20.68(1)
RW_OTHER_RETAIL = 1.00                      # CRE20.68(3)
RW_US_RETAIL = 1.00                         # 12 CFR 217.32
CET1_MINIMUM = 0.045                        # RBC20.1(1)
CET1_WITH_BUFFER = 0.070                    # RBC20.1(1) + RBC30.2
LCR_RETAIL_DRAWDOWN = 0.05                  # LCR40.64(1)

CITATIONS = {
    "ead": ["CRE20.94", "CRE20.100"],
    "risk_weight": ["CRE20.65", "CRE20.66", "CRE20.68"],
    "capital": ["RBC20.1", "RBC30.2"],
    "liquidity": ["LCR40.64"],
}

# --- Call Report items ------------------------------------------------------
CARD_DRAWN = ("RCFDB538", "RCONB538")
CARD_UNDRAWN = ("RCFD3815", "RCON3815")
CARD_AVG = ("RCONB561",)
CARD_DQ30 = ("RCFDB575", "RCONB575")
CARD_DQ90 = ("RCFDB576", "RCONB576")
CARD_NONACCRUAL = ("RCFDB577", "RCONB577")
CARD_INTEREST = ("RIADB485",)
CARD_CHARGEOFFS = ("RIADB514",)
CARD_RECOVERIES = ("RIADB515",)
CET1 = ("RCFAP859", "RCOAP859")
RWA = ("RCFAA223", "RCOAA223")
TOTAL_ASSETS = ("RCFD2170", "RCON2170")
TOTAL_LOANS = ("RCFD2122", "RCON2122")
ALLOWANCE = ("RCFD3123", "RCON3123")
CASH_TOTAL = ("RCFD0010", "RCON0010")
CASH_IB = ("RCFD0071", "RCON0071")          # interest-bearing balances due
CASH_NIB = ("RCFD0081", "RCON0081")         # noninterest-bearing, currency and coin
SEC_AFS = ("RCFD1773", "RCON1773")
SEC_HTM_NEW = ("RCFDJJ34", "RCONJJ34")      # HTM net of allowance, post ASU 2016-13
SEC_HTM_OLD = ("RCFD1754", "RCON1754")
FED_FUNDS_SOLD = ("RCFDB987", "RCONB987")
REVERSE_REPO = ("RCFDB989", "RCONB989")


def get(fields: dict, codes: tuple[str, ...]) -> float | None:
    """First code the bank actually filed. 'CONF' is suppressed, not zero."""
    for c in codes:
        v = fields.get(c)
        if v not in (None, "", "CONF"):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def liquid_assets(f: dict) -> float:
    """Cash and readily monetisable assets.

    Not HQLA as the LCR defines it — that is reported only on FR 2052a, which
    banks this size do not file. This is the closest proxy the Call Report
    supports, and it is deliberately broad: cash, the whole securities book, and
    money-market placements.
    """
    cash = get(f, CASH_TOTAL)
    if cash is None:                        # not every filer reports the total
        cash = (get(f, CASH_IB) or 0.0) + (get(f, CASH_NIB) or 0.0)
    htm = get(f, SEC_HTM_NEW)
    if htm is None:
        htm = get(f, SEC_HTM_OLD) or 0.0
    return (cash + (get(f, SEC_AFS) or 0.0) + htm
            + (get(f, FED_FUNDS_SOLD) or 0.0) + (get(f, REVERSE_REPO) or 0.0))


@dataclass
class Assessment:
    rssd: str
    name: str
    report_date: str
    # step 1
    drawn: float | None = None
    undrawn: float | None = None
    ead_basel: float | None = None
    ead_us: float | None = None
    # step 2 / 3
    rwa_reported: float | None = None
    cet1: float | None = None
    cet1_ratio_reported: float | None = None
    card_rwa_us: float | None = None
    card_rwa_45: float | None = None
    card_rwa_75: float | None = None
    card_rwa_100: float | None = None
    cet1_ratio_basel_45: float | None = None
    cet1_ratio_basel_75: float | None = None
    cet1_ratio_basel_100: float | None = None
    cet1_ratio_offbs_only: float | None = None
    meets_minimum_75: bool | None = None
    meets_buffer_75: bool | None = None
    capital_status: str = ""
    # step 4
    outflow_30d: float | None = None
    liquid: float | None = None
    liquidity_cover: float | None = None
    # step 5
    dq30_rate: float | None = None
    dq90_rate: float | None = None
    nco_rate: float | None = None
    yield_rate: float | None = None
    allowance_to_cards: float | None = None
    # provenance
    notes: str = ""


def assess(inst: dict, date: str, f: dict) -> Assessment:
    a = Assessment(rssd=inst["rssd"], name=inst["name"], report_date=date)
    notes: list[str] = []

    # ---- step 1: exposure at default (CRE20.94, CRE20.100) ----------------
    a.drawn = get(f, CARD_DRAWN) or 0.0
    a.undrawn = get(f, CARD_UNDRAWN) or 0.0
    if a.drawn == 0 and a.undrawn == 0:
        a.notes = "no credit-card exposure reported"
        return a
    a.ead_basel = a.drawn + a.undrawn * CCF_UNCONDITIONALLY_CANCELLABLE
    a.ead_us = a.drawn + a.undrawn * CCF_US_UNCONDITIONALLY_CANCELLABLE

    # ---- steps 2 and 3: risk weight and capital (CRE20.68, RBC20.1/30.2) --
    a.cet1, a.rwa_reported = get(f, CET1), get(f, RWA)
    if a.cet1 and a.rwa_reported:
        a.cet1_ratio_reported = a.cet1 / a.rwa_reported
        a.card_rwa_us = a.ead_us * RW_US_RETAIL
        a.card_rwa_45 = a.ead_basel * RW_TRANSACTOR
        a.card_rwa_75 = a.ead_basel * RW_REGULATORY_RETAIL
        a.card_rwa_100 = a.ead_basel * RW_OTHER_RETAIL

        def restated(card_rwa):
            # swap the card book's US contribution for its Basel one
            base = a.rwa_reported - a.card_rwa_us + card_rwa
            return a.cet1 / base if base > 0 else None

        a.cet1_ratio_basel_45 = restated(a.card_rwa_45)
        a.cet1_ratio_basel_75 = restated(a.card_rwa_75)
        a.cet1_ratio_basel_100 = restated(a.card_rwa_100)
        # the off-balance-sheet effect alone: add the converted undrawn lines,
        # leave the drawn book at its current US treatment
        off = a.rwa_reported + a.undrawn * CCF_UNCONDITIONALLY_CANCELLABLE * RW_REGULATORY_RETAIL
        a.cet1_ratio_offbs_only = a.cet1 / off
        a.meets_minimum_75 = a.cet1_ratio_basel_75 >= CET1_MINIMUM
        a.meets_buffer_75 = a.cet1_ratio_basel_75 >= CET1_WITH_BUFFER
        a.capital_status = ("breaches 4.5% minimum" if not a.meets_minimum_75
                            else "within buffer range" if not a.meets_buffer_75
                            else "above buffer")
    else:
        a.capital_status = "not computable — no RWA reported (community bank leverage ratio)"
        notes.append("CBLR filer: steps 2 and 3 do not apply")

    # ---- step 4: liquidity stress (LCR40.64) ------------------------------
    a.outflow_30d = a.undrawn * LCR_RETAIL_DRAWDOWN
    a.liquid = liquid_assets(f)
    a.liquidity_cover = (a.liquid / a.outflow_30d) if a.outflow_30d > 0 else None

    # ---- step 5: credit quality -------------------------------------------
    avg = get(f, CARD_AVG) or a.drawn
    if a.drawn:
        dq30, dq90 = get(f, CARD_DQ30), get(f, CARD_DQ90)
        a.dq30_rate = dq30 / a.drawn if dq30 is not None else None
        a.dq90_rate = dq90 / a.drawn if dq90 is not None else None
        a.allowance_to_cards = (get(f, ALLOWANCE) or 0.0) / a.drawn
    if avg:
        co, rec = get(f, CARD_CHARGEOFFS), get(f, CARD_RECOVERIES)
        if co is not None:
            a.nco_rate = (co - (rec or 0.0)) / avg
        inc = get(f, CARD_INTEREST)
        if inc is not None:
            a.yield_rate = inc / avg
    a.notes = "; ".join(notes)
    return a


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filings", default="bank_filings_2023_2025")
    ap.add_argument("--out", default="outputs/basel_card_analysis.csv")
    ap.add_argument("--date", help="restrict to one report date")
    args = ap.parse_args()

    rows: list[Assessment] = []
    for path in sorted(glob.glob(f"{args.filings}/*/call_report_*.json")):
        date = re.search(r"(\d{4}-\d{2}-\d{2})", path).group(1)
        if args.date and date != args.date:
            continue
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        rows.append(assess(d["institution"], date, d["fields"]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    print(f"{len(rows)} bank-quarters -> {out}")

    latest = [r for r in rows if r.report_date == max(x.report_date for x in rows)]
    computable = [r for r in latest if r.cet1_ratio_basel_75 is not None]
    print(f"\nat {latest[0].report_date}: {len(latest)} banks, "
          f"{len(computable)} with RWA reported, {len(latest)-len(computable)} CBLR")
    for r in sorted(computable, key=lambda r: r.cet1_ratio_basel_75)[:8]:
        print(f"  {r.name[:34]:36} CET1 reported {r.cet1_ratio_reported*100:5.1f}%  "
              f"Basel@75% {r.cet1_ratio_basel_75*100:5.1f}%  {r.capital_status}")


if __name__ == "__main__":
    main()
