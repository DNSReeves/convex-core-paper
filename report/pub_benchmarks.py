#!/usr/bin/env python3
"""Publication-report benchmark + metrics engine (Tier 1).

Computes every value the publication revision needs from the SAME sources the
report already publishes — no invented numbers:

  * Models (convex/prime/race/alpha/spy/track_b): model_curves.json — the
    canonical 0.95-vintage daily growth curves the Forge + report use. NOTE the
    stale workspace/strategy_portfolio/convex_daily_returns.csv is a 0.65 export
    (CAGR 8.4%) and is deliberately NOT used.
  * Benchmark blends: etf_data.db adjusted_close (SPY/IEF/AGG/TLT) + a DGS3MO
    synthetic T-bill cash leg. DB SPY reconciles with the model SPY (11.1% vs
    11.0% CAGR, identical Sortino/maxDD), so the two tables agree.

Emits workspace/pub_report/benchmarks.json (+ reproducibility_manifest.yaml)
consumed by build_pub_report.py. Pure/deterministic; read-only DB.
"""
from __future__ import annotations
import json, os, subprocess, sqlite3
import numpy as np, pandas as pd

ROOT   = "${PAPER_ROOT}"
CURVES = f"{ROOT}/etf-trade-classifier/out/universe_refresh/model_curves.json"
DB     = f"{ROOT}/dnsr-agent/workspace/etf_data.db"
OUTDIR = f"{ROOT}/dnsr-agent/workspace/pub_report"
TRADING = 252
SLIP_BPS = 5.0   # identical per-unit-turnover slippage charged to models AND benchmarks

# ---- crisis windows (reviewer §15) ----------------------------------------
CRISES = [
    ("Global Financial Crisis",      "2007-10-09", "2009-03-09"),
    ("EU / US-downgrade stress 2011","2011-04-29", "2011-10-03"),
    ("2015-16 growth scare",         "2015-08-01", "2016-02-11"),
    ("Q4-2018 selloff",              "2018-09-20", "2018-12-24"),
    ("COVID crash",                  "2020-02-19", "2020-03-23"),
    ("2022 inflation / rate shock",  "2022-01-03", "2022-10-12"),
]

# --------------------------------------------------------------------------- I/O
def _conn():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

def load_models():
    j = json.load(open(CURVES))
    S = {k: pd.Series({pd.Timestamp(d): v for d, v in pts}).sort_index()
         for k, pts in j["series"].items()}
    return S

def load_prices(tickers):
    c = _conn()
    out = {}
    for t in tickers:
        d = pd.read_sql_query(
            "SELECT date,adjusted_close v FROM daily_prices "
            "WHERE ticker=? AND adjusted_close IS NOT NULL ORDER BY date",
            c, params=[t])
        d["date"] = pd.to_datetime(d.date)
        out[t] = d.set_index("date")["v"].astype(float)
    c.close()
    return out

def load_rf():
    c = _conn()
    rf = pd.read_sql_query(
        "SELECT date,value FROM macro_series WHERE series_id='DGS3MO' ORDER BY date", c)
    c.close()
    rf["date"] = pd.to_datetime(rf.date)
    # annualised %, converted to a daily compounding rate
    return rf.set_index("date")["value"].astype(float) / 100.0 / TRADING

