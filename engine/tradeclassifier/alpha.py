"""v1 alpha forecasting — deterministic regime-conditioned rank ensemble
(design spec §8, confirmed default).

8 continuous features per ETF → z-scored WITHIN DATE across the universe
(never across time — the model's own look-ahead control #1) → weighted sum
with per-regime weight templates (config data) → alpha score.

Expected-alpha bps requires the Phase-B per-fold calibration; Phase A reports
score + rank only (omit-never-fabricate). IC tooling lives here for Phase B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

FEATURES = ("mom_12_1", "vol_adj_mom_63", "rs_63", "ma_dist_200",
            "rolling_alpha_252", "down_capture_inv", "dd_improve",
            "rsi_centered", "val_5y")


def alpha_features(adj: list[float],
                   rsi14: float | None,
                   rolling_alpha_252: float | None,
                   down_capture: float | None,
                   rs_63: float | None) -> dict[str, float | None]:
    """The 8 continuous features. Missing history → None (excluded from that
    date's z-rank; the ensemble renormalizes over available features).
    rs_63 arrives precomputed from DATE-ALIGNED returns (see beta.aligned_returns
    — positional alignment was the 2026-06-11 beta bug)."""
    c = [x for x in adj if x is not None]
    f: dict[str, float | None] = {k: None for k in FEATURES}
    # data-quality guard (2026-06-11, wide-universe Phase 2): zero/negative
    # closes (corrupt rows in some delisted funds) would divide-by-zero —
    # return all-None features so the ticker is skipped on this date
    if c and min(c[-260:]) <= 0:
        return f

    if len(c) >= 253:
        f["mom_12_1"] = c[-22] / c[-253] - 1.0          # 12-1 month momentum
    if len(c) >= 64:
        r63 = c[-1] / c[-64] - 1.0
        rets = np.diff(np.asarray(c[-64:], dtype=float)) / np.asarray(c[-64:-1], dtype=float)
        vol = float(rets.std() * np.sqrt(252))
        f["vol_adj_mom_63"] = r63 / vol if vol > 1e-9 else None
    f["rs_63"] = rs_63
    if len(c) >= 200:
        f["ma_dist_200"] = c[-1] / (sum(c[-200:]) / 200) - 1.0
    f["rolling_alpha_252"] = rolling_alpha_252
    f["down_capture_inv"] = (1.0 - down_capture) if down_capture is not None else None
    if len(c) >= 63 + 21:
        dd_now = c[-1] / max(c[-63:]) - 1.0
        past = c[:-21]
        dd_then = past[-1] / max(past[-63:]) - 1.0
        f["dd_improve"] = dd_now - dd_then
    f["rsi_centered"] = (rsi14 - 50.0) if rsi14 is not None else None
    # slow value proxy (#1b): cheap vs own 5y average scores HIGH — the
    # fundamentals-free value signal, negatively correlated with the
    # momentum block by construction (factor report: tilts shorted VAL)
    if len(c) >= 1260:
        avg5y = sum(c[-1260:]) / 1260.0
        f["val_5y"] = -(c[-1] / avg5y - 1.0)
    return f


def zrank_within_date(feature_table: Mapping[str, Mapping[str, float | None]],
                      *, clip: float = 3.0) -> dict[str, dict[str, float | None]]:
    """{ticker: {feature: value}} → same shape, z-scored per feature across
    tickers ON THIS DATE ONLY. <3 live values or zero dispersion → all None
    for that feature (degraded, never invented)."""
    tickers = list(feature_table)
    out: dict[str, dict[str, float | None]] = {t: {} for t in tickers}
    for k in FEATURES:
        vals = [(t, feature_table[t].get(k)) for t in tickers]
        live = [(t, v) for t, v in vals if v is not None]
        if len(live) < 3:
            for t in tickers:
                out[t][k] = None
            continue
        arr = np.asarray([v for _, v in live], dtype=float)
        mu, sd = float(arr.mean()), float(arr.std())
        for t, v in vals:
            if v is None or sd <= 1e-12:
                out[t][k] = None
            else:
                out[t][k] = float(np.clip((v - mu) / sd, -clip, clip))
    return out


@dataclass
class AlphaScore:
    ticker: str
    score: float | None          # weighted z-sum, ~[-3, 3]
    display: float | None        # 0-100 mapping (display only)
    features_used: int
    attribution: dict[str, float]   # feature → weight·z (exact, linear)


def score_universe(zranks: Mapping[str, Mapping[str, float | None]],
                   regime_primary: str,
                   templates: Mapping[str, Mapping[str, float]], *,
                   score_center: float = 50.0, score_scale: float = 16.7,
                   min_features: int = 4) -> dict[str, AlphaScore]:
    """Regime-conditioned linear ensemble. A ticker with fewer than
    min_features live z-ranks gets score None (insufficient evidence)."""
    w = templates.get(regime_primary) or templates["RISK_NEUTRAL"]
    out: dict[str, AlphaScore] = {}
    for t, zr in zranks.items():
        live = {k: z for k, z in zr.items() if z is not None and w.get(k, 0) > 0}
        if len(live) < min_features:
            out[t] = AlphaScore(t, None, None, len(live), {})
            continue
        wsum = sum(w[k] for k in live)
        attrib = {k: round(w[k] / wsum * z, 4) for k, z in live.items()}
        s = sum(attrib.values())
        out[t] = AlphaScore(t, round(s, 4),
                            round(score_center + score_scale * s, 1),
                            len(live), attrib)
    return out


def information_coefficient(scores: Mapping[str, float],
                            forward_residuals: Mapping[str, float]) -> float | None:
    """Daily cross-sectional Spearman IC (Phase-B validation/degradation metric)."""
    common = [t for t in scores if t in forward_residuals
              and scores[t] is not None and forward_residuals[t] is not None]
    if len(common) < 5:
        return None
    s = np.asarray([scores[t] for t in common], dtype=float)
    r = np.asarray([forward_residuals[t] for t in common], dtype=float)
    sr = np.argsort(np.argsort(s)).astype(float)
    rr = np.argsort(np.argsort(r)).astype(float)
    if sr.std() <= 0 or rr.std() <= 0:
        return None
    return float(np.corrcoef(sr, rr)[0, 1])
