"""Trailing-only technical features (base §8 inputs; §4.3 — no centered windows,
no full-sample transforms; trailing percentiles only).

All functions take plain lists ordered oldest→newest, computed AS OF the last
element. A feature whose history is too short returns None — the A1 group
degradation machinery handles the rest. Indicator math uses Tier-A adjusted
closes (addendum A6: rs_ratio both legs adjusted; the vintage disclosure covers
it); ATR uses raw OHLC (adjusted highs/lows don't exist in the warehouse — noted
in the feature dict as atr basis).

"Slope" throughout = value now minus value `n` sessions ago (deterministic,
documented; base spec leaves slope definition open).
"""

from __future__ import annotations

import statistics
from typing import Any, Sequence


# ── primitives ───────────────────────────────────────────────────────────────

def sma(x: Sequence[float], n: int) -> float | None:
    if len(x) < n:
        return None
    return sum(x[-n:]) / n


def sma_series(x: Sequence[float], n: int, points: int) -> list[float] | None:
    """Last `points` SMA values (each trailing-only)."""
    if len(x) < n + points - 1:
        return None
    return [sum(x[i - n:i]) / n for i in range(len(x) - points + 1, len(x) + 1)]


def ema_series(x: Sequence[float], n: int) -> list[float] | None:
    if len(x) < n:
        return None
    k = 2.0 / (n + 1)
    out = [sum(x[:n]) / n]
    for v in x[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(x: Sequence[float], n: int) -> float | None:
    s = ema_series(x, n)
    return s[-1] if s else None


def roc(x: Sequence[float], n: int) -> float | None:
    if len(x) < n + 1 or x[-1 - n] == 0:
        return None
    return x[-1] / x[-1 - n] - 1.0


def rsi_series(x: Sequence[float], n: int = 14) -> list[float] | None:
    """Wilder RSI; returns the running series (needed for rising/oversold-within-
    last-10 checks)."""
    if len(x) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(x)):
        d = x[i] - x[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    out = []
    for i in range(n, len(gains) + 1):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        rs = avg_g / avg_l if avg_l > 0 else float("inf")
        out.append(100.0 - 100.0 / (1.0 + rs) if avg_l > 0 else 100.0)
    return out


def macd_parts(x: Sequence[float], fast: int = 12, slow: int = 26,
               signal: int = 9) -> tuple[list[float], list[float], list[float]] | None:
    ef, es = ema_series(x, fast), ema_series(x, slow)
    if ef is None or es is None:
        return None
    m = min(len(ef), len(es))
    line = [a - b for a, b in zip(ef[-m:], es[-m:])]
    if len(line) < signal:
        return None
    sig = ema_series(line, signal)
    if sig is None:
        return None
    k = min(len(line), len(sig))
    line, sig = line[-k:], sig[-k:]
    hist = [a - b for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger_lower(x: Sequence[float], n: int = 20, k: float = 2.0,
                    points: int = 1) -> list[float] | None:
    """Last `points` lower-band values."""
    if len(x) < n + points - 1:
        return None
    out = []
    for i in range(len(x) - points + 1, len(x) + 1):
        w = x[i - n:i]
        m = sum(w) / n
        sd = statistics.pstdev(w)
        out.append(m - k * sd)
    return out


def atr_pct_series(high: Sequence[float], low: Sequence[float],
                   close: Sequence[float], n: int = 14,
                   points: int = 1) -> list[float] | None:
    """Wilder ATR as a % of close; last `points` values. Raw OHLC basis."""
    m = min(len(high), len(low), len(close))
    if m < n + points + 1:
        return None
    high, low, close = high[-m:], low[-m:], close[-m:]
    trs = []
    for i in range(1, m):
        trs.append(max(high[i] - low[i], abs(high[i] - close[i - 1]),
                       abs(low[i] - close[i - 1])))
    atr = sum(trs[:n]) / n
    series = [atr]
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
        series.append(atr)
    pct = [a / c * 100.0 for a, c in zip(series, close[n:])]
    return pct[-points:] if len(pct) >= points else None


def adx14(high: Sequence[float], low: Sequence[float], close: Sequence[float],
          n: int = 14, points: int = 1) -> list[float] | None:
    """Wilder ADX; last `points` values."""
    m = min(len(high), len(low), len(close))
    if m < 2 * n + points + 1:
        return None
    high, low, close = high[-m:], low[-m:], close[-m:]
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, m):
        up, dn = high[i] - high[i - 1], low[i - 1] - low[i]
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(max(high[i] - low[i], abs(high[i] - close[i - 1]),
                       abs(low[i] - close[i - 1])))
    str_, spd, smd = sum(trs[:n]), sum(plus_dm[:n]), sum(minus_dm[:n])
    dxs = []
    for i in range(n, len(trs) + 1):
        if i > n:
            str_ = str_ - str_ / n + trs[i - 1]
            spd = spd - spd / n + plus_dm[i - 1]
            smd = smd - smd / n + minus_dm[i - 1]
        if str_ <= 0:
            dxs.append(0.0)
            continue
        pdi, mdi = 100 * spd / str_, 100 * smd / str_
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi > 0 else 0.0)
    if len(dxs) < n:
        return None
    adx = sum(dxs[:n]) / n
    out = [adx]
    for dx in dxs[n:]:
        adx = (adx * (n - 1) + dx) / n
        out.append(adx)
    return out[-points:] if len(out) >= points else None


