"""
FFIEC Call Report bulk data -> per-bank year-end filings.

A bank does not file an "annual report" with the FFIEC. It files a Call Report
every quarter, and the 31 December filing is the fiscal-year-end one. That is
what this module treats as the annual report.

The bulk distribution is one ZIP per reporting cycle holding ~48 tab-delimited
schedule files, each keyed on IDRSSD, some split across parts. This reassembles
them into one record per bank and writes a readable year-end report per
institution.

Why this route: www.ffiec.gov/npw refuses automated clients outright (HTTP 403
from a WAF, for curl and every other non-browser agent), and the CDR report UI is
an ASP.NET postback app. The bulk download is the route FFIEC publishes for
programmatic access, and it carries strictly more than the rendered reports do —
notably Schedule RC-L item 3815, unused credit-card line commitments, which is
absent from the FDIC series.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Fields that drive selection and the headline summary.
TOTAL_ASSETS = ("RCFD2170", "RCON2170")
TOTAL_EQUITY = ("RCFD3210", "RCON3210")
CARD_LOANS = ("RCFDB538", "RCONB538")
OTHER_REVOLVING = ("RCFDB539", "RCONB539")
TOTAL_LOANS = ("RCFD2122", "RCON2122")
UNUSED_CARD_LINES = ("RCFD3815", "RCON3815")
UNUSED_REVOLVING = ("RCFD3814", "RCON3814")
ALLOWANCE = ("RCFD3123", "RCON3123")
TIER1 = ("RCFA8274", "RCOA8274")
CET1 = ("RCFAP859", "RCOAP859")
RWA = ("RCFAA223", "RCOAA223")

SCHEDULE_RE = re.compile(r"Call Schedule ([A-Z]+) ", re.I)


def _rows(path: Path):
    """Yield (codes, dict) for a bulk schedule file, skipping the label row."""
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        r = csv.reader(fh, delimiter="\t")
        codes = [c.strip().strip('"') for c in next(r)]
        second = next(r, None)
        if second is None:
            return
        # POR has one header row; schedule files have a human-label row as row 2.
        looks_like_data = second and second[0].strip().strip('"').isdigit()
        if looks_like_data:
            yield codes, dict(zip(codes, second))
        for row in r:
            if row:
                yield codes, dict(zip(codes, row))


def load_cycle(folder: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (directory_by_rssd, values_by_rssd) for one reporting cycle."""
    directory: dict[str, dict] = {}
    values: dict[str, dict] = defaultdict(dict)

    por = next(folder.glob("*POR*.txt"), None)
    if por is None:
        raise SystemExit(f"no POR directory file in {folder}")
    for _, rec in _rows(por):
        rssd = rec.get("IDRSSD", "").strip()
        if rssd:
            directory[rssd] = {k: v.strip() for k, v in rec.items()}

    for f in sorted(folder.glob("*Call Schedule*.txt")):
        m = SCHEDULE_RE.search(f.name)
        sched = m.group(1).upper() if m else f.stem
        for _, rec in _rows(f):
            rssd = rec.get("IDRSSD", "").strip()
            if not rssd:
                continue
            for code, raw in rec.items():
                if code in ("IDRSSD", "") or raw is None:
                    continue
                raw = raw.strip()
                if raw == "":
                    continue
                values[rssd][code] = raw
            values[rssd].setdefault("_schedules", set()).add(sched)
    return directory, values


def num(vals: dict, codes: tuple[str, ...]) -> float | None:
    for c in codes:
        v = vals.get(c)
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)[:48]


def select(directory, values, max_assets_k: float, n: int) -> list[dict]:
    """Small banks with a credit-card business, ranked by total card exposure."""
    out = []
    for rssd, vals in values.items():
        assets = num(vals, TOTAL_ASSETS)
        if assets is None or assets <= 0 or assets >= max_assets_k:
            continue
        cards = num(vals, CARD_LOANS) or 0.0
        undrawn = num(vals, UNUSED_CARD_LINES) or 0.0
        if cards <= 0 and undrawn <= 0:
            continue
        info = directory.get(rssd, {})
        loans = num(vals, TOTAL_LOANS) or 0.0
        out.append({
            "rssd": rssd,
            "cert": info.get("FDIC Certificate Number", ""),
            "name": info.get("Financial Institution Name", f"RSSD {rssd}"),
            "city": info.get("Financial Institution City", ""),
            "state": info.get("Financial Institution State", ""),
            "total_assets_k": assets,
            "total_loans_k": loans,
            "credit_card_loans_k": cards,
            "unused_card_lines_k": undrawn,
            "card_exposure_k": cards + undrawn,
            "card_share_of_loans": (cards / loans) if loans else None,
            "utilisation": (cards / (cards + undrawn)) if (cards + undrawn) else None,
        })
    out.sort(key=lambda r: -r["card_exposure_k"])
    return out[:n]


