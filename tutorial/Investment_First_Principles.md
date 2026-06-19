# Investment First Principles

## Deriving a Risk-Adjusted Compounding Portfolio from Wealth Growth

**Educational purpose only. Not investment, tax, or legal advice.** The framework below is a conceptual method for thinking about portfolio construction. Exact allocations depend on goals, risk tolerance, taxes, spending needs, account type, time horizon, and implementation constraints.

---

## 1. The starting point: wealth through time

Start with portfolio wealth at time $t$:

$$
W_t
$$

If the portfolio earns return $R_{p,t+1}$ over the next period, then wealth becomes:

$$
W_{t+1}=W_t(1+R_{p,t+1})
$$

Over many periods, wealth compounds multiplicatively:

$$
W_T = W_0 \prod_{t=0}^{T-1}(1+R_{p,t+1})
$$

Taking logs turns multiplicative compounding into addition:

$$
\log\left(\frac{W_T}{W_0}\right)
=
\sum_{t=0}^{T-1}\log(1+R_{p,t+1})
$$

Divide by the number of periods:

$$
g = \frac{1}{T}\sum_{t=0}^{T-1}\log(1+R_{p,t+1})
$$

So long-run compounded growth is the average log return:

$$
g = E[\log(1+R_p)]
$$

For ordinary diversified portfolio returns, the log can be approximated as:

$$
\log(1+R_p) \approx R_p - \frac{1}{2}R_p^2
$$

That leads to the practical growth approximation:

$$
\boxed{g \approx \mu_p - \frac{1}{2}\sigma_p^2}
$$

In plain English:

$$
\boxed{\text{long-run growth of investment wealth} \approx \text{average return} - \text{volatility penalty}}
$$

This is the central idea. Long-run compounding is not driven by average return alone. It is average return minus a penalty for volatility.

One precision worth stating up front: $\sigma_p^2$ is *variance* — symmetric bumpiness — not drawdown itself. The two are related but not the same. Two portfolios can share the same variance yet have very different *left tails*, and it is the deep left-tail loss — the path that forces the portfolio to climb out of a hole — that does the lasting damage to compounding. Variance is the tractable proxy the equation gives us; the true target is the drawdown. That distinction is why Section 3 also states the problem in a drawdown-first form, and why, as Section 4 shows, reducing variance alone does not by itself single out the convexity sleeve.

---

## 2. From wealth growth to portfolio weights

Total wealth at time $t$ is $W_t$. The portfolio divides that wealth into sleeves:

$$
W_{growth,t} + W_{convex,t} + W_{duration,t} = W_t
$$

Divide every term by total wealth:

$$
\frac{W_{growth,t}}{W_t} + \frac{W_{convex,t}}{W_t} + \frac{W_{duration,t}}{W_t} = 1
$$

Define lowercase $w$ as the share of total wealth assigned to each sleeve:

$$
w_{growth}=\frac{W_{growth,t}}{W_t}
$$

$$
w_{convex}=\frac{W_{convex,t}}{W_t}
$$

$$
w_{duration}=\frac{W_{duration,t}}{W_t}
$$

Therefore:

$$
\boxed{w_{growth}+w_{convex}+w_{duration}=1}
$$

Capital $W$ means dollars of wealth. Lowercase $w$ means a portfolio weight, or share of total wealth.

The dollar amount in each sleeve is then:

$$
W_{growth,t}=w_{growth}W_t
$$

$$
W_{convex,t}=w_{convex}W_t
$$

$$
W_{duration,t}=w_{duration}W_t
$$

---

## 3. The portfolio growth equation

Let the vector of sleeve weights be:

$$
w = [w_{growth}, w_{convex}, w_{duration}]'
$$

Let $\mu$ be the vector of expected returns for the three sleeves, and let $\Sigma$ be the covariance matrix among them.

Portfolio expected return is:

$$
\mu_p = w'\mu
$$

Portfolio variance is:

$$
\sigma_p^2 = w'\Sigma w
$$

Substitute those into the growth equation:

$$
\boxed{g(w) \approx w'\mu - \frac{1}{2}w'\Sigma w}
$$