def realized_vol_ann(x: Sequence[float], n: int) -> float | None:
    if len(x) < n + 1:
        return None
    rets = [x[i] / x[i - 1] - 1 for i in range(len(x) - n, len(x))]
    return statistics.pstdev(rets) * (252 ** 0.5)


def trailing_percentile(history: Sequence[float], current: float) -> float | None:
    """Trailing-window percentile (0–100). NEVER full-sample — caller passes the
    trailing window only (§4.3)."""
    if not history:
        return None
    below = sum(1 for v in history if v <= current)
    return 100.0 * below / len(history)


def drawdown_from_high(x: Sequence[float], n: int) -> float | None:
    """Negative fraction: close vs trailing n-session high."""
    if len(x) < n:
        return None
    hi = max(x[-n:])
    return x[-1] / hi - 1.0 if hi > 0 else None


# ── the per-ETF feature vector ───────────────────────────────────────────────

def build_features(adj: Sequence[float], raw_high: Sequence[float],
                   raw_low: Sequence[float], raw_close: Sequence[float],
                   volume: Sequence[float],
                   bench_adj: Sequence[float] | None) -> dict[str, Any]:
    """Everything the §8 tables + §12/§13 gates consume, computed as of the
    last bar. Missing history → key absent/None (group degradation upstream).
    `bench_adj` None → all rs_* features None (benchmark_missing handled by
    the RS table's neutral-50 rule)."""
    f: dict[str, Any] = {}
    c = list(adj)

    # — trend (§8.1)
    s20, s50, s100, s200 = sma(c, 20), sma(c, 50), sma(c, 100), sma(c, 200)
    f["close"] = c[-1] if c else None
    f["close_gt_sma20"] = (c[-1] > s20) if s20 else None
    f["close_gt_sma50"] = (c[-1] > s50) if s50 else None
    f["close_lt_sma50"] = (c[-1] < s50) if s50 else None
    f["close_lt_sma200"] = (c[-1] < s200) if s200 else None
    f["sma20_gt_sma50"] = (s20 > s50) if (s20 and s50) else None
    f["sma50_lt_sma200"] = (s50 < s200) if (s50 and s200) else None
    s50s = sma_series(c, 50, 11)
    f["sma50_slope_pos"] = (s50s[-1] > s50s[0]) if s50s else None
    s200s = sma_series(c, 200, 11)
    f["sma200_falling"] = (s200s[-1] < s200s[0]) if s200s else None
    e12, e26 = ema(c, 12), ema(c, 26)
    f["ema12_gt_ema26"] = (e12 > e26) if (e12 and e26) else None
    f["pct_above_sma50"] = (c[-1] / s50 - 1.0) if s50 else None

    adx = adx14(raw_high, raw_low, raw_close, points=6)
    if adx:
        f["adx"] = adx[-1]
        f["adx_rising_and_trend_pos"] = (adx[-1] > adx[0]) and bool(f["close_gt_sma50"])
    else:
        f["adx_rising_and_trend_pos"] = None

    # — momentum (§8.2)
    mp = macd_parts(c)
    if mp:
        line, sig, hist = mp
        f["macd_gt_signal"] = line[-1] > sig[-1]
        f["macd_lt_signal"] = line[-1] < sig[-1]
        f["macd_hist_rising"] = len(hist) >= 2 and hist[-1] > hist[-2]
        f["macd_hist_falling"] = len(hist) >= 2 and hist[-1] < hist[-2]
        f["macd_hist_slope_pos_3d"] = (
            len(hist) >= 4 and all(hist[i] > hist[i - 1] for i in range(-3, 0))
        )
    r20, r63 = roc(c, 20), roc(c, 63)
    f["roc20_pos"] = (r20 > 0) if r20 is not None else None
    f["roc20_neg"] = (r20 < 0) if r20 is not None else None
    f["roc63_pos"] = (r63 > 0) if r63 is not None else None

    rsis = rsi_series(c, 14)
    if rsis and len(rsis) >= 11:
        f["rsi14"] = rsis[-1]
        rising = rsis[-1] > rsis[-2]
        f["rsi_rising_through_40_55"] = rising and 40.0 <= rsis[-1] <= 55.0
        f["rsi_falling_below_45"] = (not rising) and rsis[-1] < 45.0
        f["rsi14_rising_3d"] = len(rsis) >= 4 and all(
            rsis[i] > rsis[i - 1] for i in range(-3, 0))
        f["rsi14_below_35_last10"] = min(rsis[-10:]) < 35.0
        f["rsi14_gt_70"] = rsis[-1] > 70.0
    rsi5 = rsi_series(c, 5)
    if rsi5 and len(rsi5) >= 10:
        f["rsi5_below_25_last10"] = min(rsi5[-10:]) < 25.0

    # — oversold reversal (§8.3 / §13)
    bb = bollinger_lower(c, 20, 2.0, points=11)
    if bb:
        below_hist = [c[-(11 - i)] < bb[i] for i in range(10)]   # prior 10 sessions
        f["below_lower_bb_last10"] = any(below_hist) or c[-1] < bb[-1]
        f["close_above_lower_bb"] = c[-1] > bb[-1]
        f["reclaims_lower_bb"] = any(below_hist) and c[-1] > bb[-1]
    f["drawdown_63d"] = drawdown_from_high(c, 63)
    f["drawdown_126d"] = drawdown_from_high(c, 126)
    e5 = ema(c, 5)
    f["close_gt_ema5"] = (c[-1] > e5) if e5 else None
    if len(volume) >= 21:
        v20 = sum(volume[-21:-1]) / 20
        f["volume_confirms_rebound"] = (volume[-1] > v20) and len(c) >= 2 and c[-1] > c[-2]

    # — risk (§8.5)
    rv20 = realized_vol_ann(c, 20)
    f["realized_vol_20d"] = rv20
    if rv20 is not None and len(c) >= 252 + 21:
        hist_vols = []
        for i in range(252):
            w = c[-(21 + i):len(c) - i]
            rets = [w[j] / w[j - 1] - 1 for j in range(1, len(w))]
            hist_vols.append(statistics.pstdev(rets) * (252 ** 0.5))
        f["vol_pctile_252d"] = trailing_percentile(hist_vols, rv20)
    atr6 = atr_pct_series(raw_high, raw_low, raw_close, points=21)
    if atr6:
        f["atr_pct"] = atr6[-1]
        f["atr_pct_declining"] = atr6[-1] < atr6[-6]
        f["atr_pct_rising_rapidly"] = atr6[-1] > 1.25 * atr6[0]   # vs 20 sessions ago
    dd_now, dd_prev = drawdown_from_high(c, 63), (
        drawdown_from_high(c[:-5], 63) if len(c) > 68 else None)
    f["drawdown_stabilizing"] = (dd_now is not None and dd_prev is not None
                                 and dd_now >= dd_prev)
    f["new_20d_low"] = (len(c) >= 20 and c[-1] <= min(c[-20:]))

    # — relative strength (§8.4; both legs Tier-A adjusted, addendum A6)
    if bench_adj is not None and len(bench_adj) >= 2:
        m = min(len(c), len(bench_adj))
        rs = [a / b for a, b in zip(c[-m:], bench_adj[-m:])]
        rs20, rs50 = sma(rs, 20), sma(rs, 50)
        f["rs_gt_sma20"] = (rs[-1] > rs20) if rs20 else None
        f["rs_lt_sma20"] = (rs[-1] < rs20) if rs20 else None
        f["rs_sma20_gt_sma50"] = (rs20 > rs50) if (rs20 and rs50) else None
        rs20s = sma_series(rs, 20, 6)
        f["rs_slope20_pos"] = (rs20s[-1] > rs20s[0]) if rs20s else None
        f["rs_slope20_neg"] = (rs20s[-1] < rs20s[0]) if rs20s else None
        er20, br20 = roc(c, 20), roc(list(bench_adj), 20)
        er63, br63 = roc(c, 63), roc(list(bench_adj), 63)
        f["excess_ret_20d_pos"] = (er20 - br20 > 0) if (er20 is not None and br20 is not None) else None
        f["excess_ret_63d_pos"] = (er63 - br63 > 0) if (er63 is not None and br63 is not None) else None
        f["rs_improving_10_20d"] = (
            (len(rs) >= 11 and rs[-1] > rs[-11]) or (len(rs) >= 21 and rs[-1] > rs[-21])
        )
        f["rs_falling"] = bool(f.get("rs_slope20_neg"))
        f["benchmark_missing"] = False
    else:
        f["benchmark_missing"] = True

    return f
