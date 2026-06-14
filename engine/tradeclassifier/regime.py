"""A4 — regime engine: one primary risk state + orthogonal overlay tags.

Operator-confirmed default (2026-06-10): self-contained classifier, **Tier-P inputs
only**, no runtime coupling to mhd_scores. Structure is FINAL per the addendum:

- ``primary ∈ {RISK_ON, RISK_NEUTRAL, RISK_OFF, RECOVERY, LIQUIDITY_STRESS}``,
  mutually exclusive, fixed precedence LIQUIDITY_STRESS > RISK_OFF > RECOVERY >
  RISK_ON > RISK_NEUTRAL (stress wins; NEUTRAL is the residual).
- ``tags ⊆ {INFLATION_STRESS, DEFENSIVE_ROTATION, DURATION_RALLY, DOLLAR_STRESS,
  COMMODITY_STRENGTH}`` — independent booleans.
- Hysteresis: a primary flip requires the new state's conditions to hold
  ``regime_confirm_days`` (default 3) consecutive sessions.
- Comparison logging, not coupling: MHD regime_state + RACE regime recorded
  alongside (read-only, omit-if-absent) into out/regime_history.csv.

Numeric CONDITIONS are ⚠ PROVISIONAL (config/regime_rules.yaml) pending base
§9.1/§9.2 — SPEC_GAPS #7. Tests pin the evaluation semantics (precedence,
hysteresis/flapping, degradation), not the provisional numbers.

No VIX3M/VVIX/SKEW — no local source; those clauses simply don't exist here
(dropped per A4 item 1, degradation handles partially-blind states).
"""

from __future__ import annotations

import csv
import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml

from .loaders import Warehouse, _parse_date

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = REPO_ROOT / "config" / "regime_rules.yaml"

_CLAUSE_RE = re.compile(
    r"^\s*(\w+)\s*(==|>=|<=|>|<)\s*(True|False|-?\d+(?:\.\d+)?)\s*$"
)
_PARSE_CACHE: dict[str, tuple[str, str, Any]] = {}


def _parse_clause(clause: str) -> tuple[str, str, Any]:
    hit = _PARSE_CACHE.get(clause)
    if hit is None:
        m = _CLAUSE_RE.match(clause)
        if not m:
            raise ValueError(f"unparseable regime clause: {clause!r}")
        name, op, lit = m.groups()
        rhs: Any = {"True": True, "False": False}.get(lit)
        if rhs is None:
            rhs = float(lit)
        hit = _PARSE_CACHE[clause] = (name, op, rhs)
    return hit


def _eval_clause(clause: str, inputs: Mapping[str, Any]) -> bool | None:
    """True/False, or None when the input is unavailable (degrades the clause).
    Parse results are cached — the regime-threshold search evaluates the same
    clause strings ~10⁶ times."""
    name, op, rhs = _parse_clause(clause)
    v = inputs.get(name)
    if v is None:
        return None
    if op == "==":
        return bool(v) == bool(rhs) if isinstance(rhs, bool) else float(v) == rhs
    v = float(v)
    return {"<": v < rhs, ">": v > rhs, "<=": v <= rhs, ">=": v >= rhs}[op]


@dataclass
class RegimeRules:
    precedence: list[str]
    min_live_clauses: int
    states: dict[str, list[str]]          # state -> AND clause list ([] = residual)
    residual: str
    tags: dict[str, list[str]]

    @classmethod
    def load(cls, path: str | Path = RULES_FILE) -> "RegimeRules":
        raw = yaml.safe_load(Path(path).read_text())
        states: dict[str, list[str]] = {}
        residual = None
        for name, spec in raw["primary"]["states"].items():
            if spec.get("residual"):
                residual = name
                states[name] = []
            else:
                states[name] = list(spec["all"])
        if residual is None:
            raise ValueError("regime rules need exactly one residual state")
        return cls(
            precedence=list(raw["primary"]["precedence"]),
            min_live_clauses=int(raw["primary"]["min_live_clauses"]),
            states=states,
            residual=residual,
            tags={k: list(v["all"]) for k, v in raw["tags"].items()},
        )


@dataclass
class RegimeRead:
    as_of: date
    raw_primary: str            # what conditions say today, pre-hysteresis
    primary: str                # hysteresis-confirmed state
    tags: tuple[str, ...]
    degraded_states: tuple[str, ...]   # states with too few live clauses to evaluate
    pending: str | None = None  # candidate state awaiting confirmation
    pending_days: int = 0