This is the formal portfolio problem. The portfolio must seek enough expected return while controlling the variance and covariance penalty that damages compounded growth.

The mathematical objective can be written two ways.

**Growth-first form:**

$$
\max_w \quad g(w) \approx w'\mu - \frac{1}{2}w'\Sigma w
$$

subject to:

$$
w_{growth}+w_{convex}+w_{duration}=1, \quad w_i \ge 0
$$

**Drawdown-first form:**

$$
\min_w \quad \text{expected maximum drawdown}
$$

subject to:

$$
g(w) \ge g^* - \epsilon
$$

and:

$$
w_{growth}+w_{convex}+w_{duration}=1, \quad w_i \ge 0
$$

The second form is often the better framing for conservative investors and retirees. It says: preserve most of the expected compounded growth, but remove as much catastrophic drawdown risk as possible.

---

## 4. Deriving the three sleeves from first principles

The three sleeves should not appear by assertion. They follow from the growth equation.

The equation says:

$$
g \approx \mu_p - \frac{1}{2}\sigma_p^2
$$

That gives the portfolio two simultaneous requirements:

1. Raise $\mu_p$, the expected return.
2. Reduce the volatility and drawdown penalty, $\frac{1}{2}\sigma_p^2$.

A portfolio with only safe assets may reduce volatility, but it may not create enough long-run growth. A portfolio with only stocks may raise expected return, but it can create deep drawdowns that damage compounding. Therefore, the portfolio needs a return engine and more than one form of protection.

### What the growth equation settles — and what it does not

It is worth being precise about how much of the three-sleeve structure actually follows from the equation, because the equation alone does not get all the way there.

What it settles directly: the portfolio needs a **return engine** to raise $\mu_p$, and it needs to **reduce the penalty term**. That much is unavoidable.

What it does *not* settle: the equation does not, by itself, single out **convexity**. Cash and high-quality bonds also reduce $\sigma_p^2$ — so a pure mean-variance reading would be satisfied by simply holding more bonds or cash. Two facts that live *outside* the mean-variance approximation are what justify a distinct convexity sleeve:

1. **Drawdown is asymmetric; variance is not.** $\sigma_p^2$ penalizes bumpiness symmetrically and cannot distinguish two portfolios with the same variance but very different left tails. What damages compounding is the left-tail loss, so the relevant objective is closer to the drawdown-first form of Section 3 than to variance alone — and reducing left-tail risk is a job for an asset whose payoff is convex, not merely low-variance.
2. **No single hedge covers every regime.** Duration reduces the penalty in recession/deflation shocks but can *fail* in inflation/rate shocks, where stocks and bonds fall together. Reducing the penalty *across regimes* therefore requires a second, differently-behaved hedge.

So the three-sleeve split is the growth equation **plus a regime argument**: the equation says *hold a return engine and reduce the penalty*; the left-tail and regime facts below say *which hedges, and why more than one*. The sleeves are the minimal structure that satisfies both — not a conclusion the variance term reaches on its own.

### Sleeve 1: Equity / Growth

The first required sleeve is the return engine.

Growth assets, primarily equities, are included because they are the main source of long-run expected return. This sleeve exists to raise $\mu_p$. Without it, the portfolio may be stable, but it is unlikely to compound wealth aggressively enough over long horizons.

### Sleeve 2: Duration

Growth creates drawdown risk. The portfolio therefore needs an asset that can help when stocks fall because growth is weakening, recession risk is rising, or deflationary pressure appears.

High-quality duration, especially Treasuries, can serve this role. In recession or deflation panics, investors often seek safety and interest rates may fall. That can cause Treasury prices to rise while equities fall.

Duration exists to reduce the volatility and drawdown penalty in recession and deflation shocks.

### Sleeve 3: Convexity

Duration is powerful, but it is not universal protection. It can fail when the shock is inflation, rising rates, currency stress, commodity stress, or a trend-driven market dislocation. In those regimes, stocks and bonds can sometimes fall together.

The portfolio therefore needs a third payoff source that does not depend only on falling interest rates.

