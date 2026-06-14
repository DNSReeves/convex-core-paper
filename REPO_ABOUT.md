# GitHub "About" metadata (apply when creating the repo)

**Description** (one line):
> Deterministic, drawdown-controlled ETF allocation framework (Convex Core) — reproducibility companion to the research paper: model engine, report code, tests, and computed result artifacts. Hypothetical/backtested; not investment advice.

**Website**: (optional) link to the principal's LinkedIn or a paper landing page.

**Topics** (14):
`quantitative-finance` `asset-allocation` `portfolio-construction` `etf`
`backtesting` `risk-management` `drawdown-control` `volatility-targeting`
`trend-following` `factor-investing` `reproducible-research` `pre-registration`
`quant` `python`

---

### Apply via `gh`

```bash
gh repo create DNSReeves/convex-core-paper --public --source=. --remote=origin --push \
  --description "Deterministic, drawdown-controlled ETF allocation framework (Convex Core) — reproducibility companion to the research paper: model engine, report code, tests, and computed result artifacts. Hypothetical/backtested; not investment advice."

gh repo edit DNSReeves/convex-core-paper \
  --add-topic quantitative-finance,asset-allocation,portfolio-construction,etf,backtesting,risk-management,drawdown-control,volatility-targeting,trend-following,factor-investing,reproducible-research,pre-registration,quant,python
```

(Or paste the Description and Topics into the repo's **About** ⚙️ panel on github.com.)