def _fmt(v, pct=False):
    if v is None:
        return "n/a"
    return f"{v * 100:,.1f}%" if pct else f"${v / 1e3:,.1f}m"


def write_bank(dest: Path, bank: dict, vals: dict, cycle: str) -> None:
    d = dest / f"{bank['rssd']}_{slug(bank['name'])}"
    d.mkdir(parents=True, exist_ok=True)

    schedules = sorted(vals.get("_schedules", []))
    filed = {k: v for k, v in vals.items() if not k.startswith("_")}
    (d / f"call_report_{cycle}.json").write_text(json.dumps({
        "institution": {k: bank[k] for k in ("rssd", "cert", "name", "city", "state")},
        "report_date": cycle,
        "report": "FFIEC Call Report (FFIEC 031/041/051), fiscal year-end filing",
        "source": "FFIEC CDR Public Data Distribution, bulk single-period download",
        "schedules_filed": schedules,
        "field_count": len(filed),
        "fields": filed,
    }, indent=1, sort_keys=True), encoding="utf-8")

    cards = bank["credit_card_loans_k"]
    undrawn = bank["unused_card_lines_k"]
    lines = [
        f"# {bank['name']}",
        "",
        f"**Year-end Call Report, {cycle}** — RSSD {bank['rssd']}"
        + (f", FDIC cert {bank['cert']}" if bank["cert"] else "")
        + (f" — {bank['city']}, {bank['state']}" if bank["city"] else ""),
        "",
        "## Balance sheet",
        "",
        "| | |",
        "| --- | --- |",
        f"| Total assets | {_fmt(bank['total_assets_k'])} |",
        f"| Total equity | {_fmt(num(vals, TOTAL_EQUITY))} |",
        f"| Total loans and leases | {_fmt(bank['total_loans_k'])} |",
        f"| Allowance for credit losses | {_fmt(num(vals, ALLOWANCE))} |",
        "",
        "## Credit-card position",
        "",
        "| | |",
        "| --- | --- |",
        f"| Credit-card loans outstanding (RC-C B538) | {_fmt(cards)} |",
        f"| Other revolving credit plans (RC-C B539) | {_fmt(num(vals, OTHER_REVOLVING))} |",
        f"| **Unused credit-card line commitments (RC-L 3815)** | **{_fmt(undrawn)}** |",
        f"| Other unused revolving commitments (RC-L 3814) | {_fmt(num(vals, UNUSED_REVOLVING))} |",
        f"| Total card exposure (drawn + undrawn) | {_fmt(bank['card_exposure_k'])} |",
        f"| Card share of the loan book | {_fmt(bank['card_share_of_loans'], pct=True)} |",
        f"| Line utilisation (drawn / total committed) | {_fmt(bank['utilisation'], pct=True)} |",
        "",
        "## Regulatory capital",
        "",
        "| | |",
        "| --- | --- |",
        f"| Common equity tier 1 | {_fmt(num(vals, CET1))} |",
        f"| Tier 1 capital | {_fmt(num(vals, TIER1))} |",
        f"| Risk-weighted assets | {_fmt(num(vals, RWA))} |",
        "",
        f"Schedules filed: {', '.join(schedules)}.",
        "",
        f"Every field this institution reported is in `call_report_{cycle}.json` "
        f"({len(filed)} items), keyed by its MDRM code.",
    ]
    (d / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycle-dir", default="data/callreport_2025Q4")
    ap.add_argument("--cycle", default="2025-12-31")
    ap.add_argument("--out", default="annual_reports_2025")
    ap.add_argument("--max-assets", type=float, default=10_000_000, help="$ thousands")
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    directory, values = load_cycle(Path(args.cycle_dir))
    print(f"cycle {args.cycle}: {len(directory)} institutions in directory, "
          f"{len(values)} with filed data", file=sys.stderr)

    banks = select(directory, values, args.max_assets, args.n)
    print(f"selected {len(banks)} small banks (< ${args.max_assets/1e6:,.0f}bn assets) "
          f"with a credit-card business", file=sys.stderr)

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    for b in banks:
        write_bank(dest, b, values[b["rssd"]], args.cycle)

    with (dest / "INDEX.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(banks[0].keys()))
        w.writeheader()
        w.writerows(banks)
    print(f"wrote {len(banks)} bank folders + INDEX.csv -> {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