Convexity, usually implemented through trend-following or managed futures, seeks to benefit from large persistent moves across asset classes. It may help during inflation, rate, commodity, currency, or prolonged equity-trend shocks.

Convexity exists to reduce the left-tail penalty in regimes where traditional stock-bond diversification may not be enough.

### The first-principles result

The three-sleeve structure is the minimal practical architecture implied by the growth equation:

| Need from the growth equation | Portfolio job | Sleeve |
|---|---|---|
| Raise expected return $\mu_p$ | Return engine | Equity / Growth |
| Reduce drawdown in recession or deflation shocks | Deflation-crash hedge | Duration |
| Reduce drawdown when stocks and bonds may fail together | Trend/inflation-shock hedge | Convexity |

So the portfolio becomes:

$$
\boxed{w_{growth}+w_{convex}+w_{duration}=1}
$$

In plain English:

**Growth drives wealth creation. Duration protects against recession and deflation shocks. Convexity protects against inflation, rate, trend, and nontraditional shocks.**

Together, the three sleeves seek to preserve the compounding engine while reducing the drawdown penalty that interrupts long-run wealth creation.

---

## 5. Sleeve breakdown

### A. Equity / Growth sleeve

**Primary job:** drive long-run expected return.

**Why it exists:** the growth equation requires a positive return engine. Equity ownership is the main engine for long-term real wealth creation.

**Common components:**

| Component | Role | Illustrative examples |
|---|---|---|
| U.S. large-cap core | Main equity engine | broad U.S. index ETFs or mutual funds |
| International equity | Geographic and currency diversification | developed and emerging-market equity funds |
| Small-cap value / quality tilt | Factor diversification and potential return enhancement | small value, quality, profitability, or value-tilted funds |
| Low-volatility equity | Lower-volatility equity exposure | minimum-volatility or low-volatility equity funds |

**Design principles:**

- Keep Equity large enough to drive long-term compounding.
- Avoid making Equity so large that drawdown risk dominates the portfolio.
- Diversify the equity sleeve by geography, size, and factor exposure where practical.
- Use low-cost, broad funds unless there is a clear reason to use a specialized exposure.

**Typical total-portfolio range:** 50% to 85%, depending on age, risk tolerance, income needs, and sequence-of-returns risk.

---

### B. Convexity sleeve

**Primary job:** protect against large, persistent, nontraditional market shocks.

**Why it exists:** Duration does not protect every regime. Convexity is designed to help when inflation, rates, commodities, currencies, or persistent market trends create stress that traditional stock-bond portfolios may not handle well.

**Kinds of convexity assets:**

| Convexity type | Role | Best use | Caution |
|---|---|---|---|
| Managed futures / trend-following | Primary crisis-alpha exposure | sustained trends across equities, bonds, currencies, and commodities | can lose in choppy, trendless markets |
| Explicit option hedges | Direct tail-risk protection | sudden equity crashes | premium cost can drag returns |
| Put-spread or tail-risk funds | Packaged option protection | investors who want explicit crash insurance | structure, cost, and timing matter |
| Commodity trend exposure | Inflation and commodity-shock support | inflation/rate/commodity regimes | static commodities can underperform for long periods |
| Long-volatility exposure | volatility-spike protection | acute volatility shocks | high carry/roll cost; usually not a DIY core holding |
| Rebalancing convexity | portfolio-level buy-low/sell-high effect | volatile, mean-reverting markets | requires discipline; not a standalone crash hedge |
| Liquidity optionality | ability to buy distressed assets | crises and forced-selling environments | low expected return if held in excess |

**Design principles:**

- Use managed futures or trend-following as the primary practical Convexity exposure.
- Treat explicit options and long-volatility products as specialized tools, not default core holdings.
- Do not own so much insurance that the insurance cost overwhelms the return engine.
- Expect long stretches of underperformance; convexity is often least popular before it is most useful.

**Typical total-portfolio range:** 5% to 25%. For many risk-adjusted compounding portfolios, 10% to 20% is a practical range.

---

### C. Duration sleeve

**Primary job:** protect against recession, deflation, and flight-to-quality shocks.

