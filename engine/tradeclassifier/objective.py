"""Base §15.3 — the walk-forward objective.

The scalar form (directly usable per parameter set inside a fold):

    objective = CAGR + 0.50*Sharpe + 0.25*Sortino − 0.75*|MaxDD|
                − 0.10*annual_turnover − 0.10*parameter_instability
                − 0.10*regime_instability

The rank-based form (§15.3 primary) needs the candidate population; provided
as `rank_objective(metrics_list)`.
"""

from __future__ import annotations

import statistics
from typing import Mapping, Sequence


def perf_metrics(daily_returns: Sequence[float], *,
                 periods_per_year: int = 252) -> dict[str, float]:
    if not daily_returns:
        return {"cagr": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0,
                "ann_vol": 0.0}
    n = len(daily_returns)
    wealth, peak, max_dd = 1.0, 1.0, 0.0
    for r in daily_returns:
        wealth *= (1.0 + r)
        peak = max(peak, wealth)
        max_dd = min(max_dd, wealth / peak - 1.0)
    yrs = n / periods_per_year
    cagr = wealth ** (1.0 / yrs) - 1.0 if yrs > 0 and wealth > 0 else -1.0
    mu = statistics.fmean(daily_returns)
    sd = statistics.pstdev(daily_returns)
    downside = [r for r in daily_returns if r < 0]
    dsd = statistics.pstdev(downside) if len(downside) > 1 else 0.0
    sharpe = (mu / sd) * (periods_per_year ** 0.5) if sd > 0 else 0.0
    sortino = (mu / dsd) * (periods_per_year ** 0.5) if dsd > 0 else 0.0
    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino,
            "max_drawdown": max_dd, "ann_vol": sd * (periods_per_year ** 0.5)}


def scalar_objective(m: Mapping[str, float], *, annual_turnover: float = 0.0,
                     parameter_instability: float = 0.0,
                     regime_instability: float = 0.0) -> float:
    return (m["cagr"]
            + 0.50 * m["sharpe"]
            + 0.25 * m["sortino"]
            - 0.75 * abs(m["max_drawdown"])
            - 0.10 * annual_turnover
            - 0.10 * parameter_instability
            - 0.10 * regime_instability)


def _ranks(vals: Sequence[float], reverse: bool = False) -> list[float]:
    """Fractional ranks in [0,1]; 1 = best."""
    order = sorted(range(len(vals)), key=lambda i: vals[i], reverse=not reverse)
    out = [0.0] * len(vals)
    denom = max(len(vals) - 1, 1)
    for rank, idx in enumerate(order):
        out[idx] = 1.0 - rank / denom
    return out


def rank_objective(candidates: Sequence[Mapping[str, float]]) -> list[float]:
    """§15.3 recommended ranking objective over a candidate population. Each
    candidate dict carries: cagr, sharpe, sortino, max_drawdown,
    annual_turnover, parameter_stability, regime_consistency."""
    if not candidates:
        return []
    g = lambda k: [float(c.get(k, 0.0)) for c in candidates]
    ret_r = _ranks(g("cagr"))
    sharpe_r = _ranks(g("sharpe"))
    sortino_r = _ranks(g("sortino"))
    dd_r = _ranks([abs(v) for v in g("max_drawdown")], reverse=True)   # small = good
    to_r = _ranks(g("annual_turnover"), reverse=True)
    stab_r = _ranks(g("parameter_stability"))
    reg_r = _ranks(g("regime_consistency"))
    return [0.30 * ret_r[i] + 0.25 * sharpe_r[i] + 0.20 * sortino_r[i]
            + 0.10 * dd_r[i] + 0.05 * to_r[i] + 0.05 * stab_r[i]
            + 0.05 * reg_r[i]
            for i in range(len(candidates))]
