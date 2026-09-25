"""
Profit maximisation for one small bank, subject to the extracted Basel rules.

This is the step the supervisor asked for after rules and parameters: given a
bank, define the parameters that govern it and find the portfolio that earns the
most while staying inside every constraint the rules impose.

The formulation is a linear program because at this level of aggregation it
honestly is one. Each balance-sheet bucket earns a rate and consumes capital,
leverage and liquidity in fixed proportion, so both the objective and every
constraint are linear in the allocation. Nothing is gained by pretending
otherwise, and an LP has the advantage that the binding constraint and its
shadow price fall out of the solution.

Every regulatory coefficient carries the paragraph it comes from. Every bank
coefficient is derived from that bank's own Call Report, not assumed.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

# --- regulatory parameters, each with its source ---------------------------
REG = {
    "rw_retail":      (0.75, "CRE20.68(1)", "Risk weight, regulatory retail not from transactors"),
    "rw_retail_txn":  (0.45, "CRE20.68(2)", "Risk weight, regulatory retail from transactors"),
    "rw_securities":  (0.20, "CRE20.30",    "Risk weight, investment-grade bank/sovereign paper (indicative)"),
    "rw_cash":        (0.00, "CRE20.110",   "Risk weight, cash and central bank balances"),
    "ccf_ucc":        (0.10, "CRE20.100",   "Conversion factor, unconditionally cancellable commitments"),
    "cet1_min":       (0.045, "RBC20.1(1)", "Minimum CET1 ratio"),
    "cet1_buffered":  (0.070, "RBC20.1 + RBC30.2", "CET1 minimum plus the 2.5% conservation buffer"),
    "lev_min":        (0.030, "LEV20.7",    "Minimum leverage ratio"),
    "lcr_drawdown":   (0.05,  "LCR40.64(1)", "30-day drawdown on committed retail facilities"),
    "us_ccf_ucc":     (0.00,  "12 CFR 217.33(b)(1)", "US conversion factor, unconditionally cancellable"),
    "us_rw_retail":   (1.00,  "12 CFR 217.32(l)(5)", "US risk weight, retail as residual other assets"),
}


@dataclass
class Bank:
    name: str
    rssd: str
    # balance sheet, $m
    assets: float
    cards: float
    undrawn: float
    cash: float
    securities: float
    equity: float
    cet1: float
    tier1: float
    rwa_reported: float
    # rates, decimal
    yield_card: float
    fee_rate: float
    opex_rate: float
    nco_rate: float
    yield_cash: float
    yield_sec: float
    funding_cost: float
    utilisation: float
    notes: list[str] = field(default_factory=list)

    @property
    def card_margin(self) -> float:
        """Contribution per dollar of card receivable, before funding."""
        return self.yield_card + self.fee_rate - self.nco_rate - self.opex_rate


def from_filing(path: str) -> Bank:
    d = json.loads(Path(path).read_text())
    f, inst = d["fields"], d["institution"]
    g = lambda *cs: next((float(f[c]) for c in cs if c in f and f[c] not in ("", "CONF")), None)
    m = lambda v: (v or 0.0) / 1e3          # thousands -> $m

    cards, avg = m(g("RCFDB538", "RCONB538")), m(g("RCONB561"))
    avg = avg or cards
    cash = m(g("RCFD0010", "RCON0010"))
    if not cash:
        cash = m(g("RCFD0071", "RCON0071")) + m(g("RCFD0081", "RCON0081"))
    sec = m(g("RCFD1773", "RCON1773")) + m(g("RCFDJJ34", "RCONJJ34") or g("RCFD1754", "RCON1754"))
    assets, equity = m(g("RCFD2170", "RCON2170")), m(g("RCFD3210", "RCON3210"))
    undrawn = m(g("RCFD3815", "RCON3815"))

    int_card = m(g("RIADB485"))
    int_cash = m(g("RIAD4115"))
    int_exp = m(g("RIAD4073"))
    nonint_inc, nonint_exp = m(g("RIAD4079")), m(g("RIAD4093"))
    co, rec = m(g("RIADB514")), m(g("RIADB515"))
    liabilities = assets - equity

    return Bank(
        name=inst["name"], rssd=inst["rssd"],
        assets=assets, cards=cards, undrawn=undrawn, cash=cash, securities=sec,
        equity=equity, cet1=m(g("RCFAP859", "RCOAP859")), tier1=m(g("RCFA8274", "RCOA8274")),
        rwa_reported=m(g("RCFAA223", "RCOAA223")),
        yield_card=int_card / avg,
        fee_rate=nonint_inc / cards,
        opex_rate=nonint_exp / cards,
        nco_rate=(co - rec) / avg,
        yield_cash=(int_cash / cash) if cash else 0.045,
        yield_sec=0.042,
        funding_cost=int_exp / liabilities if liabilities else 0.0,
        utilisation=cards / (cards + undrawn) if (cards + undrawn) else 0.0,
        notes=["securities yield is indicative: the bank holds almost none, so the "
               "rate is not identified from its own filing"],
    )


def optimise(b: Bank, *, ccf: float, rw_card: float, rw_sec: float,
             cet1_req: float, growth_cap: float = 0.20,
             util_lo: float = 0.10, util_hi: float = 0.25) -> dict:
    """Maximise pre-tax profit over (cards, securities, cash, undrawn lines).

    growth_cap bounds the balance sheet against its current size: a deposit
    franchise cannot be scaled arbitrarily inside a year, and leaving it
    unbounded makes the answer a statement about capital alone.
    """
    # x = [c, s, h, u]
    net = np.array([
        b.card_margin - b.funding_cost,        # cards, funded
        b.yield_sec - b.funding_cost,          # securities, funded
        b.yield_cash - b.funding_cost,         # cash, funded
        0.0,                                   # undrawn lines earn nothing until drawn
    ])
    A_ub, b_ub, names = [], [], []

    # capital: rw_card*(c + ccf*u) + rw_sec*s <= cet1 / requirement
    A_ub.append([rw_card, rw_sec, 0.0, rw_card * ccf]); b_ub.append(b.cet1 / cet1_req)
    names.append(f"CET1 ≥ {cet1_req:.1%} (RBC20.1, RBC30.2)")

    # leverage: c + s + h + ccf*u <= tier1 / 3%
    A_ub.append([1.0, 1.0, 1.0, ccf]); b_ub.append(b.tier1 / REG["lev_min"][0])
    names.append("Leverage ≥ 3% (LEV20.7)")

    # liquidity: drawdown*u - s - h <= 0
    A_ub.append([0.0, -1.0, -1.0, REG["lcr_drawdown"][0]]); b_ub.append(0.0)
    names.append("Cover a 5% line drawdown (LCR40.64)")

    # balance sheet size: c + s + h <= assets * (1 + growth_cap)
    A_ub.append([1.0, 1.0, 1.0, 0.0]); b_ub.append(b.assets * (1 + growth_cap))
    names.append(f"Balance sheet ≤ +{growth_cap:.0%} (funding capacity)")

    # utilisation band: util_lo <= c/(c+u) <= util_hi
    A_ub.append([1 - util_hi, 0.0, 0.0, -util_hi]); b_ub.append(0.0)
    names.append(f"Utilisation ≤ {util_hi:.0%}")
    A_ub.append([util_lo - 1, 0.0, 0.0, util_lo]); b_ub.append(0.0)
    names.append(f"Utilisation ≥ {util_lo:.0%}")

    res = linprog(-net, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  bounds=[(0, None)] * 4, method="highs")
    c, s, h, u = res.x
    slack = np.array(b_ub) - np.array(A_ub) @ res.x
    duals = -res.ineqlin.marginals if res.ineqlin is not None else np.zeros(len(b_ub))

    return {
        "ok": res.success, "profit": float(net @ res.x),
        "cards": c, "securities": s, "cash": h, "undrawn": u,
        "assets": c + s + h, "utilisation": c / (c + u) if (c + u) else 0,
        "rwa": rw_card * (c + ccf * u) + rw_sec * s,
        "cet1_ratio": b.cet1 / (rw_card * (c + ccf * u) + rw_sec * s),
        "constraints": [{"name": nm, "slack": float(sl), "shadow": float(dl),
                         "binding": bool(abs(sl) < 1e-6)}
                        for nm, sl, dl in zip(names, slack, duals)],
    }


def current_profit(b: Bank) -> float:
    return ((b.card_margin - b.funding_cost) * b.cards
            + (b.yield_sec - b.funding_cost) * b.securities
            + (b.yield_cash - b.funding_cost) * b.cash)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filing",
                    default="bank_filings_2023_2025/1391778_comenity-bank/call_report_2025-12-31.json")
    ap.add_argument("--out", default="outputs/optimisation.json")
    args = ap.parse_args()

    b = from_filing(args.filing)
    print(f"{b.name} (RSSD {b.rssd})")
    print(f"  assets ${b.assets:,.0f}m · cards ${b.cards:,.0f}m · undrawn ${b.undrawn:,.0f}m")
    print(f"  card yield {b.yield_card:.2%} + fees {b.fee_rate:.2%} − losses {b.nco_rate:.2%} "
          f"− opex {b.opex_rate:.2%} = margin {b.card_margin:.2%}")
    print(f"  funding {b.funding_cost:.2%} · utilisation {b.utilisation:.1%}")
    print(f"  current pre-tax contribution ${current_profit(b):,.0f}m\n")

    runs = {
        "basel": optimise(b, ccf=REG["ccf_ucc"][0], rw_card=REG["rw_retail"][0],
                          rw_sec=REG["rw_securities"][0], cet1_req=REG["cet1_buffered"][0]),
        "us_today": optimise(b, ccf=REG["us_ccf_ucc"][0], rw_card=REG["us_rw_retail"][0],
                             rw_sec=REG["rw_securities"][0], cet1_req=REG["cet1_buffered"][0]),
    }
    for k, r in runs.items():
        print(f"--- {k} ---")
        print(f"  cards ${r['cards']:,.0f}m · securities ${r['securities']:,.0f}m · "
              f"cash ${r['cash']:,.0f}m · undrawn ${r['undrawn']:,.0f}m")
        print(f"  assets ${r['assets']:,.0f}m · utilisation {r['utilisation']:.1%} · "
              f"CET1 {r['cet1_ratio']:.1%} · profit ${r['profit']:,.0f}m")
        for c in r["constraints"]:
            if c["binding"]:
                print(f"     BINDING  {c['name']}   shadow {c['shadow']:.4f}")
        print()

    Path(args.out).write_text(json.dumps(
        {"bank": b.__dict__, "current_profit": current_profit(b),
         "reg": {k: {"value": v[0], "cite": v[1], "desc": v[2]} for k, v in REG.items()},
         "runs": runs}, indent=1, default=str))
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
