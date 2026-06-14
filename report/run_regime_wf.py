#!/usr/bin/env python3
"""Regime walk-forward / robustness validation for the publication report.

Addresses the reviewer concern that two of Convex Core's protective mechanisms
(duration-sleeve mix + stress cap) — and its regime-weighted tilt scoring —
condition on a regime classifier whose numeric cutoffs are a-priori (qualitative-
spec-derived) but were not walk-forward re-validated.

Three tests, all at the live 0.95 vintage, metrics on the same DGS3MO/SPY basis
as pub_benchmarks.py:

 1. REGIME LAYER VALUE — regime-on (live) vs regime-off (force every day to
    RISK_NEUTRAL: neutral duration mix, no stress cap, no regime tilt weighting).
    Full sample AND an early (≤2014) / late (≥2015) split. If on≈off, the result
    barely depends on the regime cutoffs and cannot be materially overfit by them;
    if on≫off, tests 2–3 must show it is robust.
 2. HYSTERESIS robustness — confirm_days ∈ {2,3,5}.
 3. THRESHOLD robustness — scale every numeric magnitude cutoff by {0.8,1.0,1.2}
    (percentile cutoffs clamped to [0.01,0.99]); recomputed via the pure
    regime_series() over cached inputs.

Each variant swaps data.regime, recomputes scores for that regime (regime feeds
tilt scoring), and re-runs simulate_convex. No engine code is modified. Read-only
DB. Emits dnsr-agent/workspace/pub_report/regime_wf.json.
"""
from __future__ import annotations
import sys, json, sqlite3, copy
import numpy as np, pandas as pd, yaml

REPO = "${PAPER_ROOT}/engine"
AGENT = "${PAPER_ROOT}"
sys.path.insert(0, REPO)
from tradeclassifier.config import load_config
from tradeclassifier.loaders import Warehouse
from tradeclassifier.portfolio import MODEL_FILE, UNIVERSE_FILE
from tradeclassifier.alpha_backtest import precompute_alpha_data
from tradeclassifier.convex_core import (DEFAULTS, V2_BRAKE, V2_DEDUP_CORR, V2_DEDUP_PREFER_DROP,
                                         V2_N_TILTS, V2_PERSISTENCE, V2_TILT_POOL, V2_VALUE_SLOTS,
                                         precompute_scores, simulate_convex)
from tradeclassifier.regime import (RegimeRules, RegimeInputCache, build_inputs,
                                     regime_series, _parse_clause)

DB = f"{AGENT}/workspace/etf_data.db"
OUT = f"{AGENT}/workspace/pub_report/regime_wf.json"
TRADING = 252
SPLIT = pd.Timestamp("2015-01-01")

# ---- metric basis (identical to pub_benchmarks.py) ------------------------
def _load_rf_spy():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rf = pd.read_sql_query("SELECT date,value FROM macro_series WHERE series_id='DGS3MO' ORDER BY date", c)
    c.close()
    rf["date"] = pd.to_datetime(rf.date)
    rfd = rf.set_index("date")["value"].astype(float) / 100.0 / TRADING
    j = json.load(open(f"{REPO}/out/universe_refresh/model_curves.json"))
    spy = pd.Series({pd.Timestamp(d): v for d, v in j["series"]["spy"]}).sort_index()
    return rfd, spy.pct_change()
RFD, SPY_RET = _load_rf_spy()

def metrics(dates, rets, lo=None, hi=None):
    s = pd.Series(rets, index=pd.to_datetime([str(d) for d in dates]))
    if lo is not None: s = s[s.index >= lo]
    if hi is not None: s = s[s.index < hi]
    if len(s) < 60: return None
    g = (1 + s).cumprod()
    r = g.pct_change().dropna()
    yrs = (g.index[-1] - g.index[0]).days / 365.25
    cagr = g.iloc[-1] ** (1 / yrs) - 1
    dd = (g / g.cummax() - 1)
    ex = (r - RFD.reindex(r.index)).dropna()
    down = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    return dict(cagr=float(cagr), vol=float(r.std() * np.sqrt(TRADING)),
                sortino=float(ex.mean() / down * np.sqrt(TRADING)) if down > 0 else None,
                sharpe=float(ex.mean() / r.std() * np.sqrt(TRADING)) if r.std() > 0 else None,
                maxdd=float(dd.min()),
                calmar=float(cagr / abs(dd.min())) if dd.min() < 0 else None)

# ---- perturbed-rule construction ------------------------------------------
def scale_clause(clause: str, factor: float) -> str:
    name, op, rhs = _parse_clause(clause)
    if isinstance(rhs, bool):
        return clause                       # boolean clauses unchanged
    v = rhs * factor
    if "pctile" in name:                    # bounded [0,1]
        v = min(0.99, max(0.01, v))
    return f"{name} {op} {v:g}"

def perturb_rules(base: RegimeRules, factor: float) -> RegimeRules:
    states = {k: ([] if not v else [scale_clause(c, factor) for c in v])
              for k, v in base.states.items()}
    tags = {k: [scale_clause(c, factor) for c in v] for k, v in base.tags.items()}
    return RegimeRules(precedence=list(base.precedence), min_live_clauses=base.min_live_clauses,
                       states=states, residual=base.residual, tags=tags)

