"""Convex Core — beat buy-and-hold on Calmar/Sortino/recovery, not CAGR
(../convex_core_design_spec.md, built from the day's backtest evidence).

Four structural mechanisms, five frozen parameters, zero fitting in v1:

- strategic equity core (never exits) with the measured-IC tilt at honest size
- crisis-convexity sleeve (DBMF/KMLM/BTAL per the crisis-alpha evidence),
  PIT-folding into duration before member inception
- tag-tilted duration ladder (tags tilt, never exit)
- the volatility brake: eq_scale = min(1, vol_target/realized_21d), with a
  confirmatory LIQUIDITY_STRESS cap — responds in days, no classification lag

Reuses the alpha-beta panel (`precompute_alpha_data`), the IC tilt
(`_score_date`), shift-disciplined accounting, and the report contracts.
Benchmarks (SPY, 60/40, no-brake ablation) run in the same loop on the same
calendar with the same cost model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

import numpy as np

from .alpha_backtest import AlphaData, _score_date
from .objective import perf_metrics

# ── frozen v1 defaults (the entire searchable surface — design §3) ──────────
DEFAULTS: dict[str, float] = {
    "w_equity": 0.65,
    "w_convexity": 0.15,          # w_duration = 1 − w_equity − w_convexity
    "vol_target": 0.12,           # annualized, on the equity sleeve
    "stress_eq_scale_cap": 0.70,  # confirmatory cap in LIQUIDITY_STRESS
    "tilt_frac": 0.40,            # fraction of the equity sleeve in IC-tilted names
}

EQUITY_BASE = "SPY"
TILT_SLEEVES = ("sector_equity", "factor_equity")     # tilt candidates
N_TILTS = 3
CONVEXITY = {"DBMF": 0.50, "KMLM": 0.30, "BTAL": 0.20}
DURATION_NEUTRAL = {"IEF": 0.60, "BIL": 0.40}
DURATION_RALLY_MIX = {"TLT": 0.50, "IEF": 0.40, "BIL": 0.10}
INFLATION_MIX = {"VTIP": 0.50, "BIL": 0.30, "IEF": 0.20}
# ── v2 keeper config (2026-06-11 ablation: semivol brake + cross-asset tilts
# won individually and combined; dual-horizon/prop-release/credit-confirm/CAPE
# did not earn keep — see out/brake_v2/) ───────────────────────────────────
V2_BRAKE = {"semivol": True}
V2_TILT_POOL = TILT_SLEEVES + ("intl_equity", "commodity")
V2_N_TILTS = 5
V2_VALUE_SLOTS = 1
# tilt de-dup guard (2026-06-13): drop near-twin tilts (trailing corr > 0.95) so the
# selector can't hold redundant duplicates (e.g. DBC≈PDBC); prefer dropping the K-1
# commodity funds so the no-K-1 twin (PDBC) is kept. Confirmed performance-neutral.
V2_DEDUP_CORR = 0.95
V2_DEDUP_PREFER_DROP = frozenset({"DBC", "USO", "CPER"})   # K-1 commodity funds
V2_PERSISTENCE = 0.75  # tilt incumbency bonus (z-units): challenger must beat
                       # the incumbent by this margin. Sweep 2026-06-12: broad
                       # plateau 0.75-1.5 (CAGR 8.39-8.45, Calmar 0.657-0.676,
                       # turnover 10.5→6.0); 0.75 = earliest plateau entry =
                       # least sticky, best Sharpe (1.05); declines by 2.0     # ablation 2026-06-11: improves every column (Calmar
                       # 0.586→0.615, 2022 −2.3%→−1.4%); the deeper VAL short
                       # (−0.11 residual) is the #1b candidate (value feature)
# value-premium names in the universe (the factor report measured the tilt
# mechanism SHORT value at −0.13 / −0.64%/yr harvest — the slot guarantee
# is the measured fix, ablation 2026-06-11)
VALUE_TILTS = frozenset({"VLUE", "VTV", "IWD", "SCHD", "DVY"})

REBALANCE_EVERY = 5               # weekly decision point
BAND_REL = 0.20                   # rebalance a sleeve drifted >20% relative
BRAKE_RELEASE_STEP = 0.15         # max weekly INCREASE of eq_scale (slow re-risk)


@dataclass
class ConvexResult:
    name: str
    metrics: dict[str, float]
    calmar: float | None
    max_recovery_days: int | None
    annual_turnover: float
    daily_returns: list[float] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)
    regime_metrics: dict[str, dict] = field(default_factory=dict)
    stress_windows: dict[str, float] = field(default_factory=dict)
    # per-sleeve daily contribution (equity/convexity/duration/cost), opt-in via
    # simulate_convex(collect_attribution=True); empty on the live path
    sleeve_daily: dict[str, list[float]] = field(default_factory=dict)


def _calmar(m: Mapping[str, float]) -> float | None:
    dd = abs(m.get("max_drawdown", 0.0))
    return round(m["cagr"] / dd, 3) if dd > 1e-9 else None


def _max_recovery_days(rets: list[float]) -> int | None:
    """Longest peak-to-recovery stretch, in trading days."""
    if not rets:
        return None
    wealth = np.cumprod(1.0 + np.asarray(rets))
    # the running peak includes the starting wealth of 1.0 — a first-day
    # loss is already a drawdown
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    under = wealth < peak
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return int(longest)


STRESS_WINDOWS = {
    "GFC_2008_09": (date(2008, 9, 1), date(2009, 3, 31)),
    "COVID_2020_03": (date(2020, 2, 14), date(2020, 4, 15)),
    "RATES_2022": (date(2022, 1, 1), date(2022, 10, 31)),
}


def _window_return(days: list[date], rets: list[float],
                   start: date, end: date) -> float | None:
    vals = [r for d, r in zip(days, rets) if start <= d <= end]
    if len(vals) < 5:
        return None
    return float(np.prod(1.0 + np.asarray(vals)) - 1.0)


def _available(data: AlphaData, t: str, i: int) -> bool:
    return (t in data.prices and i >= data.first_usable.get(t, 10 ** 9) // 1
            and not np.isnan(data.prices[t][i]))


def precompute_factor_betas(data: AlphaData, *,
                            long_t: str = "VLUE", short_t: str = "SPY",
                            window: int = 252,
                            start_idx: int | None = None,
                            every: int = REBALANCE_EVERY
                            ) -> dict[int, dict[str, float]]:
    """Per-ticker rolling beta to the VAL proxy (VLUE−SPY) on rebalance days —
    the factor-aware tilt input. PIT: trailing window only."""
    if start_idx is None:
        start_idx = max(data.first_usable.get(EQUITY_BASE, 273), 273)
    lr, sr = data.rets.get(long_t), data.rets.get(short_t)
    out: dict[int, dict[str, float]] = {}
    if lr is None or sr is None:
        return out
    fac = lr - sr
    for i in range(start_idx, len(data.days)):
        if i % every != 0:
            continue
        f_win = fac[max(0, i - window + 1): i + 1]
        day_betas: dict[str, float] = {}
        for t in data.sleeve_of:
            r_win = data.rets[t][max(0, i - window + 1): i + 1]
            mask = ~(np.isnan(f_win) | np.isnan(r_win))
            if mask.sum() < 120:
                continue
            fv, rv = f_win[mask], r_win[mask]
            var = fv.var()
            if var > 0:
                day_betas[t] = float(np.cov(rv, fv, bias=True)[0, 1] / var)
        out[i] = day_betas
    return out


def precompute_scores(data: AlphaData, mcfg: dict, *,
                      start_idx: int | None = None,
                      every: int = REBALANCE_EVERY) -> dict[int, dict[str, float]]:
    """The IC scores are parameter-independent — precompute them per
    (absolute-anchored) rebalance index once; tilt SELECTION (pool/N) happens
    cheaply at sim time, so brake/tilt variants share one cache."""
    if start_idx is None:
        start_idx = max(data.first_usable.get(EQUITY_BASE, 273), 273)
    out: dict[int, dict[str, float]] = {}
    for i in range(start_idx, len(data.days)):
        if i % every != 0:
            continue
        scores, _ = _score_date(data, i, mcfg)
        out[i] = scores
    return out


def _corr_pit(data: AlphaData, a: str, b: str, i: int, window: int) -> float:
    """Trailing return correlation between two tickers over [i-window, i) — PIT."""
    ra, rb = data.rets.get(a), data.rets.get(b)
    if ra is None or rb is None:
        return 0.0
    lo = max(0, i - window)
    xa, xb = ra[lo:i], rb[lo:i]
    m = ~(np.isnan(xa) | np.isnan(xb))
    if int(m.sum()) < 60:
        return 0.0
    xa, xb = xa[m], xb[m]
    if xa.std() == 0 or xb.std() == 0:
        return 0.0
    return float(np.corrcoef(xa, xb)[0, 1])


def _dedup_tilts(picks: list[str], elig: list[str], scores: Mapping[str, float],
                 data: AlphaData, i: int, thresh: float, window: int,
                 prefer_drop: frozenset) -> list[str]:
    """Drop near-duplicate tilts (trailing corr > thresh, e.g. DBC≈PDBC). Of a twin
    pair keep the non-`prefer_drop` member (the no-K-1 fund) else the higher-scored,
    and pull in the next non-twin eligible candidate. PIT; bounded fixpoint."""
    picks = list(picks)
    bench = [t for t in elig if t not in picks]          # next-best, score order
    for _ in range(50):
        pair = next(((picks[x], picks[y])
                     for x in range(len(picks)) for y in range(x + 1, len(picks))
                     if _corr_pit(data, picks[x], picks[y], i, window) > thresh), None)
        if not pair:
            break
        a, b = pair
        if a in prefer_drop and b not in prefer_drop:
            loser = a
        elif b in prefer_drop and a not in prefer_drop:
            loser = b
        else:
            loser = a if scores.get(a, 0.0) <= scores.get(b, 0.0) else b
        picks.remove(loser)
        repl = next((c for c in bench if c not in picks
                     and all(_corr_pit(data, c, p, i, window) <= thresh for p in picks)), None)
        if repl is not None:
            picks.append(repl); bench.remove(repl)
    picks.sort(key=lambda t: -scores.get(t, 0.0))
    return picks


def _select_tilts(data: AlphaData, i: int, scores: Mapping[str, float],
                  pool: tuple[str, ...], n: int,
                  value_slots: int = 0,
                  incumbents: tuple[str, ...] = (),
                  persistence_margin: float = 0.0,
                  factor_betas: Mapping[str, float] | None = None,
                  factor_lambda: float = 0.0,
                  dedup_corr: float = 0.0, dedup_window: int = 252,
                  dedup_prefer_drop: frozenset = frozenset()) -> list[str]:
    # tilt persistence: incumbency = a score bonus of `persistence_margin`
    # (z-units); factor-aware scoring: + λ·VAL-proxy beta (rewards positive
    # value exposure — attacks the measured −0.11 VAL short at selection)
    def eff(t: str) -> float:
        e = scores[t] + (persistence_margin if t in incumbents else 0.0)
        if factor_betas is not None and factor_lambda > 0:
            e += factor_lambda * factor_betas.get(t, 0.0)
        return e
    elig = sorted(
        (t for t in scores
         if data.sleeve_of.get(t) in pool and _available(data, t, i)),
        key=lambda t: -eff(t))
    picks = elig[:n]
    if value_slots > 0:
        have = sum(1 for t in picks if t in VALUE_TILTS)
        need = value_slots - have
        if need > 0:
            value_cands = [t for t in elig if t in VALUE_TILTS
                           and t not in picks][:need]
            # replace the lowest-scored non-value picks
            for v in value_cands:
                drop = next((t for t in reversed(picks)
                             if t not in VALUE_TILTS), None)
                if drop is None:
                    break
                picks[picks.index(drop)] = v
            picks.sort(key=lambda t: -scores[t])
    if dedup_corr and dedup_corr > 0.0 and len(picks) > 1:   # drop near-duplicate twins
        picks = _dedup_tilts(picks, elig, scores, data, i,
                             dedup_corr, dedup_window, dedup_prefer_drop)
    return picks


SYNTH_TREND_BASKET = ("TLT", "GLD", "DBC")   # what DBMF replicates, long-only
                                              # (dollar leg omitted: UUP not in panel)


def _synth_trend(data: AlphaData, i: int, mass: float) -> dict[str, float]:
    """Pre-inception convexity proxy: equal thirds across basket members with
    positive 12-1 momentum; flat thirds → BIL. Deterministic, PIT."""
    out: dict[str, float] = {}
    per = mass / len(SYNTH_TREND_BASKET)
    flat = 0.0
    for t in SYNTH_TREND_BASKET:
        px = data.prices.get(t)
        if (px is None or i < 252 or np.isnan(px[i - 21]) or np.isnan(px[i - 252])
                or px[i - 252] <= 0 or not _available(data, t, i)):
            flat += per
            continue
        if px[i - 21] / px[i - 252] - 1.0 > 0:
            out[t] = out.get(t, 0.0) + per
        else:
            flat += per
    if flat > 1e-9 and _available(data, "BIL", i):
        out["BIL"] = out.get("BIL", 0.0) + flat
    return out


def _sleeve_targets(data: AlphaData, i: int, mcfg: dict,
                    params: Mapping[str, float],
                    eq_scale: float,
                    scores_cache: Mapping[int, Mapping[str, float]] | None = None,
                    tilt_pool: tuple[str, ...] = TILT_SLEEVES,
                    n_tilts: int = N_TILTS,
                    value_slots: int = 0,
                    synth_trend: bool = False,
                    incumbents: tuple[str, ...] = (),
                    persistence_margin: float = 0.0,
                    factor_betas: Mapping[str, float] | None = None,
                    factor_lambda: float = 0.0,
                    convexity: Mapping[str, float] | None = None,
                    cx_gate: float = 1.0,
                    lever_map: Mapping[str, str] | None = None,
                    lever_on: bool = False,
                    dedup_corr: float = 0.0,
                    dedup_prefer_drop: frozenset = frozenset(),
                    return_sleeves: bool = False,
                    ):
    """Target weights + the chosen tilts as of day i (close).

    cx_gate (COT crowding gate, Phase 2b): per-day scale on the convexity
    sleeve — when speculative positioning across the headline futures is at
    crowded extremes, the convexity payoff is thinner and the sleeve haircut
    folds into duration (the same fallback as pre-inception mass)."""
    w_eq = params["w_equity"] * eq_scale
    w_cx = params["w_convexity"] * cx_gate
    # convexity members enter at inception; missing mass folds into duration
    # (or, with synth_trend, into the 12-1 trend proxy basket)
    cx_avail = {t: w for t, w in (convexity or CONVEXITY).items() if _available(data, t, i)}
    cx_scale = sum(cx_avail.values())
    cx = ({t: w_cx * w / cx_scale for t, w in cx_avail.items()}
          if cx_scale > 0 else {})
    w_cx_eff = sum(cx.values())
    if synth_trend and w_cx - w_cx_eff > 1e-6:
        for t, w in _synth_trend(data, i, w_cx - w_cx_eff).items():
            cx[t] = cx.get(t, 0.0) + w
        w_cx_eff = sum(cx.values())
    w_dur = 1.0 - w_eq - w_cx_eff            # duration absorbs brake + fold mass

    # duration mix by tags (read regime tags from the panel? panel stores
    # primary only — tags via a light re-read are not worth it; v1 keys the
    # mix off the PRIMARY: stress/RISK_OFF lean long-duration, else neutral)
    primary = data.regime[i]
    if primary in ("RISK_OFF", "LIQUIDITY_STRESS"):
        dur_mix = DURATION_RALLY_MIX
    elif primary == "RECOVERY":
        dur_mix = INFLATION_MIX
    else:
        dur_mix = DURATION_NEUTRAL
    dur = {t: w_dur * w for t, w in dur_mix.items() if _available(data, t, i)}
    short = w_dur - sum(dur.values())
    if short > 1e-9 and _available(data, "BIL", i):
        dur["BIL"] = dur.get("BIL", 0.0) + short

    # equity sleeve: base + IC tilt (cache-served in search mode)
    tilt_frac = params["tilt_frac"]
    eq: dict[str, float] = {EQUITY_BASE: w_eq * (1.0 - tilt_frac)}
    if scores_cache is not None:
        tilt_cands = _select_tilts(data, i, scores_cache.get(i, {}),
                                   tilt_pool, n_tilts, value_slots,
                                   incumbents, persistence_margin,
                                   factor_betas, factor_lambda,
                                   dedup_corr=dedup_corr, dedup_prefer_drop=dedup_prefer_drop)
    else:
        scores, _ = _score_date(data, i, mcfg)
        tilt_cands = _select_tilts(data, i, scores, tilt_pool, n_tilts,
                                   value_slots, incumbents, persistence_margin,
                                   factor_betas, factor_lambda,
                                   dedup_corr=dedup_corr, dedup_prefer_drop=dedup_prefer_drop)
    if tilt_cands:
        per = w_eq * tilt_frac / len(tilt_cands)
        for t in tilt_cands:
            # LEVERED-TILT GATE (Phase 2b ablation): when the gate is open,
            # a selected tilt holds its 2× version at the SAME weight —
            # selection + persistence stay on the UNDERLYING; only the
            # instrument swaps (reset-compounding favors trends, which is
            # when the gate opens).
            inst = t
            if lever_on and lever_map and t in lever_map                     and _available(data, lever_map[t], i):
                inst = lever_map[t]
            eq[inst] = eq.get(inst, 0.0) + per
    else:
        eq[EQUITY_BASE] += w_eq * tilt_frac

    out: dict[str, float] = {}
    for part in (eq, cx, dur):
        for t, w in part.items():
            out[t] = out.get(t, 0.0) + w
    merged = {t: round(w, 5) for t, w in out.items() if w > 1e-4}
    if return_sleeves:
        # raw per-sleeve weights (pre-merge) for opt-in attribution; a ticker may
        # appear in two sleeves (e.g. BIL in duration + synth-convexity) — kept
        # separate so each sleeve's contribution is attributed to it.
        sleeves = {name: {t: round(w, 5) for t, w in d.items() if w > 1e-4}
                   for name, d in (("equity", eq), ("convexity", cx), ("duration", dur))}
        return merged, tilt_cands, sleeves
    return merged, tilt_cands


def simulate_convex(data: AlphaData, mcfg: dict, *,
                    params: Mapping[str, float] | None = None,
                    brake: bool = True,
                    brake_cfg: Mapping[str, Any] | None = None,
                    slippage_bps: float = 5.0,
                    start_idx: int | None = None,
                    end_idx: int | None = None,
                    scores_cache: Mapping[int, Mapping[str, float]] | None = None,
                    tilt_pool: tuple[str, ...] = TILT_SLEEVES,
                    n_tilts: int = N_TILTS,
                    value_slots: int = 0,
                    synth_trend: bool = False,
                    persistence_margin: float = 0.0,
                    factor_betas_cache: Mapping[int, Mapping[str, float]] | None = None,
                    factor_lambda: float = 0.0,
                    equity_adj: np.ndarray | None = None,
                    collect_returns: bool = True,
                    convexity: Mapping[str, float] | None = None,
                    convexity_gate: "np.ndarray | None" = None,
                    lever_map: Mapping[str, str] | None = None,
                    lever_gate: "np.ndarray | None" = None,
                    dedup_corr: float = 0.0,
                    dedup_prefer_drop: frozenset = frozenset(),
                    collect_attribution: bool = False) -> ConvexResult:
    """brake_cfg (v2 variants, all default-off → v1 behavior):
      semivol: bool        — brake on downside semivol×√2 instead of total vol
      dual_horizon: bool   — vol = max(10d, 21d)
      release_rate: float  — proportional re-risk (None → +0.15/wk step)
      credit_confirm: float — BAA−AAA 21d widening (pct pts) that also
                              triggers the stress cap (first Moody's use)
    equity_adj: per-day additive adjustment to w_equity (the CAPE strategic
    modulation — valuation at its native frequency; clipped to [0.30, 0.85]).
    """
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    n = len(data.days) if end_idx is None else min(end_idx, len(data.days))
    if start_idx is None:
        start_idx = max(data.first_usable.get(EQUITY_BASE, 273), 273)

    bench_rets = data.rets[data.bench]
    weights: dict[str, float] = {}
    pending_turn = 0.0
    turnover_total = 0.0
    daily: list[float] = []
    day_list: list[date] = []
    regime_rets: dict[str, list[float]] = {}
    eq_scale_prev = 1.0
    prev_tilts: tuple[str, ...] = ()
    cur_sleeves: dict[str, dict[str, float]] = {}
    sleeve_daily: dict[str, list[float]] = (
        {"equity": [], "convexity": [], "duration": [], "cost": []}
        if collect_attribution else {})

    for i in range(start_idx, n):
        if daily or weights or pending_turn:
            cost = pending_turn * slippage_bps / 1e4
            r = sum(w * (0.0 if np.isnan(data.rets[t][i]) else float(data.rets[t][i]))
                    for t, w in weights.items())
            r -= cost
            pending_turn = 0.0
            daily.append(r)
            day_list.append(data.days[i])
            regime_rets.setdefault(data.regime[i], []).append(r)
            if collect_attribution:
                for _sl in ("equity", "convexity", "duration"):
                    sleeve_daily[_sl].append(sum(
                        w * (0.0 if np.isnan(data.rets[t][i]) else float(data.rets[t][i]))
                        for t, w in cur_sleeves.get(_sl, {}).items()))
                sleeve_daily["cost"].append(-cost)

        # absolute-anchored rebalance days (fold-start independent — the tilt
        # cache and any window slice agree on which days are decision points)
        if i % REBALANCE_EVERY == 0 and i < n - 1:
            # the volatility brake (on SPY's realized vol — the sleeve's driver)
            if brake:
                bc = brake_cfg or {}

                def _rv(window: int) -> float | None:
                    win = bench_rets[max(0, i - window): i + 1]
                    win = win[~np.isnan(win)]
                    if win.size < max(8, window // 2):
                        return None
                    if bc.get("semivol"):
                        neg = np.minimum(win, 0.0)
                        return float(neg.std() * np.sqrt(252) * np.sqrt(2))
                    return float(win.std() * np.sqrt(252))

                rv = _rv(21)
                if bc.get("dual_horizon"):
                    rv10 = _rv(10)
                    if rv10 is not None:
                        rv = max(rv or 0.0, rv10)
                scale = min(1.0, p["vol_target"] / rv) if rv and rv > 0 else 1.0
                stress = data.regime[i] == "LIQUIDITY_STRESS"
                cc = bc.get("credit_confirm")
                if cc is not None and data.credit_spread is not None and i >= 21:
                    s_now, s_then = data.credit_spread[i], data.credit_spread[i - 21]
                    if not (np.isnan(s_now) or np.isnan(s_then))                             and (s_now - s_then) > cc:
                        stress = True
                if stress:
                    scale = min(scale, p["stress_eq_scale_cap"])
                # re-risking: proportional when configured, else the v1 step
                if scale > eq_scale_prev:
                    rr = bc.get("release_rate")
                    if rr is not None:
                        scale = eq_scale_prev + rr * (scale - eq_scale_prev)
                    else:
                        scale = min(scale, eq_scale_prev + BRAKE_RELEASE_STEP)
                # deadband: ignore sub-threshold scale wiggles (they defeat the
                # band governor and drive turnover ~10.5x/yr) — large moves
                # (real de-risking) always pass
                db = bc.get("deadband")
                if db is not None and abs(scale - eq_scale_prev) < db:
                    scale = eq_scale_prev
                eq_scale_prev = scale
            else:
                scale = 1.0

            p_day = p
            if equity_adj is not None and not np.isnan(equity_adj[i]):
                p_day = dict(p)
                p_day["w_equity"] = float(np.clip(
                    p["w_equity"] + equity_adj[i], 0.30, 0.85))
            fb = (factor_betas_cache.get(i) if factor_betas_cache is not None
                  else None)
            _st = _sleeve_targets(data, i, mcfg, p_day, scale,
                                  scores_cache, tilt_pool, n_tilts,
                                  value_slots, synth_trend,
                                  prev_tilts, persistence_margin,
                                  fb, factor_lambda,
                                  convexity=convexity,
                                  cx_gate=(float(convexity_gate[i])
                                           if convexity_gate is not None else 1.0),
                                  lever_map=lever_map,
                                  lever_on=(bool(lever_gate[i])
                                            if lever_gate is not None else False),
                                  dedup_corr=dedup_corr,
                                  dedup_prefer_drop=dedup_prefer_drop,
                                  return_sleeves=collect_attribution)
            if collect_attribution:
                tgt, chosen, new_sleeves = _st
            else:
                tgt, chosen = _st; new_sleeves = None
            prev_tilts = tuple(chosen)
            # band rebalance: trade only if any instrument drifted enough,
            # or this is the first allocation / the brake moved
            drifted = (not weights) or any(
                abs(tgt.get(t, 0.0) - weights.get(t, 0.0))
                > BAND_REL * max(tgt.get(t, 0.0), weights.get(t, 0.0), 1e-9)
                for t in set(tgt) | set(weights))
            if drifted:
                turn = sum(abs(tgt.get(t, 0.0) - weights.get(t, 0.0))
                           for t in set(tgt) | set(weights))
                pending_turn = turn
                turnover_total += turn
                weights = tgt
                if collect_attribution:
                    cur_sleeves = new_sleeves

    m = perf_metrics(daily)
    yrs = max(len(daily) / 252.0, 1e-9)
    return ConvexResult(
        name="convex_core" if brake else "convex_core_no_brake",
        metrics=m, calmar=_calmar(m),
        max_recovery_days=_max_recovery_days(daily),
        annual_turnover=round(turnover_total / yrs, 3),
        daily_returns=daily if collect_returns else [],
        dates=day_list if collect_returns else [],
        regime_metrics={k: perf_metrics(v) | {"days": len(v)}
                        for k, v in regime_rets.items()},
        stress_windows={k: _window_return(day_list, daily, s, e)
                        for k, (s, e) in STRESS_WINDOWS.items()},
        sleeve_daily=sleeve_daily)


def simulate_benchmark(data: AlphaData, kind: str, *,
                       slippage_bps: float = 5.0,
                       start_idx: int | None = None) -> ConvexResult:
    """SPY buy-and-hold or 60/40 SPY/IEF (monthly rebalance) on the same
    calendar + cost model."""
    n = len(data.days)
    if start_idx is None:
        start_idx = max(data.first_usable.get(EQUITY_BASE, 273), 273)
    daily: list[float] = []
    day_list: list[date] = []
    regime_rets: dict[str, list[float]] = {}
    turnover_total = 0.0
    pending_turn = 0.0
    weights: dict[str, float] = {}
    month = None

    for i in range(start_idx, n):
        if daily or weights or pending_turn:
            r = sum(w * (0.0 if np.isnan(data.rets[t][i]) else float(data.rets[t][i]))
                    for t, w in weights.items())
            r -= pending_turn * slippage_bps / 1e4
            pending_turn = 0.0
            daily.append(r)
            day_list.append(data.days[i])
            regime_rets.setdefault(data.regime[i], []).append(r)
        if kind == "spy":
            if not weights:
                weights = {"SPY": 1.0}
                pending_turn = 1.0
                turnover_total += 1.0
        elif kind == "60_40":
            if data.days[i].month != month:
                month = data.days[i].month
                tgt = {"SPY": 0.60, "IEF": 0.40}
                turn = sum(abs(tgt.get(t, 0.0) - weights.get(t, 0.0))
                           for t in set(tgt) | set(weights))
                pending_turn = turn
                turnover_total += turn
                weights = tgt
        else:
            raise ValueError(kind)

    m = perf_metrics(daily)
    yrs = max(len(daily) / 252.0, 1e-9)
    return ConvexResult(
        name=kind, metrics=m, calmar=_calmar(m),
        max_recovery_days=_max_recovery_days(daily),
        annual_turnover=round(turnover_total / yrs, 3),
        daily_returns=daily,
        dates=day_list,
        regime_metrics={k: perf_metrics(v) | {"days": len(v)}
                        for k, v in regime_rets.items()},
        stress_windows={k: _window_return(day_list, daily, s, e)
                        for k, (s, e) in STRESS_WINDOWS.items()})
