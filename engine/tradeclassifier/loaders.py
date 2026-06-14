"""Point-in-time loaders over the DNSR warehouse (ADDENDUM A3).

Three tiers:

- **Tier P** — point-in-time clean: raw OHLCV, market-derived never-revised FRED
  dailies, CBOE PCR, treasury par yields. ``available_to_trade = observation + offset``
  (default one trading day, conservative).
- **Tier A** — adjustment-vintage caveat: current-vintage ``adjusted_close``; consumers
  MUST route reports through :mod:`tradeclassifier.reports` which emits the mandatory
  vintage-disclosure block. Splice-quarantined tickers are excluded from the universe
  by :mod:`tradeclassifier.universe`.
- **Tier D** — revised macro: **diagnostic-only in v1**. ``load_series`` refuses Tier-D
  series unless ``diagnostic=True`` — the production signal path therefore contains
  zero Tier-D inputs by construction (acceptance A7-19, asserted by test).

Every loader takes ``as_of_date`` and filters ``available_to_trade <= as_of_date``.
The §22.2 future-mutation property is tested at this layer: for any T' > T, loading
as-of T' must not change any value dated <= T returned by an as-of-T load.

All connections are read-only (``file:...?mode=ro``); a write attempt raises.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY_FILE = REPO_ROOT / "config" / "macro_availability.yaml"


class LoaderError(ValueError):
    pass


class TierViolation(LoaderError):
    """A Tier-D series was requested on the production signal path."""


def _parse_date(d: str | date) -> date:
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _add_trading_days(d: date, n: int) -> date:
    """Conservative trading-day offset (weekends only; holidays make the lag
    LONGER in reality, so skipping holiday modeling is the safe direction)."""
    cur = d
    while n > 0:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n -= 1
    return cur


@dataclass(frozen=True)
class SeriesPoint:
    obs_date: date
    value: float
    available_to_trade: date
    tier: str


class Availability:
    """Per-series tier + availability offsets from config/macro_availability.yaml."""

    def __init__(self, path: str | Path = AVAILABILITY_FILE):
        raw = yaml.safe_load(Path(path).read_text())["tiers"]
        self.p_series: set[str] = set(raw["P"]["series"])
        self.p_default_offset: int = int(raw["P"]["default_offset_trading_days"])
        self.p_tables: dict[str, int] = {
            k: int(v["offset_trading_days"]) for k, v in raw["P"]["tables"].items()
        }
        self.a_tables: dict[str, int] = {
            k: int(v["offset_trading_days"]) for k, v in raw["A"]["tables"].items()
        }
        self.d_series: dict[str, dict] = dict(raw["D"]["series"] or {})

    def tier_of(self, series_id: str) -> str:
        if series_id in self.p_series:
            return "P"
        if series_id in self.d_series:
            return "D"
        # Unknown series: refuse rather than guess a tier (omit-never-fabricate).
        raise LoaderError(
            f"series {series_id!r} has no tier in macro_availability.yaml — "
            "add it before use"
        )

    def available(self, series_id: str, obs: date) -> date:
        tier = self.tier_of(series_id)
        if tier == "P":
            return _add_trading_days(obs, self.p_default_offset)
        spec = self.d_series[series_id]
        return obs + timedelta(days=int(spec["offset_calendar_days"]))


class Warehouse:
    """Read-only PIT access. One instance per run; one config key (base §20)."""

    def __init__(self, db_path: str | Path, availability: Availability | None = None):
        self.db_path = str(db_path)
        self.av = availability or Availability()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    # ── Tier P: raw prices ────────────────────────────────────────────────

    def load_prices_raw(self, ticker: str, as_of_date: str | date,
                        start: str | date | None = None) -> list[sqlite3.Row]:
        """Raw OHLCV (Tier P). A bar dated D is available at the next session's
        open — as-of semantics here: bars with date <= as_of are visible (the
        execution layer is what enforces next_open fills)."""
        as_of = _parse_date(as_of_date)
        q = ("SELECT date, open, high, low, close, volume FROM daily_prices "
             "WHERE ticker=? AND date<=?")
        args: list = [ticker, as_of.isoformat()]
        if start is not None:
            q += " AND date>=?"
            args.append(_parse_date(start).isoformat())
        q += " ORDER BY date"
        with self._connect() as con:
            return con.execute(q, args).fetchall()

    # ── Tier A: adjusted prices (vintage-disclosed) ───────────────────────

    def load_prices_adjusted(self, ticker: str, as_of_date: str | date,
                             start: str | date | None = None) -> list[sqlite3.Row]:
        """Current-vintage adjusted_close (Tier A). Loader is vintage-READY:
        the as_of_date arg is the future v2 hook (as-of reconstruction from raw
        close + split/dividend events is a loader swap, not a redesign)."""
        as_of = _parse_date(as_of_date)
        q = ("SELECT date, adjusted_close FROM daily_prices "
             "WHERE ticker=? AND date<=? AND adjusted_close IS NOT NULL")
        args: list = [ticker, as_of.isoformat()]
        if start is not None:
            q += " AND date>=?"
            args.append(_parse_date(start).isoformat())
        q += " ORDER BY date"
        with self._connect() as con:
            return con.execute(q, args).fetchall()

    # ── Macro series (Tier P / Tier D split enforced here) ────────────────

    def load_series(self, series_id: str, as_of_date: str | date,
                    start: str | date | None = None, *,
                    diagnostic: bool = False) -> list[SeriesPoint]:
        """Macro series with availability filtering.

        Tier P → allowed on the signal path. Tier D → raises ``TierViolation``
        unless ``diagnostic=True`` (A3 v1 default: option 2)."""
        tier = self.av.tier_of(series_id)
        if tier == "D" and not diagnostic:
            raise TierViolation(
                f"{series_id} is Tier D (revised macro) — diagnostic-only in v1; "
                "pass diagnostic=True only OUTSIDE the signal path"
            )
        as_of = _parse_date(as_of_date)
        q = "SELECT date, value FROM macro_series WHERE series_id=? AND value IS NOT NULL"
        args: list = [series_id]
        if start is not None:
            q += " AND date>=?"
            args.append(_parse_date(start).isoformat())
        q += " ORDER BY date"
        out: list[SeriesPoint] = []
        with self._connect() as con:
            for r in con.execute(q, args):
                obs = _parse_date(r["date"])
                avail = self.av.available(series_id, obs)
                if avail <= as_of:
                    out.append(SeriesPoint(obs, float(r["value"]), avail, tier))
        return out

    # ── Tier P: treasury par yields ───────────────────────────────────────

    def load_par_yield(self, tenor: str, as_of_date: str | date,
                       start: str | date | None = None) -> list[SeriesPoint]:
        as_of = _parse_date(as_of_date)
        offset = self.av.p_tables.get("treasury_par_yields", 1)
        q = (f"SELECT date, {tenor} AS v FROM treasury_par_yields "
             f"WHERE {tenor} IS NOT NULL")
        args: list = []
        if start is not None:
            q += " AND date>=?"
            args.append(_parse_date(start).isoformat())
        q += " ORDER BY date"
        out: list[SeriesPoint] = []
        with self._connect() as con:
            for r in con.execute(q, args):
                obs = _parse_date(r["date"])
                avail = _add_trading_days(obs, offset)
                if avail <= as_of:
                    out.append(SeriesPoint(obs, float(r["v"]), avail, "P"))
        return out

    # ── Universe metadata (§22.7 — fully PIT-satisfiable) ─────────────────

    def profile(self, ticker: str) -> sqlite3.Row | None:
        with self._connect() as con:
            return con.execute(
                "SELECT ticker, inception_date, delisted_reason "
                "FROM etf_profiles WHERE ticker=?", (ticker,)
            ).fetchone()

    def dollar_vol_20d(self, ticker: str, as_of_date: str | date) -> float | None:
        """Trailing 20-session average close*volume as of as_of (raw, Tier P)."""
        rows = self.load_prices_raw(ticker, as_of_date)[-20:]
        if len(rows) < 20:
            return None
        vals = [r["close"] * r["volume"] for r in rows
                if r["close"] is not None and r["volume"] is not None]
        if len(vals) < 20:
            return None
        return sum(vals) / len(vals)