def evaluate_primary(rules: RegimeRules, inputs: Mapping[str, Any]
                     ) -> tuple[str, tuple[str, ...]]:
    """First eligible-and-true state in fixed precedence; residual otherwise."""
    degraded: list[str] = []
    for state in rules.precedence:
        clauses = rules.states[state]
        if not clauses:                       # residual
            return state, tuple(degraded)
        results = [_eval_clause(c, inputs) for c in clauses]
        live = [r for r in results if r is not None]
        if len(live) < rules.min_live_clauses:
            degraded.append(state)            # too blind to assert — skip, never guess
            continue
        if all(live):
            return state, tuple(degraded)
    return rules.residual, tuple(degraded)


def evaluate_tags(rules: RegimeRules, inputs: Mapping[str, Any]) -> tuple[str, ...]:
    out = []
    for tag, clauses in rules.tags.items():
        results = [_eval_clause(c, inputs) for c in clauses]
        live = [r for r in results if r is not None]
        if live and len(live) == len(results) and all(live):
            out.append(tag)                   # a tag with ANY blind clause stays off
    return tuple(sorted(out))


class HysteresisTracker:
    """A4 item 3 — same discipline as RACE's hysteresis bands. A flip to a new
    primary state requires its conditions to hold ``confirm_days`` consecutive
    sessions; until confirmed the established state keeps reporting."""

    def __init__(self, confirm_days: int = 3, initial: str = "RISK_NEUTRAL"):
        self.confirm_days = confirm_days
        self.current = initial
        self.pending: str | None = None
        self.pending_days = 0

    def update(self, raw: str) -> str:
        if raw == self.current:
            self.pending, self.pending_days = None, 0
            return self.current
        if raw == self.pending:
            self.pending_days += 1
        else:
            self.pending, self.pending_days = raw, 1
        if self.pending_days >= self.confirm_days:
            self.current = self.pending
            self.pending, self.pending_days = None, 0
        return self.current


# ── Tier-P input assembly ────────────────────────────────────────────────────

def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1 or closes[-1 - n] == 0:
        return None
    return closes[-1] / closes[-1 - n] - 1.0


def _rs_change(a: list[float], b: list[float], n: int) -> float | None:
    """Change in the A/B ratio over n sessions (aligned tails)."""
    m = min(len(a), len(b))
    if m < n + 1:
        return None
    a, b = a[-m:], b[-m:]
    r_now, r_then = a[-1] / b[-1], a[-1 - n] / b[-1 - n]
    return r_now / r_then - 1.0


_SECTOR_11 = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY",
              "XLRE", "XLC")
_DEFENSIVE = ("XLU", "XLP", "XLV")
_REGIME_TICKERS = ("SPY", "HYG", "LQD", "RSP", "QQQ", "TLT", "IEF", "UUP",
                   "GLD", "DBC", "VXUS") + _SECTOR_11
_REGIME_SERIES = ("VIXCLS", "T10YIE", "DGS10", "BAMLH0A0HYM2", "BAMLC0A0CM")


class RegimeInputCache:
    """Preloaded history for fast repeated build_inputs calls.

    The per-day SQL reload was the precompute's slow loop (~20 of 60 min on
    the 2005→2026 run): every day re-read full price history for 22 tickers
    plus 5 macro series. This loads everything once and slices per day
    (bisect on date / available_to_trade — both monotone), returning exactly
    what the PIT loaders would (equivalence test-pinned)."""

    def __init__(self, wh: Warehouse, end: str | date):
        import bisect
        self._bisect = bisect
        end = _parse_date(end)
        self._closes: dict[str, tuple[list[date], list[float]]] = {}
        for t in _REGIME_TICKERS:
            rows = wh.load_prices_raw(t, end)
            pairs = [(_parse_date(r["date"]), r["close"])
                     for r in rows if r["close"] is not None]
            self._closes[t] = ([d for d, _ in pairs], [c for _, c in pairs])
        self._series: dict[str, tuple[list[date], list]] = {}
        for sid in _REGIME_SERIES:
            pts = wh.load_series(sid, end)
            self._series[sid] = ([p.available_to_trade for p in pts], pts)

    def closes(self, ticker: str, as_of: date) -> list[float]:
        dates, closes = self._closes[ticker]
        return closes[: self._bisect.bisect_right(dates, as_of)]

    def points(self, sid: str, as_of: date) -> list:
        avail, pts = self._series[sid]
        return pts[: self._bisect.bisect_right(avail, as_of)]


