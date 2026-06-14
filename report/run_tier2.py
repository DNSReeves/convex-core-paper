#!/usr/bin/env python3
"""Tier-2 pass for the publication report: the Convex ablation/sensitivity grid
and per-sleeve crisis attribution, all at the live 0.95 vintage.

Reproduces the exact 0.95 baseline from export_model_curves.py, then varies one
axis at a time (no-brake / no-convexity / no-satellites, vol-target sweep,
slippage sweep, start-date sweep), and runs one collect_attribution pass to
decompose each crisis window into equity / convexity / duration / cost.

Metrics use the SAME DGS3MO risk-free and SPY series as scripts/pub_benchmarks.py
in dnsr-agent, so the grid reconciles with the rest of the paper. Emits
dnsr-agent/workspace/pub_report/tier2.json. Read-only DB; no live config touched.

Run from the dnsr-agent venv:
  python etf-trade-classifier/scripts/research/pub_tier2/run_tier2.py
"""
from __future__ import annotations
import sys, json, sqlite3
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

DB = f"{AGENT}/workspace/etf_data.db"
OUT = f"{AGENT}/workspace/pub_report/tier2.json"
TRADING = 252

CRISES = [
    ("Global Financial Crisis",       "2007-10-09", "2009-03-09"),
    ("EU / US-downgrade stress 2011", "2011-04-29", "2011-10-03"),
    ("2015-16 growth scare",          "2015-08-01", "2016-02-11"),
    ("Q4-2018 selloff",               "2018-09-20", "2018-12-24"),
    ("COVID crash",                   "2020-02-19", "2020-03-23"),
    ("2022 inflation / rate shock",   "2022-01-03", "2022-10-12"),
]

# ---- shared metric basis (identical to dnsr-agent/scripts/pub_benchmarks.py) ----
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

def metrics(dates, rets):
    g = pd.Series((1 + pd.Series(rets, index=pd.to_datetime([str(d) for d in dates]))).cumprod())
    r = g.pct_change().dropna()
    yrs = (g.index[-1] - g.index[0]).days / 365.25
    cagr = g.iloc[-1] ** (1 / yrs) - 1
    dd = (g / g.cummax() - 1)
    ex = (r - RFD.reindex(r.index)).dropna()
    down = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    jj = pd.concat({"a": r, "b": SPY_RET}, axis=1, sort=False).dropna()
    beta = float(np.cov(jj.a, jj.b)[0, 1] / np.var(jj.b)) if len(jj) > 2 else float("nan")
    # longest underwater (days)
    uw = dd < -1e-9; longest = 0; start = None
    for d, u in uw.items():
        if u and start is None: start = d
        elif not u and start is not None: longest = max(longest, (d - start).days); start = None
    if start is not None: longest = max(longest, (uw.index[-1] - start).days)
    return dict(cagr=float(cagr), vol=float(r.std() * np.sqrt(TRADING)),
                sharpe=float(ex.mean() / r.std() * np.sqrt(TRADING)),
                sortino=float(ex.mean() / down * np.sqrt(TRADING)) if down > 0 else None,
                maxdd=float(dd.min()), calmar=float(cagr / abs(dd.min())) if dd.min() < 0 else None,
                beta=beta, recovery_days=int(longest))

# ----------------------------------------------------------------- panel + cache
cfg = load_config(f"{REPO}/config/classifier.yaml")
ucfg = yaml.safe_load(open(UNIVERSE_FILE)); mcfg = yaml.safe_load(open(MODEL_FILE))
wh = Warehouse(cfg["data"]["db_path"])
print("precomputing panel …", flush=True)
data = precompute_alpha_data(wh, ucfg, "2005-01-01", "2026-06-10",
                             confirm_days=int(cfg["regime"]["confirm_days"]))
print("precomputing scores …", flush=True)
scores = precompute_scores(data, mcfg)

BASE = dict(params={**DEFAULTS, "w_equity": 0.95}, brake_cfg=V2_BRAKE, tilt_pool=V2_TILT_POOL,
            n_tilts=V2_N_TILTS, value_slots=V2_VALUE_SLOTS, persistence_margin=V2_PERSISTENCE,
            dedup_corr=V2_DEDUP_CORR, dedup_prefer_drop=V2_DEDUP_PREFER_DROP,
            scores_cache=scores, collect_returns=True)

