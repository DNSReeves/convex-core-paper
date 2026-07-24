#!/usr/bin/env python3
"""Convexity Attribution — Project B (dnsr-agent/IMPL_CONVEX_ATTRIB.md v1.1).

Decomposes the measured Convex Core record into mechanism contributions via
exact Shapley values over the 2^5 toggle factorial (BRAKE/SLEEVE/DUR/REGIME/TILT),
per metric, per profile — plus the rebalance-cadence side study. Descriptive of
the record AS MEASURED: frozen params, production kwargs, no fitting, no promotion.

Registered conventions (spec §2, §4b):
  BRAKE  off: brake=False; off-with-REGIME-on: vol_target=1e9 inside the brake block
  SLEEVE off: w_convexity=0 (mass folds to duration — the engine's own convention)
  DUR    off: DURATION_* mixes patched to {BIL: 1.0} (save/restore; engine untouched)
  REGIME off: every day RISK_NEUTRAL — the published regime_wf convention verbatim
  TILT   off: tilt_frac=0
  Cadence study: REBALANCE_EVERY in {5,21,63,252} on the full model + a drift
  variant (BAND_REL=inf: one initial allocation, never rebalanced).
  Gross exposure instrumented per config (the 0.95/0.15 negative-duration drop).

    python scripts/run_attribution.py --start 2005-01-01 --end 2026-06-30
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from tradeclassifier import convex_core as cc  # noqa: E402
from tradeclassifier.alpha_backtest import precompute_alpha_data  # noqa: E402
from tradeclassifier.config import load_config  # noqa: E402
from tradeclassifier.convex_core import (DEFAULTS, V2_BRAKE, V2_DEDUP_CORR,  # noqa: E402
                                         V2_DEDUP_PREFER_DROP, V2_N_TILTS,
                                         V2_PERSISTENCE, V2_TILT_POOL,
                                         V2_VALUE_SLOTS, precompute_scores,
                                         simulate_convex)
from tradeclassifier.loaders import Warehouse  # noqa: E402
from tradeclassifier.portfolio import MODEL_FILE, UNIVERSE_FILE  # noqa: E402

MECHS = ("BRAKE", "SLEEVE", "DUR", "REGIME", "TILT")
METRICS = ("cagr", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar")
PROFILES = {"paper_0.95": {"w_equity": 0.95}, "default_0.65": {}}
BIL_ONLY = {"BIL": 1.0}
OUT = REPO / "out" / "attribution" / "attribution.json"


class GrossRecorder:
    """Wraps _sleeve_targets to record the weight-sum at every decision point."""

    def __init__(self):
        self.sums: list[float] = []
        self._orig = cc._sleeve_targets

    def __call__(self, *a, **kw):
        res = self._orig(*a, **kw)
        merged = res[0]
        self.sums.append(float(sum(merged.values())))
        return res

    def stats(self) -> dict:
        if not self.sums:
            return {"mean": None, "max": None, "pct_days_gt_1.02": None}
        arr = np.array(self.sums)
        return {"mean": round(float(arr.mean()), 4),
                "max": round(float(arr.max()), 4),
                "pct_days_gt_1.02": round(float((arr > 1.02).mean() * 100), 1)}


def run_config(data_on, data_off, caches, mcfg, slip, profile: dict,
               on: frozenset, *, rebalance_every: int = 5,
               band_drift: bool = False) -> dict:
    """One backtest under a toggle set. Patches module constants with
    save/restore; the engine file is never modified."""
    data = data_on if "REGIME" in on else data_off
    cache = caches["on" if "REGIME" in on else "off"] if rebalance_every == 5 else None

    p = dict(DEFAULTS)
    p.update(profile)
    if "SLEEVE" not in on:
        p["w_convexity"] = 0.0
    if "TILT" not in on:
        p["tilt_frac"] = 0.0
    brake = ("BRAKE" in on) or ("REGIME" in on)
    if "BRAKE" not in on and "REGIME" in on:
        p["vol_target"] = 1e9          # scale pins to 1; stress-cap machinery keeps production dynamics

    saved = (cc.DURATION_NEUTRAL, cc.DURATION_RALLY_MIX, cc.INFLATION_MIX,
             cc.REBALANCE_EVERY, cc.BAND_REL, cc._sleeve_targets)
    rec = GrossRecorder()
    try:
        if "DUR" not in on:
            cc.DURATION_NEUTRAL = BIL_ONLY
            cc.DURATION_RALLY_MIX = BIL_ONLY
            cc.INFLATION_MIX = BIL_ONLY
        cc.REBALANCE_EVERY = rebalance_every
        if band_drift:
            cc.BAND_REL = 1e9          # first allocation only, then drift
        cc._sleeve_targets = rec

        kw = dict(params=p, brake=brake, slippage_bps=slip,
                  scores_cache=cache, tilt_pool=V2_TILT_POOL,
                  n_tilts=V2_N_TILTS, value_slots=V2_VALUE_SLOTS,
                  persistence_margin=V2_PERSISTENCE,
                  dedup_corr=V2_DEDUP_CORR,
                  dedup_prefer_drop=V2_DEDUP_PREFER_DROP,
                  collect_returns=False)
        if brake:
            kw["brake_cfg"] = dict(V2_BRAKE)
        res = simulate_convex(data, mcfg, **kw)
    finally:
        (cc.DURATION_NEUTRAL, cc.DURATION_RALLY_MIX, cc.INFLATION_MIX,
         cc.REBALANCE_EVERY, cc.BAND_REL, cc._sleeve_targets) = saved

    m = dict(res.metrics)
    m["calmar"] = res.calmar
    return {"metrics": {k: (None if m.get(k) is None else round(float(m[k]), 6))
                        for k in METRICS},
            "annual_turnover": res.annual_turnover,
            "gross": rec.stats(),
            "stress_windows": res.stress_windows}


def shapley(values: dict[frozenset, float]) -> dict[str, float]:
    """Exact Shapley over the 5 mechanisms for one metric."""
    n = len(MECHS)
    phi = {}
    for m in MECHS:
        total = 0.0
        for r in range(n):
            for s in itertools.combinations([x for x in MECHS if x != m], r):
                S = frozenset(s)
                w = math.factorial(len(S)) * math.factorial(n - len(S) - 1) / math.factorial(n)
                total += w * (values[S | {m}] - values[S])
        phi[m] = total          # unrounded — additivity is checked on these; round at write time
    return phi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--config", default=str(REPO / "config" / "classifier.yaml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    ucfg = yaml.safe_load(UNIVERSE_FILE.read_text())
    mcfg = yaml.safe_load(MODEL_FILE.read_text())
    wh = Warehouse(cfg["data"]["db_path"])
    slip = float(cfg["costs"]["slippage_bps"])

    t0 = time.time()
    print(f"panel {args.start} -> {args.end} ...", flush=True)
    data_on = precompute_alpha_data(wh, ucfg, args.start, args.end,
                                    confirm_days=int(cfg["regime"]["confirm_days"]))
    data_off = replace(data_on, regime=["RISK_NEUTRAL"] * len(data_on.days))
    print(f"panel ready {time.time()-t0:.0f}s; scoring caches ...", flush=True)
    caches = {"on": precompute_scores(data_on, mcfg, every=5),
              "off": precompute_scores(data_off, mcfg, every=5)}
    print(f"caches ready {time.time()-t0:.0f}s; factorial ...", flush=True)

    out: dict = {"spec": "dnsr-agent/IMPL_CONVEX_ATTRIB.md v1.1",
                 "window": [args.start, args.end],
                 "engine": "tradeclassifier.convex_core (unmodified; harness patches recorded)",
                 "slippage_bps": slip, "mechanisms": list(MECHS),
                 "profiles": {}, "cadence_study": {}}

    for pname, prof in PROFILES.items():
        runs: dict[str, dict] = {}
        values: dict[str, dict[frozenset, float]] = {k: {} for k in METRICS}
        for r in range(len(MECHS) + 1):
            for combo in itertools.combinations(MECHS, r):
                on = frozenset(combo)
                key = "+".join(sorted(on)) or "none"
                res = run_config(data_on, data_off, caches, mcfg, slip, prof, on)
                runs[key] = res
                for met in METRICS:
                    values[met][on] = res["metrics"][met] or 0.0
                print(f"  [{pname}] {key:<38} cagr={res['metrics']['cagr']:.4f} "
                      f"mdd={res['metrics']['max_drawdown']:.4f} gross_max={res['gross']['max']}",
                      flush=True)

        full, empty = frozenset(MECHS), frozenset()
        shap_raw = {met: shapley(values[met]) for met in METRICS}
        addit = {met: round(sum(shap_raw[met].values())
                            - (values[met][full] - values[met][empty]), 12)
                 for met in METRICS}
        assert all(abs(v) < 1e-9 for v in addit.values()), f"additivity FAILED: {addit}"
        shap = {met: {m: round(v, 6) for m, v in shap_raw[met].items()} for met in METRICS}

        pairs = {}
        for a, b in itertools.combinations(MECHS, 2):
            pairs[f"{a}+{b}"] = {met: round(
                values[met][frozenset({a, b})] - values[met][frozenset({a})]
                - values[met][frozenset({b})] + values[met][empty], 6)
                for met in ("sortino", "max_drawdown")}
        loo = {m: {met: round(values[met][full] - values[met][full - {m}], 6)
                   for met in METRICS} for m in MECHS}

        out["profiles"][pname] = {
            "profile_params": {**DEFAULTS, **prof}, "runs": runs,
            "shapley": shap, "additivity_residuals": addit,
            "leave_one_out": loo, "pairwise_interactions": pairs}

    print("cadence study (paper profile, full model) ...", flush=True)
    prof = PROFILES["paper_0.95"]
    allon = frozenset(MECHS)
    for label, every, drift in (("weekly_5d", 5, False), ("monthly_21d", 21, False),
                                ("quarterly_63d", 63, False), ("annual_252d", 252, False),
                                ("drift_never", 5, True)):
        res = run_config(data_on, data_off, caches, mcfg, slip, prof, allon,
                         rebalance_every=every, band_drift=drift)
        out["cadence_study"][label] = res
        print(f"  {label:<14} cagr={res['metrics']['cagr']:.4f} "
              f"mdd={res['metrics']['max_drawdown']:.4f} turn={res['annual_turnover']}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {OUT} | elapsed {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