# ---- panel + caches (built once) ------------------------------------------
cfg = load_config(f"{REPO}/config/classifier.yaml")
ucfg = yaml.safe_load(open(UNIVERSE_FILE)); mcfg = yaml.safe_load(open(MODEL_FILE))
wh = Warehouse(cfg["data"]["db_path"])
print("precomputing panel …", flush=True)
data = precompute_alpha_data(wh, ucfg, "2005-01-01", "2026-06-10",
                             confirm_days=int(cfg["regime"]["confirm_days"]))
base_regime = list(data.regime)             # the live (regime-on) series

print("caching regime inputs …", flush=True)
icache = RegimeInputCache(wh, "2026-06-10")
inputs_by_day = {d: build_inputs(wh, d, cache=icache) for d in data.days}
base_rules = RegimeRules.load()

BASE = dict(params={**DEFAULTS, "w_equity": 0.95}, brake_cfg=V2_BRAKE, tilt_pool=V2_TILT_POOL,
            n_tilts=V2_N_TILTS, value_slots=V2_VALUE_SLOTS, persistence_margin=V2_PERSISTENCE,
            dedup_corr=V2_DEDUP_CORR, dedup_prefer_drop=V2_DEDUP_PREFER_DROP, collect_returns=True)

def regime_from(rules, confirm):
    rs = regime_series(rules, inputs_by_day, confirm_days=confirm)
    return [rs[d][0] for d in data.days]

def run_with_regime(label, regime_list):
    data.regime = list(regime_list)                 # swap the per-day regime
    sc = precompute_scores(data, mcfg)              # scores depend on regime — recompute
    cx = simulate_convex(data, mcfg, **{**BASE, "scores_cache": sc})
    full = metrics(cx.dates, cx.daily_returns)
    early = metrics(cx.dates, cx.daily_returns, hi=SPLIT)
    late = metrics(cx.dates, cx.daily_returns, lo=SPLIT)
    nflip = sum(1 for a, b in zip(regime_list[1:], regime_list[:-1]) if a != b)
    dist = {}
    for s in regime_list: dist[s] = dist.get(s, 0) + 1
    print(f"  {label:26} CAGR {full['cagr']*100:5.1f}%  Sortino {full['sortino']:.2f}  "
          f"maxDD {full['maxdd']*100:4.0f}%  | early Sor {early['sortino']:.2f}  late Sor {late['sortino']:.2f}",
          flush=True)
    return dict(label=label, full=full, early=early, late=late,
                regime_flips=nflip, regime_dist=dist)

results = {}
print("test 1: regime layer value …", flush=True)
results["regime_on"]  = run_with_regime("regime-on (live)", base_regime)
results["regime_off"] = run_with_regime("regime-off (all NEUTRAL)", ["RISK_NEUTRAL"] * len(data.days))

print("test 2: hysteresis robustness …", flush=True)
hyst = {}
for cd in (2, 3, 5):
    hyst[str(cd)] = run_with_regime(f"confirm_days={cd}", regime_from(base_rules, cd))

print("test 3: threshold robustness …", flush=True)
thr = {}
for f in (0.8, 1.0, 1.2):
    thr[f"{f:.1f}"] = run_with_regime(f"thresholds x{f:.1f}", regime_from(perturb_rules(base_rules, f), 3))

# ---- summary deltas --------------------------------------------------------
on, off = results["regime_on"], results["regime_off"]
def d(metric, win):
    return round(on[win][metric] - off[win][metric], 3)
layer = dict(
    full=dict(d_sortino=d("sortino", "full"), d_cagr=d("cagr", "full"), d_maxdd=d("maxdd", "full")),
    early=dict(d_sortino=d("sortino", "early"), d_maxdd=d("maxdd", "early")),
    late=dict(d_sortino=d("sortino", "late"), d_maxdd=d("maxdd", "late")))
sor_spread = lambda dd: round(max(v["full"]["sortino"] for v in dd.values())
                              - min(v["full"]["sortino"] for v in dd.values()), 3)

out = dict(
    meta=dict(vintage="w_equity=0.95", split=str(SPLIT.date()), risk_free="DGS3MO",
              note="Regime layer = duration-sleeve mix + stress cap + regime-weighted tilt scoring. "
                   "regime-off forces every day to RISK_NEUTRAL. Perturbations recomputed via the pure "
                   "regime_series() over cached PIT inputs; scores recomputed per variant."),
    regime_on=results["regime_on"], regime_off=results["regime_off"],
    hysteresis=hyst, thresholds=thr,
    layer_contribution=layer,
    sortino_spread_hysteresis=sor_spread(hyst),
    sortino_spread_thresholds=sor_spread(thr))
json.dump(out, open(OUT, "w"), indent=1)
print("\nlayer contribution (on−off):", layer)
print(f"Sortino spread — hysteresis {out['sortino_spread_hysteresis']}, "
      f"thresholds {out['sortino_spread_thresholds']}")
print("wrote", OUT)
