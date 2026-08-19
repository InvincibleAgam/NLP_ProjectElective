#!/usr/bin/env python
"""
Phase 1 end to end: Basel text -> validated rulebook -> constraints evaluated
against real small-bank quarterly filings.

    .venv/bin/python run_phase1.py

The point of running it as one command is that the claim "these rules are
analysable" is checked rather than asserted. Every stage either produces a number
from a real filing or says precisely why it cannot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "src" / "params"))

from rag.corpus import load_corpus                              # noqa: E402
from rules.validate import validate_params, validate_rules      # noqa: E402
from params.symbols import SYMBOLS                              # noqa: E402
from params.evaluate import build_env, evaluate_param           # noqa: E402
from analysis.portfolio import card_active_banks, tier_summary  # noqa: E402

OUT = Path("outputs/phase1")


def _load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get(key, [])


def coverage_table(params: list[dict]) -> pd.DataFrame:
    """Which Basel parameters can actually be measured from public filings."""
    rows = []
    for p in params:
        inputs = p.get("inputs") or []
        syms = [i.get("symbol") for i in inputs]
        known = [s for s in syms if s in SYMBOLS]
        unavail = [s for s in known if SYMBOLS[s].availability == "unavailable"]
        unknown = [s for s in syms if s not in SYMBOLS]
        if unknown:
            status = "off_vocabulary"
        elif unavail:
            status = "needs_unpublished_data"
        elif not syms:
            status = "no_inputs_declared"
        else:
            status = "computable"
        rows.append({
            "param_id": p.get("param_id"),
            "name": p.get("name"),
            "kind": p.get("kind"),
            "status": status,
            "blocking_symbols": ",".join(unavail + unknown),
            "sources_needed": "; ".join(
                sorted({SYMBOLS[s].call_report for s in unavail if SYMBOLS[s].call_report})),
            "rule_ids": ",".join(p.get("rule_ids") or []),
        })
    return pd.DataFrame(rows)


def evaluate_bank(params: list[dict], row: dict) -> tuple[list[dict], dict]:
    env = build_env(row)
    results = [evaluate_param(p, env).as_dict() for p in params]
    summary = {k: sum(r.get("status") == k for r in results)
               for k in ("satisfied", "breached", "computed", "not_computable")}
    summary["n_params"] = len(results)
    return results, summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="outputs/rules/rules.json")
    ap.add_argument("--params", default="outputs/rules/parameters.json")
    ap.add_argument("--banks", default="data/raw/banks_quarterly.parquet")
    ap.add_argument("--tier", default="small")
    ap.add_argument("--n-banks", type=int, default=10)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    paras = load_corpus()

    # ---- 1. rules: schema + verbatim grounding ---------------------------
    rules = _load(Path(args.rules), "rules")
    rrep = validate_rules(rules, paras)
    print(f"[1] rules      : {len(rules)} extracted -> {rrep.summary().splitlines()[0]}")
    for r, why in rrep.rejected[:8]:
        print(f"      - {r.get('rule_id')}: {why}")
    if len(rrep.rejected) > 8:
        print(f"      ... and {len(rrep.rejected) - 8} more")

    # ---- 2. parameters: schema + link integrity --------------------------
    params = _load(Path(args.params), "parameters")
    prep = validate_params(params, {r["rule_id"] for r in rrep.ok})
    print(f"[2] parameters : {len(params)} proposed -> {prep.summary().splitlines()[0]}")

    # ---- 3. measurability against public data ----------------------------
    cov = coverage_table(prep.ok)
    if not cov.empty:
        cov.to_csv(OUT / "coverage.csv", index=False)
        print(f"[3] coverage   : {dict(cov.status.value_counts())}")

    # ---- 4. evaluate on real banks ---------------------------------------
    df = pd.read_parquet(args.banks)
    print(f"[4] banks      : {df['CERT'].nunique()} banks, "
          f"{df['REPDTE'].nunique()} quarters")
    print(tier_summary(df).to_string(float_format=lambda v: f"{v:,.2f}"))

    targets = card_active_banks(df, args.tier).head(args.n_banks)
    latest = df[df["REPDTE"] == df["REPDTE"].max()].set_index("CERT")

    report = {}
    for cert in targets["CERT"]:
        row = latest.loc[cert].to_dict()
        results, summary = evaluate_bank(prep.ok, row)
        report[int(cert)] = {"name": row.get("NAME"), "assets_k": row.get("ASSET"),
                             "summary": summary, "results": results}
    (OUT / "compliance.json").write_text(json.dumps(report, indent=2, default=str))

    print(f"\n[5] evaluated {len(report)} {args.tier} banks with card books:")
    for cert, r in report.items():
        s = r["summary"]
        print(f"    {str(r['name'])[:42]:44} sat={s['satisfied']:3} breach={s['breached']:3} "
              f"calc={s['computed']:3} n/a={s['not_computable']:3}")

    (OUT / "rulebook.json").write_text(json.dumps(
        {"rules": rrep.ok, "parameters": prep.ok}, indent=2, ensure_ascii=False))
    print(f"\n-> {OUT}/rulebook.json, coverage.csv, compliance.json")


if __name__ == "__main__":
    main()
