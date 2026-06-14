"""Alpha-beta model Phase B — the beta-ladder walk-forward backtest
(design spec §12).

v1 has NO fitted parameters (fixed regime weight templates), so the whole
simulation is out-of-sample by construction; the score→bps calibration and IC
are computed expanding-window for validation, never fed back into allocation.

Architecture: one precompute pass builds aligned price/return matrices + the
per-day regime series (cached engine); alpha scoring + optimization run only
on WEEKLY rebalance dates (~1/5 of days); daily accounting applies the §4.4
shift discipline (weights decided at close T earn returns from T+1) with
slippage charged on the day a trade's return first accrues — same conventions
as backtest.py, pinned by the same style of tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Mapping

import numpy as np

from .alpha import FEATURES, alpha_features, information_coefficient, score_universe, zrank_within_date
from .beta import estimate_beta
from .features import rsi_series
from .loaders import Warehouse, _parse_date
from .objective import perf_metrics
from .optimizer import Candidate, optimize
from .regime import RegimeEngine, RegimeInputCache


@dataclass
class AlphaData:
    """Aligned panel: index = trading days (SPY calendar)."""
    days: list[date]
    prices: dict[str, np.ndarray]        # adjusted close, nan where absent
    rets: dict[str, np.ndarray]          # daily returns, nan where absent
    first_usable: dict[str, int]         # first index with enough history
    bench: str
    rf_daily: np.ndarray
    regime: list[str]                    # primary per day (hysteresis-confirmed)
    sleeve_of: dict[str, str]
    prior_of: dict[str, float]
    wmax_of: dict[str, float]
    credit_spread: np.ndarray | None = None   # BAA−AAA (pct pts), PIT-ffilled


def precompute_alpha_data(wh: Warehouse, ucfg: dict, start: str | date,
                          end: str | date, *, confirm_days: int = 3,
                          min_history: int = 273,
                          progress: Callable[[str], None] | None = None
                          ) -> AlphaData:
    start, end = _parse_date(start), _parse_date(end)
    bench = ucfg["benchmark"]

    sleeve_of, prior_of, wmax_of = {}, {}, {}
    for sleeve, spec in ucfg["sleeves"].items():
        for t in spec["tickers"]:
            sleeve_of[t] = sleeve
            prior_of[t] = float(spec["beta_prior"])
            wmax_of[t] = float(spec["w_max"])
    tickers = sorted(sleeve_of)

    # calendar = SPY trading days in [start, end]
    with wh._connect() as con:
        rows = con.execute(
            "SELECT date FROM daily_prices WHERE ticker='SPY' AND date>=? AND "
            "date<=? ORDER BY date", (start.isoformat(), end.isoformat())).fetchall()
    days = [_parse_date(r["date"]) for r in rows]
    idx = {d: i for i, d in enumerate(days)}
    n = len(days)

    prices: dict[str, np.ndarray] = {}
    rets: dict[str, np.ndarray] = {}
    first_usable: dict[str, int] = {}
    for t in set(tickers) | {bench}:
        arr = np.full(n, np.nan)
        for r in wh.load_prices_adjusted(t, end):
            i = idx.get(_parse_date(r["date"]))
            if i is not None:
                arr[i] = r["adjusted_close"]
        prices[t] = arr
        rr = np.full(n, np.nan)
        valid = ~np.isnan(arr)
        vi = np.where(valid)[0]
        if vi.size >= 2:
            rr[vi[1:]] = arr[vi[1:]] / arr[vi[:-1]] - 1.0
        rets[t] = rr
        first_usable[t] = int(vi[0] + min_history) if vi.size else n + 1

    # risk-free per day (DGS3MO, forward-filled)
    rf = np.zeros(n)
    pts = wh.load_series("DGS3MO", end)
    j = 0
    last = 0.0
    pts_sorted = sorted(pts, key=lambda p: p.available_to_trade)
    for i, d in enumerate(days):
        while j < len(pts_sorted) and pts_sorted[j].available_to_trade <= d:
            last = pts_sorted[j].value
            j += 1
        rf[i] = last / 100.0 / 252.0

    # BAA−AAA credit spread (Moody's, 1990+) — brake-v2 confirmation input
    credit = np.full(n, np.nan)
    try:
        baa = {p_.available_to_trade: p_.value for p_ in wh.load_series("DBAA", end)}
        aaa = {p_.available_to_trade: p_.value for p_ in wh.load_series("DAAA", end)}
        last = np.nan
        b_keys, a_keys = sorted(baa), sorted(aaa)
        bi = ai = 0
        b_last = a_last = None
        for i, d in enumerate(days):
            while bi < len(b_keys) and b_keys[bi] <= d:
                b_last = baa[b_keys[bi]]; bi += 1
            while ai < len(a_keys) and a_keys[ai] <= d:
                a_last = aaa[a_keys[ai]]; ai += 1
            if b_last is not None and a_last is not None:
                credit[i] = b_last - a_last
    except Exception:
        pass    # omit-never-fabricate: missing series → brake confirm degrades off

    eng = RegimeEngine(wh, confirm_days=confirm_days,
                       cache=RegimeInputCache(wh, end))
    regime: list[str] = []
    for i, d in enumerate(days):
        if progress and i % 250 == 0:
            progress(f"regime {d} ({i+1}/{n})")
        regime.append(eng.read(d).primary)

    return AlphaData(days=days, prices=prices, rets=rets,
                     first_usable=first_usable, bench=bench, rf_daily=rf,
                     regime=regime, sleeve_of=sleeve_of, prior_of=prior_of,
                     wmax_of=wmax_of, credit_spread=credit)


def _score_date(data: AlphaData, i: int, mcfg: dict
                ) -> tuple[dict[str, Any], dict[str, Candidate]]:
    """Alpha scores + optimizer candidates as of day index i (close)."""
    bench_px = data.prices[data.bench][: i + 1]
    bcfg = mcfg["beta"]
    feature_table: dict[str, dict] = {}
    cands: dict[str, Candidate] = {}
    blocks: dict[str, Any] = {}
    for t, sleeve in data.sleeve_of.items():
        if i < data.first_usable.get(t, 10 ** 9):
            continue
        px = data.prices[t][: i + 1]
        valid = ~(np.isnan(px) | np.isnan(bench_px))
        e_px, b_px = px[valid], bench_px[valid]
        if e_px.size < 64:
            continue
        e_rets = e_px[1:] / e_px[:-1] - 1.0
        b_rets = b_px[1:] / b_px[:-1] - 1.0
        bb = estimate_beta(
            e_rets, b_rets, prior=data.prior_of[t],
            rf_daily=float(data.rf_daily[i]),
            short_window=int(bcfg["raw_blend"]["short_window"]),
            long_window=int(bcfg["raw_blend"]["long_window"]),
            short_weight=float(bcfg["raw_blend"]["short_weight"]),
            shrink=float(bcfg["shrink_to_prior"]),
            shrink_mode=str(bcfg.get("shrink_mode", "adaptive")),
            tau=float(bcfg.get("tau", 0.25)),
            stress_threshold=float(bcfg["stress"]["bench_ret_threshold"]),
            stress_window=int(bcfg["stress"]["window_sessions"]),
            min_stress_days=int(bcfg["stress"]["min_stress_days"]))
        blocks[t] = bb
        clean = px[~np.isnan(px)].tolist()
        rsis = rsi_series(clean, 14)
        rs_63 = (float(np.prod(1 + e_rets[-63:]) - np.prod(1 + b_rets[-63:]))
                 if e_rets.size >= 63 else None)
        feature_table[t] = alpha_features(clean, rsis[-1] if rsis else None,
                                          bb.rolling_alpha_252,
                                          bb.down_capture, rs_63)
    zr = zrank_within_date(feature_table, clip=float(mcfg["optimizer"]["z_clip"]))
    scores = score_universe(zr, data.regime[i], mcfg["regime_weight_templates"])
    for t, s in scores.items():
        if s.score is None:
            continue
        cands[t] = Candidate(ticker=t, score=s.score, beta=blocks[t].shrunk,
                             stress_beta=blocks[t].stress,
                             sleeve=data.sleeve_of[t], w_max=data.wmax_of[t])
    return {t: s.score for t, s in scores.items() if s.score is not None}, cands


@dataclass
class AlphaSimResult:
    preset: str
    band: tuple[float, float]
    metrics: dict[str, float]
    realized_beta: float | None
    realized_alpha_ann: float | None
    tracking_error: float | None
    information_ratio: float | None          # vs raw SPY (yardstick artifact <β=1)
    ir_mandate: float | None                 # vs rf + mid·(bench−rf) — the honest IR
    mean_est_beta_at_rebal: float | None     # tracking diagnostic vs realized_beta
    up_capture: float | None
    down_capture: float | None
    annual_turnover: float
    n_rebalances: int
    pct_days_in_band_est: float          # est beta in band at rebalances
    mean_ic_21d: float | None
    ic_t_stat: float | None
    daily_returns: list[float] = field(default_factory=list)
    regime_returns: dict[str, dict] = field(default_factory=dict)


def simulate_alpha(data: AlphaData, mcfg: dict, *, preset: str,
                   band: tuple[float, float], sleeve_caps: Mapping[str, float],
                   cash_ticker: str = "BIL",
                   start_idx: int | None = None,
                   rebalance_every: int = 5, slippage_bps: float = 5.0,
                   progress: Callable[[str], None] | None = None
                   ) -> AlphaSimResult:
    n = len(data.days)
    if start_idx is None:
        # start once the benchmark itself is usable + a year of regime warmup
        start_idx = max(data.first_usable.get(data.bench, 273), 273)
    weights: dict[str, float] = {}
    pending_turn = 0.0
    daily: list[float] = []
    bench_daily: list[float] = []
    rf_used: list[float] = []
    regime_rets: dict[str, list[float]] = {}
    turnover_total = 0.0
    in_band_count, rebal_count = 0, 0
    est_betas: list[float] = []
    ic_obs: list[tuple[int, dict[str, float], dict[str, float]]] = []  # (i, scores, betas)

    for i in range(start_idx, n):
        # 1. accounting: yesterday's weights earn today's returns; yesterday's
        # trade cost lands today (§4.4 + day-0 convention from backtest.py)
        if daily or weights or pending_turn:
            r = 0.0
            for t, w in weights.items():
                rt = data.rets[t][i]
                r += w * (0.0 if np.isnan(rt) else float(rt))
            r -= pending_turn * slippage_bps / 1e4
            pending_turn = 0.0
            daily.append(r)
            br = data.rets[data.bench][i]
            bench_daily.append(0.0 if np.isnan(br) else float(br))
            rf_used.append(float(data.rf_daily[i]))
            regime_rets.setdefault(data.regime[i], []).append(r)

        # 2. weekly rebalance at close
        if (i - start_idx) % rebalance_every == 0 and i < n - 1:
            scores, cands = _score_date(data, i, mcfg)
            if cands:
                res = optimize(
                    list(cands.values()), beta_band=band,
                    sleeve_caps=dict(sleeve_caps), cash_ticker=cash_ticker,
                    max_names=int(mcfg["optimizer"]["max_names"]),
                    min_position=float(mcfg["optimizer"]["min_position"]),
                    min_trade=float(mcfg["optimizer"]["min_trade"]),
                    stress_band_excess=float(mcfg["beta"]["stress_band_excess"]),
                    beta_aim_frac=float(mcfg["optimizer"].get("beta_aim_frac", 0.50)),
                    w_prev=weights)
                new_w = res.weights
                turn = sum(abs(new_w.get(t, 0.0) - weights.get(t, 0.0))
                           for t in set(new_w) | set(weights))
                pending_turn = turn
                turnover_total += turn
                weights = new_w
                rebal_count += 1
                in_band_count += int(res.in_band)
                est_betas.append(res.est_beta)
                betas = {t: cands[t].beta for t in cands}
                ic_obs.append((i, scores, betas))
            if progress and rebal_count % 50 == 0:
                progress(f"rebalance {rebal_count} @ {data.days[i]}")

    # ── metrics ──────────────────────────────────────────────────────────
    m = perf_metrics(daily)
    pr = np.asarray(daily)
    br = np.asarray(bench_daily)
    rfv = np.asarray(rf_used)
    realized_beta = realized_alpha = te = ir = ir_m = upc = dnc = None
    if pr.size > 60 and br.std() > 0:
        realized_beta = float(np.cov(pr, br, bias=True)[0, 1] / br.var())
        resid = (pr - rfv) - realized_beta * (br - rfv)
        realized_alpha = float(resid.mean() * 252)
        active = pr - br
        te = float(active.std() * np.sqrt(252))
        ir = float(active.mean() / active.std() * np.sqrt(252)) if active.std() > 0 else None
        # mandate-matched IR: the benchmark a β-target mandate actually owes
        mid = (band[0] + band[1]) / 2.0
        mandate = rfv + mid * (br - rfv)
        act_m = pr - mandate
        if act_m.std() > 0:
            ir_m = float(act_m.mean() / act_m.std() * np.sqrt(252))
        up, dn = br > 0, br < 0
        if up.sum() >= 20:
            upc = float(pr[up].mean() / br[up].mean())
        if dn.sum() >= 20:
            dnc = float(pr[dn].mean() / br[dn].mean())

    # ── IC: scores at rebalance i vs forward 21d CAPM residual ──────────
    ics: list[float] = []
    for i, scores, betas in ic_obs:
        j = i + 21
        if j >= n:
            continue
        fwd: dict[str, float] = {}
        for t, sc in scores.items():
            pt0, pt1 = data.prices[t][i], data.prices[t][j]
            pb0, pb1 = data.prices[data.bench][i], data.prices[data.bench][j]
            if any(np.isnan(x) for x in (pt0, pt1, pb0, pb1)):
                continue
            r_etf = pt1 / pt0 - 1.0
            r_b = pb1 / pb0 - 1.0
            fwd[t] = float(r_etf - betas.get(t, 1.0) * r_b)
        ic = information_coefficient(scores, fwd)
        if ic is not None:
            ics.append(ic)
    mean_ic = float(np.mean(ics)) if ics else None
    ic_t = (float(np.mean(ics) / (np.std(ics) / np.sqrt(len(ics))))
            if len(ics) > 10 and np.std(ics) > 0 else None)

    yrs = max(len(daily) / 252.0, 1e-9)
    return AlphaSimResult(
        preset=preset, band=band, metrics=m,
        realized_beta=None if realized_beta is None else round(realized_beta, 3),
        realized_alpha_ann=None if realized_alpha is None else round(realized_alpha, 4),
        tracking_error=None if te is None else round(te, 4),
        information_ratio=None if ir is None else round(ir, 3),
        ir_mandate=None if ir_m is None else round(ir_m, 3),
        mean_est_beta_at_rebal=(round(float(np.mean(est_betas)), 3)
                                if est_betas else None),
        up_capture=None if upc is None else round(upc, 3),
        down_capture=None if dnc is None else round(dnc, 3),
        annual_turnover=round(turnover_total / yrs, 3),
        n_rebalances=rebal_count,
        pct_days_in_band_est=round(in_band_count / rebal_count, 4) if rebal_count else 0.0,
        mean_ic_21d=None if mean_ic is None else round(mean_ic, 4),
        ic_t_stat=None if ic_t is None else round(ic_t, 2),
        daily_returns=daily,
        regime_returns={k: perf_metrics(v) | {"days": len(v)}
                        for k, v in regime_rets.items()})
