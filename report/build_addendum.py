#!/usr/bin/env python3
"""Build the Statistical-Robustness Addendum (DSR & PBO) — a standalone companion
document to the v1.0.2 paper. The paper itself is NOT modified.

Reads workspace/pub_report/dsr_pbo.json (produced by
etf-trade-classifier/scripts/research/pub_tier2/run_dsr_pbo.py), renders an HTML
in the paper's house style, and prints a PDF with headless Chromium (Playwright).

  python scripts/build_addendum.py
Output: ~/DNSR_Convex_Core_Addendum_DSR_PBO_2026-06-14.{html,pdf}
"""
from __future__ import annotations
import json, os
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "results", "dsr_pbo.json")
OUT_HTML = os.path.join(REPO, "paper", "DNSR_Convex_Core_Addendum_DSR_PBO_REGENERATED.html")
OUT_PDF = OUT_HTML[:-5] + ".pdf"
REPO_URL = "https://github.com/DNSReeves/convex-core-paper"
CONCEPT_DOI = "10.5281/zenodo.20693931"

PRINCIPAL = "David Reeves"; ENTITY = "DNSR Investments, LLC"
LINKEDIN_URL = "https://www.linkedin.com/in/david-reeves-8a664524"
def principal_credit():
    return f'<a href="{LINKEDIN_URL}">{PRINCIPAL}, {ENTITY}</a>'

D = json.load(open(DATA))
M, DSR, PBO = D["meta"], D["dsr"], D["pbo"]
trials = D["trials"]
srs = {k: v["sharpe_annualized"] for k, v in trials.items()}
arr = np.array(list(srs.values()))
dep_lbl = f"we{M['deployed']['w_equity']:.2f}_vt{M['deployed']['vol_target']:.2f}"
ranked = sorted(srs, key=lambda k: -srs[k])
dep_rank = ranked.index(dep_lbl) + 1
cov = arr.std() / arr.mean() * 100

def pct(x, d=1): return f"{x*100:.{d}f}%"

# ---------- house style (verbatim from build_pub_report.py) --------------------
CSS = """
 body{font-family:Georgia,'Times New Roman',serif;max-width:900px;margin:34px auto;color:#1a1a1a;line-height:1.55;padding:0 30px}
 h1{font-size:25px;margin:0 0 4px} h2{font-size:18px;border-bottom:2px solid #1f77b4;padding-bottom:4px;margin-top:34px;color:#143d66}
 h3{font-size:14.5px;margin:18px 0 4px;color:#143d66} .sub{color:#555;font-size:14px} .auth{color:#333;font-size:13px;margin:6px 0}
 table{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0;font-family:Helvetica,Arial,sans-serif}
 th,td{border:1px solid #ccc;padding:5px 7px;text-align:center} th{background:#143d66;color:#fff} td:first-child{text-align:left}
 .cap{font-size:11.5px;color:#666;text-align:center;margin:-6px 0 18px}
 .abs{background:#f4f7fb;border-left:4px solid #1f77b4;padding:12px 16px;font-size:13.5px}
 .disc{font-size:11px;color:#777;border-top:1px solid #ccc;margin-top:30px;padding-top:10px}
 code{background:#eef;padding:1px 4px;border-radius:3px;font-size:12px} ul{margin:6px 0 6px 18px} li{margin:3px 0}
 pre{background:#0f1720;color:#cfe;padding:12px 14px;border-radius:6px;font-size:11px;overflow-x:auto;line-height:1.4}
 .key{background:#eef7f0;border-left:4px solid #2ca02c;padding:10px 16px;font-size:13px;margin:12px 0}
 .kicker{letter-spacing:2px;font-size:10.5px;color:#1f77b4;font-family:Helvetica,Arial,sans-serif;text-transform:uppercase}
 @media print { h2{page-break-after:avoid} table{page-break-inside:avoid} }
"""

