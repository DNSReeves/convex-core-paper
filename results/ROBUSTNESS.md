# Decision Robustness — the breach frontier of the Convex Core record

**Artifact:** [`robustness.json`](robustness.json) · **Runner:** [`report/run_robustness.py`](../report/run_robustness.py)
· **Companion to:** [`ATTRIBUTION.md`](ATTRIBUTION.md) (which mechanisms carry the record; this
file asks how much error those mechanisms survive)
· **Window:** 2005-01-01 → 2026-06-30, deployed profile (w_equity = 0.95), engine seams
default-off and bit-identical to the attribution baseline when unset
· **Method:** 46 one-at-a-time perturbations from the frozen production point across 9
assumption axes; three registered promises evaluated against a same-loop, same-cost 60/40
benchmark. Margins, never recommendations — nothing here was searched, fitted, or promoted.

## Registered promises

- **P1 (drawdown):** model MaxDD better than 60/40's (−31.4% in this window).
- **P2 (downside quality):** model Sortino ≥ 60/40's (1.002).
- **P3 (return give-up):** model CAGR ≥ 60/40 − 1.5pp (≥ 7.08%).

## Result: 3 breaches in 46 runs — all P2, none P1

**The drawdown promise never broke.** A brake fed month-stale volatility, ±30% volatility
mis-measurement, 10-day execution lag, an operator absent every other week or for all of
March 2020, 80 bps per-trade slippage, and every sleeve/ladder substitution tested — in all
46 configurations the model's MaxDD stayed better than the benchmark's. Drawdown control is
the record's most robust property, not merely its largest (per the attribution) contributor.

| axis | first breach | last intact point (min margin) |
|---|---|---|
| Signal lag (brake sees vol late) | 21 trading days — P2, Sortino 0.958 | 10d (+0.013, thinnest on the board) |
| Slippage | 40 bps — P2; 80 bps adds P3 | 25 bps (tier2.json, prior art) |
| Signal bias ±30%, window 10–63d, exec lag ≤10d, skipped rebalances, governor params, sleeve/ladder availability | — | intact through the full tested range |

## What the frontier teaches

- **Graceful, not cliff-edged:** brake-signal staleness degrades Sortino monotonically
  (1.20 → 1.18 → 1.11 → 1.02 → 0.96 at 0/2/5/10/21 days). There is no hidden cliff.
- **The brake needs direction, not precision:** Sortino holds 1.19–1.21 across ±30%
  systematic vol mis-measurement; bias shifts the CAGR↔MaxDD point, not the quality.
- **Absence-tolerant by design:** skipping every 2nd weekly decision keeps every promise
  (Sortino 1.146); so does the adversarially-timed absent-for-March-2020 scenario (1.161,
  MaxDD −19.3%). The band-rebalance mechanism is why weekly discipline matters at the week
  scale, not the day scale (execution 1–2 days late is free).
- **The stress cap is measurably a no-op** (cap disabled ≈ production on every metric) —
  a third independent confirmation, after the attribution's REGIME share (~0) and
  `regime_wf.json`, that the classification layer contributes ~nothing to the record.
- **Costs are the binding operational constraint:** at 6.3×/yr turnover the frontier lies
  between 25 and 40 bps per trade (~2.4pp/yr at 40 bps).

**Scope note.** One-at-a-time by design: this measures marginal fragility per assumption.
Combined-error surfaces were deliberately not explored (a fitted surface invites
optimization; the doctrine forbids it). Pre-registered priors and their scores — including
the one we got wrong (missed rebalances are NOT a cliff) — are recorded in
`dnsr-agent/IMPL_DECISION_ROBUSTNESS.md` and the C2 report.