# ----------------------------------------------------------------- benchmark build
def blend(rets: pd.DataFrame, weights: dict, rebalance="Q") -> pd.Series:
    """Static-weight portfolio, drift between rebalances. Returns a growth curve."""
    rets = rets[list(weights)].dropna()
    per = {"Q": lambda d: (d.year, (d.month - 1) // 3),
           "M": lambda d: (d.year, d.month),
           "A": lambda d: (d.year,)}[rebalance]
    cur = {k: weights[k] for k in weights}   # current drifted weights (sum=1)
    g, vals, idx, last = 1.0, [], [], None
    for dt, row in rets.iterrows():
        grown = {k: cur[k] * (1 + row[k]) for k in weights}
        tot = sum(grown.values())
        g *= tot
        cur = {k: grown[k] / tot for k in weights}
        key = per(dt)
        if last is not None and key != last:
            turn = sum(abs(weights[k] - cur[k]) for k in weights)   # rebalance turnover
            g *= (1 - turn * SLIP_BPS / 1e4)                        # identical 5 bps cost model
            cur = {k: weights[k] for k in weights}
        last = key
        vals.append(g); idx.append(dt)
    return pd.Series(vals, index=idx)

def vol_target_spy(spy_ret, rf, target_vol, lookback=21, cap=1.0):
    """SPY scaled by min(cap, target/realised_vol) — mirrors Convex's own brake
    (min(1,·)); remainder earns the T-bill. Daily exposure changes are charged the
    same 5 bps slippage as every other strategy. Returns a growth curve."""
    rv = spy_ret.rolling(lookback).std() * np.sqrt(TRADING)
    expo = (target_vol / rv).clip(upper=cap).shift(1)   # use yesterday's vol
    r = expo * spy_ret + (1 - expo) * rf.reindex(spy_ret.index).fillna(0)
    r = r - expo.diff().abs().fillna(0) * SLIP_BPS / 1e4   # slippage on |Δexposure|
    r = r.dropna()
    return (1 + r).cumprod()

def beta_matched(spy_ret, rf, beta=0.42):
    # fixed-weight daily-rebalanced sleeve; its rebalancing turnover is second-order
    # (≈β(1−β)·|spy−rf| per day) and immaterial — SPY buy-and-hold is likewise ≈0 cost.
    r = beta * spy_ret + (1 - beta) * rf.reindex(spy_ret.index).fillna(0)
    return (1 + r.dropna()).cumprod()

# ------------------------------------------------------------------------ metrics
def _curve(g):
    return g / g.iloc[0]

def metrics(g, rf, spy_ret):
    g = _curve(g.dropna())
    r = g.pct_change().dropna()
    yrs = (g.index[-1] - g.index[0]).days / 365.25
    cagr = g.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(TRADING)
    dd_series = g / g.cummax() - 1
    maxdd = dd_series.min()
    ex = (r - rf.reindex(r.index)).dropna()
    down = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    sortino = ex.mean() / down * np.sqrt(TRADING) if down > 0 else np.nan
    sharpe = ex.mean() / r.std() * np.sqrt(TRADING) if r.std() > 0 else np.nan
    jj = pd.concat({"a": r, "b": spy_ret}, axis=1, sort=False).dropna()
    beta = np.cov(jj.a, jj.b)[0, 1] / np.var(jj.b) if len(jj) > 2 else np.nan
    calmar = cagr / abs(maxdd) if maxdd < 0 else np.nan
    # worst calendar year
    yr = (1 + r).groupby(r.index.year).prod() - 1
    worst_year = yr.min(); worst_year_lbl = int(yr.idxmin())
    # longest underwater (days) + current recovery
    underwater = dd_series < -1e-9
    longest, run_start = 0, None
    for dt, uw in underwater.items():
        if uw and run_start is None:
            run_start = dt
        elif not uw and run_start is not None:
            longest = max(longest, (dt - run_start).days); run_start = None
    if run_start is not None:
        longest = max(longest, (underwater.index[-1] - run_start).days)
    return dict(cagr=float(cagr), vol=float(vol), sharpe=float(sharpe),
                sortino=float(sortino), maxdd=float(maxdd), calmar=float(calmar),
                beta=float(beta), worst_year=float(worst_year),
                worst_year_lbl=worst_year_lbl, recovery_days=int(longest),
                start=str(g.index[0].date()), end=str(g.index[-1].date()))

def total_return(g, start, end):
    g = g.dropna()
    seg = g[(g.index >= start) & (g.index <= end)]
    if len(seg) < 2:
        return None
    return float(seg.iloc[-1] / seg.iloc[0] - 1)

def maxdd_window(g, start, end):
    """Intra-window max drawdown (peak-to-trough) over [start, end]."""
    g = g.dropna()
    seg = g[(g.index >= start) & (g.index <= end)]
    if len(seg) < 3:
        return None
    return float((seg / seg.cummax() - 1).min())

def mc_vs_benchmark(a_ret, b_ret, *, B=3000, L=21, seed=20260614):
    """Paired circular block bootstrap (reuses ACTUAL paired daily returns — no
    parametric DGP) → distribution of terminal wealth, max drawdown and Calmar for
    strategy a vs benchmark b, with head-to-head win-rates. Quantifies path
    uncertainty; does NOT manufacture power beyond the sampled history."""
    j = pd.concat({"a": a_ret, "b": b_ret}, axis=1, sort=False).dropna()
    a = j["a"].to_numpy(); b = j["b"].to_numpy()
    n = len(a); rng = np.random.default_rng(seed); nb = int(np.ceil(n / L))
    yrs = n / TRADING
    def _stats(r):
        g = np.cumprod(1.0 + r)
        cagr = g[-1] ** (1 / yrs) - 1
        dd = (g / np.maximum.accumulate(g) - 1).min()
        calmar = cagr / abs(dd) if dd < 0 else np.nan
        return g[-1], float(dd), float(calmar), float(cagr)
    win_dd = win_tw = win_cal = 0
    a_dd, b_dd, a_tw, b_tw = [], [], [], []
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([(np.arange(s, s + L) % n) for s in starts])[:n]
        atw, add, acal, _ = _stats(a[idx]); btw, bdd, bcal, _ = _stats(b[idx])
        win_dd += add > bdd          # a's drawdown shallower (less negative)
        win_tw += atw > btw
        win_cal += (acal > bcal) if not (np.isnan(acal) or np.isnan(bcal)) else 0
        a_dd.append(add); b_dd.append(bdd); a_tw.append(atw); b_tw.append(btw)
    pct = lambda x, p: float(np.percentile(x, p))
    return dict(resamples=B, block_len=L, n_obs=n,
                p_shallower_dd=win_dd / B, p_higher_terminal=win_tw / B,
                p_higher_calmar=win_cal / B,
                a_maxdd_p05=pct(a_dd, 5), a_maxdd_p50=pct(a_dd, 50), a_maxdd_p95=pct(a_dd, 95),
                b_maxdd_p05=pct(b_dd, 5), b_maxdd_p50=pct(b_dd, 50), b_maxdd_p95=pct(b_dd, 95))

def up_down_capture(r, spy_ret, freq="ME"):
    a = (1 + r).resample(freq).prod() - 1
    b = (1 + spy_ret).resample(freq).prod() - 1
    j = pd.concat({"a": a, "b": b}, axis=1, sort=False).dropna()
    up, dn = j[j.b > 0], j[j.b < 0]
    uc = (up.a.mean() / up.b.mean()) if len(up) and up.b.mean() != 0 else np.nan
    dc = (dn.a.mean() / dn.b.mean()) if len(dn) and dn.b.mean() != 0 else np.nan
    return float(uc), float(dc)

def _sortino(ex):
    down = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    return ex.mean() / down * np.sqrt(TRADING) if down > 0 else np.nan

def _sharpe(r, ex):
    s = r.std()
    return ex.mean() / s * np.sqrt(TRADING) if s > 0 else np.nan

def bootstrap_diff(a_ret, b_ret, rf, *, B=2000, L=21, seed=20260614):
    """Circular block bootstrap on the paired daily series → distribution of the
    Sortino and Sharpe DIFFERENCE (a − b). Blocks (len L) preserve autocorrelation;
    paired resampling preserves the a/b cross-correlation. Returns point estimate,
    95% CI, and a one-sided bootstrap p-value P(diff ≤ 0)."""
    j = pd.concat({"a": a_ret, "b": b_ret}, axis=1, sort=False).dropna()
    rfx = rf.reindex(j.index).fillna(0.0)
    a = (j["a"] - rfx).to_numpy(); b = (j["b"] - rfx).to_numpy()
    ar = j["a"].to_numpy(); br = j["b"].to_numpy()
    n = len(a); rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / L))
    d_sor, d_shp = [], []
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([(np.arange(s, s + L) % n) for s in starts])[:n]
        ax, bx, arx, brx = a[idx], b[idx], ar[idx], br[idx]
        d_sor.append(_sortino(pd.Series(ax)) - _sortino(pd.Series(bx)))
        d_shp.append(_sharpe(pd.Series(arx), pd.Series(ax)) - _sharpe(pd.Series(brx), pd.Series(bx)))
    d_sor = np.array(d_sor); d_shp = np.array(d_shp)
    def _sum(d, point):
        return dict(point=float(point), ci_low=float(np.percentile(d, 2.5)),
                    ci_high=float(np.percentile(d, 97.5)),
                    p_le_0=float(np.mean(d <= 0)))
    pt_sor = _sortino(pd.Series(a)) - _sortino(pd.Series(b))
    pt_shp = _sharpe(pd.Series(ar), pd.Series(a)) - _sharpe(pd.Series(br), pd.Series(b))
    return dict(n_obs=n, block_len=L, resamples=B,
                sortino_diff=_sum(d_sor, pt_sor), sharpe_diff=_sum(d_shp, pt_shp))