def run(label, **over):
    kw = dict(BASE)
    if "params" in over:
        kw["params"] = {**BASE["params"], **over.pop("params")}
    kw.update(over)
    cx = simulate_convex(data, mcfg, **kw)
    m = metrics(cx.dates, cx.daily_returns)
    m["turnover"] = cx.annual_turnover
    print(f"  {label:22} CAGR {m['cagr']*100:5.1f}%  Sortino {m['sortino']:.2f}  "
          f"maxDD {m['maxdd']*100:4.0f}%  turn {m['turnover']:.1f}", flush=True)
    return m, cx

def start_idx_for(year):
    tgt = pd.Timestamp(f"{year}-01-01").date()
    for i, d in enumerate(data.days):
        if d >= tgt:
            return i
    return None

print("baseline + ablations …", flush=True)
base_m, base_cx = run("baseline (0.95)")
grid = {"baseline": base_m}
grid["no_brake"]      = run("no vol-brake", brake=False)[0]
grid["no_convexity"]  = run("no convexity sleeve", params={"w_convexity": 0.0})[0]
grid["no_satellites"] = run("no satellites (tilt=0)", params={"tilt_frac": 0.0})[0]

voltgt = {}
for vt in (0.10, 0.12, 0.14, 0.16):
    voltgt[f"{vt:.2f}"] = run(f"vol_target {vt:.2f}", params={"vol_target": vt})[0]

slip = {}
for bps in (0.0, 5.0, 10.0, 25.0):
    slip[f"{bps:.0f}"] = run(f"slippage {bps:.0f}bps", slippage_bps=bps)[0]

startd = {}
for yr in (2006, 2008, 2010, 2013):
    si = start_idx_for(yr)
    startd[str(yr)] = run(f"start {yr}", start_idx=si)[0] if si is not None else None

# --------------------------------------------------------------- attribution
print("attribution pass …", flush=True)
attr_cx = simulate_convex(data, mcfg, **{**BASE, "collect_attribution": True})
# sanity: attribution run reproduces the baseline returns exactly
assert len(attr_cx.daily_returns) == len(base_cx.daily_returns), "length mismatch"
maxdiff = max(abs(a - b) for a, b in zip(attr_cx.daily_returns, base_cx.daily_returns))
print(f"  attribution vs baseline max daily-return diff = {maxdiff:.2e} (must be ~0)")
assert maxdiff < 1e-12, "collect_attribution changed the returns!"

dts = pd.to_datetime([str(d) for d in attr_cx.dates])
sd = {k: pd.Series(v, index=dts) for k, v in attr_cx.sleeve_daily.items()}
tot = pd.Series(attr_cx.daily_returns, index=dts)
attribution = []
for label, a, b in CRISES:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    mask = (dts >= a) & (dts <= b)
    if mask.sum() < 5:
        attribution.append(dict(window=label, total=None)); continue
    row = dict(window=label, start=str(a.date()), end=str(b.date()),
               total=float(tot[mask].sum()))
    for k in ("equity", "convexity", "duration", "cost"):
        row[k] = float(sd[k][mask].sum())
    row["residual"] = row["total"] - (row["equity"] + row["convexity"] + row["duration"] + row["cost"])
    attribution.append(row)
    print(f"  {label:30} total {row['total']*100:+5.1f}%  eq {row['equity']*100:+5.1f}  "
          f"cx {row['convexity']*100:+5.1f}  dur {row['duration']*100:+5.1f}", flush=True)

out = dict(
    meta=dict(vintage="w_equity=0.95", baseline_source="export_model_curves.py config",
              risk_free="DGS3MO", note="Ablations vary one axis at a time off the live 0.95 config; "
              "metrics use the same DGS3MO/SPY basis as pub_benchmarks.py."),
    baseline=base_m, ablations={"no_brake": grid["no_brake"], "no_convexity": grid["no_convexity"],
                                "no_satellites": grid["no_satellites"]},
    vol_target=voltgt, slippage=slip, start_date=startd,
    attribution=attribution,
    attribution_note="Per-sleeve contribution = sum of daily sleeve returns over the window "
                     "(arithmetic; 'residual' is the compounding cross-term). Cost = slippage drag.")
json.dump(out, open(OUT, "w"), indent=1)
print("wrote", OUT)