P = []
P.append(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Convex Core — Statistical-Robustness Addendum (DSR & PBO)</title><style>{CSS}</style></head><body>""")

# ---- header -------------------------------------------------------------------
P.append(f"""
<div class="kicker">Companion Addendum · Statistical Robustness</div>
<h1>Deflated Sharpe Ratio &amp; Probability of Backtest Overfitting</h1>
<div class="sub">A companion to <i>Convex Core and the DNSR Model Suite: A Deterministic ETF Allocation
Framework for Drawdown-Controlled Compounding</i></div>
<div class="auth"><b>Principal:</b> {principal_credit()} · Houston, Texas · June 2026<br>
<b>Research system:</b> the DNSR Agentic AI pipeline, directed and reviewed by the principal.
No large-language model participates in the portfolio math.</div>
<p style="font-size:12px;color:#555"><b>Scope.</b> This addendum is a standalone supplement. <b>The v1.0.2 paper is
unchanged.</b> It is distributed with the same reproducibility companion
(<a href="{REPO_URL}">{REPO_URL}</a>, concept DOI <code>{CONCEPT_DOI}</code>) and addresses the single piece
of future work the review board left open: quantifying how much of Convex Core's risk-adjusted record could be a
multiple-testing or backtest-overfitting artifact.</p>
""")

# ---- abstract -----------------------------------------------------------------
P.append(f"""
<div class="abs"><b>Summary.</b> Treating the model's two continuous dials
(<code>w_equity</code> × <code>vol_target</code>, {M['panel']['N_trials']} configurations) as the trial set over a
{M['panel']['T_months']}-month panel ({M['panel']['start']} → {M['panel']['end']}), the deployed configuration's Sharpe
survives multiple-testing deflation overwhelmingly: <b>Deflated Sharpe Ratio = {DSR['deflated_sharpe_ratio']:.5f}</b>
(minimum track record ≈ {DSR['min_track_record_length_months_95']:.0f} months vs. {M['panel']['T_months']} available).
The configurations are near-identical (annualized-Sharpe coefficient of variation {cov:.1f}%), and the
<b>deployed configuration ranks {dep_rank}ᵗʰ of {M['panel']['N_trials']}</b> on Sharpe — it was chosen by a-priori risk
posture, not by maximizing the backtest, so selection bias cannot have inflated it. The CSCV
<b>Probability of Backtest Overfitting = {PBO['pbo']:.2f}</b> reflects that the dials are not meaningfully
distinguishable in-sample (selecting a "best" dial is sampling noise), while every selected configuration remains
profitable out-of-sample in 100% of {PBO['n_splits']:,} splits. The diagnostics corroborate the paper's
parameter-minimal, deterministic design rather than revealing a tuned edge.</div>
""")

# ---- A1 motivation ------------------------------------------------------------
P.append(f"""
<h2>A1 · Why this test</h2>
<p>A backtest's Sharpe ratio can be inflated two ways that have nothing to do with genuine edge: by <b>selection</b>
(trying many configurations and reporting the luckiest) and by <b>non-normality</b> (fat tails and skew that make a
given Sharpe less informative than the Gaussian assumption implies). The paper's defense is structural — the model is
deterministic, its parameters fixed a-priori, and its negative results published — but the review board asked for the
quantitative complement: the <b>Deflated Sharpe Ratio (DSR)</b>, which discounts the observed Sharpe for both the number
of trials and the return distribution's shape, and the <b>Probability of Backtest Overfitting (PBO)</b>, which measures
whether choosing the in-sample-best configuration generalizes out-of-sample.</p>
""")

# ---- A2 method ----------------------------------------------------------------
P.append(f"""
<h2>A2 · Method</h2>
<h3>Trial set</h3>
<p>The honest count of "trials" is the model's genuine search space. Convex Core exposes two continuous dials — the
equity-weight target <code>w_equity</code> and the volatility target <code>vol_target</code>. We sweep
<code>w_equity ∈ {{{', '.join(f'{x:.2f}' for x in M['w_equity_grid'])}}}</code> ×
<code>vol_target ∈ {{{', '.join(f'{x:.2f}' for x in M['vol_target_grid'])}}}</code> =
{M['panel']['N_trials']} configurations, each run through the <i>same</i> deterministic engine (same regime layer,
sleeves, brake, and costs) and reduced to a monthly total-return stream. The deployed paper configuration is
(<code>w_equity={M['deployed']['w_equity']}</code>, <code>vol_target={M['deployed']['vol_target']}</code>). All
{M['panel']['N_trials']} streams share a common {M['panel']['T_months']}-month window.</p>
<h3>Deflated Sharpe Ratio</h3>
<p>The DSR is the probability that the deployed configuration's <i>true</i> Sharpe exceeds the
<i>expected maximum Sharpe under the null</i> that no configuration has skill — where that expected maximum grows with
the number of trials and the dispersion of Sharpe across them — evaluated through the Probabilistic Sharpe Ratio, which
corrects for the sample's skewness and kurtosis and length. DSR &gt; 0.95 means the result survives the
multiple-testing penalty. (Bailey &amp; López de Prado, 2014.)</p>
<h3>Probability of Backtest Overfitting (CSCV)</h3>
<p>Combinatorially-Symmetric Cross-Validation splits the {M['panel']['T_months']}-month panel into
{PBO['S_blocks']} contiguous blocks of {PBO['block_len_months']} months. For every one of the
{PBO['n_splits']:,} symmetric ways to assign half the blocks in-sample and half out-of-sample, it selects the
configuration with the best in-sample Sharpe and records that configuration's out-of-sample rank. <b>PBO</b> is the
fraction of splits in which the in-sample winner lands below the out-of-sample median. (Bailey, Borwein,
López de Prado &amp; Zhu, 2017.)</p>
""")

# ---- A3 DSR result ------------------------------------------------------------
P.append(f"""
<h2>A3 · Result — parameter insensitivity and the Deflated Sharpe Ratio</h2>
<p>Across the entire {M['panel']['N_trials']}-configuration grid the annualized Sharpe spans only
{arr.min():.3f}–{arr.max():.3f} (mean {arr.mean():.3f}, standard deviation {arr.std():.3f}, coefficient of variation
<b>{cov:.1f}%</b>). The model is strikingly insensitive to its dials: there is no poor configuration to avoid and no
standout configuration to cherry-pick. Tellingly, the <b>deployed configuration ranks {dep_rank}ᵗʰ of
{M['panel']['N_trials']}</b> — near the bottom on Sharpe — because <code>w_equity=0.95</code> was selected for
accumulation-phase upside capture (an a-priori risk-posture choice), not to flatter the backtest.</p>
<table>
<tr><th>Quantity</th><th>Value</th></tr>
<tr><td>Deployed configuration</td><td>w_equity {M['deployed']['w_equity']}, vol_target {M['deployed']['vol_target']}</td></tr>
<tr><td>Observations (months)</td><td>{DSR['T_months']}</td></tr>
<tr><td>Number of trials (N)</td><td>{DSR['n_trials']}</td></tr>
<tr><td>Sharpe — monthly (annualized)</td><td>{DSR['sharpe_monthly']:.3f} ({DSR['sharpe_annualized']:.2f})</td></tr>
<tr><td>Skewness</td><td>{DSR['skew']:.2f}</td></tr>
<tr><td>Kurtosis (normal = 3)</td><td>{DSR['kurtosis']:.2f}</td></tr>
<tr><td>Variance of Sharpe across trials</td><td>{DSR['var_sharpe_across_trials']:.2e}</td></tr>
<tr><td>Expected max Sharpe under null — annualized</td><td>{DSR['expected_max_sharpe_null_annualized']:.3f}</td></tr>
<tr><td>Probabilistic Sharpe vs. 0</td><td>{DSR['psr_vs_zero']:.5f}</td></tr>
<tr><td><b>Deflated Sharpe Ratio</b></td><td><b>{DSR['deflated_sharpe_ratio']:.5f}</b></td></tr>
<tr><td>Min. track record for 95% significance</td><td>{DSR['min_track_record_length_months_95']:.0f} months</td></tr>
</table>
<div class="cap">Table 1. Deflated Sharpe Ratio for the deployed configuration. The multiplicity penalty is small
because the trials barely disperse; the near-normal shape (kurtosis {DSR['kurtosis']:.2f}, mild negative skew) leaves the
Sharpe essentially intact. DSR ≈ 1 with a {DSR['min_track_record_length_months_95']:.0f}-month minimum track record
against {DSR['T_months']} months observed.</div>
""")

# ---- A4 PBO result ------------------------------------------------------------
P.append(f"""
<h2>A4 · Result — Probability of Backtest Overfitting</h2>
<table>
<tr><th>Quantity</th><th>Value</th></tr>
<tr><td>Method</td><td>CSCV ({PBO['S_blocks']} blocks × {PBO['block_len_months']} months, {PBO['n_splits']:,} splits)</td></tr>
<tr><td><b>Probability of Backtest Overfitting</b></td><td><b>{PBO['pbo']:.3f}</b></td></tr>
<tr><td>Median OOS rank of the in-sample best (0.5 = random)</td><td>{PBO['median_oos_rank_of_is_best']:.2f}</td></tr>
<tr><td>P(selected configuration's OOS Sharpe &lt; 0)</td><td>{PBO['prob_oos_sharpe_below_zero']:.3f}</td></tr>
<tr><td>OOS-vs-IS degradation slope</td><td>{PBO['oos_is_degradation_slope']:.2f}</td></tr>
</table>
<div class="cap">Table 2. CSCV overfitting diagnostics over {PBO['months_used']} months.</div>
<p>PBO = {PBO['pbo']:.2f} reads, against a naïve &lt;0.5 rule of thumb, as a borderline figure — but the correct reading
is that it is the <b>expected null</b> here. CSCV asks whether the in-sample-best configuration generalizes; when the
configurations are near-identical (Sharpe CoV {cov:.1f}%, Table 1), there is no genuinely-best configuration to identify,
so the in-sample winner is chosen by sampling noise and lands near the out-of-sample median by construction (median OOS
rank {PBO['median_oos_rank_of_is_best']:.2f}). The diagnostic that actually carries signal is the out-of-sample outcome
of the selected configuration: it is <b>profitable in 100% of the {PBO['n_splits']:,} splits</b>
(P(OOS Sharpe &lt; 0) = {PBO['prob_oos_sharpe_below_zero']:.3f}). The mildly negative degradation slope
({PBO['oos_is_degradation_slope']:.2f}) is precisely why the model fixes its dials a-priori instead of optimizing them —
chasing the highest in-sample Sharpe hands a little back out-of-sample. None of this is overfitting in the sense PBO was
designed to expose (a tuned strategy that collapses out-of-sample); it is the fingerprint of a parameter-insensitive
design.</p>
""")

# ---- A5 interpretation --------------------------------------------------------
P.append(f"""
<h2>A5 · Interpretation — what this does and does not establish</h2>
<div class="key"><b>It establishes:</b> (1) the deployed Sharpe is not a multiple-testing illusion — it survives
deflation with a {DSR['min_track_record_length_months_95']:.0f}-month minimum track record against {DSR['T_months']}
months of data; (2) the model is parameter-insensitive over its dial space ({cov:.1f}% Sharpe CoV), so there is no
configuration-selection edge to overfit; (3) the deployment choice was not Sharpe-maximizing (rank {dep_rank}/{M['panel']['N_trials']}),
foreclosing the cherry-picking failure mode by construction; (4) across {PBO['n_splits']:,} out-of-sample folds the
family never loses money.</div>
<p><b>It does not establish</b> live performance, edge over the strongest balanced benchmark on risk-adjusted ratios
(the paper's §8 is explicit that the advantage over 40/60 is in return, not risk), or robustness to <i>structural</i>
choices outside the two dials swept here (sleeve definitions, regime cutoffs, universe) — those are probed by the §13
ablation grid and §6 walk-forward, not by this test. CSCV's PBO is also least informative exactly when trials are
near-identical, as they are here; we therefore lean on the accompanying out-of-sample loss probability and the
non-optimized deployment rank rather than the PBO point estimate alone. These results sharpen, and are consistent with,
the paper's §3.1 (determinism, no fitted parameters) and §15 (limitations).</p>
""")

# ---- reproducibility ----------------------------------------------------------
P.append(f"""
<h2>A6 · Reproducibility</h2>
<p>Computed by <code>scripts/research/pub_tier2/run_dsr_pbo.py</code> from the same deterministic engine, warehouse,
and monthly basis as the paper; the artifact is <code>results/dsr_pbo.json</code>. Re-run from the companion repository:</p>
<pre>python scripts/research/pub_tier2/run_dsr_pbo.py   # writes results/dsr_pbo.json
python report/build_addendum.py                    # renders this addendum (HTML + PDF)</pre>
<p style="font-size:12px;color:#555">References — Bailey, D. &amp; López de Prado, M. (2014), <i>The Deflated Sharpe
Ratio</i>, Journal of Portfolio Management 40(5). · Bailey, D., Borwein, J., López de Prado, M. &amp; Zhu, Q. (2017),
<i>The Probability of Backtest Overfitting</i>, Journal of Computational Finance 20(4).</p>
""")

# ---- disclaimer (verbatim) ----------------------------------------------------
P.append(f"""
<div class="disc"><b>Disclaimer.</b> This addendum presents hypothetical, backtested model performance for research and
decision-support purposes only. The results were not achieved by an actual client account and do not reflect the impact
of individual investor circumstances, taxes, custody fees, advisory fees, account restrictions, or implementation delays.
Backtested performance is inherently limited because it is constructed with the benefit of historical data and may not
reflect conditions that would have existed during live trading. Past performance does not guarantee future results. This
is not investment advice, an offer, or a solicitation. Research conducted by the DNSR Agentic AI system (with Anthropic
Fable 5 and Opus 4.8), directed and reviewed by {principal_credit()}, who is responsible for its use.
© 2026 DNSR Investments, LLC.</div>
</body></html>""")

HTML = "\n".join(P)
open(OUT_HTML, "w").write(HTML)
print("wrote", OUT_HTML, f"({len(HTML)//1024} KB)")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(); pg.goto("file://" + OUT_HTML, wait_until="networkidle")
        pg.pdf(path=OUT_PDF, format="Letter", print_background=True,
               margin={"top": "0.6in", "bottom": "0.6in", "left": "0.5in", "right": "0.5in"})
        b.close()
    print("wrote", OUT_PDF, f"({os.path.getsize(OUT_PDF)//1024} KB)")
except Exception as ex:
    print("PDF render skipped:", type(ex).__name__, str(ex)[:160])
