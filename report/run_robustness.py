#!/usr/bin/env python3
"""Decision Robustness — Project C (dnsr-agent/IMPL_DECISION_ROBUSTNESS.md v1.0).

Per assumption axis: the smallest perturbation that breaks each registered promise
vs the 60/40 benchmark (P1 MaxDD better, P2 Sortino >=, P3 CAGR give-up <= 1.5pp).
One-at-a-time from the frozen production point. Margins, never recommendations.

    python scripts/run_robustness.py --start 2005-01-01 --end 2026-06-30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from tradeclassifier import convex_core as cc  # noqa: E402
from tradeclassifier.alpha_backtest import precompute_alpha_data  # noqa: E402
from tradeclassifier.config import load_config  # noqa: E402
from tradeclassifier.convex_core import (DEFAULTS, V2_BRAKE, V2_DEDUP_CORR,  # noqa: E402
                                         V2_DEDUP_PREFER_DROP, V2_N_TILTS,
                                         V2_PERSISTENCE, V2_TILT_POOL,
                                         V2_VALUE_SLOTS, precompute_scores,
                                         simulate_benchmark, simulate_convex)
from tradeclassifier.loaders import Warehouse  # noqa: E402
from tradeclassifier.portfolio import MODEL_FILE, UNIVERSE_FILE  # noqa: E402

OUT = REPO / "out" / "robustness" / "robustness.json"
BIL_ONLY = {"BIL": 1.0}
ALL_IEF = {"IEF": 1.0}
P3_TOLERANCE = 0.015     # registered: CAGR give-up bound vs 60/40


def metrics_of(res) -> dict:
    m = {k: round(float(res.metrics[k]), 6)
         for k in ("cagr", "ann_vol", "sharpe", "sortino", "max_drawdown")}
    m["calmar"] = res.calmar
    m["annual_turnover"] = res.annual_turnover
    return m


def promises(m: dict, bench: dict) -> dict:
    """Registered §1 breach criteria. Margins are signed: positive = intact."""
    return {
        "P1_maxdd": {"intact": m["max_drawdown"] > bench["max_drawdown"],
                     "margin": round(m["max_drawdown"] - bench["max_drawdown"], 4)},
        "P2_sortino": {"intact": m["sortino"] >= bench["sortino"],
                       "margin": round(m["sortino"] - bench["sortino"], 4)},
        "P3_cagr": {"intact": m["cagr"] >= bench["cagr"] - P3_TOLERANCE,
                    "margin": round(m["cagr"] - (bench["cagr"] - P3_TOLERANCE), 4)},
    }


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
    data = precompute_alpha_data(wh, ucfg, args.start, args.end,
                                 confirm_days=int(cfg["regime"]["confirm_days"]))
    scores = precompute_scores(data, mcfg, every=5)
    print(f"ready {time.time()-t0:.0f}s", flush=True)

    prod_params = {**DEFAULTS, "w_equity": 0.95}

    def run_model(*, params=None, sim_kw=None, patch=None) -> dict:
        """One perturbed run. patch: dict of module-constant overrides (saved/restored)."""
        p = dict(prod_params)
        if params:
            p.update(params)
        kw = dict(params=p, slippage_bps=slip, brake_cfg=dict(V2_BRAKE),
                  scores_cache=scores, tilt_pool=V2_TILT_POOL, n_tilts=V2_N_TILTS,
                  value_slots=V2_VALUE_SLOTS, persistence_margin=V2_PERSISTENCE,
                  dedup_corr=V2_DEDUP_CORR, dedup_prefer_drop=V2_DEDUP_PREFER_DROP,
                  collect_returns=False)
        if sim_kw:
            kw.update(sim_kw)
        saved = {k: getattr(cc, k) for k in (patch or {})}
        try:
            for k, v in (patch or {}).items():
                setattr(cc, k, v)
            return metrics_of(simulate_convex(data, mcfg, **kw))
        finally:
            for k, v in saved.items():
                setattr(cc, k, v)

    # benchmark at production costs (and per-slippage for the shared O3 axis)
    bench = {slip: metrics_of(simulate_benchmark(data, "60_40", slippage_bps=slip))}

    AXES: dict[str, list[tuple[str, dict]]] = {
        "S1_signal_lag":    [(f"lag_{k}d", {"sim_kw": {"brake_vol_lag": k}}) for k in (0, 2, 5, 10, 21)],
        "S2_signal_bias":   [(f"bias_{b}", {"sim_kw": {"brake_vol_bias": b}}) for b in (0.7, 0.85, 1.0, 1.15, 1.3)],
        "S3_signal_window": [(f"win_{w}d", {"sim_kw": {"brake_vol_window": w}}) for w in (10, 15, 21, 42, 63)],
        "O1_exec_lag":      [(f"exec_{k}d", {"sim_kw": {"exec_lag_days": k}}) for k in (0, 1, 2, 5, 10)],
        "O2_missed_rebal":  [("none", {}),
                             ("skip_every_4th", {"sim_kw": {"skip_every": 4}}),
                             ("skip_every_3rd", {"sim_kw": {"skip_every": 3}}),
                             ("skip_every_2nd", {"sim_kw": {"skip_every": 2}}),
                             ("absent_2020_03", {"sim_kw": {"skip_months": frozenset({"2020-03"})}})],
        "O3_slippage":      [(f"slip_{s}bps", {"sim_kw": {"slippage_bps": float(s)}, "bench_slip": float(s)})
                             for s in (5, 40, 80)],
        "G1_stress_cap":    [(f"cap_{c}", {"params": {"stress_eq_scale_cap": c}}) for c in (0.55, 0.70, 0.85, 1.0)],
        "G1_release_step":  [(f"release_{r}", {"patch": {"BRAKE_RELEASE_STEP": r}}) for r in (0.05, 0.15, 0.30)],
        "G1_band":          [(f"band_{b}", {"patch": {"BAND_REL": b}}) for b in (0.10, 0.20, 0.40)],
        "I1_sleeve":        [("production", {}),
                             ("dbmf_only", {"sim_kw": {"convexity": {"DBMF": 1.0}}}),
                             ("kmlm_only", {"sim_kw": {"convexity": {"KMLM": 1.0}}}),
                             ("synth_trend", {"sim_kw": {"convexity": {}, "synth_trend": True}}),
                             ("none", {"params": {"w_convexity": 0.0}})],
        "I2_ladder":        [("production", {}),
                             ("all_ief", {"patch": {"DURATION_NEUTRAL": ALL_IEF,
                                                    "DURATION_RALLY_MIX": ALL_IEF,
                                                    "INFLATION_MIX": ALL_IEF}}),
                             ("all_bil", {"patch": {"DURATION_NEUTRAL": BIL_ONLY,
                                                    "DURATION_RALLY_MIX": BIL_ONLY,
                                                    "INFLATION_MIX": BIL_ONLY}})],
    }

    out = {"spec": "dnsr-agent/IMPL_DECISION_ROBUSTNESS.md v1.0",
           "window": [args.start, args.end], "profile": prod_params,
           "p3_tolerance": P3_TOLERANCE, "engine_seams_commit": "c24da31",
           "benchmark": {"kind": "60_40 same-loop", "metrics_by_slippage":
                         {str(k): v for k, v in bench.items()}},
           "axes": {}}

    n_runs = 0
    for axis, points in AXES.items():
        rows = {}
        for label, spec in points.items() if isinstance(points, dict) else points:
            bslip = spec.pop("bench_slip", slip)
            if bslip not in bench:
                bench[bslip] = metrics_of(simulate_benchmark(data, "60_40", slippage_bps=bslip))
            m = run_model(**spec)
            n_runs += 1
            rows[label] = {"metrics": m, "promises": promises(m, bench[bslip])}
            broken = [k for k, v in rows[label]["promises"].items() if not v["intact"]]
            print(f"  {axis:<17} {label:<16} cagr={m['cagr']:.4f} sortino={m['sortino']:.3f} "
                  f"mdd={m['max_drawdown']:.4f}  {'BREACH: ' + ','.join(broken) if broken else 'intact'}",
                  flush=True)
        out["axes"][axis] = rows
    out["benchmark"]["metrics_by_slippage"] = {str(k): v for k, v in bench.items()}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"\n{n_runs} model runs -> {OUT} | elapsed {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
