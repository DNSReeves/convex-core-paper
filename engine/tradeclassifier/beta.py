"""Beta estimation + risk analytics for the alpha-beta model (design spec §9).

All inputs are trailing daily returns from Tier-A adjusted closes (vintage
disclosure inherited via reports.py). numpy admitted per the confirmed defaults.

- raw beta: 0.5·OLS(63d) + 0.5·OLS(252d) vs the benchmark
- shrunk beta: (1−s)·raw + s·sleeve prior (Vasicek-style, s=0.30 default)
- stress beta: OLS restricted to benchmark ≤ −1% days, trailing 2y; needs
  ≥ min_stress_days observations else None (degraded, reported — never guessed)
- capture ratios (252d), correlation stability (std of quarterly 63d corrs)
- rolling alpha: annualized mean daily CAPM residual (252d) — feature input
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def daily_returns(adj: list[float]) -> np.ndarray:
    a = np.asarray([x for x in adj if x is not None], dtype=float)
    if a.size < 2:
        return np.empty(0)
    return a[1:] / a[:-1] - 1.0


def aligned_returns(etf_pairs: list[tuple], bench_pairs: list[tuple]
                    ) -> tuple[np.ndarray, np.ndarray]:
    """DATE-ALIGNED daily returns (inner join on date, then diff).

    Positional tail-alignment is wrong on real data: missing adjusted-close
    days drift the two tails out of phase and beta collapses toward zero
    (caught live 2026-06-11 — VTI showed beta 0.29, USO −1.20)."""
    be = {d: v for d, v in bench_pairs if v is not None}
    common = [(d, v, be[d]) for d, v in etf_pairs
              if v is not None and d in be]
    if len(common) < 3:
        return np.empty(0), np.empty(0)
    common.sort(key=lambda x: x[0])
    e = np.asarray([v for _, v, _ in common], dtype=float)
    b = np.asarray([w for _, _, w in common], dtype=float)
    return e[1:] / e[:-1] - 1.0, b[1:] / b[:-1] - 1.0


def _ols_beta(etf: np.ndarray, bench: np.ndarray) -> float | None:
    if etf.size < 2 or bench.size < 2:
        return None
    var = bench.var()
    if var <= 0:
        return None
    return float(np.cov(etf, bench, bias=True)[0, 1] / var)


def _aligned_tail(etf: np.ndarray, bench: np.ndarray, n: int
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    m = min(etf.size, bench.size)
    if m < n:
        return None
    return etf[-n:], bench[-n:]


@dataclass
class BetaBlock:
    raw: float | None            # blended 63/252 OLS; None if history too short
    shrunk: float                # always defined (falls back to the prior)
    prior: float
    beta_source: str             # "blend" | "short_only" | "prior"
    stress: float | None         # None when too few stress days (degraded)
    stress_days: int
    rolling_alpha_252: float | None   # annualized CAPM residual
    up_capture: float | None
    down_capture: float | None
    corr_stability: float | None      # lower = steadier relationship


def _beta_se(etf: np.ndarray, bench: np.ndarray, beta: float) -> float | None:
    """Standard error of the OLS beta: se² = var(resid) / (n · var(bench))."""
    n = etf.size
    if n < 30 or bench.var() <= 0:
        return None
    resid = etf - beta * bench
    return float(np.sqrt(resid.var() / (n * bench.var())))


def estimate_beta(etf_rets: np.ndarray, bench_rets: np.ndarray, *,
                  prior: float, rf_daily: float = 0.0,
                  short_window: int = 63, long_window: int = 252,
                  short_weight: float = 0.5, shrink: float = 0.30,
                  shrink_mode: str = "adaptive", tau: float = 0.25,
                  stress_threshold: float = -0.01,
                  stress_window: int = 504, min_stress_days: int = 15
                  ) -> BetaBlock:
    """shrink_mode="adaptive" (default, Phase C): proper Vasicek — the shrink
    weight is se²(raw)/(se²+τ²), so a well-estimated daily 252d beta barely
    shrinks while a noisy/short one leans on the sleeve prior. The fixed-0.30
    mode (Phase A/B) systematically biased estimates toward priors and left
    realized portfolio beta UNDER target (ladder evidence: in estimated band
    84–96% of rebalances, realized 0.05–0.35 below)."""
    pair_s = _aligned_tail(etf_rets, bench_rets, short_window)
    pair_l = _aligned_tail(etf_rets, bench_rets, long_window)

    raw: float | None
    se: float | None = None
    if pair_l is not None and pair_s is not None:
        b_s, b_l = _ols_beta(*pair_s), _ols_beta(*pair_l)
        raw = (short_weight * b_s + (1 - short_weight) * b_l
               if b_s is not None and b_l is not None else None)
        if raw is not None and b_l is not None:
            se = _beta_se(*pair_l, b_l)
        source = "blend"
    elif pair_s is not None:
        raw = _ols_beta(*pair_s)
        if raw is not None:
            se = _beta_se(*pair_s, raw)
        source = "short_only"
    else:
        raw, source = None, "prior"

    if raw is None:
        shrunk, source = prior, "prior"
    elif shrink_mode == "adaptive" and se is not None:
        w = se ** 2 / (se ** 2 + tau ** 2)
        shrunk = (1 - w) * raw + w * prior
    else:
        shrunk = (1 - shrink) * raw + shrink * prior

    # stress beta — the crisis-alpha population
    stress, n_stress = None, 0
    pair_w = _aligned_tail(etf_rets, bench_rets, min(stress_window,
                                                     min(etf_rets.size, bench_rets.size)))
    if pair_w is not None:
        e, b = pair_w
        mask = b <= stress_threshold
        n_stress = int(mask.sum())
        if n_stress >= min_stress_days:
            stress = _ols_beta(e[mask], b[mask])

    # rolling alpha + captures over 252d
    alpha_ann = up_cap = down_cap = None
    if pair_l is not None:
        e, b = pair_l
        beta_for_resid = shrunk
        resid = (e - rf_daily) - beta_for_resid * (b - rf_daily)
        alpha_ann = float(resid.mean() * 252)
        up, down = b > 0, b < 0
        if up.sum() >= 20 and float(b[up].mean()) != 0:
            up_cap = float(e[up].mean() / b[up].mean())
        if down.sum() >= 20 and float(b[down].mean()) != 0:
            down_cap = float(e[down].mean() / b[down].mean())

    # correlation stability: std of the last four quarterly 63d correlations
    corr_stab = None
    pair_y = _aligned_tail(etf_rets, bench_rets, 252)
    if pair_y is not None:
        e, b = pair_y
        corrs = []
        for q in range(4):
            es, bs = e[q * 63:(q + 1) * 63], b[q * 63:(q + 1) * 63]
            if es.std() > 0 and bs.std() > 0:
                corrs.append(float(np.corrcoef(es, bs)[0, 1]))
        if len(corrs) >= 3:
            corr_stab = float(np.std(corrs))

    return BetaBlock(raw=raw if raw is None else round(raw, 4),
                     shrunk=round(shrunk, 4), prior=prior, beta_source=source,
                     stress=stress if stress is None else round(stress, 4),
                     stress_days=n_stress,
                     rolling_alpha_252=None if alpha_ann is None else round(alpha_ann, 5),
                     up_capture=None if up_cap is None else round(up_cap, 3),
                     down_capture=None if down_cap is None else round(down_cap, 3),
                     corr_stability=None if corr_stab is None else round(corr_stab, 4))
