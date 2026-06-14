"""Convex Core engine pins (companion repo). Auxiliary tests from the private
suite (search-sampling, factor-report, bootstrap, live-DB smoke) were trimmed —
they exercise tooling outside the published engine. These 16 are self-contained
(synthetic data, no warehouse needed)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from tradeclassifier.alpha_backtest import AlphaData
from tradeclassifier.convex_core import (DEFAULTS, _max_recovery_days,
                                         simulate_benchmark, simulate_convex)
from .conftest import requires_db
from ._mcfg import MCFG


def _panel(n: int = 700, vol_regime: str = "calm", seed: int = 13) -> AlphaData:
    rng = np.random.default_rng(seed)
    days, d = [], date(2021, 1, 4)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    sigma = {"calm": 0.006, "violent": 0.03}[vol_regime]
    bench = rng.normal(0.0004, sigma, n)
    series = {
        "SPY": bench,
        "XLK": 1.2 * bench + rng.normal(0, 0.004, n),
        "MTUM": 1.1 * bench + rng.normal(0, 0.004, n),
        "QUAL": 0.9 * bench + rng.normal(0, 0.004, n),
        "IEF": -0.1 * bench + rng.normal(0.0001, 0.003, n),
        "TLT": -0.2 * bench + rng.normal(0.0001, 0.006, n),
        "BIL": np.full(n, 0.00012),
        "VTIP": rng.normal(0.0001, 0.002, n),
        "DBMF": rng.normal(0.0002, 0.005, n),
        "KMLM": rng.normal(0.0002, 0.006, n),
        "BTAL": -0.5 * bench + rng.normal(0, 0.004, n),
    }
    prices, rets, first = {}, {}, {}
    for t, r in series.items():
        px = 100 * np.cumprod(1 + r)
        prices[t] = px
        rr = np.full(n, np.nan)
        rr[1:] = px[1:] / px[:-1] - 1.0
        rets[t] = rr
        first[t] = 273
    sleeves = {"SPY": "broad_equity", "XLK": "sector_equity",
               "MTUM": "factor_equity", "QUAL": "factor_equity",
               "IEF": "treasury", "TLT": "treasury", "BIL": "treasury",
               "VTIP": "inflation_linked", "DBMF": "managed_futures",
               "KMLM": "managed_futures", "BTAL": "managed_futures"}
    return AlphaData(days=days, prices=prices, rets=rets, first_usable=first,
                     bench="SPY", rf_daily=np.zeros(n),
                     regime=["RISK_NEUTRAL"] * n,
                     sleeve_of=sleeves,
                     prior_of={t: 1.0 for t in sleeves},
                     wmax_of={t: 0.4 for t in sleeves})


def test_brake_derisks_in_violent_vol():
    calm = simulate_convex(_panel(vol_regime="calm"), MCFG)
    violent = simulate_convex(_panel(vol_regime="violent"), MCFG)
    violent_nobrake = simulate_convex(_panel(vol_regime="violent"), MCFG,
                                      brake=False)
    # the brake cuts realized vol vs the unbraked book in a violent market
    assert violent.metrics["ann_vol"] < violent_nobrake.metrics["ann_vol"]
    # and barely binds in a calm one (vol ~9.5% < 12% target)
    assert calm.metrics["ann_vol"] <= violent_nobrake.metrics["ann_vol"]


def test_convexity_folds_to_duration_pre_inception():
    p = _panel()
    # push managed-futures inception past the window end
    for t in ("DBMF", "KMLM", "BTAL"):
        p.first_usable[t] = 10 ** 9
        p.prices[t][:] = np.nan
        p.rets[t][:] = np.nan
    r = simulate_convex(p, MCFG)
    assert r.metrics["cagr"] is not None        # runs fine without the sleeve
    # duration absorbed the mass — turnover stays sane
    assert r.annual_turnover < 5.0


def test_band_rebalancing_limits_turnover():
    r = simulate_convex(_panel(), MCFG)
    # weekly full-rebalance would be far higher; bands keep it modest
    assert r.annual_turnover < 3.0


def test_attribution_is_noninvasive_and_sums():
    """collect_attribution must NOT change the returns (live path identity) and
    the per-sleeve daily contributions must sum to the total (gross of cost)."""
    base = simulate_convex(_panel(), MCFG)
    attr = simulate_convex(_panel(), MCFG, collect_attribution=True)
    # 1) bit-identical returns — the instrumentation is opt-in and side-effect-free
    assert attr.daily_returns == base.daily_returns
    assert base.sleeve_daily == {}                      # off by default
    sd = attr.sleeve_daily
    assert set(sd) == {"equity", "convexity", "duration", "cost"}
    n = len(attr.daily_returns)
    assert all(len(v) == n for v in sd.values())
    # 2) equity + convexity + duration + cost == total, every day
    for i in range(n):
        recon = sd["equity"][i] + sd["convexity"][i] + sd["duration"][i] + sd["cost"][i]
        assert abs(recon - attr.daily_returns[i]) < 1e-12


def test_deterministic():
    a = simulate_convex(_panel(), MCFG)
    b = simulate_convex(_panel(), MCFG)
    assert a.daily_returns == b.daily_returns


def test_recovery_days_metric():
    assert _max_recovery_days([0.1, -0.05, 0.06]) == 1
    assert _max_recovery_days([-0.5, 0.0, 0.0]) == 3   # never recovers
    assert _max_recovery_days([]) is None


def test_benchmarks():
    p = _panel()
    spy = simulate_benchmark(p, "spy")
    s6040 = simulate_benchmark(p, "60_40")
    # SPY benchmark ≈ the bench series itself (minus one-time entry cost)
    bench_m = np.nanmean(p.rets["SPY"][274:])
    assert abs(np.mean(spy.daily_returns) - bench_m) < 2e-4
    assert s6040.metrics["ann_vol"] < spy.metrics["ann_vol"]
    with pytest.raises(ValueError):
        simulate_benchmark(p, "70_30")



def test_scores_cache_equivalence():
    """Search-mode (cached scores) must reproduce live-mode exactly."""
    from tradeclassifier.convex_core import precompute_scores
    p = _panel()
    sc = precompute_scores(p, MCFG)
    live = simulate_convex(p, MCFG)
    cached = simulate_convex(p, MCFG, scores_cache=sc)
    assert live.daily_returns == cached.daily_returns




def test_brake_v2_variants_behave():
    """semivol ignores up-vol; dual horizon reacts faster; credit confirm
    triggers the stress cap on a synthetic spread blowout."""
    import numpy as np
    base = _panel(vol_regime="violent")
    v_semi = simulate_convex(base, MCFG, brake_cfg={"semivol": True})
    v_full = simulate_convex(base, MCFG)
    # both brake; results differ (different vol measure) but both de-risk
    assert v_semi.daily_returns != v_full.daily_returns
    assert v_semi.metrics["ann_vol"] < 0.20

    # credit confirm: huge spread widening forces the stress cap → lower vol
    p = _panel(vol_regime="calm")
    p.credit_spread = np.linspace(1.0, 12.0, len(p.days))  # >0.20/21d widening
    capped = simulate_convex(p, MCFG, brake_cfg={"credit_confirm": 0.20})
    free = simulate_convex(p, MCFG)
    assert capped.metrics["ann_vol"] < free.metrics["ann_vol"]

    # proportional release: differs from step release after a vol spike
    v_prop = simulate_convex(base, MCFG, brake_cfg={"release_rate": 0.5})
    assert v_prop.daily_returns != v_full.daily_returns


def test_xasset_pool_changes_tilts():
    from tradeclassifier.convex_core import precompute_scores
    p = _panel()
    # make an intl-ish name by relabeling QUAL's sleeve
    p.sleeve_of["QUAL"] = "intl_equity"
    sc = precompute_scores(p, MCFG)
    narrow = simulate_convex(p, MCFG, scores_cache=sc)
    wide = simulate_convex(p, MCFG, scores_cache=sc,
                           tilt_pool=("sector_equity", "factor_equity",
                                      "intl_equity"), n_tilts=3)
    # QUAL is now reachable only in the wide pool → different paths
    assert narrow.daily_returns != wide.daily_returns




def test_equity_adj_moves_exposure():
    import numpy as np
    p = _panel()
    up = simulate_convex(p, MCFG, equity_adj=np.full(len(p.days), +0.15))
    dn = simulate_convex(p, MCFG, equity_adj=np.full(len(p.days), -0.25))
    assert up.metrics["ann_vol"] > dn.metrics["ann_vol"]
    # nan adj days fall back to the base weight (no crash)
    half = np.full(len(p.days), np.nan)
    half[::2] = 0.10
    mixed = simulate_convex(p, MCFG, equity_adj=half)
    assert mixed.metrics["cagr"] is not None


def test_value_slot_guarantee():
    from tradeclassifier.convex_core import _select_tilts, VALUE_TILTS
    p = _panel()
    p.sleeve_of["VLUE"] = "factor_equity"
    p.rets["VLUE"] = p.rets["QUAL"]; p.prices["VLUE"] = p.prices["QUAL"]
    p.first_usable["VLUE"] = 273
    scores = {"XLK": 3.0, "MTUM": 2.5, "QUAL": 2.0, "VLUE": 0.5}
    picks = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"),
                          3, value_slots=1)
    assert "VLUE" in picks and len(picks) == 3
    # without the slot, VLUE (lowest score) is excluded
    picks0 = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"),
                           3, value_slots=0)
    assert "VLUE" not in picks0




def test_synth_trend_fills_missing_convexity():
    import numpy as np
    p = _panel()
    for t in ("DBMF", "KMLM", "BTAL"):       # no managed futures era
        p.first_usable[t] = 10 ** 9
        p.prices[t][:] = np.nan
        p.rets[t][:] = np.nan
    plain = simulate_convex(p, MCFG)
    synth = simulate_convex(p, MCFG, synth_trend=True)
    assert synth.daily_returns != plain.daily_returns   # proxy engaged
    assert synth.metrics["cagr"] is not None


def test_brake_deadband_reduces_scale_churn():
    base = _panel(vol_regime="violent")
    plain = simulate_convex(base, MCFG)
    db = simulate_convex(base, MCFG, brake_cfg={"deadband": 0.10})
    assert db.annual_turnover <= plain.annual_turnover


def test_tilt_persistence_retains_incumbents():
    from tradeclassifier.convex_core import _select_tilts
    p = _panel()
    scores = {"XLK": 2.0, "MTUM": 1.9, "QUAL": 1.85}
    # without persistence: top-2 = XLK, MTUM
    picks0 = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"), 2)
    assert picks0 == ["XLK", "MTUM"]
    # QUAL incumbent + margin 0.25: QUAL effective 2.10 beats MTUM 1.9
    picks1 = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"), 2,
                           incumbents=("QUAL",), persistence_margin=0.25)
    assert "QUAL" in picks1
    # a big challenger gap still wins the slot
    scores2 = {"XLK": 2.0, "MTUM": 2.5, "QUAL": 1.0}
    picks2 = _select_tilts(p, 300, scores2, ("sector_equity", "factor_equity"), 2,
                           incumbents=("QUAL",), persistence_margin=0.25)
    assert "QUAL" not in picks2


def test_factor_lambda_rewards_value_beta():
    from tradeclassifier.convex_core import _select_tilts
    p = _panel()
    scores = {"XLK": 2.0, "MTUM": 1.9, "QUAL": 1.7}
    fb = {"XLK": -0.5, "MTUM": -0.4, "QUAL": 0.9}
    base = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"), 2)
    assert base == ["XLK", "MTUM"]
    aware = _select_tilts(p, 300, scores, ("sector_equity", "factor_equity"), 2,
                          factor_betas=fb, factor_lambda=0.5)
    assert "QUAL" in aware     # 1.7 + 0.45 beats MTUM's 1.9 - 0.2