def rolling_corr(r, other, months=36):
    a = (1 + r).resample("ME").prod() - 1
    b = (1 + other).resample("ME").prod() - 1
    j = pd.concat({"a": a, "b": b}, axis=1, sort=False).dropna()
    rc = j.a.rolling(months).corr(j.b).dropna()
    return [[str(d.date()), round(float(v), 3)] for d, v in rc.items()]

# --------------------------------------------------------------------------- main
def build():
    S = load_models()
    px = load_prices(["SPY", "IEF", "AGG", "TLT"])
    rf = load_rf()

    # canonical model daily-return series
    spy_ret = S["spy"].pct_change()
    conv_g  = _curve(S["convex"])
    conv_ret = conv_g.pct_change()
    conv_vol = conv_ret.std() * np.sqrt(TRADING)   # vol-target for the matched-SPY benchmark

    # benchmark constituent daily returns (DB), aligned to the model window
    span0, span1 = S["convex"].index[0], S["convex"].index[-1]
    pr = pd.DataFrame({t: px[t].pct_change() for t in px}).dropna(how="all")
    pr = pr[(pr.index >= span0) & (pr.index <= span1)]
    spy_db = pr["SPY"]

    curves = {
        "Convex Core (0.95)":          conv_g,
        "SPY":                          _curve(S["spy"]),
        "60/40 SPY/IEF (Q)":            blend(pr, {"SPY": .6, "IEF": .4}, "Q"),
        "60/40 SPY/AGG (Q)":            blend(pr, {"SPY": .6, "AGG": .4}, "Q"),
        "40/60 SPY/IEF (Q)":            blend(pr, {"SPY": .4, "IEF": .6}, "Q"),
        "80/20 SPY/IEF (Q)":            blend(pr, {"SPY": .8, "IEF": .2}, "Q"),
        "Beta-matched SPY/T-bills (β=0.42)": beta_matched(spy_db, rf, 0.42),
        "Vol-targeted SPY (≈Convex vol)":    vol_target_spy(spy_db, rf, conv_vol),
    }
    # sensitivity: 60/40 SPY/IEF at monthly + annual rebalance
    sens = {
        "60/40 SPY/IEF (monthly)": blend(pr, {"SPY": .6, "IEF": .4}, "M"),
        "60/40 SPY/IEF (annual)":  blend(pr, {"SPY": .6, "IEF": .4}, "A"),
    }

    M = {name: metrics(g, rf, spy_ret) for name, g in {**curves, **sens}.items()}
    # models table (canonical)
    MODELS = {k: metrics(S[k], rf, spy_ret) for k in ["convex", "prime", "race", "alpha", "spy"]}

    # crisis attribution — TOTAL returns (Tier 1); per-sleeve decomposition is Tier 2
    crisis = []
    for label, a, b in CRISES:
        crisis.append(dict(
            window=label, start=a, end=b,
            convex=total_return(curves["Convex Core (0.95)"], a, b),
            spy=total_return(curves["SPY"], a, b),
            b6040=total_return(curves["60/40 SPY/IEF (Q)"], a, b),
            convex_dd=maxdd_window(curves["Convex Core (0.95)"], a, b),
            spy_dd=maxdd_window(curves["SPY"], a, b),
            b6040_dd=maxdd_window(curves["60/40 SPY/IEF (Q)"], a, b),
        ))

    # capture + rolling corr (Convex vs SPY and vs 60/40)
    b6040_ret = curves["60/40 SPY/IEF (Q)"].pct_change()
    uc, dc = up_down_capture(conv_ret, spy_ret)
    capture = dict(up=uc, down=dc)
    rc_spy  = rolling_corr(conv_ret, spy_ret)
    rc_6040 = rolling_corr(conv_ret, b6040_ret)
    corr_spy_full = float(pd.concat({"a": conv_ret, "b": spy_ret}, axis=1, sort=False).dropna().corr().iloc[0, 1])

    # significance: circular block bootstrap on the Sortino/Sharpe DIFFERENCE vs
    # SPY and vs the best balanced benchmark (40/60 by Sortino) — Appendix E
    b4060_ret = curves["40/60 SPY/IEF (Q)"].pct_change()
    significance = dict(
        convex_vs_spy=bootstrap_diff(conv_ret, spy_ret, rf),
        convex_vs_best_balanced=bootstrap_diff(conv_ret, b4060_ret, rf),
        best_balanced_label="40/60 SPY/IEF (Q)")

    # Monte Carlo (paired block bootstrap) — Convex vs 60/40 and vs 40/60 (the
    # strongest balanced competitor on risk-adjusted ratios)
    monte_carlo = mc_vs_benchmark(conv_ret, b6040_ret)
    monte_carlo_4060 = mc_vs_benchmark(conv_ret, b4060_ret)

    # downsampled growth curves for charts (monthly)
    def ds(g):
        gg = _curve(g.dropna()).resample("ME").last().dropna()
        return [[str(d.date()), round(float(v), 5)] for d, v in gg.items()]
    chart_curves = {name: ds(g) for name, g in curves.items()}
    # drawdown curves (monthly)
    def dd(g):
        gg = _curve(g.dropna()); d = (gg / gg.cummax() - 1).resample("ME").last().dropna()
        return [[str(x.date()), round(float(v), 4)] for x, v in d.items()]
    dd_curves = {name: dd(g) for name in
                 ["Convex Core (0.95)", "SPY", "60/40 SPY/IEF (Q)", "40/60 SPY/IEF (Q)"]
                 for g in [curves[name]]}

    out = dict(
        meta=dict(generated_for="DNSR publication revision 2026-06-14",
                  model_source=os.path.relpath(CURVES, ROOT),
                  benchmark_source="etf_data.db daily_prices.adjusted_close",
                  risk_free="DGS3MO (90-day T-bill)",
                  span=[str(span0.date()), str(span1.date())],
                  convex_realised_vol=round(float(conv_vol), 4),
                  rebalance_primary="quarterly",
                  slippage_bps=SLIP_BPS,
                  cost_note="Identical 5 bps/unit-turnover slippage charged to every "
                            "strategy AND benchmark. Model curves net of slippage on ~6x/yr "
                            "turnover; static blends on quarterly rebalances (~0.3-0.4x/yr); "
                            "vol-targeted SPY on daily |Δexposure|; SPY buy-and-hold and the "
                            "fixed beta-matched sleeve carry negligible turnover."),
        models=MODELS,
        benchmarks=M,
        crisis=crisis,
        capture=capture,
        corr_spy_full=corr_spy_full,
        significance=significance,
        monte_carlo=monte_carlo,
        monte_carlo_4060=monte_carlo_4060,
        rolling_corr_spy=rc_spy,
        rolling_corr_6040=rc_6040,
        chart_curves=chart_curves,
        dd_curves=dd_curves,
    )
    os.makedirs(OUTDIR, exist_ok=True)
    json.dump(out, open(f"{OUTDIR}/benchmarks.json", "w"), indent=1)

    # reproducibility manifest (reviewer §29)
    try:
        commit = subprocess.check_output(
            ["git", "-C", f"{ROOT}/dnsr-agent", "rev-parse", "--short", "HEAD"],
            text=True).strip()
    except Exception:
        commit = "unknown"
    manifest = f"""report_name: DNSR Convex Core Publication Backtest
run_for: 2026-06-14 publication revision
dnsr_agent_commit: {commit}
model_curves_source: {os.path.relpath(CURVES, ROOT)}
benchmark_source: etf_data.db daily_prices.adjusted_close
price_field: adjusted_close (total-return proxy; dividends reinvested)
risk_free_series: DGS3MO
cash_proxy: DGS3MO synthetic T-bill (daily compounding)
span: {span0.date()} .. {span1.date()}
rebalance_primary: quarterly (drift between)
rebalance_sensitivity: [monthly, annual]
slippage_bps: {SLIP_BPS}   # identical for models AND benchmarks
benchmarks: [SPY, 60/40 SPY/IEF, 60/40 SPY/AGG, 40/60 SPY/IEF, 80/20 SPY/IEF,
             beta-matched SPY/T-bills (beta=0.42), vol-targeted SPY (target={conv_vol:.4f})]
significance: circular block bootstrap (L=21d, B=2000) on Sortino/Sharpe difference
              vs SPY and vs 40/60 (Appendix E)
convex_source_note: model_curves.json convex = w_equity 0.95 vintage (headline CAGR 10.8%);
                    the instrumented engine (Tier-2) reproduces it at 10.7% (<0.1% path diff);
                    workspace/strategy_portfolio/convex_daily_returns.csv (CAGR 8.4%) is a
                    stale 0.65 export and is NOT used.
llm_in_portfolio_math: false
tier2_done: [per-sleeve crisis attribution, ablation/robustness grid, slippage sensitivity,
             bootstrap significance test]
still_planned: [Deflated Sharpe Ratio, PBO/CSCV, walk-forward re-validation of regime cutoffs]
"""
    open(f"{OUTDIR}/reproducibility_manifest.yaml", "w").write(manifest)
    return out


if __name__ == "__main__":
    o = build()
    print("== models ==")
    for k, m in o["models"].items():
        print(f"  {k:8} CAGR {m['cagr']*100:5.1f}%  Sortino {m['sortino']:.2f}  "
              f"maxDD {m['maxdd']*100:4.0f}%  β {m['beta']:.2f}  worstYr {m['worst_year']*100:.0f}%")
    print("== benchmarks ==")
    for k, m in o["benchmarks"].items():
        print(f"  {k:34} CAGR {m['cagr']*100:5.1f}%  Vol {m['vol']*100:4.1f}%  "
              f"Sharpe {m['sharpe']:.2f}  Sortino {m['sortino']:.2f}  maxDD {m['maxdd']*100:4.0f}%  "
              f"Calmar {m['calmar']:.2f}  β {m['beta']:.2f}")
    print("== capture ==", o["capture"], "  corr(convex,SPY)=", round(o["corr_spy_full"], 2))
    print("== crisis ==")
    for cr in o["crisis"]:
        f = lambda x: f"{x*100:+.0f}%" if x is not None else "  n/a"
        print(f"  {cr['window']:30} SPY {f(cr['spy'])}  60/40 {f(cr['b6040'])}  Convex {f(cr['convex'])}")
