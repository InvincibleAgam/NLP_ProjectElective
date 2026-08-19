"""
FDIC BankFind Suite connector: the bank-side counterpart to the Basel corpus.

Every US insured depository files a quarterly Call Report; the FDIC republishes
a normalised subset of it.  That is the "openly published quarterly report" this
project analyses — it is structured, free, complete for all ~4,200 active banks,
and needs no scraping of 600 PDFs.

Size tiering follows the *regulatory* thresholds rather than round numbers,
because the whole point is that which rules bind depends on which tier a bank is
in:

    small   < $10bn    community-bank leverage-ratio eligible (12 CFR 217.12)
    medium  $10-100bn  above the CBLR/stress-test line, below tailoring Cat IV
    large   > $100bn   tailoring Categories I-IV (12 CFR 252 / 217)

Known gap, recorded rather than papered over: undrawn credit-card lines
(Call Report Schedule RC-L, RCFD3815) are NOT in the FDIC series.  Constraints
that need them are flagged `availability: unavailable` and must source
Schedule RC-L directly.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://api.fdic.gov/banks"
CACHE = Path("data/raw/fdic")

SIZE_TIERS = [("small", 0, 10_000_000), ("medium", 10_000_000, 100_000_000),
              ("large", 100_000_000, float("inf"))]   # $ thousands

FIN_FIELDS = [
    "CERT", "REPDTE", "ASSET",
    # credit portfolio composition
    "LNLSGR", "LNLSNET", "LNCRCD", "LNAUTO", "LNCONOTH", "LNCI", "LNAG",
    "LNRE", "LNRECONS", "LNRERES", "LNREMULT", "LNRENRES",
    # other earning assets
    "SC", "SCUS", "SCMUNI", "CHBAL",
    # funding
    "DEP", "DEPDOM", "DEPINS", "DEPUNINS", "FREPP",
    # capital and RWA
    "EQTOT", "RBCT1C", "RBCT1J", "RBCT2", "RWAJT",
    "RBCT1CER", "RBC1RWAJ", "RBCRWAJ", "RBC1AAJ",
    # credit quality
    "LNATRES", "LNATRESR", "NTLNLS", "NCLNLS", "NAASSET", "NPERFV", "ELNATR",
    # performance
    "ROA", "ROE", "NIMY", "EEFFR", "INTINC",
]

LOAN_BUCKETS = {
    "credit_card": "LNCRCD",
    "auto": "LNAUTO",
    "other_consumer": "LNCONOTH",
    "commercial_industrial": "LNCI",
    "agricultural": "LNAG",
    "re_construction": "LNRECONS",
    "re_residential_1_4": "LNRERES",
    "re_multifamily": "LNREMULT",
    "re_nonresidential": "LNRENRES",
}


def _get(endpoint: str, params: dict, retries: int = 4) -> dict:
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NLP-PE academic research"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as exc:                        # transient API flakiness
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"FDIC request failed after {retries} tries: {url}\n{last}")


def _paged(endpoint: str, params: dict, page: int = 5000) -> list[dict]:
    out, offset = [], 0
    while True:
        d = _get(endpoint, {**params, "limit": page, "offset": offset, "format": "json"})
        rows = [r["data"] for r in d.get("data", [])]
        out.extend(rows)
        total = d.get("meta", {}).get("total", len(out))
        offset += page
        if offset >= total or not rows:
            return out


def institutions(min_assets_k: int = 0, cache: bool = True) -> pd.DataFrame:
    """Active FDIC-insured institutions with headline size."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"institutions_{min_assets_k}.parquet"
    if cache and f.exists():
        return pd.read_parquet(f)
    filt = "ACTIVE:1"
    if min_assets_k:
        filt += f" AND ASSET:[{min_assets_k} TO *]"
    rows = _paged("institutions", {
        "filters": filt,
        "fields": "CERT,NAME,ASSET,CITY,STALP,BKCLASS,OFFDOM,ESTYMD,WEBADDR",
    })
    df = pd.DataFrame(rows)
    if cache:
        df.to_parquet(f)
    return df


def financials(certs: list[int], repdtes: list[str], cache: bool = True) -> pd.DataFrame:
    """Quarterly Call Report series for the given banks."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = f"fin_{len(certs)}_{repdtes[0]}_{repdtes[-1]}.parquet"
    f = CACHE / key
    if cache and f.exists():
        return pd.read_parquet(f)

    frames = []
    for rd in repdtes:
        for i in range(0, len(certs), 200):          # keep the filter string sane
            chunk = certs[i:i + 200]
            filt = f"REPDTE:{rd} AND CERT:({' OR '.join(str(c) for c in chunk)})"
            frames.extend(_paged("financials", {"filters": filt, "fields": ",".join(FIN_FIELDS)}))
    df = pd.DataFrame(frames)
    for c in df.columns:
        if c not in ("ID",):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if cache:
        df.to_parquet(f)
    return df


def quarter_ends(n: int, latest: str) -> list[str]:
    """The n most recent quarter-end REPDTEs, oldest first."""
    y, m = int(latest[:4]), int(latest[4:6])
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}{[31, 30, 30, 31][m // 3 - 1]:02d}")
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return sorted(out)


def size_tier(asset_k: float) -> str:
    for name, lo, hi in SIZE_TIERS:
        if lo <= asset_k < hi:
            return name
    return "large"


def portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Add credit-portfolio composition shares to a financials frame."""
    out = df.copy()
    gross = out["LNLSGR"].replace(0, pd.NA)
    for name, col in LOAN_BUCKETS.items():
        out[f"share_{name}"] = out[col] / gross
    out["share_of_assets_loans"] = out["LNLSGR"] / out["ASSET"]
    out["size_tier"] = out["ASSET"].map(size_tier)
    # concentration of the loan book (Herfindahl over the buckets above)
    shares = out[[f"share_{n}" for n in LOAN_BUCKETS]].fillna(0.0)
    out["loan_hhi"] = (shares ** 2).sum(axis=1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull FDIC quarterly bank financials.")
    ap.add_argument("--latest", default="20260331", help="most recent quarter end, YYYYMMDD")
    ap.add_argument("--quarters", type=int, default=12)
    ap.add_argument("--min-assets", type=int, default=1_000_000, help="$ thousands")
    ap.add_argument("--max-banks", type=int, default=0)
    ap.add_argument("--out", default="data/raw/banks_quarterly.parquet")
    args = ap.parse_args()

    inst = institutions(args.min_assets)
    inst = inst.sort_values("ASSET", ascending=False)
    if args.max_banks:
        inst = inst.head(args.max_banks)
    certs = inst["CERT"].astype(int).tolist()
    rds = quarter_ends(args.quarters, args.latest)
    print(f"{len(certs)} banks x {len(rds)} quarters ({rds[0]}..{rds[-1]})")

    fin = financials(certs, rds)
    fin = fin.merge(inst[["CERT", "NAME", "STALP", "BKCLASS"]], on="CERT", how="left")
    fin = portfolio(fin)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fin.to_parquet(args.out)
    print(f"{len(fin)} bank-quarters -> {args.out}")
    print(fin.groupby("size_tier")["CERT"].nunique())


if __name__ == "__main__":
    main()
