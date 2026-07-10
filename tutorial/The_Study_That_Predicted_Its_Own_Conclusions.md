# The Study That Predicted Its Own Conclusions

*Third in a series. The first argued for reading CAPE as a thermometer, not a timer. The second built the three-sleeve portfolio and separated the costs a strategy must pay from the costs an implementation chooses to pay. This one is about what happened when I put two of my own instincts on trial.*

---

Cash showed up. It always does, eventually — a position gets called away, a distribution lands, a sale closes — and it arrives carrying two questions that feel equally important. *When* should this money go into the market? And *where*, exactly, should it go?

I have spent twenty-five years accumulating opinions about both. I watched a company I built get sold into the very top of the dot-com bubble, in March of 2000, and that experience installed a permanent reflex: surely you don't just *put it all in*. Surely you wait for a dip, watch a signal, respect the thermometer. And surely, once you do deploy, the choice of vehicle matters — small value over the index, this fund over that one. Opinions are cheap, though. So this summer I did something different: I wrote both questions down as formal hypotheses, specified the tests before touching the data, froze the parameters, and let the machinery run each test against out-of-sample history exactly once.

The unusual part — the part this essay is named for — is that for the second study I wrote the conclusions *first*. Before a single result existed, the design document contained a section titled "The honest headline, written in advance," predicting what the data would and would not be able to say. Then the study ran, and the pre-written headline survived contact with the data in every clause. I want to explain why that isn't cheating. It is, I've come to think, the whole discipline.

## When: the question the data could answer

The first study was a stress test of a famous Vanguard result — that lump-sum investing beats dollar-cost averaging about two-thirds of the time — using every improvement I could throw at it. Fourteen deployment strategies: moving-average gates, oversold accelerators, credit-spread triggers, yield-curve signals, a valuation brake, a regime-detecting hidden Markov model, and ensembles of all of them. Twenty-seven years of data to tune on. A frozen, untouched 2020–2026 window to test on — a window that conveniently contained a crash, an inflation bear, and a melt-up.

Nothing worked. Not one strategy beat putting the money in on day one, and thirteen of fourteen lagged it outright, by roughly 75 to 360 basis points of terminal wealth per one-year episode. The Vanguard two-thirds figure reproduced almost exactly. Even in-sample — with parameters selected on the very data being measured — nothing beat immediate deployment, because a short deployment window pointed at an asset with positive drift is a cash-drag machine, and twenty-seven years of history already knew it.

Timing paid exactly once: the twelve episodes that began in 2022, when the market fell straight through the deployment window. That is the textbook case where averaging in wins, it happened, and the other fifty-five episodes took the winnings back with interest. What waiting *reliably* bought was about two points of shallower drawdown on the arriving cash — real, measurable, and honestly described as an insurance premium rather than a return. If you want that insurance, plain dollar-cost averaging over a short window is the cheapest way to buy it. The signal-gated versions were the worst of both worlds: they paid the drag and missed the re-entries.

For someone whose founding memory is selling into March 2000, "deploy on receipt" is an uncomfortable verdict. That discomfort is precisely why the study was worth running. My reflex was built from one data point; the test used eight hundred.

## Where: the question that had to be split in three

The second study looked symmetric — same machinery, new question — and it was nothing of the kind. Before designing it I ran the arithmetic every backtest quietly skips: given how much a candidate fund's returns wander from the benchmark's, how large would a true advantage have to be before this much history could detect it?

The answer restructured the entire study. To reliably detect a two-percent-a-year edge in a fund that tracks eight points away from the index, you need on the order of a century of data. A six-year live comparison can only detect advantages so large that no serious equity fund plausibly has them. Which means the popular pastime — lining up ETFs over the last five years and crowning a winner — is not a lax test. It is not a test at all.

So "does the destination matter" became three questions at three scales, each assigned the strongest verdict the evidence could actually support. Does the *asset class* matter — stocks versus bonds versus cash? Enormously, and formally: on nearly a century of data, parking a deployed dollar in Treasury bills instead of equities cost about six and a half percent per year, and no correction for multiple comparisons dents it. Does the choice *among broad equity funds* matter — total market, international, equal-weight, low-volatility? Here the honest answer is that the data cannot rank them, and the study was designed to say so rather than manufacture a verdict: the statistical machinery kept all six candidates as indistinguishable, exactly as the power arithmetic predicted before any data was touched. And do *factor tilts* matter — the value, size, and momentum premia? At the scale of a century, yes: momentum and small-cap value survive every family-wide correction I could apply. Over their six live years as actual funds, they delivered winter — negative relative returns and tracking drag — which is not a refutation of a hundred-year premium, but is a fair price quote on the patience required to hold one.

## Why writing the headline first isn't cheating

Predicting your conclusions sounds like the definition of bias. It is the opposite, for one reason: the prediction was falsifiable and the protocol was frozen. The pre-written headline said the asset-class test would reject, the broad-equity test would come back unrankable, and the factor test would split between its century-scale and live-scale answers. Every one of those clauses could have died. Had a deployment signal cleared its corrected threshold, had a broad fund separated from the pack, the headline would have been wrong in public, inside my own document, with the parameters already locked so I could not quietly re-tune my way to agreement.

Most backtests run the ritual in reverse — compute first, then write a story that fits, then call the story a finding. Writing the conclusion first, as a hypothesis with named failure conditions, is what turns a backtest into an experiment. The value isn't being right. The value is that being wrong was allowed to happen and didn't.

## What the two studies say together

Composed, the verdicts fit in one sentence: **when you deploy doesn't matter — deploy on receipt — and where you deploy is a policy decision, not a horse race.** The only destination choice the data can formally defend is the asset-class weight: how much of the portfolio is doing the compounding, how much is built to pay off when things break, how much funds next year's groceries. That is the three-sleeve question, and it belongs to written policy, revisited on a thermometer's schedule — not to a leaderboard of five-year fund returns. Within the sleeves, differences among sensible funds are real but small relative to their noise, which means they should be chosen on cost, breadth, and the evidence behind their tilt, then left alone for a very long time.

There is a quieter lesson underneath, and it may be the more useful one: knowing which questions your data can answer is itself the skill. The timing question was answerable, and the answer contradicted my oldest instinct. The fund-picking question was mostly unanswerable, and pretending otherwise is how an industry sells horse races. The rarest output of a quantitative study is a confident *"this cannot be known from this data"* — and it is worth more than most findings, because it tells you where conviction must come from structure rather than statistics.

## What would change my mind

Good frameworks state their failure conditions. Deploy-on-receipt inherits the equity premium as an assumption; a world of durably negative real expected equity returns would retire it. The unrankability of broad funds is a statement about sample sizes, not metaphysics; another few decades of divergence would sharpen it. And the factor verdict is only as strong as its cost model — the momentum premium survives today's expense ratios, but a full accounting of turnover compresses it, and I hold the live-fund winter as evidence that the compression is real.

## The bottom line

I put two instincts on trial. The one that felt like wisdom — wait for your moment — lost. The one that felt like diligence — find the best fund — turned out to be a question the data mostly can't adjudicate, which is its own kind of verdict. What survived both trials is the thing I keep arriving at from every direction: a portfolio with a good shape beats a portfolio with a good forecast, and the shape is decided by policy, in writing, in advance — headline first.

---

*This reflects my personal approach to our own portfolio and is not investment advice. Everyone's spending needs, tax situation, and risk tolerance differ.*
