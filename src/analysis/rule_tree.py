"""
A balance-sheet-shaped tree of the Basel Framework, with rules hung on the nodes.

The Basel Framework is organised by *standard* — capital here, liquidity there,
leverage somewhere else — which is the wrong shape for asking "what governs this
part of my book?". A bank looking at its credit-card portfolio has to gather
CRE20 for the risk weight, CRE20 again for the conversion factor, LCR40 for the
drawdown, NSF30 for the funding, LEX for concentration and SRP for provisioning.

This module inverts that. The tree is shaped like a balance sheet — assets,
liabilities and funding, off-balance sheet, capital, and the constraints that cut
across all of them — and every node carries the rules that actually govern it.

The taxonomy is not invented. Its exposure classes are Basel's own, taken from
the heading structure of the framework itself: the branches under Assets are the
section headings of CRE20, the deposit branches are the run-off categories of
LCR40, the capital branches are the components in CAP10. Assignment then works
by matching each rule's source paragraph against those headings, so a rule lands
where the framework itself put it rather than where a keyword happened to hit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Node fields:
#   id, label, desc      what the node is
#   paras                explicit paragraph ranges, e.g. ("CRE20", 63, 68) -- strongest signal
#   headings             substrings matched against the source paragraph's heading path
#   chapters             chapter-level fallback
#   keywords             text fallback, lowest weight
#   note                 an observation worth surfacing on the node itself
#   children             sub-nodes
def N(id, label, desc="", paras=None, headings=None, chapters=None, keywords=None,
      note="", status="", children=None):
    return {"id": id, "label": label, "desc": desc, "paras": paras or [],
            "headings": headings or [], "chapters": chapters or [],
            "keywords": keywords or [], "note": note, "status": status,
            "children": children or []}


TAXONOMY = N("root", "The bank balance sheet under Basel III",
    "Every branch is a part of the book; every leaf carries the rules that govern it.",
    children=[

    # =========================== ASSETS ================================
    N("assets", "Assets and exposures",
      "What the bank owns or is owed. These drive risk-weighted assets, and therefore the capital requirement.",
      children=[

      N("sa", "Credit risk — standardised approach",
        "The default method for measuring credit risk. Exposures are sorted into classes and each class carries a prescribed risk weight.",
        chapters=["CRE20", "CRE21"],
        children=[
          N("sa-sovereign", "Sovereign exposures",
            "Central governments and central banks. Weights follow external ratings, with national discretion for domestic-currency exposures.",
            paras=[("CRE20", 7, 15)], headings=["Exposures to sovereigns"]),
          N("sa-pse", "Public sector entities",
            "Non-central-government PSEs, weighted by reference to their sovereign or as banks.",
            paras=[("CRE20", 16, 19)], headings=["public sector entities"]),
          N("sa-mdb", "Multilateral development banks",
            "MDBs meeting the eligibility criteria attract a 0% weight.",
            paras=[("CRE20", 20, 21)], headings=["multilateral development banks"]),
          N("sa-bank", "Bank exposures",
            "Claims on other banks, graded by the External Credit Risk Assessment Approach or the Standardised Credit Risk Assessment Approach.",
            paras=[("CRE20", 22, 33)], headings=["Exposures to banks"]),
          N("sa-covered", "Covered bonds",
            "Bonds secured on a ring-fenced cover pool, attracting preferential weights.",
            paras=[("CRE20", 34, 39)], headings=["covered bonds"]),
          N("sa-secfirm", "Securities firms and other financial institutions",
            "Treated as banks where subject to equivalent prudential standards, otherwise as corporates.",
            paras=[("CRE20", 40, 40)], headings=["securities firms"]),
          N("sa-corp", "Corporate exposures", "Claims on companies.",
            paras=[("CRE20", 41, 53)], headings=["Exposures to corporates"],
            children=[
              N("sa-corp-general", "General corporate", "Rated and unrated corporates.",
                paras=[("CRE20", 41, 46)], keywords=["corporate exposure", "unrated corporate"]),
              N("sa-corp-sme", "Small and medium enterprises",
                "SMEs below the revenue threshold take a preferential weight; those meeting the retail criteria move to regulatory retail instead.",
                paras=[("CRE20", 47, 47)], keywords=["sme", "small and medium"]),
              N("sa-corp-specialised", "Specialised lending",
                "Project, object and commodities finance, where repayment depends on the asset financed.",
                paras=[("CRE20", 48, 53)], keywords=["specialised lending", "project finance",
                                                     "object finance", "commodities finance"]),
            ]),
          N("sa-subdebt", "Subordinated debt, equity and other capital instruments",
            "Weighted at 150% for subordinated debt and capital instruments other than equities.",
            paras=[("CRE20", 54, 62)], headings=["Subordinated debt, equity"]),

          # ---- the branch this project turns on ----
          N("sa-retail", "Retail exposures",
            "Exposures to individuals and small businesses. Credit cards live here.",
            paras=[("CRE20", 63, 68)], headings=["Retail exposure class"],
            note="Basel's product criterion names credit cards, charge cards and overdrafts explicitly (CRE20.65(1)).",
            children=[
              N("sa-retail-criteria", "Regulatory retail criteria",
                "Three tests: the product criterion, a EUR 1m cap on aggregated exposure to one counterparty, and a 0.2% granularity limit.",
                paras=[("CRE20", 65, 65)], keywords=["regulatory retail", "granularity"]),
              N("sa-retail-transactor", "Regulatory retail — transactors · 45%",
                "Cards repaid in full at every scheduled date for twelve months. The lowest retail weight in the framework.",
                paras=[("CRE20", 66, 66)], keywords=["transactor"],
                note="No US regulatory report discloses the transactor split, so this weight cannot be evidenced from public filings."),
              N("sa-retail-revolver", "Regulatory retail — revolvers · 75%",
                "Regulatory retail that is not transactor business. The default where transactor status cannot be shown.",
                paras=[("CRE20", 68, 68)], keywords=["75%", "not arise from"]),
              N("sa-retail-other", "Other retail · 100%",
                "Retail exposures failing the regulatory retail criteria.",
                paras=[("CRE20", 67, 67)], keywords=["other retail"]),
            ]),

          N("sa-re", "Real estate exposures",
            "Exposures secured by immovable property, split by property type and by whether repayment depends materially on cash flows the property generates.",
            paras=[("CRE20", 69, 91)], headings=["Real estate exposure class"],
            children=[
              N("sa-re-resi", "Regulatory residential real estate",
                "Owner-occupied and buy-to-let housing meeting the regulatory criteria; weight varies by loan-to-value.",
                keywords=["residential real estate"]),
              N("sa-re-comm", "Regulatory commercial real estate",
                "Commercial property meeting the regulatory criteria.",
                keywords=["commercial real estate"]),
              N("sa-re-other", "Other real estate",
                "Exposures secured by property that fail the regulatory criteria.",
                keywords=["other real estate"]),
              N("sa-re-adc", "Land acquisition, development and construction",
                "ADC lending, weighted at 150% unless the residential carve-out applies.",
                keywords=["land acquisition", "adc"]),
            ]),
          N("sa-fx-multiplier", "Currency mismatch multiplier",
            "A 1.5x multiplier on unhedged retail and residential exposures where the borrower's income is in a different currency from the loan.",
            paras=[("CRE20", 92, 93)], headings=["currency mismatch"]),
          N("sa-defaulted", "Defaulted exposures",
            "Exposures past due more than 90 days or otherwise in default, weighted at 100% or 150% depending on provisioning.",
            paras=[("CRE20", 106, 109)], headings=["Defaulted exposures"]),
          N("sa-other-assets", "Other assets",
            "The residual bucket. Note that the US rule places credit-card loans here rather than in a retail class.",
            paras=[("CRE20", 110, 120)], headings=["Other assets"]),
          N("sa-ccr", "Counterparty credit risk and credit derivatives",
            "Exposures whose value depends on a counterparty's performance.",
            headings=["counterparty credit risk", "Credit derivatives"],
            chapters=["CRE50", "CRE51", "CRE52", "CRE53", "CRE54", "CRE55", "CRE56"]),
          N("sa-duediligence", "Due diligence requirements",
            "Banks must perform their own assessment rather than relying mechanically on external ratings.",
            paras=[("CRE20", 4, 6)], headings=["Due diligence"]),
        ]),

      N("irb", "Credit risk — internal ratings-based approach",
        "Banks with supervisory approval estimate their own risk parameters. Requires PD, LGD and EAD estimates that public filings do not contain.",
        chapters=["CRE30", "CRE31", "CRE32", "CRE34", "CRE35", "CRE36"],
        children=[
          N("irb-classes", "Categorisation of exposures",
            "The IRB asset classes: corporate, sovereign, bank, retail, equity and purchased receivables.",
            headings=["Categorisation of exposures", "Definition of"]),
          N("irb-qrre", "Qualifying revolving retail exposures",
            "The IRB home of credit cards, split into transactors and revolvers, with its own asset correlation.",
            paras=[("CRE30", 20, 26)], keywords=["qrre", "qualifying revolving"]),
          N("irb-retail", "Retail risk components and functions",
            "PD, LGD and EAD estimation for retail, including drawdown behaviour on undrawn card lines.",
            headings=["Retail exposures", "Risk components for retail"]),
          N("irb-corp", "Corporate, sovereign and bank exposures",
            "Foundation and advanced approaches for wholesale exposures.",
            headings=["Corporate, sovereign and bank"]),
          N("irb-requirements", "Minimum requirements for IRB use",
            "Rating system design, validation, governance and the data history required for approval.",
            status="not-yet-extracted",
            chapters=["CRE36"]),
        ]),

      N("crm", "Credit risk mitigation",
        "What a bank may recognise to reduce an exposure: collateral, guarantees, credit derivatives and netting. These are the levers that cut RWA without shrinking the book.",
        chapters=["CRE22"],
        children=[
          N("crm-collateral", "Eligible collateral and haircuts",
            "The simple and comprehensive approaches, and the haircuts applied to collateral value.",
            keywords=["collateral", "haircut"]),
          N("crm-guarantee", "Guarantees and credit derivatives",
            "Substitution of the protection provider's risk weight for the obligor's.",
            keywords=["guarantee", "credit derivative", "protection"]),
          N("crm-netting", "On-balance sheet netting",
            "Netting of loans against deposits with the same counterparty.",
            keywords=["netting"]),
          N("crm-maturity", "Maturity mismatch and currency mismatch",
            "Adjustments where protection matures before the exposure or is denominated differently.",
            keywords=["maturity mismatch", "currency mismatch"]),
        ]),

      N("sec", "Securitisation exposures",
        "Positions in securitised pools, whether retained as originator or bought as investor. Credit-card receivables are a common underlying.",
        status="not-yet-extracted",
        chapters=["CRE40", "CRE41", "CRE42", "CRE43", "CRE44", "CRE45"],
        children=[
          N("sec-definitions", "Definitions and scope",
            "Traditional and synthetic securitisation, tranching, and what counts as a securitisation exposure.",
            headings=["Definitions and general terminology"]),
          N("sec-revolving", "Revolving securitisations and early amortisation",
            "Structures backed by revolving credit — credit cards above all — and the provisions that accelerate repayment when performance deteriorates.",
            keywords=["early amortisation", "revolving securitisation", "controlled amortisation"],
            note="The natural route for a card issuer to move receivables off balance sheet."),
          N("sec-srt", "Significant risk transfer and operational requirements",
            "What an originator must demonstrate before it may stop holding capital against the underlying pool.",
            keywords=["significant risk transfer", "operational requirement", "clean break"]),
          N("sec-implicit", "Implicit support",
            "Support beyond contractual obligation, which forces the bank back into holding capital against the whole pool.",
            keywords=["implicit support"]),
          N("sec-stc", "Simple, transparent and comparable criteria",
            "The STC criteria that unlock preferential capital treatment.",
            keywords=["simple, transparent", "stc criteria", "homogeneity"]),
          N("sec-hierarchy", "Capital calculation hierarchy",
            "SEC-IRBA, SEC-ERBA, SEC-SA and the 1250% fallback.",
            keywords=["sec-irba", "sec-erba", "sec-sa", "1250%"]),
        ]),

      N("hqla", "High-quality liquid assets",
        "The unencumbered assets a bank holds to survive a thirty-day stress. The numerator of the Liquidity Coverage Ratio.",
        chapters=["LCR30", "LCR31"],
        children=[
          N("hqla-characteristics", "Characteristics and operational requirements",
            "What makes an asset liquid in stress, and the operational control the bank must demonstrate over it.",
            headings=["Characteristics of HQLA", "Operational requirements", "Fundamental characteristics"]),
          N("hqla-l1", "Level 1 assets",
            "Cash, central bank reserves and qualifying sovereign debt. No haircut, no cap.",
            headings=["Level 1 assets"]),
          N("hqla-l2a", "Level 2A assets",
            "Certain sovereign, corporate and covered bonds. 15% haircut; Level 2 capped at 40% of the stock.",
            headings=["Level 2 assets"]),
          N("hqla-l2b", "Level 2B assets",
            "Lower-rated corporates, some equities and RMBS. Heavier haircuts and a 15% cap.",
            headings=["Level 2B assets"]),
        ]),

      N("mkt", "Trading book and market risk",
        "Positions held with trading intent. Deliberately outside the scope of a credit-card study; the branch is here so the tree is structurally complete.",
        status="out-of-scope",
        chapters=["MAR10", "MAR11", "MAR12", "MAR20", "MAR21", "MAR22", "MAR23",
                  "MAR30", "MAR31", "MAR33", "MAR40", "MAR50"]),

      N("op", "Operational risk",
        "Loss from failed processes, people, systems or external events. Measured from a business indicator plus an internal loss multiplier.",
        status="not-yet-extracted",
        chapters=["OPE10", "OPE25"]),
    ]),

    # ===================== LIABILITIES AND FUNDING ======================
    N("funding", "Liabilities and funding",
      "How the book is paid for. Funding stability determines both the liquidity requirement and how safely the asset side can be grown.",
      children=[
        N("dep", "Deposits", "Retail and wholesale deposit funding, graded by how likely it is to run.",
          chapters=["LCR40"],
          children=[
            N("dep-retail-stable", "Retail deposits — stable · 3–5% run-off",
              "Insured deposits in a transactional relationship. The stickiest funding a bank has.",
              headings=["Retail deposit run-off"], keywords=["stable deposits", "3%", "deposit insurance"]),
            N("dep-retail-less", "Retail deposits — less stable · 10%+",
              "Uninsured, high-value, rate-driven or internet-sourced retail deposits.",
              keywords=["less stable", "high-value"]),
            N("dep-sme", "Small business customer deposits",
              "Treated as retail where aggregate funding from one customer is below EUR 1 million.",
              keywords=["small business customer"]),
            N("dep-wholesale-op", "Wholesale — operational deposits · 25%",
              "Balances held for clearing, custody or cash management.",
              keywords=["operational deposits", "clearing, custody"]),
            N("dep-wholesale-nonop", "Wholesale — non-operational · 40% / 100%",
              "Corporate and sovereign funding without an operational relationship.",
              headings=["unsecured wholesale funding run-off"], keywords=["non-operational"]),
            N("dep-financial", "Funding from financial institutions · 100%",
              "Assumed to run in full within thirty days.",
              keywords=["financial institution", "100%"]),
          ]),
        N("fund-secured", "Secured funding and repo",
          "Repo and other collateralised borrowing, with run-off driven by the collateral's quality.",
          headings=["Secured funding run-off"], keywords=["secured funding", "repurchase"]),
        N("nsfr", "Net stable funding ratio",
          "A one-year constraint requiring stable funding against illiquid assets. Where the LCR governs a thirty-day shock, the NSFR governs the shape of the book.",
          chapters=["NSF10", "NSF20", "NSF30", "NSF99"],
          children=[
            N("nsfr-asf", "Available stable funding",
              "Capital and liabilities weighted by how reliably they stay for a year.",
              headings=["Definition of available stable funding"], keywords=["available stable funding", "asf"]),
            N("nsfr-rsf", "Required stable funding",
              "Assets and off-balance-sheet exposures weighted by how hard they are to monetise. Undrawn commitments carry an RSF charge.",
              keywords=["required stable funding", "rsf"]),
            N("nsfr-interdependent", "Interdependent assets and liabilities",
              "The narrow case where a matched pair may be excluded from both sides.",
              headings=["Interdependent assets"]),
          ]),
      ]),

    # ======================= OFF-BALANCE SHEET ==========================
    N("obs", "Off-balance sheet",
      "Promises to lend that have not been drawn. For a card issuer this is the largest exposure the bank has, and the one most easily overlooked.",
      note="Across the 50 small card banks in this study, undrawn commitments are several times the drawn book.",
      children=[
        N("obs-ccf", "Credit conversion factors",
          "How an undrawn promise becomes a credit-equivalent exposure.",
          paras=[("CRE20", 94, 105)], headings=["Off-balance sheet items"],
          children=[
            N("obs-ucc", "Unconditionally cancellable commitments · 10% CCF",
              "Commitments the bank may cancel at any time without notice. Credit-card lines are the archetype.",
              paras=[("CRE20", 100, 100)], keywords=["unconditionally cancellable"],
              note="Basel applies 10%; the US rule in force applies 0% (12 CFR 217.33(b)(1)). This single divergence is the largest in the study."),
            N("obs-commit", "Other commitments · 40% CCF",
              "Commitments that cannot be cancelled at will, regardless of maturity.",
              paras=[("CRE20", 98, 98)], keywords=["40% ccf"]),
            N("obs-substitutes", "Direct credit substitutes · 100% CCF",
              "Guarantees, standby letters of credit and acceptances that stand in for direct lending.",
              paras=[("CRE20", 95, 95)], keywords=["direct credit substitute"]),
            N("obs-transaction", "Transaction-related contingents · 50% CCF",
              "Performance bonds, bid bonds and warranties.",
              paras=[("CRE20", 96, 97)], keywords=["transaction-related", "note issuance"]),
            N("obs-trade", "Trade-related contingents · 20% CCF",
              "Short-term self-liquidating letters of credit arising from the movement of goods.",
              paras=[("CRE20", 99, 99)], keywords=["trade letters of credit", "self-liquidating"]),
          ]),
        N("obs-lcr", "Undrawn facilities under the liquidity standard",
          "The thirty-day drawdown assumed on committed lines. Unconditionally cancellable facilities are excluded from this section and left to national discretion.",
          headings=["Additional requirements"],
          keywords=["drawdown", "committed credit and liquidity facilities", "contingent funding"],
          note="LCR40.59 excludes unconditionally cancellable facilities, routing them to LCR40.67. The property that earns a card line a low conversion factor also removes it from the 5% drawdown."),
        N("obs-lev", "Off-balance sheet in the leverage exposure measure",
          "The leverage ratio converts the same commitments, but with its own floor, so it can bind where the risk-based ratio does not.",
          # LEV30 and CRE20 share the heading "Off-balance sheet items", so the
          # heading alone ties and the earlier-defined node wins. The paragraph
          # range is what actually separates them.
          paras=[("LEV30", 44, 62)],
          chapters=["LEV30"], headings=["Off-balance sheet items"]),
      ]),

    # ============================ CAPITAL ===============================
    N("capital", "Capital",
      "What absorbs loss. The constraint every asset-side decision ultimately runs into.",
      children=[
        N("cap-cet1", "Common Equity Tier 1",
          "Common shares, retained earnings and disclosed reserves. The highest-quality capital and the binding constraint in practice.",
          chapters=["CAP10"], headings=["Common Equity Tier 1", "Common shares issued by the bank"]),
        N("cap-at1", "Additional Tier 1",
          "Perpetual instruments subordinated to depositors, with fully discretionary coupons.",
          headings=["Additional Tier 1"]),
        N("cap-t2", "Tier 2",
          "Gone-concern capital: subordinated debt with a minimum original maturity of five years.",
          headings=["Tier 2 capital"]),
        N("cap-adjustments", "Regulatory adjustments and deductions",
          "Goodwill, deferred tax assets, holdings in other financial institutions and the threshold deductions.",
          chapters=["CAP30"]),
        N("cap-minimums", "Minimum capital ratios",
          "CET1 at least 4.5% of RWA, Tier 1 at least 6%, total capital at least 8%, at all times.",
          chapters=["RBC20", "RBC25"]),
        N("cap-buffers", "Buffers above the minimum",
          "The capital conservation buffer, the countercyclical buffer and the G-SIB surcharge. Eroding them constrains distributions rather than breaching a minimum.",
          chapters=["RBC30", "RBC40"],
          children=[
            N("cap-buf-conservation", "Capital conservation buffer · 2.5%",
              "CET1 held above the minimum; falling into the range caps dividends, buybacks and bonuses.",
              keywords=["conservation buffer"]),
            N("cap-buf-ccyb", "Countercyclical buffer · 0–2.5%",
              "Raised by national authorities when credit growth runs ahead of the economy.",
              keywords=["countercyclical"]),
            N("cap-buf-gsib", "Systemic surcharges",
              "Additional CET1 for global and domestic systemically important banks.",
              chapters=["SCO40", "SCO50"], keywords=["systemically important"]),
          ]),
        N("cap-transitional", "Transitional arrangements",
          "Phase-in and grandfathering of instruments that no longer qualify.",
          status="not-yet-extracted",
          chapters=["CAP90", "RBC90"]),
      ]),

    # ======================= CROSS-CUTTING ==============================
    N("cross", "Constraints that cut across the book",
      "Requirements that do not attach to one asset class but bind the balance sheet as a whole.",
      children=[
        N("lev", "Leverage ratio",
          "Tier 1 capital over a non-risk-weighted exposure measure, at least 3%. A backstop that bites hardest on banks whose assets carry low risk weights.",
          # LEV40's paragraphs inherit "Off-balance sheet items" from the tail of
          # LEV30 in the source PDF, which outscores a chapter match. Anchor on
          # the paragraph ids, which are validated against the corpus.
          paras=[("LEV10", 1, 20), ("LEV20", 1, 20), ("LEV40", 1, 20), ("LEV90", 1, 20)],
          chapters=["LEV10", "LEV20", "LEV30", "LEV40", "LEV90"]),
        N("lcr", "Liquidity coverage ratio",
          "HQLA over net thirty-day stressed outflows, at least 100%. The requirement itself; its inputs sit under Assets and Liabilities.",
          chapters=["LCR10", "LCR20", "LCR90", "LCR99"]),
        N("lex", "Large exposures and concentration",
          "A cap of 25% of Tier 1 capital on exposure to a single counterparty or group of connected clients.",
          chapters=["LEX10", "LEX20", "LEX30", "LEX40"]),
        N("srp", "Supervisory review — Pillar 2",
          "Where the supervisor judges risks the formulas miss.",
          status="not-yet-extracted",
          chapters=["SRP10", "SRP20", "SRP30", "SRP31", "SRP32", "SRP33", "SRP35",
                    "SRP36", "SRP50", "SRP98", "SRP99"],
          children=[
            N("srp-credit", "Credit risk management and provisioning",
              "Underwriting standards, expected credit loss practice and the adequacy of allowances.",
              chapters=["SRP32"]),
            N("srp-concentration", "Concentration risk",
              "Risk from correlated exposures that individually sit inside every limit.",
              keywords=["concentration"]),
            N("srp-irrbb", "Interest rate risk in the banking book",
              "Economic value and earnings sensitivity to rate moves.",
              chapters=["SRP31", "SRP98"]),
            N("srp-liquidity", "Liquidity monitoring metrics",
              "Contractual maturity mismatch, funding concentration and available unencumbered assets.",
              chapters=["SRP50"]),
            N("srp-stress", "Stress testing and ICAAP",
              "The bank's own assessment of capital adequacy under adverse conditions.",
              keywords=["stress test", "icaap", "internal capital"]),
          ]),
        N("dis", "Disclosure — Pillar 3",
          "What must be published. This determines what an outside analyst can see at all.",
          status="not-yet-extracted",
          chapters=["DIS10", "DIS20", "DIS21", "DIS25", "DIS26", "DIS30", "DIS31",
                    "DIS35", "DIS40", "DIS42", "DIS43", "DIS45", "DIS50", "DIS51",
                    "DIS55", "DIS60", "DIS70", "DIS75", "DIS80", "DIS85", "DIS99"]),
        N("sco", "Scope and proportionality",
          "Which banks the framework binds, how groups are consolidated, and how requirements scale with size and systemic importance.",
          status="not-yet-extracted",
          chapters=["SCO10", "SCO30", "SCO40", "SCO50", "SCO60", "SCO95"]),
      ]),
])


def flatten(node, depth=0, parent=None, out=None):
    out = [] if out is None else out
    node["_depth"], node["_parent"] = depth, parent
    out.append(node)
    for c in node["children"]:
        flatten(c, depth + 1, node["id"], out)
    return out


PARA_RE = re.compile(r"^([A-Z]{3})(\d+)\.(\d+)")


def score(rule, node, headings: dict[str, list[str]]) -> float:
    """How strongly a rule belongs to a node. Higher wins; 0 means no match."""
    src = rule["source"]
    pids = src.get("para_ids") or []
    best = 0

    for pid in pids:
        m = PARA_RE.match(pid)
        if not m:
            continue
        ch, num = m.group(1) + m.group(2), int(m.group(3))
        for (pch, lo, hi) in node["paras"]:
            if pch == ch and lo <= num <= hi:
                best = max(best, 100)

    hp = " > ".join(h for pid in pids for h in headings.get(pid, [])).lower()
    for h in node["headings"]:
        if h.lower() in hp:
            best = max(best, 60)

    # Derive the chapter from the paragraph id rather than the extracted
    # "chapter" field: para_ids are validated against the corpus, that field is
    # free-form model output and is sometimes wrong (LEV40 rules labelled LEV30).
    chapters = {PARA_RE.match(pid).group(1) + PARA_RE.match(pid).group(2)
                for pid in pids if PARA_RE.match(pid)} or {src.get("chapter")}
    if chapters & set(node["chapters"]):
        best = max(best, 30)

    if node["keywords"]:
        blob = (rule["title"] + " " + rule["statement"] + " " + rule["quote"]).lower()
        hit = max((len(k) for k in node["keywords"] if k.lower() in blob), default=0)
        if hit:
            best = max(best, 25 + min(hit, 20) / 100.0)
    return best


def build(rules, paragraphs):
    headings = {p["para_id"]: p["heading_path"] for p in paragraphs}
    index = {r["rule_id"]: r for r in rules}
    nodes = flatten(TAXONOMY)
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        n["rules"] = []

    unplaced = []
    for r in rules:
        scored = [(score(r, n, headings), -n["_depth"], n["id"]) for n in nodes if n["id"] != "root"]
        scored = [s for s in scored if s[0] > 0]
        if not scored:
            unplaced.append(r)
            continue
        # strongest signal wins; deepest node breaks ties, so a rule lands on the
        # most specific branch that claims it
        best = max(scored, key=lambda t: (t[0], -t[1]))
        by_id[best[2]]["rules"].append(r["rule_id"])

    # A parent's paragraph range covers its children's, so a broad range match on
    # the parent outranks a keyword match on the right child. Walk top-down and
    # push each rule to a child that claims it, so rules settle as deep as they
    # legitimately can.
    for n in nodes:
        if not n["children"]:
            continue
        keep = []
        for rid in n["rules"]:
            r = index[rid]
            cand = [(score(r, c, headings), c) for c in n["children"]]
            cand = [(s, c) for s, c in cand if s > 0]
            if cand:
                max(cand, key=lambda t: t[0])[1]["rules"].append(rid)
            else:
                keep.append(rid)
        n["rules"] = keep

    for n in reversed(nodes):
        n["rule_count"] = len(n["rules"])
        n["total_count"] = n["rule_count"] + sum(c["total_count"] for c in n["children"])
    return TAXONOMY, unplaced


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rules", default="outputs/rules/rules.json")
    ap.add_argument("--paras", default="data/basel/paragraphs.jsonl")
    ap.add_argument("--out", default="outputs/rule_tree.json")
    args = ap.parse_args()

    rules = json.loads(Path(args.rules).read_text())["rules"]
    paras = [json.loads(l) for l in Path(args.paras).read_text().splitlines() if l.strip()]
    tree, unplaced = build(rules, paras)

    index = {r["rule_id"]: r for r in rules}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"tree": tree, "rules": index}, indent=1, ensure_ascii=False))

    nodes = flatten(tree)
    leaves = [n for n in nodes if not n["children"]]
    print(f"{len(nodes)} nodes ({len(leaves)} leaves) | {len(rules)} rules | "
          f"{sum(n['rule_count'] for n in nodes)} placed | {len(unplaced)} unplaced")
    empty = [n["id"] for n in leaves if n["total_count"] == 0]
    if empty:
        print(f"empty leaves ({len(empty)}): {', '.join(empty)}")
    if unplaced:
        print("unplaced sample:")
        for r in unplaced[:10]:
            print(f"   {r['rule_id']:44} {r['source']['chapter']}")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
