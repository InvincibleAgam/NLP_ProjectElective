"""
FFIEC Call Report bulk data -> per-bank filing histories.

A bank does not file an "annual report" with the FFIEC. It files a Call Report
every quarter, and the 31 December filing is the fiscal-year-end one. This module
collects a run of quarterly cycles, so each bank ends up with three annual
filings (the year-ends) and the eight intervening quarters that show how it got
between them.

The bulk distribution is one ZIP per reporting cycle holding ~48 tab-delimited
schedule files keyed on IDRSSD, some split across parts. Cycles are read one at a
time and filtered down to the selected banks immediately, because holding twelve
parsed cycles at once costs gigabytes and buys nothing.

Why this route: www.ffiec.gov/npw refuses automated clients outright (HTTP 403
from a WAF), and the CDR report UI is an ASP.NET postback app. The bulk download
is the route FFIEC publishes for programmatic access, and it carries strictly
more than the rendered reports do — notably Schedule RC-L item 3815, unused
credit-card line commitments, which is absent from the FDIC series.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# --- field codes ------------------------------------------------------------
# Each is a tuple because banks with foreign offices file RCFD/RCFA codes while
# domestic-only banks file RCON/RCOA; we take whichever the bank actually used.
TOTAL_ASSETS = ("RCFD2170", "RCON2170")
TOTAL_EQUITY = ("RCFD3210", "RCON3210")
TOTAL_LOANS = ("RCFD2122", "RCON2122")
CARD_LOANS = ("RCFDB538", "RCONB538")
OTHER_REVOLVING = ("RCFDB539", "RCONB539")
UNUSED_CARD_LINES = ("RCFD3815", "RCON3815")
UNUSED_REVOLVING = ("RCFD3814", "RCON3814")
ALLOWANCE = ("RCFD3123", "RCON3123")
CET1 = ("RCFAP859", "RCOAP859")
TIER1 = ("RCFA8274", "RCOA8274")
RWA = ("RCFAA223", "RCOAA223")
LEVERAGE_RATIO = ("RCFA7204", "RCOA7204")      # tier 1 leverage ratio, percent
TIER1_RBC_RATIO = ("RCFA7206", "RCOA7206")
NET_INCOME = ("RIAD4340",)
CARD_CHARGEOFFS = ("RIADB514",)
CARD_RECOVERIES = ("RIADB515",)

SCHEDULE_RE = re.compile(r"Call Schedule ([A-Z]+) ", re.I)
CYCLE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _rows(path: Path):
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        r = csv.reader(fh, delimiter="\t")
        codes = [c.strip().strip('"') for c in next(r)]
        second = next(r, None)
        if second is None:
            return
        # POR carries one header row; schedule files carry a human-label row too.
        if second and second[0].strip().strip('"').isdigit():
            yield dict(zip(codes, second))
        for row in r:
            if row:
                yield dict(zip(codes, row))


def discover_cycles(root: Path) -> list[tuple[str, Path]]:
    return sorted(((p.name, p) for p in root.iterdir()
                   if p.is_dir() and CYCLE_DIR_RE.match(p.name)), key=lambda t: t[0])


def load_cycle(folder: Path, only: set[str] | None = None) -> tuple[dict, dict]:
    """(directory_by_rssd, values_by_rssd) for one cycle, optionally filtered."""
    directory: dict[str, dict] = {}
    values: dict[str, dict] = defaultdict(dict)

    por = next(folder.glob("*POR*.txt"), None)
    if por is None:
        raise SystemExit(f"no POR directory file in {folder}")
    for rec in _rows(por):
        rssd = (rec.get("IDRSSD") or "").strip()
        if rssd and (only is None or rssd in only):
            directory[rssd] = {k: (v or "").strip() for k, v in rec.items()}

    for f in sorted(folder.glob("*Call Schedule*.txt")):
        m = SCHEDULE_RE.search(f.name)
        sched = m.group(1).upper() if m else f.stem
        for rec in _rows(f):
            rssd = (rec.get("IDRSSD") or "").strip()
            if not rssd or (only is not None and rssd not in only):
                continue
            bucket = values[rssd]
            for code, raw in rec.items():
                if code in ("IDRSSD", "") or raw is None or raw.strip() == "":
                    continue
                bucket[code] = raw.strip()
            bucket.setdefault("_schedules", set()).add(sched)
    return directory, values


def num(vals: dict, codes: tuple[str, ...]) -> float | None:
    for c in codes:
        v = vals.get(c)
        if v not in (None, "", "CONF"):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)[:48]


def metrics(vals: dict) -> dict:
    """Headline figures for one bank-quarter."""
    assets = num(vals, TOTAL_ASSETS)
    loans = num(vals, TOTAL_LOANS)
    cards = num(vals, CARD_LOANS)
    undrawn = num(vals, UNUSED_CARD_LINES)
    cet1, rwa = num(vals, CET1), num(vals, RWA)
    committed = (cards or 0) + (undrawn or 0)
    co, rec = num(vals, CARD_CHARGEOFFS), num(vals, CARD_RECOVERIES)
    return {
        "total_assets_k": assets,
        "total_loans_k": loans,
        "total_equity_k": num(vals, TOTAL_EQUITY),
        "credit_card_loans_k": cards,
        "other_revolving_k": num(vals, OTHER_REVOLVING),
        "unused_card_lines_k": undrawn,
        "unused_revolving_k": num(vals, UNUSED_REVOLVING),
        "card_exposure_k": committed or None,
        "card_share_of_loans": (cards / loans) if (cards and loans) else None,
        "utilisation": (cards / committed) if (cards and committed) else None,
        "allowance_k": num(vals, ALLOWANCE),
        "cet1_k": cet1,
        "tier1_k": num(vals, TIER1),
        "rwa_k": rwa,
        "cet1_ratio": (cet1 / rwa) if (cet1 and rwa) else None,
        "tier1_rbc_ratio_pct": num(vals, TIER1_RBC_RATIO),
        "leverage_ratio_pct": num(vals, LEVERAGE_RATIO),
        "net_income_ytd_k": num(vals, NET_INCOME),
        "card_net_chargeoffs_ytd_k": (co - rec) if (co is not None and rec is not None) else None,
    }


def select(directory, values, max_assets_k: float, n: int) -> list[dict]:
    """Small banks with a credit-card business, ranked by total card exposure."""
    out = []
    for rssd, vals in values.items():
        m = metrics(vals)
        a = m["total_assets_k"]
        if not a or a >= max_assets_k:
            continue
        if not (m["credit_card_loans_k"] or m["unused_card_lines_k"]):
            continue
        info = directory.get(rssd, {})
        out.append({
            "rssd": rssd,
            "cert": info.get("FDIC Certificate Number", ""),
            "name": info.get("Financial Institution Name", f"RSSD {rssd}"),
            "city": info.get("Financial Institution City", ""),
            "state": info.get("Financial Institution State", ""),
            **m,
        })
    out.sort(key=lambda r: -(r["card_exposure_k"] or 0))
    return out[:n]


def _m(v):
    return "n/a" if v is None else f"${v / 1e3:,.1f}m"


def _p(v):
    return "n/a" if v is None else f"{v * 100:,.1f}%"


TREND_COLS = ["total_assets_k", "total_loans_k", "credit_card_loans_k",
              "unused_card_lines_k", "card_exposure_k", "utilisation",
              "card_share_of_loans", "cet1_k", "rwa_k", "cet1_ratio",
              "leverage_ratio_pct", "allowance_k", "net_income_ytd_k",
              "card_net_chargeoffs_ytd_k"]


def write_bank(dest: Path, bank: dict, series: dict[str, dict], cycles: list[str]) -> None:
    d = dest / f"{bank['rssd']}_{slug(bank['name'])}"
    d.mkdir(parents=True, exist_ok=True)

    per_q = {}
    for cyc in cycles:
        vals = series.get(cyc)
        if not vals:
            continue
        filed = {k: v for k, v in vals.items() if not k.startswith("_")}
        per_q[cyc] = metrics(vals)
        (d / f"call_report_{cyc}.json").write_text(json.dumps({
            "institution": {k: bank[k] for k in ("rssd", "cert", "name", "city", "state")},
            "report_date": cyc,
            "report": "FFIEC Call Report (FFIEC 031/041/051)",
            "is_fiscal_year_end": cyc.endswith("12-31"),
            "source": "FFIEC CDR Public Data Distribution, bulk single-period download",
            "schedules_filed": sorted(vals.get("_schedules", [])),
            "field_count": len(filed),
            "fields": filed,
        }, indent=1, sort_keys=True), encoding="utf-8")

    with (d / "trends.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["report_date"] + TREND_COLS)
        for cyc in cycles:
            if cyc in per_q:
                w.writerow([cyc] + [per_q[cyc].get(c) for c in TREND_COLS])

    years = [c for c in cycles if c.endswith("12-31")]
    present = [c for c in cycles if c in per_q]
    lines = [
        f"# {bank['name']}",
        "",
        f"RSSD {bank['rssd']}"
        + (f" · FDIC cert {bank['cert']}" if bank["cert"] else "")
        + (f" · {bank['city']}, {bank['state']}" if bank["city"] else ""),
        "",
        f"Call Reports for {len(present)} quarters, {present[0]} to {present[-1]}. "
        f"The {'/'.join(y[:4] for y in years if y in per_q)} year-end filings are the annual reports; "
        "the rest are the quarters in between.",
        "",
        "## Annual filings (fiscal year-end)",
        "",
        "| | " + " | ".join(y[:4] for y in years) + " |",
        "| --- |" + " ---: |" * len(years),
    ]

    def arow(label, key, fmt=_m):
        return f"| {label} | " + " | ".join(
            fmt(per_q.get(y, {}).get(key)) for y in years) + " |"

    lines += [
        arow("Total assets", "total_assets_k"),
        arow("Total loans and leases", "total_loans_k"),
        arow("Total equity", "total_equity_k"),
        arow("Credit-card loans (RC-C B538)", "credit_card_loans_k"),
        arow("**Unused card lines (RC-L 3815)**", "unused_card_lines_k"),
        arow("Total card exposure", "card_exposure_k"),
        arow("Line utilisation", "utilisation", _p),
        arow("Card share of loans", "card_share_of_loans", _p),
        arow("CET1 capital", "cet1_k"),
        arow("Risk-weighted assets", "rwa_k"),
        arow("CET1 ratio", "cet1_ratio", _p),
        arow("Allowance for credit losses", "allowance_k"),
        arow("Net income (full year)", "net_income_ytd_k"),
        arow("Card net charge-offs (full year)", "card_net_chargeoffs_ytd_k"),
        "",
        "## Quarterly series",
        "",
        "| quarter | assets | card loans | unused card lines | utilisation | CET1 ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cyc in present:
        m = per_q[cyc]
        lines.append(f"| {cyc} | {_m(m['total_assets_k'])} | {_m(m['credit_card_loans_k'])} "
                     f"| {_m(m['unused_card_lines_k'])} | {_p(m['utilisation'])} "
                     f"| {_p(m['cet1_ratio'])} |")

    missing = [c for c in cycles if c not in per_q]
    lines += [
        "",
        f"Full series in `trends.csv`. Every field as filed is in "
        f"`call_report_<date>.json`, keyed by MDRM code.",
    ]
    if missing:
        lines.append("")
        lines.append(f"No filing found for: {', '.join(missing)} — the institution "
                     "was not chartered or not reporting under this RSSD then.")
    if any(cyc.endswith("12-31") for cyc in present):
        lines += ["", "Income and charge-off items are year-to-date, so the "
                      "December figure is the full year."]
    (d / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="data/callreport")
    ap.add_argument("--out", default="bank_filings_2023_2025")
    ap.add_argument("--max-assets", type=float, default=10_000_000, help="$ thousands")
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    cycles = discover_cycles(Path(args.root))
    if not cycles:
        raise SystemExit(f"no cycle folders under {args.root}")
    print(f"cycles: {', '.join(c for c, _ in cycles)}", file=sys.stderr)

    latest_name, latest_path = cycles[-1]
    directory, values = load_cycle(latest_path)
    banks = select(directory, values, args.max_assets, args.n)
    keep = {b["rssd"] for b in banks}
    print(f"selected {len(banks)} small banks on {latest_name} "
          f"(< ${args.max_assets/1e6:,.0f}bn assets, with a card business)", file=sys.stderr)

    series: dict[str, dict[str, dict]] = defaultdict(dict)
    for name, path in cycles:
        vals = values if name == latest_name else load_cycle(path, only=keep)[1]
        for rssd in keep:
            if rssd in vals:
                series[rssd][name] = vals[rssd]
        print(f"  {name}: {sum(1 for r in keep if r in vals)}/{len(keep)} banks filed",
              file=sys.stderr)

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    order = [c for c, _ in cycles]
    for b in banks:
        write_bank(dest, b, series[b["rssd"]], order)

    with (dest / "INDEX.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(banks[0].keys()))
        w.writeheader()
        w.writerows(banks)
    print(f"wrote {len(banks)} bank folders x {len(order)} quarters -> {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