def build_inputs(wh: Warehouse, as_of_date: str | date,
                 cache: RegimeInputCache | None = None) -> dict[str, Any]:
    """Assemble the Tier-P regime inputs as of a date (base §9.1 blend).
    Missing history → None (clause-level degradation downstream). Raw closes
    only (Tier P); breadth is PIT-derived from the sector closes themselves.
    With `cache`, no SQL is touched (precompute path)."""
    as_of = _parse_date(as_of_date)

    def _closes_of(t: str) -> list[float]:
        if cache is not None:
            return cache.closes(t, as_of)
        rows = wh.load_prices_raw(t, as_of)
        return [r["close"] for r in rows if r["close"] is not None]

    def _points_of(sid: str) -> list:
        if cache is not None:
            return cache.points(sid, as_of)
        return wh.load_series(sid, as_of)

    closes: dict[str, list[float]] = {t: _closes_of(t) for t in _REGIME_TICKERS}

    spy = closes["SPY"]
    out: dict[str, Any] = {}

    if len(spy) >= 200:
        sma200 = sum(spy[-200:]) / 200
        sma50 = sum(spy[-50:]) / 50
        sma20 = sum(spy[-20:]) / 20
        out["spy_above_200dma"] = spy[-1] > sma200
        out["spy_sma50_above_sma200"] = sma50 > sma200
        out["spy_below_sma50_or_200"] = spy[-1] < sma50 or spy[-1] < sma200
        out["spy_reclaimed_sma20_or_50"] = spy[-1] > sma20 or spy[-1] > sma50
        # "recently below SMA200 or SMA50" (§9.2 RECOVERY): within last 20 sessions
        below_recent = False
        for i in range(20):
            if len(spy) < 200 + i:
                break
            window = spy[: len(spy) - i]
            s200_i = sum(window[-200:]) / 200
            s50_i = sum(window[-50:]) / 50
            if window[-1] < s200_i or window[-1] < s50_i:
                below_recent = True
                break
        out["spy_below_sma_within_20d"] = below_recent
    out["spy_ret_63d"] = _ret(spy, 63)
    out["spy_ret_20d"] = _ret(spy, 20)
    if len(spy) >= 22:
        rets = [spy[i] / spy[i - 1] - 1 for i in range(len(spy) - 21, len(spy))]
        out["spy_vol_21d_ann"] = statistics.pstdev(rets) * (252 ** 0.5)
    if len(spy) >= 252:
        high = max(spy[-252:])
        out["spy_dd_from_252d_high"] = spy[-1] / high - 1.0

    vix_pts = _points_of("VIXCLS")
    vix_vals = [p.value for p in vix_pts]
    if vix_vals:
        out["vix"] = vix_vals[-1]
        if len(vix_vals) >= 21:
            out["vix_chg_20d"] = vix_vals[-1] - vix_vals[-21]
        tail = vix_vals[-252:]
        if len(tail) >= 60:
            below = sum(1 for v in tail if v <= vix_vals[-1])
            out["vix_pctile_252d"] = below / len(tail)
            med = statistics.median(tail)
            out["vix_vs_median_252d"] = vix_vals[-1] / med if med else None

    out["hyg_lqd_rs_63d"] = _rs_change(closes["HYG"], closes["LQD"], 63)
    out["hyg_lqd_rs_20d"] = _rs_change(closes["HYG"], closes["LQD"], 20)
    out["rsp_spy_rs_63d"] = _rs_change(closes["RSP"], spy, 63)
    out["qqq_spy_rs_63d"] = _rs_change(closes["QQQ"], spy, 63)
    out["vxus_spy_rs_63d"] = _rs_change(closes["VXUS"], spy, 63)
    for t in ("TLT", "IEF", "UUP", "GLD", "DBC"):
        out[f"{t.lower()}_ret_63d"] = _ret(closes[t], 63)

    # §9.2 sector-rotation inputs: defensives (XLU/XLP/XLV) and inflation
    # cyclicals (XLE/XLB) vs SPY, averaged 63d RS change
    defs = [v for t in _DEFENSIVE
            if (v := _rs_change(closes[t], spy, 63)) is not None]
    out["def_spy_rs_63d"] = sum(defs) / len(defs) if defs else None
    infl = [v for t in ("XLE", "XLB")
            if (v := _rs_change(closes[t], spy, 63)) is not None]
    out["xle_xlb_spy_rs_63d"] = sum(infl) / len(infl) if infl else None

    # PIT market breadth: % of the 11 sector ETFs above their own 200dma
    above, counted = 0, 0
    for t in _SECTOR_11:
        c = closes[t]
        if len(c) >= 200:
            counted += 1
            if c[-1] > sum(c[-200:]) / 200:
                above += 1
    out["breadth_pct_above_200dma"] = (100.0 * above / counted) if counted >= 6 else None

    # Tier-P rate / inflation-expectation trends
    for sid, key in (("T10YIE", "breakeven_chg_20d"), ("DGS10", "dgs10_chg_20d")):
        pts = _points_of(sid)
        if len(pts) >= 21:
            out[key] = pts[-1].value - pts[-21].value

    for sid, key in (("BAMLH0A0HYM2", "hy_oas"), ("BAMLC0A0CM", "ig_oas")):
        pts = _points_of(sid)
        if pts:
            out[key] = pts[-1].value
            if len(pts) >= 21:
                out[f"{key}_trend_20d"] = pts[-1].value - pts[-21].value
    return out


