# Convexity Attribution — mechanism decomposition of the Convex Core record

**Artifact:** [`attribution.json`](attribution.json) · **Runner:** [`report/run_attribution.py`](../report/run_attribution.py)
· **Engine:** `etf-trade-classifier/tradeclassifier/convex_core.py`, unmodified, production V2 kwargs
· **Window:** 2005-01-01 → 2026-06-30 (the engine's own span; the paper's headline table uses
2006-02-07 → 2026-06-10 — full-model metrics agree within the window difference)
· **Method:** exact Shapley values over the 2⁵ mechanism factorial, per metric, per profile;
additivity residuals 0 at 1e-12; plus a rebalance-cadence side study. Every number below is in
the artifact. *Descriptive decomposition of the measured record — nothing was fitted, tuned, or
promoted.*

## The five mechanisms

BRAKE (semivol volatility brake) · SLEEVE (crisis-convexity: DBMF/KMLM/BTAL) · DUR (Treasury
ladder) · REGIME (all classification reads — the regime-off convention of `regime_wf.json`,
verbatim) · TILT (IC tilt). Rebalancing is a cadence side study (ill-posed as a toggle: the
brake *is* trading). Diversification is reported as the interaction structure, not a toggle.

## Headline — deployed profile (w_equity = 0.95)

| | CAGR | Sortino | MaxDD |
|---|---|---|---|
| Full model | 10.6% | 1.20 | −18.0% |
| All mechanisms off (static 0.95 SPY + BIL) | 10.7% | 0.79 | −53.1% |

**The model's value is risk-shape at zero CAGR cost.** Shapley shares of the improvement:

| mechanism | Sortino share | MaxDD share | CAGR effect |
|---|---|---|---|
| **BRAKE** | **68%** | **75%** | −0.8pp/yr |
| TILT | 11% | 15% | +0.2pp |
| DUR | 12% | 7% | +0.4pp |
| REGIME | 5% | 3% | −0.0pp |
| SLEEVE | 4% | 0% | +0.1pp |

The ranking is robust to the profile: at w_equity = 0.65, BRAKE is 75% of Sortino and DUR rises
to clear #2 (33% — at 0.95 there is little duration weight to work with).

## The sleeve, honestly

The full-window share understates the crisis-convexity sleeve **by construction**: pre-inception
mass folds into duration, so the sleeve existed for ~7 of 21.5 years. Per stress window
(full vs without-SLEEVE):

| window | full | −SLEEVE | saved |
|---|---|---|---|
| GFC 2008-09 | −5.0% | −5.0% | 0 (not yet alive — was duration) |
| COVID 2020-03 | −6.7% | −8.0% | 1.3pp (partially alive) |
| **RATES 2022** | **−0.9%** | **−6.6%** | **5.7pp — fully alive, its designed crisis type** |

One fully-live episode is one observation; both facts stand together.

## Structure

- **BRAKE+DUR** is the designed synergy (+0.07 to +0.12 Sortino interaction): the brake
  de-risks *into* the ladder. **BRAKE+TILT** is negative (−0.07 to −0.09): tilts add
  volatility the brake then caps.
- **REGIME contributes ~nothing** — confirming `regime_wf.json`'s layer-contribution result
  from an independent decomposition.
- **Cadence:** weekly→monthly costs 1.2pp CAGR and 3.3pp MaxDD; never-rebalancing is
  catastrophic (MaxDD −47.7%). The weekly decision cadence is load-bearing.
- **Gross-exposure disclosure:** the deployed 0.95 profile with the 0.15 sleeve implies
  w_dur = −0.10 at full equity scale; the engine drops negative duration weight, so calm weeks
  run gross ≈ 1.10 (mean 1.032; >1.02 on 40.8% of decision weeks; the 0.65 profile never
  exceeds 1.0). Effect is small (within the sleeve's +0.1pp CAGR share) and is disclosed
  wherever the deployed profile's record is cited.

## Registered conventions

Toggle-off definitions, the REGIME-scope amendment (made before results were read), the
BRAKE-off/REGIME-on construction (`vol_target = 1e9` inside the engine's own brake block), and
the gross-exposure finding are registered in `dnsr-agent/IMPL_CONVEX_ATTRIB.md` v1.1.
