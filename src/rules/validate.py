"""
Grounding and schema validation for extracted rules and parameters.

The anti-hallucination guarantee in this project is deliberately *mechanical*
rather than model-judged: a rule survives only if its `quote` is an exact
substring of the source paragraph it cites.  No LLM is asked whether the quote
is faithful, so no LLM can be wrong about it.

Normalisation before matching is limited to whitespace and the typographic
characters PDF extraction is known to vary on (quotes, dashes, non-breaking
spaces).  Nothing that could change meaning is normalised away.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.corpus import Para, load_corpus  # noqa: E402

RULE_CLASSES = {
    "scope_definition", "capital_adequacy", "credit_risk_rwa", "credit_risk_mitigation",
    "provisioning", "liquidity", "funding", "leverage", "concentration",
    "securitisation", "issuance_underwriting", "operational", "supervisory_review",
    "disclosure",
}
PRODUCTS = {
    "credit_card", "revolving_retail", "personal_loan", "sme", "mortgage",
    "corporate", "sovereign", "bank_exposure", "securitisation", "all",
}
OBLIGATIONS = {"must", "should", "may", "definition"}
KINDS = {"coefficient", "ratio_requirement", "limit", "eligibility_test", "input_definition"}
AVAILABILITY = {"exact", "proxy", "unavailable"}

_QUOTE_MAP = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", "−": "-", " ": " ",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in _QUOTE_MAP.items():
        s = s.replace(a, b)
    # The BIS export renders its page footer in a font with no ToUnicode map, so
    # it extracts as a 38-character run of U+FFFD. Dropping it on both sides keeps
    # a quote that happens to span a page break matchable.
    s = s.replace("\ufffd", "")
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class Report:
    ok: list[dict] = field(default_factory=list)
    rejected: list[tuple[dict, str]] = field(default_factory=list)

    def add_ok(self, r): self.ok.append(r)
    def reject(self, r, why): self.rejected.append((r, why))

    def summary(self) -> str:
        lines = [f"accepted {len(self.ok)}, rejected {len(self.rejected)}"]
        for r, why in self.rejected:
            lines.append(f"  REJECT {r.get('rule_id') or r.get('param_id')}: {why}")
        return "\n".join(lines)


def validate_rules(rules: list[dict], paras: list[Para]) -> Report:
    idx = {p.para_id: p for p in paras}
    haystack = {pid: norm(" ".join([p.text, *p.footnotes, *p.faqs])) for pid, p in idx.items()}
    rep = Report()
    seen: set[str] = set()

    for r in rules:
        rid = r.get("rule_id")
        if not rid:
            rep.reject(r, "missing rule_id"); continue
        if rid in seen:
            rep.reject(r, f"duplicate rule_id {rid}"); continue

        for f in ("title", "statement", "quote", "source", "obligation", "rule_class", "products"):
            if not r.get(f):
                rep.reject(r, f"missing field '{f}'"); break
        else:
            pids = r["source"].get("para_ids") or []
            missing = [p for p in pids if p not in idx]
            if not pids:
                rep.reject(r, "no source.para_ids"); continue
            if missing:
                rep.reject(r, f"cites non-existent paragraph(s): {missing}"); continue
            if r["obligation"] not in OBLIGATIONS:
                rep.reject(r, f"bad obligation '{r['obligation']}'"); continue
            bad_cls = set(r["rule_class"]) - RULE_CLASSES
            if bad_cls:
                rep.reject(r, f"unknown rule_class {sorted(bad_cls)}"); continue
            bad_prod = set(r["products"]) - PRODUCTS
            if bad_prod:
                rep.reject(r, f"unknown products {sorted(bad_prod)}"); continue

            q = norm(r["quote"])
            if len(q) < 25:
                rep.reject(r, "quote too short to be verifiable"); continue
            if not any(q in haystack[p] for p in pids):
                rep.reject(r, f"quote not found verbatim in {pids}"); continue

            seen.add(rid)
            rep.add_ok(r)
    return rep


def validate_params(params: list[dict], rule_ids: set[str]) -> Report:
    rep = Report()
    seen: set[str] = set()
    for p in params:
        pid = p.get("param_id")
        if not pid:
            rep.reject(p, "missing param_id"); continue
        if pid in seen:
            rep.reject(p, f"duplicate param_id {pid}"); continue
        if p.get("kind") not in KINDS:
            rep.reject(p, f"bad kind '{p.get('kind')}'"); continue
        if not p.get("formula"):
            rep.reject(p, "missing formula"); continue
        linked = set(p.get("rule_ids") or [])
        if not linked:
            rep.reject(p, "not linked to any rule"); continue
        orphan = linked - rule_ids
        if orphan:
            rep.reject(p, f"links to unknown rule(s) {sorted(orphan)}"); continue
        for inp in p.get("inputs") or []:
            if inp.get("availability") not in AVAILABILITY:
                rep.reject(p, f"input '{inp.get('symbol')}' bad availability"); break
        else:
            seen.add(pid)
            rep.add_ok(p)
    return rep


def _read(path: str) -> list[dict]:
    txt = Path(path).read_text(encoding="utf-8")
    data = json.loads(txt)
    return data if isinstance(data, list) else data.get("rules") or data.get("parameters") or []


if __name__ == "__main__":
    paras = load_corpus()
    rules = _read(sys.argv[1])
    rep = validate_rules(rules, paras)
    print("RULES:", rep.summary())
    if len(sys.argv) > 2:
        prep = validate_params(_read(sys.argv[2]), {r["rule_id"] for r in rep.ok})
        print("PARAMS:", prep.summary())