# ── comparison logging (A4 item 4 — read-only, omit-if-absent) ───────────────

def _comparison_columns(db_path: str, as_of: date) -> dict[str, Any]:
    out: dict[str, Any] = {"mhd_regime_state": "", "race_regime": ""}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            r = con.execute(
                "SELECT regime_state FROM mhd_scores WHERE date<=? "
                "ORDER BY date DESC LIMIT 1", (as_of.isoformat(),)
            ).fetchone()
            if r:
                out["mhd_regime_state"] = r[0]
            r = con.execute(
                "SELECT value FROM macro_series WHERE series_id='RACE_REGIME' "
                "AND date<=? ORDER BY date DESC LIMIT 1", (as_of.isoformat(),)
            ).fetchone()
            if r and r[0] is not None:
                out["race_regime"] = int(r[0])
        finally:
            con.close()
    except Exception:
        pass  # omit-if-absent: comparison data must never break the engine
    return out


def regime_series(rules: RegimeRules,
                  inputs_by_day: Mapping[date, Mapping[str, Any]],
                  confirm_days: int = 3
                  ) -> dict[date, tuple[str, tuple[str, ...]]]:
    """Pure regime evaluation over precomputed inputs — no DB, no engine.
    The regime-threshold search re-runs this per candidate rule set."""
    tracker = HysteresisTracker(confirm_days=confirm_days,
                                initial=rules.residual)
    out: dict[date, tuple[str, tuple[str, ...]]] = {}
    for day in sorted(inputs_by_day):
        inputs = inputs_by_day[day]
        raw, _ = evaluate_primary(rules, inputs)
        confirmed = tracker.update(raw)
        out[day] = (confirmed, evaluate_tags(rules, inputs))
    return out


class RegimeEngine:
    def __init__(self, wh: Warehouse, *, confirm_days: int = 3,
                 rules: RegimeRules | None = None,
                 history_path: str | Path | None = None,
                 cache: RegimeInputCache | None = None):
        self.wh = wh
        self.rules = rules or RegimeRules.load()
        self.tracker = HysteresisTracker(confirm_days=confirm_days,
                                         initial=self.rules.residual)
        self.history_path = Path(history_path) if history_path else None
        self.cache = cache

    def read(self, as_of_date: str | date, *, log: bool = False) -> RegimeRead:
        as_of = _parse_date(as_of_date)
        inputs = build_inputs(self.wh, as_of, cache=self.cache)
        self.last_inputs = inputs          # exposed for the inputs precompute
        raw, degraded = evaluate_primary(self.rules, inputs)
        confirmed = self.tracker.update(raw)
        tags = evaluate_tags(self.rules, inputs)
        read = RegimeRead(as_of=as_of, raw_primary=raw, primary=confirmed,
                          tags=tags, degraded_states=degraded,
                          pending=self.tracker.pending,
                          pending_days=self.tracker.pending_days)
        if log and self.history_path:
            self._log(read)
        return read

    def _log(self, read: RegimeRead) -> None:
        cmp_cols = _comparison_columns(self.wh.db_path, read.as_of)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.history_path.exists()
        with self.history_path.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "primary", "raw_primary", "tags",
                            "degraded_states", "mhd_regime_state", "race_regime"])
            w.writerow([read.as_of.isoformat(), read.primary, read.raw_primary,
                        "|".join(read.tags), "|".join(read.degraded_states),
                        cmp_cols["mhd_regime_state"], cmp_cols["race_regime"]])
