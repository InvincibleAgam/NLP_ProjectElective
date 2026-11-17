"""Basel III-constrained profitability ranking of small-bank credit-card books.

Universe : 50 small banks (<$10bn) in bank_filings_2023_2025/, FY2023-FY2025.
Material : average drawn card balance >= $50m and card income reported (RIADB485 > 0).

Profit   : card risk-adjusted margin (RAM) = card interest & fee income (RIADB485)
           - net charge-offs (RIADB514 - RIADB515) - funding cost (bank cost of funds x avg drawn)
           Pre-opex: the Call Report does not split noninterest expense by product.
Capital  : Basel card RWA = 75% x (drawn + 10% x undrawn)          CRE20.68, CRE20.100
           capital consumed = 7.0% CET1 x card RWA                 RBC20.1 + RBC30.2
RORAC    : RAM / capital consumed   (profit per $ of Basel III capital the card book uses)
Gates    : Basel-restated CET1 >= 7.0%; Basel leverage (UCC at 10% CCF) >= 3%;
           liquid assets >= 5% x undrawn lines (30-day drawdown, LCR40.64).
Optimum  : largest new committed-line volume L (at the bank's own utilisation u)
           before the first gate binds; incremental profit = L x u x RAM rate.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, '/home/claude/NLP_ProjectElective/src/analysis')
from basel_cards import (get, liquid_assets, CARD_DRAWN, CARD_UNDRAWN, CET1, RWA, TOTAL_ASSETS,
    TOTAL_LOANS, ALLOWANCE, CARD_DQ30, CARD_INTEREST, CARD_CHARGEOFFS, CARD_RECOVERIES,
    SEC_AFS, SEC_HTM_NEW, SEC_HTM_OLD, CASH_TOTAL)

CCF, RW, RW_US, CET1_REQ, LEV_REQ, LCR_DD = 0.10, 0.75, 1.00, 0.07, 0.03, 0.05
T1, LEV_EXP = ("RCFA8274", "RCOA8274"), ("RCFAA224", "RCOAA224")
ROOT = Path('/home/claude/NLP_ProjectElective/bank_filings_2023_2025')

rows = []
for p in sorted(ROOT.glob('*/call_report_*.json')):
    j = json.loads(p.read_text()); f = j['fields']
    rows.append(dict(rssd=j['institution']['rssd'], name=j['institution']['name'].title() + ' (' + j['institution']['city'].title() + ', ' + j['institution']['state'] + ')',
        date=j['report_date'], drawn=get(f, CARD_DRAWN) or 0.0, undrawn=get(f, CARD_UNDRAWN) or 0.0,
        assets=get(f, TOTAL_ASSETS), loans=get(f, TOTAL_LOANS) or 0.0, cet1=get(f, CET1),
        t1=get(f, T1), rwa=get(f, RWA), levexp=get(f, LEV_EXP), allow=get(f, ALLOWANCE) or 0.0,
        dq30=get(f, CARD_DQ30), card_inc=get(f, CARD_INTEREST), co=get(f, CARD_CHARGEOFFS),
        rec=get(f, CARD_RECOVERIES), nie=get(f, ("RIAD4093",)), intexp=get(f, ("RIAD4073",)), ni=get(f, ("RIAD4340",)),
        liquid=liquid_assets(f), cash=get(f, CASH_TOTAL) or 0.0,
        secs=(get(f, SEC_AFS) or 0) + (get(f, SEC_HTM_NEW) or get(f, SEC_HTM_OLD) or 0)))
q = pd.DataFrame(rows); q['date'] = pd.to_datetime(q['date'])

def year(y):
    b = q[q.date == f'{y}-12-31'].set_index('rssd')
    w = q[(q.date >= f'{y-1}-12-31') & (q.date <= f'{y}-12-31')]
    b = b.join(w.groupby('rssd')[['drawn', 'assets']].mean().add_prefix('avg_'))
    b['nco'] = b.co.fillna(0) - b.rec.fillna(0)
    b['cof'] = b.intexp / b.avg_assets
    b['yield_'] = b.card_inc / b.avg_drawn
    b['nco_rate'] = b.nco / b.avg_drawn
    b['ram'] = b.card_inc - b.nco - b.cof * b.avg_drawn
    b['ram_rate'] = b.ram / b.avg_drawn
    b['util'] = b.drawn / (b.drawn + b.undrawn)
    b['card_share'] = b.drawn / b.loans.replace(0, np.nan)
    b['ead'] = b.drawn + CCF * b.undrawn
    b['card_rwa'] = RW * b.ead
    b['cblr'] = b.rwa.isna()
    other = (b.assets - b.loans - b.cash - b.secs).clip(lower=0)
    proxy = b.card_rwa + (b.loans - b.drawn) + 0.2 * b.secs + other   # conservative, CBLR filers only
    b['rwa_b'] = np.where(b.cblr, proxy, b.rwa - RW_US * b.drawn + b.card_rwa)
    b['cet1_b'] = b.cet1 / b.rwa_b
    b['lev_b'] = b.t1 / (b.levexp + CCF * b.undrawn)
    b['liq'] = b.liquid / (LCR_DD * b.undrawn).replace(0, np.nan)
    b['rorac'] = b.ram / (CET1_REQ * b.card_rwa)
    b['opex_alloc'] = b.nie * (b.drawn / b.loans.replace(0, np.nan)).clip(upper=1)
    b['rorac_postopex'] = (b.ram - b.opex_alloc) / (CET1_REQ * b.card_rwa)   # sensitivity only
    b['roe_basel'] = b.ni / (CET1_REQ * b.rwa_b)          # bank-level cross-check, after tax & opex
    b['dq30_rate'] = b.dq30 / b.drawn.replace(0, np.nan)
    b['g_cet1'] = b.cet1_b >= CET1_REQ
    b['g_lev'] = b.lev_b >= LEV_REQ
    b['g_liq'] = (b.liq >= 1) | b.liq.isna()
    b['compliant'] = b.g_cet1 & b.g_lev & b.g_liq
    b['material'] = (b.avg_drawn >= 50_000) & (b.card_inc.fillna(0) > 0)
    # ---- optimum issuance: per $1 of new committed line at utilisation u --------------
    u = b.util.clip(lower=0.01)
    ead1 = u + CCF * (1 - u)
    L_cap = (b.cet1 / CET1_REQ - b.rwa_b) / (RW * ead1)
    L_lev = (b.t1 / LEV_REQ - (b.levexp + CCF * b.undrawn)) / ead1
    L_liq = (b.liquid - LCR_DD * b.undrawn) / (u + LCR_DD * (1 - u))   # drawdowns self-funded
    L = pd.concat([L_cap, L_lev, L_liq], axis=1); L.columns = ['capital', 'leverage', 'liquidity']
    b['L_opt'] = L.min(axis=1).clip(lower=0)
    b['binding'] = L.fillna(np.inf).idxmin(axis=1)
    b['binding_ext'] = L[['capital', 'leverage']].fillna(np.inf).idxmin(axis=1)
    b['L_opt_ext'] = L[['capital', 'leverage']].min(axis=1).clip(lower=0)  # new deposits fund draws
    b['dprofit'] = b.L_opt * u * b.ram_rate
    b['dprofit_ext'] = b.L_opt_ext * u * b.ram_rate
    b['year'] = y
    return b.reset_index()

allv = pd.concat([year(y) for y in (2023, 2024, 2025)], ignore_index=True)
allv.to_csv('/home/claude/work/basel_card_profit_all_years.csv', index=False)
m = allv[allv.material].copy()
m['rank'] = m.groupby('year').rorac.rank(ascending=False)
m['rank_compliant'] = m[m.compliant].groupby('year').rorac.rank(ascending=False)
out = m[['year', 'name', 'avg_drawn', 'undrawn', 'util', 'card_share', 'yield_', 'nco_rate', 'cof',
         'ram_rate', 'ram', 'card_rwa', 'rorac', 'rorac_postopex', 'roe_basel', 'dq30_rate', 'cet1_b', 'lev_b', 'liq',
         'cblr', 'g_cet1', 'g_lev', 'g_liq', 'compliant', 'rank_compliant', 'binding', 'L_opt', 'dprofit',
         'binding_ext', 'L_opt_ext', 'dprofit_ext']].sort_values(['year', 'rorac'], ascending=[True, False])
out.to_csv('/home/claude/work/basel_card_profit_ranking.csv', index=False)
pd.set_option('display.width', 260); pd.set_option('display.max_columns', 40)
for y in (2023, 2024, 2025):
    print(f'\n==== FY{y}')
    print(out[out.year == y].drop(columns='year').round(3).to_string(index=False))
