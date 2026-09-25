"""Render the rule tree as a self-contained, explorable HTML page."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("tree_template.html")


def trim(tree: dict, rules: dict) -> tuple[dict, dict]:
    """Keep only what the page renders, so the payload stays small."""
    used: set[str] = set()

    def node(n):
        used.update(n["rules"])
        return {
            "id": n["id"], "label": n["label"], "desc": n["desc"],
            "note": n.get("note", ""), "status": n.get("status", ""),
            "rules": n["rules"], "n": n["rule_count"], "t": n["total_count"],
            # parameters are the point of the exercise, so they travel with the node
            "params": [{"k": g["kind"], "l": g["label"],
                        "v": [{"raw": v["raw"], "pct": v["pct"], "money": v["money"],
                               "q": v["qualifier"], "c": v["cites"][0] if v["cites"] else "",
                               "r": v["rules"][0] if v["rules"] else ""}
                              for v in g["values"]]}
                       for g in n.get("params", [])],
            "p": n.get("param_count", 0), "pt": n.get("param_total", 0),
            "children": [node(c) for c in n["children"]],
        }

    t = node(tree)
    r = {}
    for rid in used:
        s = rules[rid]
        r[rid] = {
            "t": s["title"], "s": s["statement"], "q": s["quote"],
            "c": ", ".join(s["source"]["para_ids"]),
            "o": s["obligation"], "k": s.get("rule_class", []),
            "p": s.get("products", []), "v": s.get("numeric_values", []),
            "r": s.get("portfolio_relevance", ""),
        }
    return t, r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", default="outputs/rule_tree.json")
    ap.add_argument("--out", default="outputs/rule_tree.html")
    args = ap.parse_args()

    d = json.loads(Path(args.tree).read_text())
    tree, rules = trim(d["tree"], d["rules"])
    html = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps({"tree": tree, "rules": rules}, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("/*__DATA__*/", payload)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"{len(rules)} rules -> {args.out} ({len(html)/1e3:.0f} KB)")


if __name__ == "__main__":
    main()
