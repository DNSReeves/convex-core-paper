# Convex Core — Reproducibility Companion

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20693931.svg)](https://doi.org/10.5281/zenodo.20693931)

Companion code and data artifacts for the research report
**“Convex Core and the DNSR Model Suite: A Deterministic ETF Allocation Framework
for Drawdown-Controlled Compounding”** ([`paper/`](paper/)).

**Principal:** David Reeves, DNSR Investments, LLC — https://www.linkedin.com/in/david-reeves-8a664524
**Research system:** the DNSR Agentic AI pipeline (with Anthropic Fable 5 and Opus 4.8),
directed and reviewed by the principal, who is responsible for its use.

> **Not investment advice.** All performance herein is *hypothetical, backtested*,
> net of modeled costs. Past performance does not guarantee future results. See the
> paper’s §15 (Limitations) and Disclaimer.

---

## Tutorials — start here for intuition

Two self-contained, visual explainers (inline-SVG charts, zero dependencies) that build an
intuitive understanding of the models *before* the formal paper:

- **[Convex Core — an intuitive tutorial](tutorial/convex_tutorial.html)** — what *convex*
  means, how it lives inside `w_equity + w_convexity + w_duration = 1`, the specific ETFs, the
  regime engine, a 20-year growth-of-$1 chart vs SPY and 60/40, and the equity-core options
  (SPY / VTI / VXUS / IWM, CAPE / valuation).
- **[Convex Prime — the leveraged sibling](tutorial/prime_tutorial.html)** — what leverage does
  to a convex payoff, how it’s sized / capped / sentiment-gated, and the honest risk/reward trade.
- **[A derivation from first principles](DERIVATION.md)** ([HTML](tutorial/convex_derivation.html)) —
  how the equation `w_equity + w_convexity + w_duration = 1` and the volatility brake follow from
  maximizing expected log-growth, with each step marked *rigorous* or *design choice* (companion to §4.1).

> GitHub serves `.html` as source. To **read them rendered**, open the files in any browser, or
> use the htmlpreview proxy —
> [▶ Core](https://htmlpreview.github.io/?https://github.com/DNSReeves/convex-core-paper/blob/main/tutorial/convex_tutorial.html)
> · [▶ Prime](https://htmlpreview.github.io/?https://github.com/DNSReeves/convex-core-paper/blob/main/tutorial/prime_tutorial.html)
> · [▶ Derivation](https://htmlpreview.github.io/?https://github.com/DNSReeves/convex-core-paper/blob/main/tutorial/convex_derivation.html).
> Educational illustrations of the model — *not investment advice*.

## Backtest position ledger — the model's full evolution, 2006→present

See *exactly* how Convex Core changed week by week — every ETF, its weight, the regime, the
volatility brake, and growth-of-$1 vs SPY — across the entire backtest. The convexity sleeve, for
instance, is empty in 2008 (those funds didn't exist yet — their weight folds into Treasuries),
appears as BTAL by 2019, and is the full DBMF/KMLM/BTAL set by 2026. Point-in-time TARGET weights,
suggest-only.

Each ledger opens to the current year for a fast first paint; pick an earlier start year or
*Full history* to extend it (Convex Core/Prime back to 2006, RACE to 2007).

- **[Convex Core ledger](results/backtest_ledger_convex.html)** — equity / convexity / duration sleeves + the volatility brake.
- **[Convex Prime ledger](results/backtest_ledger_prime.html)** — the leveraged sibling, same three sleeves.
- **[RACE ledger](results/backtest_ledger_race.html)** — the seven-sleeve Regime-Adaptive Capital Engine (US-core / factor / intl / fixed-income / real-assets / crisis-alpha / cash).

> Rendered (GitHub Pages):
> [▶ Convex Core](https://dnsreeves.github.io/convex-core-paper/results/backtest_ledger_convex.html)
> · [▶ Convex Prime](https://dnsreeves.github.io/convex-core-paper/results/backtest_ledger_prime.html)
> · [▶ RACE](https://dnsreeves.github.io/convex-core-paper/results/backtest_ledger_race.html).

---

## Why this repo exists

The paper’s central claim is methodological: a deterministic, auditable, reproducible
allocation model, validated with pre-registered tests and *published negative results*.
This repository exists so a third party can **inspect and re-run the method** rather than
take the numbers on faith. It contains the model engine, the benchmark/report code, the
computed result artifacts, and the tests — everything except the licensed vendor data
(see [Data](#data)).

## What’s included

| Path | Contents |
|---|---|
| `paper/` | The report (PDF + self-contained HTML) and the **Statistical-Robustness Addendum** — Deflated Sharpe Ratio & Probability of Backtest Overfitting (PDF + HTML). |
| `tutorial/` | **Visual, intuitive tutorials** — `convex_tutorial.html` (Convex Core) and `prime_tutorial.html` (Convex Prime). Self-contained HTML with inline-SVG figures. See [Tutorials](#tutorials--start-here-for-intuition) above. |
| `engine/tradeclassifier/` | The deterministic model engine — `convex_core.py` (the flagship) and the shared point-in-time alpha/beta/regime panel it depends on (`alpha_backtest`, `alpha`, `beta`, `features`, `optimizer`, `loaders`, `objective`, `regime`, `config`). **Zero fitted parameters; no LLM in the allocation math.** |
| `config/` | Model + regime configuration (`regime_rules.yaml`, `ira_profile.yaml`, etc.). The regime clause set is reproduced verbatim in the paper’s Appendix I. |
| `report/` | `pub_benchmarks.py` (benchmark construction + metrics + bootstrap significance), `build_pub_report.py` (assembles the paper), `run_tier2.py` (sleeve ablations + crisis attribution), `run_regime_wf.py` (regime walk-forward validation), `run_dsr_pbo.py` (deflated-Sharpe + backtest-overfitting diagnostics), `build_addendum.py` (assembles the addendum). |
| `results/` | Computed **model outputs** (not raw vendor data): `model_curves.json` (growth-of-$1 per model), `benchmarks.json`, `tier2.json`, `regime_wf.json`, `dsr_pbo.json`, `reproducibility_manifest.yaml`. These reproduce the paper’s tables/figures (and the addendum) directly. |
| `tests/` | `test_convex_core.py` — engine pins (vol brake, PIT fold, determinism, attribution non-invasiveness). |

## Data

The model is built from a local warehouse of daily ETF OHLCV and macro series sourced
from **EODHD, FMP, and FRED**. That data is **licensed and is not redistributed here.**
To rebuild it from your own vendor keys, see [`data/README.md`](data/README.md) for the
schema and the series list. The `results/*.json` artifacts let you reproduce every table
and figure in the paper **without** the raw data; the full engine run requires rebuilding
the warehouse.

## Reproducing the paper

```bash
pip install -r requirements.txt

# (1) Regenerate the paper (all tables + figures) from the shipped result
#     artifacts — NO vendor data required. Self-resolves against results/.
#     Verified: reproduces the distributed paper. Output:
#       paper/DNSR_Convex_Core_Publication_REGENERATED.html
python report/build_pub_report.py

# (1b) Regenerate the Statistical-Robustness Addendum (DSR & PBO) from
#      results/dsr_pbo.json — also NO vendor data required. Output:
#        paper/DNSR_Convex_Core_Addendum_DSR_PBO_REGENERATED.html (+ .pdf)
python report/build_addendum.py

# (2) Run the engine unit tests (synthetic data, no warehouse needed):
PYTHONPATH=engine pytest tests/

# (3) Full engine re-run from scratch — REQUIRES a rebuilt data/etf_data.db
#     (see data/README.md). These scripts read paths via the PAPER_ROOT env var:
export PAPER_ROOT=$(pwd)
python report/pub_benchmarks.py   # rebuilds results/benchmarks.json (+ bootstrap)
python report/run_tier2.py        # sleeve ablations + crisis attribution
python report/run_regime_wf.py    # regime walk-forward validation
python report/run_dsr_pbo.py      # deflated Sharpe + backtest-overfitting (DSR/PBO)
```

> **Reproducibility status.** Step (1) is self-contained and has been verified to regenerate
> the paper from the shipped `results/*.json` artifacts. Steps (3) reproduce those artifacts
> from a rebuilt warehouse; they were extracted from a larger private system and read paths
> via `PAPER_ROOT`. The PDF is produced from the HTML with a headless browser (e.g.
> Playwright/Chromium).

## Honest scope (read this)

This work claims **no novel strategy or anomaly.** Convex Core is a synthesis of
well-published premia — volatility-managed equity (Moreira & Muir 2017), crisis-alpha /
trend-following (Hurst, Ooi & Pedersen 2017), and defensive / betting-against-beta
(Frazzini & Pedersen 2014). The negative results corroborate the anomaly-replication
literature (Hou, Xue & Zhang 2020; McLean & Pontiff 2016). The contribution is
**integrative and methodological**: negative-results discipline, end-to-end determinism
and reproducibility, significance-tested and honestly-calibrated claims, and an
AI-conducted, pre-registered research process. See the paper’s §3.1.

## Citation

> Reeves, D. (DNSR Investments, LLC), with the DNSR Agentic AI system (Anthropic Fable 5 /
> Opus 4.8). *Convex Core and the DNSR Model Suite: A Deterministic ETF Allocation Framework
> for Drawdown-Controlled Compounding.* 2026.

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff) — GitHub renders a
**“Cite this repository”** button from it (APA/BibTeX export).

## License

- **Code** (engine, report/research scripts, tests): **PolyForm Noncommercial License 1.0.0** —
  source-available and fully auditable; noncommercial use permitted, commercial use requires a
  separate grant from the licensor. SPDX: `PolyForm-Noncommercial-1.0.0`. Full text in [`LICENSE`](LICENSE).
- **Paper & documentation** (`paper/`, this README, `data/README.md`): **CC BY-NC 4.0**
  (https://creativecommons.org/licenses/by-nc/4.0/).

Copyright © 2026 DNSR Investments, LLC. Licensor: David Reeves
(https://www.linkedin.com/in/david-reeves-8a664524).
