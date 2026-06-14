"""Greedy rank-and-risk allocator — v1 (design spec §10, confirmed default).

Deterministic, dependency-free, auditable: every admission/rejection/scale step
is logged. cvxpy is the flag-gated v2 behind this same interface.

Algorithm:
1. Sort eligible candidates by alpha score descending.
2. Admit greedily at min(name cap, sleeve room) up to max_names, while the
   projected portfolio beta (with cash fill at beta≈0) can still land in the
   band: stop admitting once risky beta mass reaches the band's upper edge.
3. Scale the risky book so Σw·β hits the band midpoint where possible; cash
   (BIL) absorbs the residual weight.
4. Stress-beta repair: while Σw·β_stress > target + excess, swap the worst
   stress contributor for the next-ranked candidate with materially lower
   stress beta (bounded passes; flag if unrepaired).
5. Turnover governor vs the previous portfolio: drop |Δw| < min_trade.

Returns weights + a full decision log + feasibility flags. Infeasible targets
(e.g. 1.3 beta from a defensive universe) come back flagged, never silently
missed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class Candidate:
    ticker: str
    score: float                 # alpha score (higher better)
    beta: float                  # shrunk beta
    stress_beta: float | None
    sleeve: str
    w_max: float                 # per-name cap (sleeve-level w_max)


@dataclass
class OptimizerResult:
    weights: dict[str, float]
    cash_weight: float
    cash_ticker: str
    est_beta: float
    est_stress_beta: float | None
    in_band: bool
    stress_ok: bool | None       # None = not assessable (no stress betas)
    log: list[str] = field(default_factory=list)
    turnover_skipped: list[str] = field(default_factory=list)


def _portfolio_beta(weights: Mapping[str, float],
                    betas: Mapping[str, float]) -> float:
    return sum(w * betas[t] for t, w in weights.items())


def optimize(candidates: Sequence[Candidate], *,
             beta_band: tuple[float, float],
             sleeve_caps: Mapping[str, float],
             cash_ticker: str = "BIL",
             cash_beta: float = 0.0,
             max_names: int = 25,
             min_position: float = 0.01,
             min_trade: float = 0.005,
             stress_band_excess: float = 0.15,
             beta_aim_frac: float = 0.50,
             w_prev: Mapping[str, float] | None = None) -> OptimizerResult:
    lo, hi = beta_band
    mid = (lo + hi) / 2.0
    # the working target INSIDE the band: low enough to preserve the alpha
    # tilt, high enough that mean-reverting measured betas still realize
    # in-band (Phase C calibration — operator-tunable)
    aim = lo + beta_aim_frac * (hi - lo)
    stress_limit = mid + stress_band_excess
    log: list[str] = []
    by_t = {c.ticker: c for c in candidates}
    betas = {c.ticker: c.beta for c in candidates}

    def sbeta(t: str) -> float:
        """Stress beta with a conservative fallback: unknown stress behavior
        is assumed at least as risky as normal beta (never assumed safe)."""
        s = by_t[t].stress_beta
        return s if s is not None else max(betas[t], 0.0)

    ranked = sorted((c for c in candidates if c.score is not None),
                    key=lambda c: -c.score)

    weights: dict[str, float] = {}
    sleeve_used: dict[str, float] = {}

    def name_room(c: Candidate) -> float:
        return min(c.w_max,
                   sleeve_caps.get(c.sleeve, 1.0) - sleeve_used.get(c.sleeve, 0.0))

    def admit(c: Candidate, w: float, why: str) -> None:
        weights[c.ticker] = round(w, 4)
        sleeve_used[c.sleeve] = sleeve_used.get(c.sleeve, 0.0) + w
        log.append(f"admit:{c.ticker}:w={w:.3f}:beta={c.beta:.2f}"
                   f":sbeta={sbeta(c.ticker):.2f}:score={c.score:.2f}:{why}")

    def remove(t: str, why: str) -> None:
        c = by_t[t]
        sleeve_used[c.sleeve] = sleeve_used.get(c.sleeve, 0.0) - weights[t]
        log.append(f"remove:{t}:{why}")
        del weights[t]

    def port_beta() -> float:
        return _portfolio_beta(weights, betas)

    def port_stress() -> float:
        return sum(w * sbeta(t) for t, w in weights.items())

    # ── admission: greedy by score, with BOTH beta budgets enforced ─────────
    for c in ranked:
        if len(weights) >= max_names:
            log.append(f"stop:max_names:{max_names}")
            break
        r = min(name_room(c), 1.0 - sum(weights.values()))
        if r < min_position:
            log.append(f"reject:{c.ticker}:no_room({c.sleeve})")
            continue
        # normal-beta budget: once the book reaches the midpoint, stop adding
        # high-beta names (cash fill only lowers beta)
        if port_beta() >= aim and c.beta > 0.3:
            log.append(f"reject:{c.ticker}:beta_budget(beta={c.beta:.2f})")
            continue
        # stress budget: never admit a name whose stress contribution would
        # push the book past the stress limit (USO lesson: stress beta +1.7
        # on a normal beta of -1.2 — admission must see both)
        s = sbeta(c.ticker)
        if port_stress() + r * max(s, 0.0) > stress_limit and s > 0.3:
            log.append(f"reject:{c.ticker}:stress_budget(sbeta={s:.2f})")
            continue
        admit(c, r, "rank")

    # ── repair rounds: scale-down / stress swaps / stress-aware beta lift ───
    for round_i in range(3):
        b, st = port_beta(), port_stress()
        if lo <= b <= hi and st <= stress_limit + 1e-9:
            break

        if b > aim:                                  # too hot → scale to aim
            scale = aim / b
            for t in list(weights):
                weights[t] = round(weights[t] * scale, 4)
            for s_ in sleeve_used:
                sleeve_used[s_] *= scale
            weights = {t: w for t, w in weights.items() if w >= min_position}
            log.append(f"scale:risky_book:x{scale:.3f}")

        passes = 0                                   # stress swaps
        while port_stress() > stress_limit and passes < 8:
            worst = max(weights, key=lambda t: weights[t] * sbeta(t))
            sub = next((c for c in ranked if c.ticker not in weights
                        and sbeta(c.ticker) < sbeta(worst) - 0.2
                        and name_room(c) >= min_position), None)
            if sub is None:
                log.append("FLAG:stress_unrepairable")
                break
            remove(worst, f"stress_swap_for:{sub.ticker}")
            # post-remove, 1 - sum() already includes the freed weight
            admit(sub, min(name_room(sub),
                           1.0 - sum(weights.values())), "stress_swap")
            passes += 1

        passes = 0                                   # stress-aware beta lift
        # lift aims at the band MIDPOINT, not the floor: measured
        # betas regress to the mean (selection picks high-measured-beta
        # names), so realized beta lands ~0.1-0.15 below estimate —
        # aiming mid keeps realized inside the band (Phase C ladder fix)
        while port_beta() < aim and passes < 15:
            b, st = port_beta(), port_stress()
            cash_avail = 1.0 - sum(weights.values())
            lifters = [c for c in ranked if c.ticker not in weights
                       and c.beta >= b + 0.05
                       and name_room(c) >= min_position
                       and st + min_position * max(sbeta(c.ticker), 0.0)
                       <= stress_limit + 0.02]
            lifter = max(lifters, key=lambda c: (c.score, c.beta), default=None)
            if lifter is None:
                if b >= lo:
                    break              # floor met; mid unreachable is fine
                log.append(f"FLAG:beta_lift_exhausted:b={b:.3f}<lo={lo}")
                break
            if cash_avail >= min_position:
                # size so the stress limit is respected
                s = max(sbeta(lifter.ticker), 0.0)
                w_stress_ok = ((stress_limit + 0.02 - st) / s) if s > 0 else 1.0
                w = min(name_room(lifter), cash_avail, max(w_stress_ok, 0.0))
                if w < min_position:
                    log.append(f"FLAG:beta_lift_stress_bound:b={b:.3f}")
                    break
                admit(lifter, w, "beta_lift")
            else:
                dragger = min((t for t in weights if betas[t] < b + 0.1),
                              key=lambda t: by_t[t].score, default=None)
                if dragger is None:
                    log.append(f"FLAG:beta_lift_no_dragger:b={b:.3f}")
                    break
                remove(dragger, f"beta_lift_swap_for:{lifter.ticker}")
                admit(lifter,
                      min(name_room(lifter), 1.0 - sum(weights.values())),
                      "beta_lift_swap")
            passes += 1

    weights = {t: round(w, 4) for t, w in weights.items() if w >= min_position}

    # turnover governor
    skipped: list[str] = []
    if w_prev:
        for t in list(weights):
            if abs(weights[t] - w_prev.get(t, 0.0)) < min_trade and t in w_prev:
                weights[t] = w_prev[t]
                skipped.append(t)

    cash = round(max(0.0, 1.0 - sum(weights.values())), 4)
    est_beta = round(_portfolio_beta(weights, betas) + cash * cash_beta, 4)
    known_stress = [t for t in weights if by_t[t].stress_beta is not None]
    est_stress = (round(sum(weights[t] * by_t[t].stress_beta
                            for t in known_stress), 4)
                  if known_stress else None)
    in_band = lo <= est_beta <= hi
    stress_ok = (est_stress <= stress_limit + 1e-9) if est_stress is not None else None
    if not in_band:
        log.append(f"FLAG:beta_out_of_band:est={est_beta}:band=({lo},{hi})")

    return OptimizerResult(
        weights=weights, cash_weight=cash, cash_ticker=cash_ticker,
        est_beta=est_beta, est_stress_beta=est_stress,
        in_band=in_band, stress_ok=stress_ok, log=log,
        turnover_skipped=skipped)
