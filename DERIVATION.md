# Convex Core — A Derivation from First Principles

*How the allocation equation `w_equity + w_convexity + w_duration = 1` and the volatility
brake follow from one objective: maximizing long-horizon compound growth.*

**What this is — and isn't.** Convex Core was originally *authored from empirical evidence*
(the design spec, built from backtests). This note shows the *same* equation is what a
first-principles argument recommends — so theory and evidence agree. It is a principled
justification, **not a uniqueness proof**: the derivation terminates in a few named design
choices, marked **[rigorous]** or **[design choice]** so you can see where judgment enters.

---

## Step 0 — Maximize *geometric* growth

Terminal wealth is multiplicative, so the objective is expected log-growth:

```
g = E[ ln(1 + R) ]  ≈  μ − ½σ²        (μ = E[R], σ² = Var(R))
```

Variance is a **direct subtraction** from compound growth: reducing σ² raises `g` *even if it
lowers* the arithmetic mean μ. So conceding ≤1%/yr of arithmetic return to cut risk is
**growth-optimal**, not merely risk-averse. Drawdowns sharpen it — recovery from a loss `d`
requires a gain `d/(1−d) > d` (−50% needs +100%), so recovery is **convex** in the loss, and the
quantity to minimize is specifically the **left-tail / drawdown variance**. **[rigorous — an identity]**

## Step 1 — Abandon return forecasting

Mean–variance optimization needs an estimate of μ, but on this universe μ is **not forecastable**
at useful precision (the market-timing search was negative; cross-sectional IC ≈ 0.026), and MVO
is "error-maximizing" under estimation error (Michaud). The principled response is to allocate by
**role**, under the one constraint that needs no estimate — full investment, no leverage:

```
Σ wᵢ = 1                              (the budget constraint)
```

That is the left-hand side of the equation. **[rigorous, given the empirical premise]**

## Step 2 — The three roles

Exactly three functions are needed:

1. **Capture the one premium you believe in** → an **equity core** `w_equity`.
2. **Hedge the left tail — which has two regimes.** Stock–bond correlation is regime-dependent:
   Treasuries rally in deflationary crashes (2008, 2020) but fall *with* equities in
   inflation/rate-shock crashes (2022). One hedge can't cover both, so the tail-hedge splits:
   - **Duration** `w_duration` — hedges the deflationary crash.
   - **Crisis-convexity** `w_convexity` — long-volatility trend-following + anti-beta, hedges the
     inflationary regime duration misses.

```
w_equity + w_convexity + w_duration = 1     (w_duration = the plug)
```

"Convexity" is literal: trend-following replicates *long lookback straddles* (Fung & Hsieh, 2001),
bending the payoff upward in the tails — the positive co-skew that attacks Step 0's left-tail
variance. **[the equation is rigorous; "exactly two hedge sleeves" is a design choice motivated by
the two documented regimes]**

## Step 3 — The volatility brake from Kelly

Log-optimal (Kelly) sizing in a risky asset is `f* = μ/σ²`. Because the Sharpe ratio `S = μ/σ` is
more stable than the mean, and volatility *is* forecastable (clustering), substitute:

```
f* = S/σ  ∝  1/σ        →  cap at 1 (no leverage)  →  eq_scale = min(1, σ_target / σ̂_21d)
```

That is the brake — the one piece of "timing" that survives, because it conditions on σ̂
(estimable) and never on μ (not). **[rigorous, under "Sharpe more stable than the mean"]**

## Step 4 — Freeze the parameters

Since μ is unforecastable, optimizing the weights in-sample would re-introduce the estimation
error the structure exists to avoid; freezing them makes the backtest out-of-sample by
construction. "Zero fitting" is *required* by the same premise that produced the equation.
**[rigorous; the specific values 0.65 / 0.15 / 0.20 are a design choice]**

---

## The defensible statement

> The Convex Core equation is the form that **maximizing expected log-growth** implies once one
> accepts that **expected returns are not forecastable but volatility is**: a premium-capturing
> core, a convex crisis hedge and a duration ballast for the two crash regimes, sized by a
> Kelly-style volatility brake, with parameters frozen because optimizing them would re-create the
> estimation error the structure exists to avoid.

The mechanisms recombine well-published premia; the paper claims **no novel strategy**. To the
authors' knowledge the specific three-sleeve, frozen-parameter formulation with the
realized-volatility brake, as presented here, has not been previously published in this form.

## References

- Kelly (1956), *A New Interpretation of Information Rate* — log-optimal growth.
- Markowitz (1952); Michaud (1989), *The Markowitz Optimization Enigma* — estimation error in MVO.
- Moreira & Muir (2017), *Volatility-Managed Portfolios*; Harvey et al. (2018) — the volatility brake.
- Hurst, Ooi & Pedersen (2017), *A Century of Evidence on Trend-Following* (JPM) — crisis alpha.
- Fung & Hsieh (2001), *The Risk in Hedge Fund Strategies* — trend-following as long lookback straddles.
- Frazzini & Pedersen (2014), *Betting Against Beta* — the anti-beta sleeve.

*Companion to the Convex Core white paper (§4.1). Hypothetical/backtested context; not investment
advice. The portfolio math is deterministic — no large-language model participates in the engine.*
