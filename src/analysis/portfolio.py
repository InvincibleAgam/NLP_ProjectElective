"""
Bank size tiering and credit-portfolio composition.

Two questions the brief asks before any rule can be applied:
  - which size tier is this bank in (because that decides which rules bind), and
  - what does its credit portfolio currently look like?

Tiering uses regulatory thresholds, not round numbers — see `ingest.fdic`. The
composition view is deliberately expressed as *shares of the loan book* rather
than dollars, because that is the quantity a redistribution proposal actually
moves, and it makes banks of different sizes comparable.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

BUCKETS = [
    "credit_card", "auto", "other_consumer", "commercial_industrial",
    "agricultural", "re_construction", "re_residential_1_4",
    "re_multifamily", "re_nonresidential",
]
SHARE_COLS = [f"share_{b}" for b in BUCKETS]


def latest_quarter(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["REPDTE"] == df["REPDTE"].max()].copy()


def tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    latest = latest_quarter(df)
    g = latest.groupby("size_tier")
    out = pd.DataFrame({
        "banks": g["CERT"].nunique(),
        "assets_usd_bn": g["ASSET"].sum() / 1e6,
        "median_assets_usd_mn": g["ASSET"].median() / 1e3,
        "with_credit_cards": g.apply(lambda d: int((d["LNCRCD"] > 0).sum()), include_groups=False),
        "median_cc_share": g["share_credit_card"].median(),
        "median_cet1_pct": g["RBCT1CER"].median(),
    })
    return out.reindex(["small", "medium", "large"]).dropna(how="all")


def card_active_banks(df: pd.DataFrame, tier: str = "small",
                      min_share: float = 0.005, min_balance_k: float = 10_000) -> pd.DataFrame:
    """Banks in a tier whose card book is large enough to be worth modelling."""
    latest = latest_quarter(df)
    sel = latest[(latest["size_tier"] == tier)
                 & (latest["LNCRCD"] >= min_balance_k)
                 & (latest["share_credit_card"] >= min_share)]
    cols = ["CERT", "NAME", "STALP", "ASSET", "LNLSGR", "LNCRCD", "share_credit_card",
            "RBCT1CER", "RBC1AAJ", "ROA", "ROE", "NIMY", "EEFFR",
            "LNATRESR", "NTLNLS", "loan_hhi"]
    return sel[[c for c in cols if c in sel.columns]].sort_values(
        "share_credit_card", ascending=False)


def composition(df: pd.DataFrame, cert: int) -> pd.DataFrame:
    """One bank's loan-book composition over the available quarters."""
    b = df[df["CERT"] == cert].sort_values("REPDTE")
    return b.set_index("REPDTE")[SHARE_COLS + ["ASSET", "LNLSGR", "RBCT1CER"]]


def peer_group(df: pd.DataFrame, cert: int, n: int = 15,
               asset_band: float = 0.5) -> pd.DataFrame:
    """Same tier, comparable size, ranked by how similar the loan mix is.

    Similarity is L1 distance over bucket shares: two banks are peers when they
    are exposed to the same things, not merely when they are the same size.
    """
    latest = latest_quarter(df)
    me = latest[latest["CERT"] == cert]
    if me.empty:
        raise ValueError(f"CERT {cert} not present in the latest quarter")
    me = me.iloc[0]
    lo, hi = me["ASSET"] * (1 - asset_band), me["ASSET"] * (1 + asset_band)
    cand = latest[(latest["size_tier"] == me["size_tier"])
                  & latest["ASSET"].between(lo, hi)
                  & (latest["CERT"] != cert)].copy()
    mine = me[SHARE_COLS].astype(float).fillna(0.0)
    cand["mix_distance"] = (cand[SHARE_COLS].fillna(0.0) - mine).abs().sum(axis=1)
    cols = ["CERT", "NAME", "ASSET", "share_credit_card", "mix_distance",
            "ROA", "ROE", "NIMY", "EEFFR", "RBCT1CER", "LNATRESR"]
    return cand.sort_values("mix_distance")[[c for c in cols if c in cand.columns]].head(n)


def main() -> None:
    ap = argparse.ArgumentParser(description="Size tiers and portfolio composition.")
    ap.add_argument("--data", default="data/raw/banks_quarterly.parquet")
    ap.add_argument("--tier", default="small")
    ap.add_argument("--cert", type=int)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    pd.set_option("display.width", 200, "display.max_columns", 40)

    print(f"bank-quarters: {len(df)}  banks: {df['CERT'].nunique()}  "
          f"quarters: {sorted(df['REPDTE'].unique())[0]}..{sorted(df['REPDTE'].unique())[-1]}\n")
    print("=== size tiers (latest quarter) ===")
    print(tier_summary(df).to_string(float_format=lambda v: f"{v:,.3f}"))

    print(f"\n=== {args.tier} banks with a material credit-card book ===")
    ca = card_active_banks(df, args.tier)
    print(f"{len(ca)} banks")
    print(ca.head(args.top).to_string(index=False, float_format=lambda v: f"{v:,.3f}"))

    if args.cert:
        print(f"\n=== CERT {args.cert}: composition over time ===")
        print(composition(df, args.cert).to_string(float_format=lambda v: f"{v:,.4f}"))
        print(f"\n=== CERT {args.cert}: peer group ===")
        print(peer_group(df, args.cert).to_string(index=False, float_format=lambda v: f"{v:,.3f}"))


if __name__ == "__main__":
    main()
