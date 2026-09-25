"""
Classify the parameters a rule carries, and hang them on the tree.

The supervisor's framing throughout has been that rules are not the deliverable —
parameters are. "From those rules come the parameters. Which parameters do we
look into?" A branch of the tree is only useful for portfolio work once you can
see, at a glance, what quantities govern it: which risk weight, which conversion
factor, which threshold, which limit.

Extraction is deterministic. Every rule already carries `numeric_values`, short
strings lifted from its text during extraction ("45% risk weight", "25% of Tier 1
capital", "30 calendar days"). This module types them — it does not invent them —
so a parameter shown on a node is traceable to a rule and from there to a
verbatim paragraph.

Anything that cannot be confidently typed is kept as `other` rather than forced
into a category, because a mislabelled risk weight is worse than an unlabelled
number.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

# Ordered: the first pattern that matches wins, so the specific must precede the
# general. "25% of Tier 1 capital" is a limit against capital, not a capital
# ratio, so capital_limit is tested before capital_ratio.
KINDS: list[tuple[str, str, re.Pattern]] = [
    ("formula",       "Formulae",                re.compile(r"=\s*[A-Za-z0-9{(\[]|\bsqrt\b|\bmax\{|\bmin\{|alpha =", re.I)),
    ("lgd",           "Loss given default",      re.compile(r"\blgd\b", re.I)),
    ("risk_weight",   "Risk weights",            re.compile(r"risk[- ]weight|\brw\b", re.I)),
    ("ccf",           "Conversion factors",      re.compile(r"\bccf\b|credit conversion|conversion factor", re.I)),
    ("asf",           "ASF factors",             re.compile(r"\basf\b|available stable funding", re.I)),
    ("rsf",           "RSF factors",             re.compile(r"\brsf\b|required stable funding", re.I)),
    ("hqla",          "HQLA levels and caps",    re.compile(r"level 1|level 2a|level 2b|\bhqla\b", re.I)),
    ("runoff",        "Run-off and drawdown",    re.compile(r"run[- ]?off|draw[- ]?down|outflow|inflow|facility rate", re.I)),
    ("haircut",       "Haircuts",                re.compile(r"haircut|overcollateralisation|discount to market", re.I)),
    ("payout",        "Distribution constraints", re.compile(r"earnings retention|payout|conserv|quartile|retention|%\s*(->|→)|%:\s*\d", re.I)),
    ("deduction",     "Deductions",              re.compile(r"deduction|deducted", re.I)),
    ("capital_limit", "Limits against capital",  re.compile(r"of (the bank's )?(tier ?1|tier ?2|cet ?1|common equity|eligible|total|regulatory)?\s?capital", re.I)),
    ("capital_ratio", "Capital ratios and buffers", re.compile(r"cet ?1|tier ?1|tier ?2|total rwa|credit rwa|total capital|standardised rwa|leverage ratio|minimum ratio|buffer|capital ratio|capital categories", re.I)),
    ("concentration", "Concentration limits",    re.compile(r"of the (overall|subset)|granularity|portfolio|single (counterparty|client)|exposure limit", re.I)),
    ("multiplier",    "Multipliers",             re.compile(r"multiplier|\d+(\.\d+)?\s*[x×]\b|notch", re.I)),
    ("rating",        "Rating bands",            re.compile(r"\b(aaa|aa[-+]?|a[-+]?|bbb[-+]?|bb[-+]?|ccc|a-1|a-2|a-3|p-1|p-2)\b|investment[- ]grade|credit rating|cutoff score", re.I)),
    ("bps",           "Basis-point measures",    re.compile(r"\bbps\b|basis points?", re.I)),
    ("share",         "Shares of an amount",     re.compile(r"of (the )?(deposit|nominal|maturing|returnable|market) (amount|value|assets)|of nominal|of maturing", re.I)),
    ("provisioning",  "Provisioning conditions", re.compile(r"specific provisions|provisions (equal|less|no less)", re.I)),
    ("frequency",     "Observation frequency",   re.compile(r"at least (annually|monthly|quarterly|semi-annually|weekly|daily)|mark[- ]to[- ]market|remargining|averaging|lookback|reporting lag|at origination|refresh", re.I)),
    ("threshold",     "Thresholds and bands",    re.compile(r"ltv|loan-to-value|property value|threshold|exceed|floor|\bcap\b|ceiling|maximum|minimum|€|\$|£|million|billion|maturity band|price decline|vote|voting|share capital", re.I)),
    ("horizon",       "Time horizons",           re.compile(r"\b(day|days|month|months|year|years|quarter|annum|calendar)\b", re.I)),
    ("count",         "Counts and enumerations", re.compile(r"^\d+\s+\w+|conditions|sub-classes|items|categories", re.I)),
]

PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MONEY = re.compile(r"([€$£])\s?(\d+(?:[.,]\d+)?)\s*(million|billion|bn|m\b)?", re.I)


def classify(text: str) -> dict:
    """Type one numeric_values string. Never guesses past what the words support."""
    t = text.strip()
    kind, label = "other", "Other parameters"
    for k, lab, pat in KINDS:
        if pat.search(t):
            kind, label = k, lab
            break

    pcts = [float(m) for m in PCT.findall(t)]
    money = MONEY.search(t)
    # the qualifier is what distinguishes 45% from 75%: the condition attached
    qual = re.sub(r"^\s*[\d.,%€$£\s]+", "", t).strip()
    qual = re.sub(r"^(risk[- ]weight|ccf|asf factor|rsf factor|run-?off (factor|rate)|haircut)\s*", "", qual, flags=re.I).strip()

    return {
        "raw": t,
        "kind": kind,
        "label": label,
        "pct": pcts[0] if pcts else None,
        "money": f"{money.group(1)}{money.group(2)}{' ' + money.group(3) if money.group(3) else ''}" if money else None,
        "qualifier": qual.strip(" ()") or None,
    }


def node_parameters(node: dict, rules: dict) -> list[dict]:
    """Parameters on one node, grouped by kind, each carrying its source rules."""
    groups: OrderedDict[str, dict] = OrderedDict()
    for rid in node["rules"]:
        r = rules.get(rid)
        if not r:
            continue
        for raw in (r.get("numeric_values") or []):
            p = classify(raw)
            g = groups.setdefault(p["kind"], {"kind": p["kind"], "label": p["label"], "values": []})
            hit = next((v for v in g["values"] if v["raw"].lower() == p["raw"].lower()), None)
            if hit:
                if rid not in hit["rules"]:
                    hit["rules"].append(rid)
                    hit["cites"].append(", ".join(r["source"]["para_ids"]))
            else:
                g["values"].append({**p, "rules": [rid],
                                    "cites": [", ".join(r["source"]["para_ids"])]})

    order = [k for k, _, _ in KINDS] + ["other"]
    out = sorted(groups.values(), key=lambda g: order.index(g["kind"]))
    for g in out:
        # numeric parameters read best in ascending order; the rest alphabetically
        g["values"].sort(key=lambda v: (v["pct"] is None, v["pct"] if v["pct"] is not None else 0, v["raw"]))
    return out


def attach(tree: dict, rules: dict) -> tuple[int, int]:
    """Walk the tree, attaching parameters to every node. Returns (nodes, params)."""
    n_nodes = n_params = 0

    def walk(n):
        nonlocal n_nodes, n_params
        params = node_parameters(n, rules)
        n["params"] = params
        n["param_count"] = sum(len(g["values"]) for g in params)
        n_nodes += 1
        n_params += n["param_count"]
        for c in n["children"]:
            walk(c)
        n["param_total"] = n["param_count"] + sum(c["param_total"] for c in n["children"])

    walk(tree)
    return n_nodes, n_params


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", default="outputs/rule_tree.json")
    ap.add_argument("--out", default="outputs/rule_tree.json")
    args = ap.parse_args()

    d = json.loads(Path(args.tree).read_text())
    nodes, params = attach(d["tree"], d["rules"])
    Path(args.out).write_text(json.dumps(d, indent=1, ensure_ascii=False))

    # coverage report: how much could actually be typed
    from collections import Counter
    kinds = Counter()

    def walk(n):
        for g in n["params"]:
            kinds[g["kind"]] += len(g["values"])
        for c in n["children"]:
            walk(c)
    walk(d["tree"])

    print(f"{nodes} nodes, {params} parameters classified")
    for k, c in kinds.most_common():
        lab = next((l for kk, l, _ in KINDS if kk == k), "Other parameters")
        print(f"   {c:4}  {k:14} {lab}")
    unt = kinds.get("other", 0)
    print(f"\nuntyped: {unt}/{params} ({100*unt/max(params,1):.0f}%)")


if __name__ == "__main__":
    main()