**Why it exists:** Growth assets can suffer deeply when the economy contracts or investors de-risk. High-quality duration can provide ballast when interest rates fall and Treasury prices rise.

**Common components:**

| Component | Role | Caution |
|---|---|---|
| Intermediate Treasuries | core duration ballast | less crisis sensitivity than long Treasuries |
| Long Treasuries | stronger recession/deflation hedge | higher rate sensitivity; can fall sharply when rates rise |
| Treasury STRIPS | very high duration exposure | extreme interest-rate sensitivity |
| T-bills / money-market funds | liquidity, stability, volatility-brake parking | limited upside in deflationary crashes |
| Municipal bonds | taxable-account income substitute | weaker flight-to-quality hedge than Treasuries; tax rules vary |

**Design principles:**

- Use high-quality bonds for true defensive ballast.
- Recognize that Duration is not a universal hedge; it can fail in inflation/rising-rate regimes.
- Match duration length to risk tolerance: intermediate duration is steadier; long duration gives more crisis sensitivity but more rate risk.
- For retirees, treat short Treasuries or money-market funds as part of liquidity and sequence-risk management.

**Typical total-portfolio range:** 10% to 35%, depending on risk profile and spending needs.

---

## 6. Should Duration be folded into Convexity?

Technically, Duration has convex properties. Bond prices respond nonlinearly to changes in yields, and long-duration Treasuries can be powerful in recession or deflation panics.

However, for portfolio design, Duration should usually remain separate from Convexity.

| Question | Keep separate | Fold together |
|---|---|---|
| Educational clarity | better | weaker |
| Regime clarity | better | weaker |
| Allocation control | better | weaker |
| Simplicity | slightly less simple | simpler |
| Best for DIY guide | yes | usually no |

The reason is that Duration and Convexity protect different regimes.

**Duration** is the recession/deflation hedge.

**Convexity** is the trend/inflation/rate-shock hedge.

They are both defensive, but they are not the same defense. Keeping them separate makes the framework easier to understand and more robust to different crash types.

Best formulation:

$$
\boxed{\text{Equity = return engine}}
$$

$$
\boxed{\text{Duration = recession/deflation hedge}}
$$

$$
\boxed{\text{Convexity = trend/inflation-shock hedge}}
$$

---

## 7. Allocation by investor profile

These are educational model allocations, not personalized recommendations. The right allocation depends on income needs, pension/Social Security coverage, account type, taxes, risk tolerance, time horizon, and ability to stay invested during stress.

| Investor profile | Main risk | Equity / Growth | Convexity | Duration | Rationale |
|---|---:|---:|---:|---:|---|
| Young aggressive accumulator | Under-compounding over a long horizon | 80% | 10% | 10% | Highest growth engine; small ballast helps behavior and crisis control. |
| Young risk-aware accumulator | Growth with better drawdown control | 75% | 10% | 15% | Growth-heavy, with more ballast for severe bear markets. |
| Middle-aged balanced investor | Balancing compounding and capital preservation | 65% | 15% | 20% | Core balance: compounding engine plus left-tail protection. |
| Pre-retirement investor | Approaching sequence-of-returns risk | 60% | 20% | 20% | More Convexity as sequence risk approaches; still growth-oriented. |
| Retired, sequence-risk aware | Early retirement drawdown risk | 50% | 20% | 30% | Lower Equity; more defense against forced selling during withdrawals. |
| Retired, highly conservative | Spending stability and capital preservation | 45% | 20% | 35% | Greater ballast and lower upside; requires funded-plan confirmation. |

### Sequence-of-returns risk

Sequence-of-returns risk is the risk that poor market returns occur early in retirement, while the investor is withdrawing from the portfolio. The same average return can produce very different outcomes depending on the order of returns.

For an accumulator, a bear market can be an opportunity because contributions buy assets at lower prices. For a retiree, the same bear market can be dangerous because withdrawals force the sale of depressed assets. That permanently reduces the capital base available for recovery.

Therefore, retirement portfolios usually need more attention to maximum drawdown, liquidity, and withdrawal timing than accumulation portfolios.

Practical retirement principles:

- Hold enough liquid reserves to avoid forced selling during a major drawdown.
- Keep enough Equity to preserve long-term purchasing power.
- Use Duration for recession/deflation shocks.
- Use Convexity for inflation, rate, commodity, and trend shocks.
- Rebalance from appreciated defensive sleeves into depressed Growth assets when policy rules allow.
- Consider gradually increasing Equity later in retirement if sequence risk has passed and the plan remains well funded.

---

## 8. Practical allocation ranges

The following ranges are a useful planning map:

| Risk posture | Equity / Growth | Convexity | Duration | Comment |
|---|---:|---:|---:|---|
| Growth-oriented | 70% to 85% | 5% to 10% | 5% to 20% | high compounding potential, higher drawdown |
| Balanced risk-adjusted compounding | 60% to 70% | 10% to 20% | 15% to 25% | best general-purpose range |
| Drawdown-controlled | 50% to 60% | 15% to 25% | 20% to 30% | suitable near retirement or for moderate withdrawals |
| Conservative income-oriented | 40% to 55% | 15% to 25% | 30% to 40% | lower expected growth, lower drawdown target |

A practical default is:

$$
\boxed{65\%\ \text{Equity} + 15\%\ \text{Convexity} + 20\%\ \text{Duration}}
$$

A more drawdown-controlled version is:

$$
\boxed{60\%\ \text{Equity} + 20\%\ \text{Convexity} + 20\%\ \text{Duration}}
$$

A sequence-risk-aware retirement version is:

$$
\boxed{50\%\ \text{Equity} + 20\%\ \text{Convexity} + 30\%\ \text{Duration}}
$$

---

## 9. Operating rules

A first-principles framework is only useful if it can be operated consistently.

**Rule 1: Define the objective.**

Use either:

$$
\max g(w)
$$

or:

$$
\min \text{drawdown subject to acceptable } g(w)
$$

For retirees, the second formulation is usually more appropriate.

**Rule 2: Keep the sleeves distinct.**

Equity, Convexity, and Duration have different jobs. Do not judge each sleeve by the same standard. Equity should lead in bull markets. Duration should help in recession/deflation shocks. Convexity should help in persistent dislocations and some regimes where bonds fail.

**Rule 3: Rebalance with discipline.**

Rebalancing is how the portfolio harvests diversification. In a crisis, the hedge that paid off may be trimmed and the beaten-down return engine may be replenished.

**Rule 4: Do not overbuy insurance.**

Too little protection leaves the portfolio exposed to catastrophic loss. Too much protection can starve the return engine. The goal is not maximum protection. The goal is enough protection to preserve compounding.

**Rule 5: Respect taxes and account location.**

Taxable accounts often favor broad equity ETFs and tax-efficient instruments. Retirement accounts are often better places for tax-inefficient trend-following funds and Treasury income. Account placement can materially affect after-tax compounding.

**Rule 6: Use liquidity deliberately.**

Cash and T-bills are not high-return assets, but they reduce forced-selling risk and create optionality. For retirees, liquidity is part of the risk-control system.

---

## 10. Summary

The framework begins with wealth:

$$
W_{t+1}=W_t(1+R_{p,t+1})
$$

Compounding leads to the growth equation:

$$
g \approx \mu_p - \frac{1}{2}\sigma_p^2
$$

Plain English:

$$
\text{long-run wealth growth} \approx \text{average return} - \text{volatility penalty}
$$

That equation implies a portfolio design problem. The investor needs enough return to compound, but not so much unprotected risk that drawdowns damage the compounding process.

That leads to three sleeves:

$$
w_{growth}+w_{convex}+w_{duration}=1
$$

**Equity / Growth** raises expected return.

**Duration** protects against recession and deflation shocks.

**Convexity** protects against trend, inflation, rate, commodity, and nontraditional shocks.

The result is not a guarantee and not a single perfect allocation. It is a first-principles method for organizing investment wealth around risk-adjusted compounding.

The central objective is:

**Preserve the return engine while reducing the deep drawdowns that interrupt compounding.**
