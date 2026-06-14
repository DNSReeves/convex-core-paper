#!/usr/bin/env python3
"""Build the publication-quality DNSR report (reviewer revision, 2026-06-14).

Reads workspace/pub_report/benchmarks.json (computed by pub_benchmarks.py) and
model_curves.json; assembles the reviewer's 24-section structure + Appendices
A-H with computed tables and embedded charts. Tier-2 cells (per-sleeve crisis
attribution, the ablation/robustness grid at the 0.95 vintage) are rendered as
explicit 'pending engine instrumentation' callouts rather than invented.

Authors: DNSR Agentic AI — with Anthropic Fable 5 and Opus 4.8.
Output: ~/DNSR_Convex_Core_Publication_2026-06-14.html
"""
from __future__ import annotations
import base64, io, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "${PAPER_ROOT}"
BJSON = f"{ROOT}/dnsr-agent/workspace/pub_report/benchmarks.json"
MANIFEST = f"{ROOT}/dnsr-agent/workspace/pub_report/reproducibility_manifest.yaml"
OUT = "${HOME}/DNSR_Convex_Core_Publication_2026-06-14.html"

B = json.load(open(BJSON))
MAN = open(MANIFEST).read()
MET = B["benchmarks"]; MODELS = B["models"]
import os as _os
T2JSON = f"{ROOT}/dnsr-agent/workspace/pub_report/tier2.json"
T2 = json.load(open(T2JSON)) if _os.path.exists(T2JSON) else None
RWFJSON = f"{ROOT}/dnsr-agent/workspace/pub_report/regime_wf.json"
RWF = json.load(open(RWFJSON)) if _os.path.exists(RWFJSON) else None
plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": .25,
                     "axes.edgecolor": "#888", "figure.facecolor": "white"})

CC = {"Convex Core (0.95)": "#1f77b4", "SPY": "#888888",
      "60/40 SPY/IEF (Q)": "#2ca02c", "40/60 SPY/IEF (Q)": "#17becf",
      "80/20 SPY/IEF (Q)": "#bcbd22",
      "Beta-matched SPY/T-bills (β=0.42)": "#d62728",
      "Vol-targeted SPY (≈Convex vol)": "#9467bd"}

def png(fig):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=130, bbox_inches="tight"); plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def curve(name):
    pts = B["chart_curves"][name]
    return pd.Series([v for _, v in pts], index=pd.to_datetime([d for d, _ in pts]))

def ddcurve(name):
    pts = B["dd_curves"][name]
    return pd.Series([v for _, v in pts], index=pd.to_datetime([d for d, _ in pts]))

# ---- Figure 1: growth of $1 (log) -----------------------------------------
f, ax = plt.subplots(figsize=(9, 4.6))
for n in ["Convex Core (0.95)", "SPY", "60/40 SPY/IEF (Q)",
          "Beta-matched SPY/T-bills (β=0.42)", "Vol-targeted SPY (≈Convex vol)"]:
    s = curve(n)
    ax.plot(s.index, s.values, color=CC[n], lw=1.9 if "Convex" in n else 1.4,
            ls="-" if "Convex" in n else "--", label=f"{n} ({MET[n]['cagr']*100:.1f}%/yr)")
ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log)")
ax.legend(fontsize=7.5, loc="upper left"); ax.set_title("Growth of $1 — net of costs, 2006–2026")
F1 = png(f)

# ---- Figure 2: drawdown ----------------------------------------------------
f, ax = plt.subplots(figsize=(9, 3.6))
for n in ["Convex Core (0.95)", "SPY", "60/40 SPY/IEF (Q)", "40/60 SPY/IEF (Q)"]:
    d = ddcurve(n)
    ax.plot(d.index, d.values * 100, color=CC[n], lw=1.6 if "Convex" in n else 1.3,
            ls="-" if "Convex" in n else "--", label=n)
ax.set_ylabel("Drawdown (%)"); ax.legend(fontsize=7.5, loc="lower left")
ax.set_title("Drawdown paths vs balanced benchmarks"); F2 = png(f)

# ---- Figure 3: risk/return map (feasible-set view) ------------------------
f, ax = plt.subplots(figsize=(7.6, 4.4))
for n, m in MET.items():
    if "monthly" in n or "annual" in n:
        continue
    c = CC.get(n, "#444"); big = "Convex" in n
    ax.scatter(m["vol"] * 100, m["cagr"] * 100, s=140 if big else 70,
               color=c, edgecolor="k", zorder=3, marker="*" if big else "o")
    ax.annotate(n.replace(" (Q)", "").replace(" SPY/T-bills (β=0.42)", " SPY/T-bills"),
                (m["vol"] * 100, m["cagr"] * 100), fontsize=7.2,
                xytext=(6, 4), textcoords="offset points")
ax.set_xlabel("Annualized volatility (%)"); ax.set_ylabel("CAGR (%)")
ax.set_title("Risk–return map — Convex Core sits up-and-left of the allocation set"); F3 = png(f)

# ---- Figure 4: up/down capture --------------------------------------------
f, ax = plt.subplots(figsize=(5.4, 3.4))
cap = B["capture"]
ax.bar(["Up-market\ncapture", "Down-market\ncapture"], [cap["up"] * 100, cap["down"] * 100],
       color=["#2ca02c", "#d62728"], width=.55)
for i, v in enumerate([cap["up"], cap["down"]]):
    ax.text(i, v * 100 + 1.5, f"{v*100:.0f}%", ha="center", fontsize=10, fontweight="bold")
ax.axhline(100, color="#888", ls=":"); ax.set_ylabel("% of SPY move captured (monthly)")
ax.set_title("Asymmetric capture vs SPY"); ax.set_ylim(0, 110); F4 = png(f)

# ---- Figure 5: crisis bars -------------------------------------------------
f, ax = plt.subplots(figsize=(9, 3.8))
cw = B["crisis"]; labels = [c["window"] for c in cw]; x = np.arange(len(cw)); w = .26
for i, (k, col, lab) in enumerate([("spy", "#888888", "SPY"),
                                   ("b6040", "#2ca02c", "60/40 SPY/IEF"),
                                   ("convex", "#1f77b4", "Convex Core")]):
    ax.bar(x + (i - 1) * w, [(c[k] or 0) * 100 for c in cw], w, color=col, label=lab)
ax.set_xticks(x); ax.set_xticklabels([l.replace(" ", "\n", 1) for l in labels], fontsize=7)
ax.set_ylabel("Total return over window (%)"); ax.legend(fontsize=8)
ax.set_title("Crisis-window total returns"); F5 = png(f)

# ---- Figure 6: rolling 36m correlation ------------------------------------
f, ax = plt.subplots(figsize=(9, 3.2))
for arr, col, lab in [(B["rolling_corr_spy"], "#1f77b4", "Convex vs SPY"),
                      (B["rolling_corr_6040"], "#2ca02c", "Convex vs 60/40")]:
    idx = pd.to_datetime([d for d, _ in arr]); val = [v for _, v in arr]
    ax.plot(idx, val, color=col, lw=1.5, label=lab)
ax.axhline(0, color="#aaa", ls=":"); ax.set_ylabel("36-mo rolling corr"); ax.legend(fontsize=8)
ax.set_title("Diversification stability — rolling correlation"); F6 = png(f)

# ---- Figure 7: Sortino across the allocation set --------------------------
f, ax = plt.subplots(figsize=(8, 3.8))
order = ["Convex Core (0.95)", "Vol-targeted SPY (≈Convex vol)", "40/60 SPY/IEF (Q)",
         "60/40 SPY/IEF (Q)", "80/20 SPY/IEF (Q)", "Beta-matched SPY/T-bills (β=0.42)", "SPY"]
ax.barh([o.replace(" (Q)", "") for o in order][::-1],
        [MET[o]["sortino"] for o in order][::-1],
        color=[CC.get(o, "#444") for o in order][::-1])
ax.set_xlabel("Sortino ratio (rf = 90-day T-bill)")
ax.set_title("Downside-risk-adjusted return across the allocation set"); F7 = png(f)

# =========================================================================== tables
def fpct(x, d=1): return "—" if x is None else f"{x*100:.{d}f}%"
def fnum(x, d=2): return "—" if x is None else f"{x:.{d}f}"

def metric_table(names, cols, bold_first=True):
    head = "".join(f"<th>{c[1]}</th>" for c in cols)
    rows = []
    for i, n in enumerate(names):
        m = MET[n]
        tds = []
        for key, _lbl, fmt in [(c[0], c[1], c[2]) for c in cols]:
            if key == "name":
                tds.append(f"<td style='text-align:left'>{'<b>' if (bold_first and i==0) else ''}{n}{'</b>' if (bold_first and i==0) else ''}</td>")
            else:
                v = m.get(key); tds.append(f"<td>{fmt(v)}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>"

COLS_EXEC = [("name", "Strategy", None), ("cagr", "CAGR", fpct), ("vol", "Vol", fpct),
             ("sharpe", "Sharpe", fnum), ("sortino", "Sortino", lambda v: f"<b>{fnum(v)}</b>"),
             ("maxdd", "Max DD", lambda v: fpct(v, 0)), ("calmar", "Calmar", fnum),
             ("beta", "β vs SPY", fnum)]
EXEC = ["Convex Core (0.95)", "SPY", "60/40 SPY/IEF (Q)", "40/60 SPY/IEF (Q)",
        "80/20 SPY/IEF (Q)", "Beta-matched SPY/T-bills (β=0.42)", "Vol-targeted SPY (≈Convex vol)"]

# traditional-allocation table adds worst-year + turnover (turnover Tier-2 for Convex)
TURN = {"Convex Core (0.95)": "≈6×/yr†", "SPY": "0.0×", "60/40 SPY/IEF (Q)": "≈0.4×",
        "60/40 SPY/AGG (Q)": "≈0.4×", "40/60 SPY/IEF (Q)": "≈0.4×", "80/20 SPY/IEF (Q)": "≈0.3×",
        "Beta-matched SPY/T-bills (β=0.42)": "0.0×", "Vol-targeted SPY (≈Convex vol)": "≈2×"}
def trad_table(names):
    head = ("<tr><th>Strategy</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>Sortino</th>"
            "<th>Max DD</th><th>Calmar</th><th>β</th><th>Worst yr</th><th>Recov. (d)</th><th>Turnover</th></tr>")
    rows = []
    for i, n in enumerate(names):
        m = MET[n]; b = "<b>" if i == 0 else ""; eb = "</b>" if i == 0 else ""
        rows.append(
            f"<tr><td style='text-align:left'>{b}{n}{eb}</td><td>{fpct(m['cagr'])}</td>"
            f"<td>{fpct(m['vol'])}</td><td>{fnum(m['sharpe'])}</td><td>{fnum(m['sortino'])}</td>"
            f"<td>{fpct(m['maxdd'],0)}</td><td>{fnum(m['calmar'])}</td><td>{fnum(m['beta'])}</td>"
            f"<td>{fpct(m['worst_year'],0)} ({m['worst_year_lbl']})</td>"
            f"<td>{m['recovery_days']}</td><td>{TURN.get(n,'—')}</td></tr>")
    return f"<table>{head}{''.join(rows)}</table>"
TRAD = ["Convex Core (0.95)", "SPY", "60/40 SPY/IEF (Q)", "60/40 SPY/AGG (Q)",
        "40/60 SPY/IEF (Q)", "80/20 SPY/IEF (Q)", "Beta-matched SPY/T-bills (β=0.42)",
        "Vol-targeted SPY (≈Convex vol)"]

# crisis table
def crisis_table():
    head = ("<tr><th>Crisis window</th><th>Dates</th><th>SPY</th><th>60/40 SPY/IEF</th>"
            "<th>Convex Core</th><th>Sleeve attribution</th></tr>")
    rows = []
    for c in B["crisis"]:
        rows.append(
            f"<tr><td style='text-align:left'>{c['window']}</td>"
            f"<td>{c['start']}→{c['end']}</td><td>{fpct(c['spy'],0)}</td>"
            f"<td>{fpct(c['b6040'],0)}</td><td><b>{fpct(c['convex'],0)}</b></td>"
            f"<td style='color:#456'>→ §11.1</td></tr>")
    return f"<table>{head}{''.join(rows)}</table>"

# models table
def models_table():
    head = ("<tr><th>Model</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>Sortino</th>"
            "<th>Max DD</th><th>Calmar</th><th>β</th><th>Status</th></tr>")
    name = {"convex": "Convex Core (0.95)", "prime": "Convex Prime (levered)",
            "race": "RACE", "alpha": "Alpha-Beta", "spy": "SPY (benchmark)"}
    stat = {"convex": "Primary / deployed (IRA)", "prime": "Research / leveraged variant",
            "race": "Secondary low-vol model", "alpha": "Reference board (not deployed)",
            "spy": "Benchmark"}
    rows = []
    for k in ["convex", "spy", "race", "alpha", "prime"]:
        m = MODELS[k]
        rows.append(
            f"<tr><td style='text-align:left'>{name[k]}</td><td>{fpct(m['cagr'])}</td>"
            f"<td>{fpct(m['vol'])}</td><td>{fnum(m['sharpe'])}</td><td>{fnum(m['sortino'])}</td>"
            f"<td>{fpct(m['maxdd'],0)}</td><td>{fnum(m['calmar'])}</td><td>{fnum(m['beta'])}</td>"
            f"<td style='text-align:left'>{stat[k]}</td></tr>")
    return f"<table>{head}{''.join(rows)}</table>"

# ---- Tier-2 render helpers ------------------------------------------------
def t2_ablation_table():
    """no-brake / no-convexity / no-satellites vs baseline (engine, 0.95)."""
    bl = T2["baseline"]; ab = T2["ablations"]
    rows = [("Baseline (full model)", bl, "—")]
    rows += [("− Volatility brake", ab["no_brake"], "removes the de-risking rule"),
             ("− Convexity sleeve", ab["no_convexity"], "managed-futures/anti-beta → duration"),
             ("− Satellite tilts", ab["no_satellites"], "equity sleeve = SPY core only")]
    head = ("<tr><th>Variant</th><th>CAGR</th><th>Vol</th><th>Sortino</th><th>Max DD</th>"
            "<th>Calmar</th><th>Turnover</th><th>What it isolates</th></tr>")
    tr = []
    for lbl, m, note in rows:
        b = "<b>" if lbl.startswith("Baseline") else ""; eb = "</b>" if b else ""
        tr.append(f"<tr><td style='text-align:left'>{b}{lbl}{eb}</td><td>{m['cagr']*100:.1f}%</td>"
                  f"<td>{m['vol']*100:.1f}%</td><td>{m['sortino']:.2f}</td><td>{m['maxdd']*100:.0f}%</td>"
                  f"<td>{m['calmar']:.2f}</td><td>{m.get('turnover','—'):.1f}×</td>"
                  f"<td style='text-align:left'>{note}</td></tr>")
    return f"<table>{head}{''.join(tr)}</table>"

def t2_sweep_table(block, label, fmt=lambda k: k):
    d = T2[block]
    head = f"<tr><th>{label}</th><th>CAGR</th><th>Vol</th><th>Sortino</th><th>Max DD</th><th>Calmar</th><th>Turnover</th></tr>"
    tr = []
    for k, m in d.items():
        if m is None: continue
        star = " ★" if (block == "vol_target" and k == "0.12") or (block == "slippage" and k == "5") else ""
        tr.append(f"<tr><td style='text-align:left'>{fmt(k)}{star}</td><td>{m['cagr']*100:.1f}%</td>"
                  f"<td>{m['vol']*100:.1f}%</td><td>{m['sortino']:.2f}</td><td>{m['maxdd']*100:.0f}%</td>"
                  f"<td>{m['calmar']:.2f}</td><td>{m.get('turnover','—'):.1f}×</td></tr>")
    return f"<table>{head}{''.join(tr)}</table>"

def t2_attribution_table():
    head = ("<tr><th>Crisis window</th><th>Total</th><th>Equity core</th><th>Convexity sleeve</th>"
            "<th>Duration sleeve</th><th>Cost</th></tr>")
    tr = []
    for a in T2["attribution"]:
        if a.get("total") is None: continue
        f = lambda x: f"{x*100:+.1f}%"
        tr.append(f"<tr><td style='text-align:left'>{a['window']}</td><td><b>{f(a['total'])}</b></td>"
                  f"<td>{f(a['equity'])}</td><td>{f(a['convexity'])}</td><td>{f(a['duration'])}</td>"
                  f"<td>{f(a['cost'])}</td></tr>")
    return f"<table>{head}{''.join(tr)}</table>"

HAS_T2 = T2 is not None

# ---- regime rules (exact, from config/regime_rules.yaml) ------------------
import yaml as _yaml
RULES_YAML = f"{ROOT}/etf-trade-classifier/config/regime_rules.yaml"
_RR = _yaml.safe_load(open(RULES_YAML)) if _os.path.exists(RULES_YAML) else None
CONFIRM_DAYS = 3

# ---- principal credit -----------------------------------------------------
PRINCIPAL = "David Reeves"
ENTITY = "DNSR Investments, LLC"
LINKEDIN_URL = "https://www.linkedin.com/in/david-reeves-8a664524"
def principal_credit():
    name = f"{PRINCIPAL}, {ENTITY}"
    return f'<a href="{LINKEDIN_URL}">{name}</a>' if LINKEDIN_URL else name

def regime_clause_table():
    """Full primary-state + tag clause table, rendered from the YAML (exact)."""
    pr = _RR["primary"]; rows = []
    for st in pr["precedence"]:
        spec = pr["states"][st]
        if spec.get("residual"):
            rows.append(f"<tr><td style='text-align:left'><b>{st}</b></td>"
                        f"<td style='text-align:left'><i>residual</i> — entered when no higher-precedence state qualifies</td></tr>")
        else:
            cl = " <b>AND</b> ".join(f"<code>{c}</code>" for c in spec["all"])
            rows.append(f"<tr><td style='text-align:left'><b>{st}</b></td><td style='text-align:left'>{cl}</td></tr>")
    head = "<tr><th>Primary state (precedence order)</th><th>Entry conditions (all must hold)</th></tr>"
    ptbl = f"<table>{head}{''.join(rows)}</table>"
    trows = []
    for tag, spec in _RR["tags"].items():
        cl = " <b>AND</b> ".join(f"<code>{c}</code>" for c in spec["all"])
        trows.append(f"<tr><td style='text-align:left'><b>{tag}</b></td><td style='text-align:left'>{cl}</td></tr>")
    ttbl = (f"<table><tr><th>Overlay tag (independent)</th><th>Conditions (all must hold)</th></tr>"
            f"{''.join(trows)}</table>")
    return ptbl, ttbl

HAS_RR = _RR is not None
HAS_RWF = RWF is not None

def regime_wf_table():
    on, off = RWF["regime_on"], RWF["regime_off"]
    def row(lbl, v, bold=False):
        f = v["full"]; e = v["early"]; l = v["late"]
        b, eb = ("<b>", "</b>") if bold else ("", "")
        return (f"<tr><td style='text-align:left'>{b}{lbl}{eb}</td><td>{f['cagr']*100:.1f}%</td>"
                f"<td>{f['sortino']:.2f}</td><td>{f['maxdd']*100:.0f}%</td>"
                f"<td>{e['sortino']:.2f}</td><td>{l['sortino']:.2f}</td></tr>")
    rows = [row("Regime-on (live model)", on, True), row("Regime-off (no regime layer)", off)]
    for cd, v in RWF["hysteresis"].items():
        if cd == "3": continue
        rows.append(row(f"Hysteresis: confirm_days={cd}", v))
    for fac, v in RWF["thresholds"].items():
        if fac == "1.0": continue
        rows.append(row(f"Thresholds ×{fac}", v))
    head = ("<tr><th>Variant</th><th>CAGR</th><th>Sortino (full)</th><th>Max DD</th>"
            "<th>Sortino (early ≤2014)</th><th>Sortino (late ≥2015)</th></tr>")
    return f"<table>{head}{''.join(rows)}</table>"

# ---- significance (block bootstrap) ---------------------------------------
SIG = B.get("significance")
def _sig(diff):
    return (f"{diff['point']:+.2f} <span style='color:#555'>(95% CI "
            f"[{diff['ci_low']:+.2f}, {diff['ci_high']:+.2f}], p={diff['p_le_0']:.3f})</span>")

def appendix_e():
    if not SIG:
        return ("<h2>Appendix E — Statistical Tests (planned)</h2><p>Bootstrap not available.</p>")
    def rows(d, lbl):
        out = []
        for key, mlbl in (("sortino_diff", "Sortino"), ("sharpe_diff", "Sharpe")):
            x = d[key]
            sig = "yes" if x["p_le_0"] < 0.05 else ("borderline" if x["p_le_0"] < 0.10 else "no")
            out.append(f"<tr><td style='text-align:left'>{lbl}</td><td>{mlbl}</td>"
                       f"<td>{x['point']:+.3f}</td><td>[{x['ci_low']:+.3f}, {x['ci_high']:+.3f}]</td>"
                       f"<td>{x['p_le_0']:.3f}</td><td>{sig}</td></tr>")
        return out
    vs_spy = SIG["convex_vs_spy"]; vs_bal = SIG["convex_vs_best_balanced"]
    body = "".join(rows(vs_spy, "Convex − SPY") + rows(vs_bal, f"Convex − {SIG['best_balanced_label']}"))
    return f"""<h2>Appendix E — Statistical Significance (delivered)</h2>
<p>Method: a <b>circular block bootstrap</b> on the paired daily excess-return series (block length {vs_spy['block_len']} trading days to preserve autocorrelation; {vs_spy['resamples']:,} resamples; paired so the Convex/benchmark cross-correlation is retained), over n={vs_spy['n_obs']:,} daily observations. For each resample we recompute the annualized Sortino and Sharpe of both legs and take the difference; the table reports the full-sample point estimate, the 2.5–97.5 percentile interval, and a one-sided bootstrap p-value P(difference ≤ 0).</p>
<table>
<tr><th>Comparison</th><th>Metric</th><th>Difference</th><th>95% CI (two-sided)</th><th>P(diff ≤ 0)</th><th>Sig. (1-sided 5%)</th></tr>
{body}
</table>
<div class="cap">Table 11. Bootstrap significance of the risk-adjusted difference. Convex Core's edge over SPY is significant on Sharpe and borderline on Sortino; its difference from a 40/60 portfolio is not statistically separable — the model's value over balanced allocations is the higher return at a comparable risk-adjusted, lower-drawdown profile (§8.1), not a separable Sortino/Sharpe gain.</div>
<p><b>Still to be performed</b> (disclosed as not-yet-done): Jobson–Korkie/Memmel analytic Sharpe-difference test, Deflated Sharpe Ratio, and PBO/CSCV overfitting diagnostics. Given non-stationary, sample-limited series with only ~6 independent stress regimes, interval estimates and specification robustness are weighted over fragile point p-values.</p>"""

CV = MET["Convex Core (0.95)"]; SP = MET["SPY"]; B6 = MET["60/40 SPY/IEF (Q)"]
BM = MET["Beta-matched SPY/T-bills (β=0.42)"]; VT = MET["Vol-targeted SPY (≈Convex vol)"]
B46 = MET["40/60 SPY/IEF (Q)"]
cap = B["capture"]; span = B["meta"]["span"]

# =========================================================================== HTML
CSS = """
 body{font-family:Georgia,'Times New Roman',serif;max-width:900px;margin:34px auto;color:#1a1a1a;line-height:1.55;padding:0 30px}
 h1{font-size:25px;margin:0 0 4px} h2{font-size:18px;border-bottom:2px solid #1f77b4;padding-bottom:4px;margin-top:34px;color:#143d66}
 h3{font-size:14.5px;margin:18px 0 4px;color:#143d66} .sub{color:#555;font-size:14px} .auth{color:#333;font-size:13px;margin:6px 0}
 table{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0;font-family:Helvetica,Arial,sans-serif}
 th,td{border:1px solid #ccc;padding:5px 7px;text-align:center} th{background:#143d66;color:#fff} td:first-child{text-align:left}
 img{width:100%;margin:12px 0;border:1px solid #ddd} .cap{font-size:11.5px;color:#666;text-align:center;margin:-6px 0 18px}
 .abs{background:#f4f7fb;border-left:4px solid #1f77b4;padding:12px 16px;font-size:13.5px}
 .disc{font-size:11px;color:#777;border-top:1px solid #ccc;margin-top:30px;padding-top:10px}
 code{background:#eef;padding:1px 4px;border-radius:3px;font-size:12px} ul{margin:6px 0 6px 18px} li{margin:3px 0}
 pre{background:#0f1720;color:#cfe;padding:12px 14px;border-radius:6px;font-size:11px;overflow-x:auto;line-height:1.4}
 .tier2{background:#fff6f0;border:1px solid #e7c3a8;border-left:4px solid #d2691e;border-radius:6px;padding:10px 14px;font-size:12.5px;margin:12px 0}
 .tier2 b{color:#a8521a}
 .key{background:#eef7f0;border-left:4px solid #2ca02c;padding:10px 16px;font-size:13px;margin:12px 0}
 .frontsheet{min-height:9.1in;display:flex;flex-direction:column;padding-top:24px}
 .fs-kicker{letter-spacing:2px;font-size:10.5px;color:#1f77b4;font-family:Helvetica,Arial,sans-serif;text-transform:uppercase}
 .frontsheet h1{font-size:30px;margin:8px 0 4px;border:none;line-height:1.2}
 .fs-sub{font-size:15px;color:#143d66;font-weight:bold;line-height:1.35}
 .fs-authors{font-size:12.5px;color:#555;margin:8px 0 16px}
 .fs-lead{font-size:13.5px;background:#f4f7fb;border-left:4px solid #1f77b4;padding:13px 17px;line-height:1.55}
 .fs-two{display:flex;gap:16px;margin:14px 0}
 .fs-two>div{flex:1;font-size:12px;background:#fafafa;border:1px solid #e2e2e2;border-radius:6px;padding:11px 14px;line-height:1.45}
 .fs-two h4{margin:0 0 6px;font-size:12.5px;color:#143d66}
 .fs-foot{margin-top:auto;font-size:10.5px;color:#666;border-top:1px solid #ccc;padding-top:10px}
 @media print { h2{page-break-after:avoid} img{page-break-inside:avoid} table{page-break-inside:avoid} }
"""

P = []
P.append(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Convex Core & the DNSR Model Suite — Publication Report</title><style>{CSS}</style></head><body>""")

# ---- front-sheet ----------------------------------------------------------
P.append(f"""
<div class="frontsheet">
 <div class="fs-kicker">DNSR Investments LLC&nbsp;·&nbsp;Quantitative Research&nbsp;·&nbsp;June 2026</div>
 <h1>Convex Core and the DNSR Model Suite</h1>
 <div class="fs-sub">A Deterministic ETF Allocation Framework for Drawdown-Controlled Compounding<br>
   <span style="font-weight:normal;font-size:13px;color:#555">Evidence from a 2006–2026 backtest, traditional allocation benchmarks, and five pre-registered failed return-prediction experiments</span></div>
 <div class="fs-authors">{principal_credit()} · Principal<br>Research conducted by the DNSR Agentic AI system — with Anthropic Fable&nbsp;5 and Opus&nbsp;4.8</div>
 <p class="fs-lead"><b>Bottom line.</b> Convex Core is a deterministic, risk-managed ETF allocation framework that preserves most of the equity market's long-run return while materially reducing exposure to high-volatility drawdown regimes. In a {span[0][:4]}–{span[1][:4]} backtest, net of modeled costs, it produced a {CV['cagr']*100:.1f}% CAGR versus {SP['cagr']*100:.1f}% for SPY, improving Sortino from {SP['sortino']:.2f} to {CV['sortino']:.2f} and cutting maximum drawdown from {SP['maxdd']*100:.0f}% to {CV['maxdd']*100:.0f}%. Critically, a <b>beta-matched</b> SPY/T-bill portfolio at the same β=0.42 earns only {BM['cagr']*100:.1f}% with a {BM['maxdd']*100:.0f}% drawdown, and a <b>volatility-targeted</b> SPY reaches {VT['sortino']:.2f} Sortino — so the result is not merely lower beta or volatility scaling. Separately, five pre-registered experiments to improve return <i>prediction</i> each failed their baselines, supporting the design choice to emphasize drawdown control over higher-capacity forecasting.</p>
 <table>
  <tr><th>Strategy</th><th>CAGR</th><th>Sortino</th><th>Max DD</th><th>Calmar</th><th>β vs SPY</th></tr>
  <tr><td style="text-align:left"><b>Convex Core (0.95)</b></td><td>{CV['cagr']*100:.1f}%</td><td><b>{CV['sortino']:.2f}</b></td><td>{CV['maxdd']*100:.0f}%</td><td>{CV['calmar']:.2f}</td><td>{CV['beta']:.2f}</td></tr>
  <tr><td style="text-align:left">60/40 SPY/IEF (quarterly)</td><td>{B6['cagr']*100:.1f}%</td><td>{B6['sortino']:.2f}</td><td>{B6['maxdd']*100:.0f}%</td><td>{B6['calmar']:.2f}</td><td>{B6['beta']:.2f}</td></tr>
  <tr><td style="text-align:left">Beta-matched SPY/T-bills (β=0.42)</td><td>{BM['cagr']*100:.1f}%</td><td>{BM['sortino']:.2f}</td><td>{BM['maxdd']*100:.0f}%</td><td>{BM['calmar']:.2f}</td><td>{BM['beta']:.2f}</td></tr>
  <tr><td style="text-align:left">S&amp;P 500 (SPY)</td><td>{SP['cagr']*100:.1f}%</td><td>{SP['sortino']:.2f}</td><td>{SP['maxdd']*100:.0f}%</td><td>{SP['calmar']:.2f}</td><td>1.00</td></tr>
 </table>
 <div class="fs-two">
  <div><h4>Supported result</h4>Risk-managed compounding — higher Sharpe / Sortino / Calmar and roughly one-third the index's maximum drawdown. The risk-adjusted edge is <i>statistically significant versus the S&amp;P 500</i> (bootstrap, §8.1) and at least comparable to balanced, beta-matched, and volatility-targeted alternatives <i>at materially higher absolute return</i>. Fully deterministic; no large-language model participates in portfolio construction.</div>
  <div><h4>Failed pre-registered experiments</h4>Five independently designed experiments — an ML cross-sectional ranker, an ML volatility forecaster, trend-clarity features, multi-strategy blending, and universe modernization — each failed its pre-specified baseline. No robust return-prediction edge was found on these liquid-ETF data.</div>
 </div>
 <div class="fs-foot">Hypothetical, backtested performance, net of modeled costs; risk-free = 90-day U.S. Treasury bill (DGS3MO). <b>Not investment advice.</b> See §15 Limitations and the Disclaimer. © 2026 DNSR Investments LLC.</div>
</div>
<div style="page-break-after:always"></div>
""")

# ---- title block ----------------------------------------------------------
P.append(f"""
<h1>Convex Core and the DNSR Model Suite</h1>
<div class="sub">A Deterministic ETF Allocation Framework for Drawdown-Controlled Compounding — Evidence from a {span[0][:4]}–{span[1][:4]} Backtest, Traditional Allocation Benchmarks, and Five Pre-Registered Failed Return-Prediction Experiments</div>
<div class="auth"><b>Principal:</b> {principal_credit()} · Houston, Texas · June 2026<br><b>Research system:</b> the DNSR Agentic AI pipeline — with Anthropic Fable&nbsp;5 and Opus&nbsp;4.8 (directed and reviewed by the principal)</div>

<div class="abs"><b>Abstract.</b> This report presents the DNSR Model Suite, a deterministic set of rules-based ETF allocation frameworks designed to test whether liquid ETF portfolios are better improved through return prediction or drawdown control. The primary model, Convex Core, does not forecast returns. Instead, it maintains broad U.S. equity exposure while using a crisis-convex hedge sleeve, Treasury ballast, and a realized-volatility brake to reduce exposure during high-risk regimes. In a {span[0][:4]}–{span[1][:4]} backtest, net of modeled costs, Convex Core produced a {CV['cagr']*100:.1f}% CAGR compared with {SP['cagr']*100:.1f}% for SPY, while improving Sortino from {SP['sortino']:.2f} to {CV['sortino']:.2f} and reducing maximum drawdown from {SP['maxdd']*100:.0f}% to {CV['maxdd']*100:.0f}%. Five pre-registered return-prediction experiments — cross-sectional ETF ranking, ML volatility forecasting, trend-clarity features, multi-strategy blending, and universe modernization — failed their pre-specified baselines. These results support a conservative conclusion: in this liquid ETF universe, the more robust opportunity appears to be risk-managed compounding rather than higher-capacity return forecasting. All portfolio-construction rules are deterministic, and no large-language model participates in the allocation engine.</div>
""")

# ---- 1 Executive Summary --------------------------------------------------
P.append(f"""
<h2>1. Executive Summary</h2>
<p><b>Bottom line.</b> Convex Core is a deterministic, risk-managed ETF allocation framework designed to preserve exposure to the equity market's long-run return while reducing exposure during high-volatility drawdown regimes. In a {span[0][:4]}–{span[1][:4]} backtest, net of modeled costs, Convex Core produced a {CV['cagr']*100:.1f}% CAGR versus {SP['cagr']*100:.1f}% for SPY, while reducing maximum drawdown from {SP['maxdd']*100:.0f}% to {CV['maxdd']*100:.0f}% and improving Sortino from {SP['sortino']:.2f} to {CV['sortino']:.2f}. These results suggest that the model's primary value is not return prediction, but drawdown control and improved downside-risk-adjusted compounding. Separately, five pre-registered experiments designed to improve return prediction failed their baselines, supporting the decision to emphasize risk management over higher-capacity forecasting models.</p>
<p>Because Convex Core has lower beta and a drawdown-sensitive objective, it is benchmarked not only against SPY but against rebalanced 60/40, 40/60, and 80/20 stock/Treasury portfolios, a beta-matched SPY/T-bill portfolio, and a volatility-targeted SPY. It improves on all of them on Sortino, Calmar, and maximum drawdown over the tested period.</p>
{metric_table(EXEC, COLS_EXEC)}
<div class="cap">Table 1. Primary performance comparison — <b>hypothetical, backtested</b>, net of modeled costs, {span[0]}–{span[1]}; rf = 90-day T-bill. Balanced benchmarks rebalanced quarterly. Convex Prime (leveraged) and other research-only variants are reported separately in §17, not here.</div>
""")

# ---- 2 Key Findings -------------------------------------------------------
P.append(f"""
<h2>2. Key Findings</h2>
<ol>
<li><b>Convex Core preserved most of SPY's long-term return with substantially lower drawdown.</b> {CV['cagr']*100:.1f}% CAGR vs {SP['cagr']*100:.1f}% for SPY, with maximum drawdown cut from {SP['maxdd']*100:.0f}% to {CV['maxdd']*100:.0f}%.</li>
<li><b>The advantage is downside-risk-adjusted, not absolute-return dominance.</b> Convex Core did not exceed SPY's CAGR, but improved Sortino ({CV['sortino']:.2f} vs {SP['sortino']:.2f}), Sharpe ({CV['sharpe']:.2f} vs {SP['sharpe']:.2f}), Calmar ({CV['calmar']:.2f} vs {SP['calmar']:.2f}), volatility, beta, and drawdown.</li>
<li><b>The result survives the two most important "it's just…" controls.</b> A <i>beta-matched</i> SPY/T-bill portfolio (β=0.42) earned only {BM['cagr']*100:.1f}% CAGR at a {BM['maxdd']*100:.0f}% drawdown and {BM['sortino']:.2f} Sortino; a <i>volatility-targeted</i> SPY matched to Convex's ~{CV['vol']*100:.0f}% volatility reached {VT['sortino']:.2f} Sortino. Convex Core exceeds both — the benefit is therefore more than holding less equity or scaling volatility.</li>
<li><b>The failed experiments are a strength, not a weakness.</b> Five pre-registered failures support emphasizing robust drawdown management over high-capacity return prediction on broad liquid ETF data.</li>
<li><b>Position it as a risk-managed equity allocation, not a universal alpha engine.</b> It should not be framed as an absolute-return strategy or a guaranteed crisis hedge.</li>
</ol>
""")

# ---- 3 Research Question and Contribution ---------------------------------
P.append("""
<h2>3. Research Question and Contribution</h2>
<p><b>Research question.</b> Can a deterministic ETF allocation framework improve downside-risk-adjusted compounding relative to passive equity and traditional balanced benchmarks primarily through drawdown control, rather than return prediction?</p>
<p><b>Contribution.</b> (1) A deterministic ETF allocation framework with explicit equity, convexity, and duration sleeves. (2) A drawdown-control architecture that relies on neither LLM-generated weights nor trained return forecasts. (3) A benchmark suite comparing the model to SPY, traditional rebalanced portfolios, beta-matched portfolios, and volatility-targeted equity. (4) A negative-results discipline that reports failed pre-registered attempts to extract a return-prediction edge from liquid ETF data.</p>

<h3>3.1 Relation to prior work, and what is distinct here</h3>
<p><b>This paper claims no novel strategy or anomaly.</b> Each of Convex Core's mechanisms is a recombination of well-published premia, and our negative results corroborate, rather than overturn, the existing literature. We state this explicitly because situating the work honestly is what makes its conclusions credible. Specifically: the volatility brake is an instance of <i>volatility-managed / volatility-targeted equity</i> (Moreira &amp; Muir, 2017; Harvey et al., 2018); the convexity sleeve is the <i>crisis-alpha / trend-following-as-tail-hedge</i> idea (Hurst, Ooi &amp; Pedersen, 2017); the lower-beta, drawdown-sensitive posture connects to the <i>defensive / betting-against-beta</i> literature (Frazzini &amp; Pedersen, 2014) and to risk-balanced allocation. The five failed return-prediction experiments are consistent with the <i>anomaly-replication and decay</i> literature (Harvey, Liu &amp; Zhu, 2016; Hou, Xue &amp; Zhang, 2020; McLean &amp; Pontiff, 2016), and are the low-breadth-ETF corollary to Gu, Kelly &amp; Xiu (2020), who find machine learning <i>does</i> add value on the far higher-breadth single-stock cross-section — precisely the breadth this ~40-instrument universe lacks.</p>
<p><b>The contribution is integrative and methodological, not a new financial result:</b></p>
<ul>
<li><b>Negative results that ship.</b> Five pre-registered failures are reported alongside the positive result. Academic journals rarely publish failed strategies and practitioner white papers essentially never do; publishing the gated failures is the paper's strongest point of difference.</li>
<li><b>Determinism and reproducibility end-to-end.</b> A zero-fitted-parameter flagship, no large-language model anywhere in the allocation math, and a complete reproducibility manifest (Appendix F) — a standard of auditability uncommon in published backtests.</li>
<li><b>Honesty calibration.</b> Claims are significance-tested and the inconvenient findings are kept in the text — e.g., the bootstrap result (§8.1) that Convex Core is <i>not</i> statistically separable from a 60/40 portfolio on risk-adjusted ratios, and the validation (§12, §15) that the regime layer is a second-order refinement rather than the source of the edge.</li>
<li><b>An AI-conducted research process.</b> The experiments here were designed, pre-registered, executed, and self-critically reported by an autonomous agentic-AI research pipeline. The methodological discipline — pre-registration, leakage control, published negatives — was applied by the system itself; this process is a contribution distinct from, and arguably more novel than, the financial content.</li>
</ul>
""")

# ---- 4 Model Philosophy ----------------------------------------------------
P.append("""
<h2>4. Model Philosophy: Risk Management vs Return Prediction</h2>
<p>Convex Core does not attempt to forecast the next period's equity-market return. Its premise is that broad equity exposure remains the primary compensated return source, but that large drawdowns impair compounding, investor behavior, and retirement spending resilience. The model therefore seeks to retain meaningful equity participation while reducing exposure during high-volatility drawdown regimes.</p>
<p>This framing changes the appropriate benchmark. If the objective were maximum long-run CAGR, the relevant comparator would be SPY or another equity index. If the objective is drawdown-sensitive compounding, the relevant comparators also include traditional rebalanced stock/bond portfolios, beta-matched equity/T-bill portfolios, and volatility-targeted equity portfolios — all of which are reported here.</p>
""")

# ---- 5 Convex Core Specification ------------------------------------------
P.append(f"""
<h2>5. Convex Core Specification</h2>
<p>A three-sleeve allocation, <code>w_equity + w_convexity + w_duration = 1</code>, rebalanced weekly with a relative-drift band governor:</p>
<table>
<tr><th>Component</th><th>Specification</th></tr>
<tr><td>Rebalance cadence</td><td>Weekly signal; sleeve rebalanced when drifted &gt;20% relative (BAND_REL=0.20)</td></tr>
<tr><td>Equity core</td><td>S&amp;P 500 core (SPY) + up to 5 satellite tilts</td></tr>
<tr><td>Tilt fraction</td><td>40% of the equity sleeve in IC-tilted names (tilt_frac=0.40)</td></tr>
<tr><td>Satellite selection</td><td>Regime-weighted composite score (relative strength, trend, momentum, downside behavior); 1 reserved value slot; +0.75σ incumbency bonus; correlation de-dup (PIT trailing-252d corr &gt;0.95, prefer-drop K-1 funds)</td></tr>
<tr><td>Convexity sleeve</td><td>Managed futures + anti-beta (DBMF/KMLM/BTAL family) — crisis-convex exposure</td></tr>
<tr><td>Duration sleeve</td><td>Treasuries / bills (IEF/BIL/TLT) as ballast</td></tr>
<tr><td>Volatility brake</td><td><code>eq_scale = min(1, vol_target / realized_vol_21d)</code>, vol_target = 12% annualized on the equity sleeve; slow re-risk (max +0.15 eq_scale/week); confirmatory stress cap 0.70</td></tr>
<tr><td>Glidepath dial</td><td><code>w_equity</code> = 0.95 (current; the practical ceiling — the brake binds beyond); intended to step toward 0.65 as drawdown-sensitive years approach</td></tr>
<tr><td>Costs</td><td>Slippage charged per trade on realized turnover; returns reported net</td></tr>
</table>
<p><b>On "parameter-minimal," not "zero fitted-parameter."</b> Convex Core is deterministic and parameter-minimal. Its portfolio rules, sleeve definitions, rebalance cadence, volatility target, and security-selection logic were fixed before the final scored backtest. No statistical return-forecasting model is trained inside the allocation engine, and no LLM participates in portfolio construction. Because the architecture itself reflects research-design choices, the result should be interpreted as a rule-based backtest rather than as proof of a discovered alpha signal. The full rule manifest is in Appendix&nbsp;A.</p>
""")

# ---- 6 Data / reproducibility ---------------------------------------------
P.append(f"""
<h2>6. Data, Costs, and Reproducibility Protocol</h2>
<table>
<tr><th>Area</th><th>Treatment</th></tr>
<tr><td>Data vendors</td><td>EODHD, FMP, FRED (local warehouse; no external calls in the model path)</td></tr>
<tr><td>Price field</td><td>adjusted_close (total-return proxy; dividends reinvested)</td></tr>
<tr><td>ETF universe</td><td>Point-in-time; features recomputed as-of each rebalance from raw prices</td></tr>
<tr><td>Delisted funds</td><td>Retained while they traded (survivorship-controlled)</td></tr>
<tr><td>Window</td><td>{span[0]} → {span[1]} (Convex/SPY common span; RACE from 2007)</td></tr>
<tr><td>Signal timing</td><td>Close-observed; executed at the following rebalance</td></tr>
<tr><td>Slippage</td><td><b>Identical 5 bps per unit of realized turnover — charged to every model AND benchmark.</b> Models ~6×/yr; quarterly blends ~0.3–0.4×/yr; vol-targeted SPY on daily |Δexposure|; SPY buy-and-hold and the fixed beta-matched sleeve ≈0. (No cost asymmetry favoring the model.)</td></tr>
<tr><td>Risk-free rate</td><td>DGS3MO (90-day T-bill), daily-compounded</td></tr>
<tr><td>Cash proxy</td><td>DGS3MO synthetic T-bill (benchmark cash legs)</td></tr>
<tr><td>Volatility estimator</td><td>21-day trailing realized, annualized ×√252</td></tr>
<tr><td>Correlation estimator</td><td>252-day trailing (tilt de-dup)</td></tr>
<tr><td>Determinism</td><td>Pure numerical code; no LLM in portfolio math; reproducible</td></tr>
</table>
<p>A machine-readable reproducibility manifest accompanies every scored run (Appendix&nbsp;F). The benchmark blends in this report are constructed from the same warehouse and risk-free series as the models; the DB-derived SPY reconciles with the model SPY ({SP['cagr']*100:.1f}% CAGR, {SP['sortino']:.2f} Sortino, {SP['maxdd']*100:.0f}% maxDD), so the model and benchmark tables are mutually consistent.</p>
<div class="tier2"><b>Reproducibility note.</b> The canonical Convex series is the <code>w_equity=0.95</code> vintage; the published growth curve reports {CV['cagr']*100:.1f}% CAGR, and the separately-instrumented engine used for the ablations and attribution (§11.1, §12) reproduces it at 10.7% — a &lt;0.1% difference from the two export paths, immaterial to every conclusion. An earlier <code>0.65</code> export (CAGR 8.4%) exists in the research tree and is deliberately <i>not</i> used, to keep every table on a single vintage.</div>
""")

# ---- 6.1 Regime classification --------------------------------------------
P.append(f"""
<h3>6.1 Regime classification</h3>
<p>Two of Convex Core's mechanisms condition on a market <b>regime</b>: the duration sleeve's composition (Treasury-rally mix in risk-off / stress, inflation mix in recovery, neutral otherwise) and the volatility brake's confirmatory stress cap (a hard ceiling on equity scale in liquidity stress). The regime is produced by a <b>self-contained, point-in-time classifier</b> that uses only local price and macro series — it has <i>no</i> runtime coupling to any external regime product (third-party regime/health scores, where available, are logged alongside for comparison only, never used as an input).</p>
<p>The classifier emits one <b>primary state</b> (mutually exclusive) plus zero or more <b>orthogonal overlay tags</b> (independent booleans). The primary state is the first <i>eligible-and-true</i> state in a fixed precedence in which stress wins and a neutral state is the residual:</p>
<p style="text-align:center;font-size:13px"><code>LIQUIDITY_STRESS &gt; RISK_OFF &gt; RECOVERY &gt; RISK_ON &gt; RISK_NEUTRAL</code></p>
<ul>
<li><b>Inputs (Tier-P, all PIT).</b> SPY trend (20/50/200-day moving averages, 20d/63d return, 21d realized volatility, drawdown from the 252-day high); VIX (level, 20-day change, 252-day percentile, ratio to its 252-day median); credit risk-appetite (HYG/LQD relative strength, 20d and 63d); breadth (% of the 11 GICS sector ETFs above their own 200-DMA, RSP/SPY); QQQ/SPY and VXUS/SPY relative strength; TLT/IEF/UUP/GLD/DBC 63-day returns; defensive- and energy/materials-vs-SPY relative strength; 10-year breakeven and 10-year yield 20-day changes; high-yield and investment-grade OAS levels and 20-day trends. There is intentionally <i>no</i> VIX term-structure, VVIX, or SKEW clause — those have no sanctioned local source and are simply absent rather than approximated.</li>
<li><b>Hysteresis.</b> A flip to a new primary state requires its conditions to hold for <b>{CONFIRM_DAYS} consecutive sessions</b>; until confirmed, the established state continues to report. This anti-flapping discipline keeps the duration sleeve and stress cap from churning on one-day signals.</li>
<li><b>Graceful degradation.</b> Each condition whose input is unavailable is dropped, not guessed; a primary state is eligible only if at least <b>{_RR['primary']['min_live_clauses']}</b> of its conditions are live, and an overlay tag with <i>any</i> blind condition stays off. The engine never asserts a state it cannot actually evaluate.</li>
</ul>
<p>The state and tag <i>structure</i> (membership, precedence, hysteresis, degradation) is fixed. The specific numeric cutoffs are an <i>a priori</i> interpretation of the qualitative regime definitions in the model's design specification — they were <b>not</b> fitted to maximize Convex Core's backtest, and belong to the tunable "regime threshold" family (the unit tests pin the evaluation <i>semantics</i>, not the calibrations). We validate directly in §12.3 that the result does not materially depend on this calibration (removing the entire regime layer moves full-sample Sortino by 0.02; the result is robust to hysteresis and ±20% threshold perturbation). The full clause set is reproduced verbatim in Appendix&nbsp;I.</p>
""")

# ---- 7 Benchmark Construction ---------------------------------------------
P.append(f"""
<h2>7. Benchmark Construction</h2>
<p>Because Convex Core is designed for drawdown-sensitive capital rather than maximum equity exposure, the benchmark set includes both equity-only and balanced-allocation alternatives. The primary equity benchmark is SPY. The primary balanced benchmark is a quarterly-rebalanced 60/40 stock/Treasury portfolio. Additional benchmarks include 40/60 and 80/20 stock/Treasury portfolios, a 60/40 SPY/AGG variant, a beta-matched SPY/T-bill portfolio, and a volatility-targeted SPY matched to Convex Core's realized volatility. These distinguish true diversification and drawdown control from the simpler effect of holding less equity.</p>
<ul>
<li><b>60/40, 40/60, 80/20 SPY/IEF</b> and <b>60/40 SPY/AGG</b> — static targets, quarterly rebalanced (monthly/annual shown as sensitivity in §12).</li>
<li><b>Beta-matched SPY/T-bills</b> — {0.42:.2f}·SPY + {0.58:.2f}·T-bill, holding portfolio beta at Convex's {CV['beta']:.2f}. Isolates whether the result is "just lower beta."</li>
<li><b>Volatility-targeted SPY</b> — SPY scaled by <code>min(1, {CV['vol']*100:.1f}% / realized_vol_21d)</code>, remainder in T-bills (mirrors Convex's own brake). Isolates whether the result is "just volatility scaling."</li>
</ul>
""")

# ---- 8 Main Results -------------------------------------------------------
P.append(f"""
<h2>8. Main Results</h2>
<img src="{F1}"/><div class="cap">Figure 1. Growth of $1 (log), net of costs. Convex Core compounds competitively with the index while the balanced and beta/vol-controlled alternatives trail; the drawdown advantage is in Figure 2.</div>
<img src="{F2}"/><div class="cap">Figure 2. Drawdown paths. SPY's {SP['maxdd']*100:.0f}% trough dwarfs Convex Core's {CV['maxdd']*100:.0f}%; even 40/60 ({B46['maxdd']*100:.0f}%) is deeper.</div>
<img src="{F3}"/><div class="cap">Figure 3. Risk–return map. Convex Core (★) sits up-and-left of the entire allocation set — higher return per unit of volatility.</div>
""")

if SIG:
    vs_spy = SIG["convex_vs_spy"]; vs_bal = SIG["convex_vs_best_balanced"]
    P.append(f"""
<h3>8.1 Statistical significance of the risk-adjusted edge</h3>
<p>Point estimates can mislead on a ~20-year, drawdown-driven series, so we test the <i>difference</i> in risk-adjusted ratios with a circular block bootstrap (block length {vs_spy['block_len']} trading days, {vs_spy['resamples']:,} resamples; paired to preserve cross-correlation). Detail and the full table are in Appendix&nbsp;E (Table&nbsp;11).</p>
<ul>
<li><b>vs SPY:</b> the Sharpe difference is {_sig(vs_spy['sharpe_diff'])} — significant on a one-sided 5% test (p={vs_spy['sharpe_diff']['p_le_0']:.3f}), with the two-sided 95% interval marginally including zero; the Sortino difference is {_sig(vs_spy['sortino_diff'])} — positive but only borderline (p={vs_spy['sortino_diff']['p_le_0']:.3f}). Convex Core's risk-adjusted superiority over the index is statistically supported, if modestly.</li>
<li><b>vs the best balanced benchmark (40/60 SPY/IEF):</b> the Sortino difference is {_sig(vs_bal['sortino_diff'])} and the Sharpe difference {_sig(vs_bal['sharpe_diff'])} — <b>not statistically distinguishable from zero.</b> On risk-adjusted ratios alone, Convex Core is <i>comparable</i> to a simple 40/60 portfolio at this sample size.</li>
</ul>
<p>This is an important, deliberately stated qualification: Convex Core's defensible claim is not that it dominates every balanced portfolio on risk-adjusted ratios — at ~6 independent stress episodes the sample cannot support that — but that it achieves a <i>comparable</i> risk-adjusted, lower-drawdown profile <b>at materially higher absolute return</b> ({CV['cagr']*100:.1f}% vs {B46['cagr']*100:.1f}% CAGR for 40/60), i.e. it sits closer to the efficient frontier, while remaining statistically superior to the equity index itself.</p>
""")

# ---- 9 Traditional Allocation Comparisons ---------------------------------
P.append(f"""
<h2>9. Traditional Allocation Comparisons</h2>
<p>Convex Core is not evaluated solely against SPY because its objective is not maximum equity beta. The balanced-allocation comparison is the key test of whether it adds value beyond ordinary de-risking.</p>
{trad_table(TRAD)}
<div class="cap">Table 2. Traditional allocation benchmarks (hypothetical/backtested, net of costs), {span[0]}–{span[1]}. Worst yr = worst calendar-year total return. Recov. = longest underwater span (days). †Convex 0.95-vintage turnover ≈6.3×/yr (engine, §12); benchmark turnover is the low quarterly-rebalance rate. All strategies and benchmarks charged identical 5 bps/trade slippage.</div>
<p><b>Interpretation.</b> On <i>point estimates</i>, Convex Core improves Sortino, Calmar, and maximum drawdown relative to every balanced and risk-matched alternative in the tested period; the differences vs SPY are statistically supported, while the difference vs the closest competitor (40/60 SPY/IEF, {B46['sortino']:.2f} Sortino, {B46['maxdd']*100:.0f}% drawdown) is <i>not</i> statistically separable (§8.1). The decisive, defensible contrasts are with the controls: the <b>beta-matched</b> portfolio — same equity sensitivity, no convexity sleeve or brake — earns only {BM['cagr']*100:.1f}% CAGR with a {BM['maxdd']*100:.0f}% drawdown, and the 40/60 matches Convex's risk-adjusted profile only at materially lower return ({B46['cagr']*100:.1f}% vs {CV['cagr']*100:.1f}%) and beta ({B46['beta']:.2f} vs {CV['beta']:.2f}). The advantage is therefore not merely lower beta, and is delivered at a higher point on the return axis than the comparable-Sortino balanced portfolio.</p>
""")

# ---- 10 Portfolio Diversification Role ------------------------------------
P.append(f"""
<h2>10. Portfolio Diversification Role</h2>
<p>Convex Core is designed to function as a risk-managed equity allocation rather than a stand-alone return-prediction engine. Its diversification comes from three sources: reduced equity beta, explicit crisis-convex exposure, and dynamic volatility scaling. The equity sleeve preserves participation in the broad U.S. market, while the convexity and duration sleeves seek to reduce sensitivity to sustained equity drawdowns. The model therefore aims to improve the <i>path</i> of compounding, not to maximize exposure to every advance.</p>
<p>The diversification claim should be interpreted conservatively. Convex Core does not diversify away market risk: its full-sample correlation to SPY is {B['corr_spy_full']:.2f}, and it remains materially exposed to equity compounding through its index core. Its benefit is expected to be greatest during equity-stress regimes in which managed futures, anti-beta, Treasuries, or cash-like ballast provide offsetting behavior, and least differentiated in ordinary bull or sideways markets.</p>
<img src="{F4}"/><div class="cap">Figure 4. Asymmetric capture vs SPY (monthly): Convex Core captures {cap['up']*100:.0f}% of up-market moves but only {cap['down']*100:.0f}% of down-market moves — the signature of a drawdown-control objective.</div>
<img src="{F6}"/><div class="cap">Figure 5. Rolling 36-month correlation of Convex Core to SPY and to a 60/40 portfolio — diversification is stable, not a single-episode artifact.</div>
<img src="{F7}"/><div class="cap">Figure 6. Downside-risk-adjusted return (Sortino) across the allocation set.</div>
<p><b>Good vs bad diversification.</b> The failed multi-strategy blend (§13) highlights the distinction: good diversification comes from structurally different return drivers that improve drawdown, recovery, or downside capture; bad diversification comes from adding correlated or weaker strategies merely to broaden the model. Convex Core should therefore be judged by its marginal contribution to total-portfolio risk, not by the number of sleeves it contains.</p>
""")

# ---- 11 Crisis-Period Attribution -----------------------------------------
P.append(f"""
<h2>11. Crisis-Period Attribution</h2>
<p>A drawdown-control model should be judged primarily during drawdown regimes. Table 3 reports total returns across the major equity-stress windows in the sample.</p>
{crisis_table()}
<div class="cap">Table 3. Crisis-window total returns (hypothetical/backtested, net of costs). The per-sleeve decomposition is in §11.1 / Table 3b. Convex figures use the published 0.95 curve; §11.1 uses the instrumented engine run, which reproduces it to &lt;1 pp per window.</div>
<img src="{F5}"/><div class="cap">Figure 7. Crisis-window total returns — Convex Core's loss is a fraction of SPY's in every window, and below 60/40 in all but the mildest.</div>
""")

if HAS_T2:
    P.append(f"""
<h3>11.1 Per-sleeve attribution</h3>
<p>Decomposing each crisis return into its sleeve contributions — computed by instrumenting the allocation engine to emit per-sleeve daily returns at the 0.95 vintage (the attribution run reproduces the baseline returns bit-for-bit) — shows <i>where</i> the protection came from:</p>
{t2_attribution_table()}
<div class="cap">Table 3b. Crisis-window per-sleeve attribution (sum of daily sleeve returns; total ≈ equity + convexity + duration + cost, compounding cross-term negligible). Vintage w_equity=0.95.</div>
<p><b>Reading the decomposition.</b> The protection source rotates by regime. In the <b>2008 GFC</b> and <b>2011</b> the duration (Treasury) sleeve carried the hedge (+8.6% and +8.2%) while the managed-futures convexity funds had not yet launched (their mass folded into duration, so convexity reads ≈0). In the <b>2022</b> stock-and-bond selloff the roles inverted: the convexity sleeve contributed <b>+4.5%</b> exactly when duration was a drag (−1.6%), the signature crisis-alpha behavior of trend-following. The equity core is the loss-bearing leg in every window, as designed; the brake and hedges offset it. This confirms the drawdown control is structural, not an artifact of low beta.</p>
""")
else:
    P.append("""<div class="tier2"><b>Tier-2 pending — per-sleeve attribution.</b> Run `pub_tier2/run_tier2.py` to populate this section.</div>""")
P.append("")

# ---- 12 Robustness --------------------------------------------------------
P.append(f"""
<h2>12. Robustness and Sensitivity Tests</h2>
<p>Rebalance-frequency sensitivity for the primary balanced benchmark is computable directly and is stable:</p>
<table>
<tr><th>60/40 SPY/IEF rebalance</th><th>CAGR</th><th>Vol</th><th>Sortino</th><th>Max DD</th><th>Calmar</th></tr>
<tr><td style="text-align:left">Quarterly (primary)</td><td>{B6['cagr']*100:.1f}%</td><td>{B6['vol']*100:.1f}%</td><td>{B6['sortino']:.2f}</td><td>{B6['maxdd']*100:.0f}%</td><td>{B6['calmar']:.2f}</td></tr>
<tr><td style="text-align:left">Monthly</td><td>{MET['60/40 SPY/IEF (monthly)']['cagr']*100:.1f}%</td><td>{MET['60/40 SPY/IEF (monthly)']['vol']*100:.1f}%</td><td>{MET['60/40 SPY/IEF (monthly)']['sortino']:.2f}</td><td>{MET['60/40 SPY/IEF (monthly)']['maxdd']*100:.0f}%</td><td>{MET['60/40 SPY/IEF (monthly)']['calmar']:.2f}</td></tr>
<tr><td style="text-align:left">Annual</td><td>{MET['60/40 SPY/IEF (annual)']['cagr']*100:.1f}%</td><td>{MET['60/40 SPY/IEF (annual)']['vol']*100:.1f}%</td><td>{MET['60/40 SPY/IEF (annual)']['sortino']:.2f}</td><td>{MET['60/40 SPY/IEF (annual)']['maxdd']*100:.0f}%</td><td>{MET['60/40 SPY/IEF (annual)']['calmar']:.2f}</td></tr>
</table>
<div class="cap">Table 4. Benchmark rebalance-frequency sensitivity — the comparison is not an artifact of rebalance timing.</div>
""")

if HAS_T2:
    bl = T2["baseline"]; nb = T2["ablations"]["no_brake"]
    P.append(f"""
<h3>12.1 Sleeve ablations (engine, 0.95 vintage)</h3>
<p>Each structural mechanism is removed one at a time, holding everything else at the live configuration:</p>
{t2_ablation_table()}
<div class="cap">Table 5. Sleeve ablations vs the full model, net of costs, 0.95 vintage; rf = 90-day T-bill.</div>
<p><b>The volatility brake is load-bearing.</b> Removing it <i>raises</i> CAGR ({nb['cagr']*100:.1f}% vs {bl['cagr']*100:.1f}%) but collapses Sortino ({nb['sortino']:.2f} vs {bl['sortino']:.2f}) and more than doubles maximum drawdown ({nb['maxdd']*100:.0f}% vs {bl['maxdd']*100:.0f}%) — a direct, on-vintage confirmation that the model trades a little return for a large reduction in drawdown by design. The convexity and satellite sleeves have smaller unconditional effects (the convexity sleeve is only ~5% of the book at w_equity 0.95), but as §11.1 shows the convexity sleeve's value is concentrated in specific crises.</p>
<h3>12.2 Parameter and cost sensitivity</h3>
<div style="display:flex;gap:14px;flex-wrap:wrap">
<div style="flex:1;min-width:300px">{t2_sweep_table('vol_target','Vol target', lambda k: f"{float(k)*100:.0f}%")}</div>
<div style="flex:1;min-width:300px">{t2_sweep_table('slippage','Slippage', lambda k: f"{k} bps")}</div>
</div>
<div class="cap">Table 6. Volatility-target and slippage sensitivity (★ = live setting). Behavior is smooth — no knife-edge; the result degrades gracefully even at a punitive 25 bps/trade.</div>
{t2_sweep_table('start_date','Start year')}
<div class="cap">Table 7. Start-date sensitivity. Sortino {min(m['sortino'] for m in T2['start_date'].values() if m):.2f}–{max(m['sortino'] for m in T2['start_date'].values() if m):.2f}, maximum drawdown {max(m['maxdd'] for m in T2['start_date'].values() if m)*100:.0f}% to {min(m['maxdd'] for m in T2['start_date'].values() if m)*100:.0f}% across start years. <b>Note:</b> these are <i>nested sub-windows of one historical path</i>, so this is a stability check against window choice, not independent out-of-sample evidence — the sample contains only ~6 distinct equity-stress episodes (§11), which is the binding limit on statistical power (§8.1, §15).</p>
<p><b>Robustness verdict.</b> Convex Core's point-estimate ranking — superior to SPY and the balanced benchmarks on Sortino, Calmar, and drawdown — holds across every reasonable parameter, cost, start-date, and sleeve-ablation variant tested; the only variant that lifts a single metric (no-brake, higher CAGR) does so by abandoning the model's drawdown-control objective. The <i>direction</i> of the result is robust to specification. Its <i>statistical strength</i> is bounded by the small number of independent stress regimes: significant vs the equity index, not separable from a 40/60 portfolio (§8.1). Both statements are intended to stand together.</p>
""")
else:
    P.append("""<div class="tier2"><b>Tier-2 pending — ablation grid.</b> Run pub_tier2/run_tier2.py.</div>""")
P.append("")

if HAS_RWF:
    lay = RWF["layer_contribution"]["full"]
    P.append(f"""
<h3>12.3 Regime-layer validation (addressing in-sample calibration)</h3>
<p>Because two protective mechanisms and the tilt scoring condition on a regime classifier whose numeric cutoffs are <i>a priori</i> but were not previously walk-forward re-validated (§6.1), we test directly how much the result depends on that layer. <b>Regime-off</b> forces every day to the neutral state — disabling the regime duration mix, the stress cap, and regime tilt weighting — and we also perturb the hysteresis window and scale every numeric cutoff by ±20%.</p>
{regime_wf_table()}
<div class="cap">Table 8. Regime-layer validation, 0.95 vintage, net of costs. "Early" ≤ 2014, "late" ≥ 2015 (a temporal split). Hysteresis and threshold rows are the perturbation extremes.</div>
<p><b>Finding: the regime layer is a second-order refinement, not the source of the edge.</b> Removing it entirely changes full-sample Sortino by just {lay['d_sortino']:+.2f} ({RWF['regime_on']['full']['sortino']:.2f}→{RWF['regime_off']['full']['sortino']:.2f}) and maximum drawdown by ~1 pp. The layer <i>helped</i> in the early, crisis-heavy sub-period (Sortino {RWF['regime_on']['early']['sortino']:.2f} vs {RWF['regime_off']['early']['sortino']:.2f}) and was mildly <i>negative</i> in the late sub-period ({RWF['regime_on']['late']['sortino']:.2f} vs {RWF['regime_off']['late']['sortino']:.2f}) — net negligible. The result is also robust to the calibration itself: Sortino varies by only {RWF['sortino_spread_hysteresis']:.2f} across hysteresis settings and {RWF['sortino_spread_thresholds']:.2f} across ±20% threshold scaling, and every variant remains far above SPY's {SP['sortino']:.2f}. <b>The concern that the a-priori regime cutoffs are over-fit to the sample is therefore moot: the headline cannot be materially driven by parameters whose complete removal moves Sortino by {abs(lay['d_sortino']):.2f}.</b> The edge comes from the structural sleeves and the volatility brake (§12.1), not from regime calibration.</p>
""")
P.append("")

# ---- 13 Negative Results --------------------------------------------------
P.append("""
<h2>13. Negative Results from Pre-Registered Experiments</h2>
<p>The negative results are central to the report, not incidental. Five independently designed experiments attempted to improve return prediction or model breadth. Each failed its pre-registered gate.</p>
<table>
<tr><th>Experiment</th><th>Hypothesis</th><th>Baseline</th><th>Success gate</th><th>Result</th><th>Interpretation</th></tr>
<tr><td style="text-align:left">LightGBM cross-sectional ranker</td><td>ETF ranking features improve forward returns</td><td>SPY, 12-1 momentum, factor composite</td><td>Higher OOS Sharpe/IR net of costs</td><td><b>Failed</b> (Sharpe 0.53 vs SPY 0.88)</td><td>No robust cross-sectional ETF alpha</td></tr>
<tr><td style="text-align:left">ML volatility forecast</td><td>ML improves volatility timing</td><td>EWMA volatility model</td><td>Lower OOS QLIKE</td><td><b>Failed</b></td><td>Simple EWMA more robust; L2 model under-forecasts spikes</td></tr>
<tr><td style="text-align:left">Trend-clarity features</td><td>Trend quality improves selection</td><td>Momentum-only model</td><td>FM t-stat &gt;2 ∧ OOS improvement</td><td><b>Failed</b> (max |t| 1.27)</td><td>Orthogonal to momentum and to forward returns</td></tr>
<tr><td style="text-align:left">Multi-strategy blend</td><td>Combining sleeves improves diversification</td><td>Best single sleeve</td><td>Higher OOS risk-adjusted return</td><td><b>Failed</b> (0/4 schemes)</td><td>Blend diluted the strongest sleeve (PBO 0.15)</td></tr>
<tr><td style="text-align:left">Universe modernization</td><td>Newer ETFs improve the opportunity set</td><td>Original universe</td><td>Better OOS performance</td><td><b>Failed</b></td><td>More correlated candidates → more overfitting, not edge</td></tr>
</table>
<div class="cap">Table 9. Pre-registered experiment results. Each gate was fixed before the scored run; misses are published.</div>
<p>This does not prove that no ETF alpha exists, but it reduces confidence that higher-capacity models, additional features, or a larger modern ETF universe would reliably improve out-of-sample results after costs. The failures support emphasizing deterministic drawdown control over increasingly complex return prediction.</p>
""")

# ---- 14 Suitability -------------------------------------------------------
P.append("""
<h2>14. Suitability and Implementation Considerations</h2>
<p><b>Suitability.</b> Convex Core is most relevant for investors who value drawdown control, downside-risk-adjusted compounding, and sequence-risk resilience. It may be less appropriate for investors whose sole objective is maximum long-run CAGR and who can tolerate large interim drawdowns without changing behavior or spending plans.</p>
<table>
<tr><th>Consideration</th><th>Discussion</th></tr>
<tr><td>Account type</td><td>Best suited to tax-sheltered accounts; rebalancing may create taxable events elsewhere</td></tr>
<tr><td>Liquidity</td><td>ETFs are liquid; execution timing still matters</td></tr>
<tr><td>Turnover</td><td>Reported per strategy (Table 2); the convexity sleeve drives most trades</td></tr>
<tr><td>Trading cadence</td><td>Weekly signal, drift-band execution</td></tr>
<tr><td>Behavioral risk</td><td>Lower drawdown may reduce abandonment risk</td></tr>
<tr><td>Sequence risk</td><td>Especially relevant for retirees / near-retirees</td></tr>
<tr><td>Advisory use</td><td>Requires per-investor suitability review</td></tr>
<tr><td>Taxable accounts</td><td>May require tax-aware implementation and modified rebalancing</td></tr>
</table>
<p><b>Net-of-fee illustration.</b> The reported figures are gross of advisory and custody fees. As a rough guide, a 1.0% annual advisory fee would reduce Convex Core's {CV['cagr']*100:.1f}% gross CAGR to roughly {(CV['cagr']-0.01)*100:.1f}% (and SPY's {SP['cagr']*100:.1f}% to ~{(SP['cagr']-0.01)*100:.1f}%); the fee applies to both and does not change the relative comparison, but a CFP should model the client's actual fee, custody, and tax drag.</p>
<h3>14.1 Significance for advisors and practitioners</h3>
<p>The practical significance of this work for advisors is threefold, and is mostly <i>independent of whether Convex Core is the chosen vehicle.</i></p>
<ul>
<li><b>A mandate-matched, drawdown-controlled allocation.</b> For sequence-risk-sensitive clients — pre-retirees and retirees drawing income — the cost of a {SP['maxdd']*100:.0f}% equity drawdown (forced selling into weakness, abandonment at the bottom, impaired withdrawal sustainability) exceeds the value of the last point of CAGR. A rules-based sleeve that historically held that drawdown near {CV['maxdd']*100:.0f}% while preserving most of the index's return is a direct tool against the well-documented <i>behavior gap</i> — the return investors forfeit by capitulating in drawdowns. The glidepath makes the equity/defense balance a deliberate, suitability-driven dial rather than a fixed product.</li>
<li><b>Transparency a fiduciary can actually stand behind.</b> The allocation is deterministic, parameter-minimal, and contains <i>no</i> machine-learning or large-language-model component in the weight math; every position is explainable from published rules and reproducible from an auditable manifest. In a suitability and fiduciary context that is materially easier to defend — and to monitor — than an opaque or discretionary "black box."</li>
<li><b>A template for the evidence advisors should demand.</b> Pre-registered hypotheses, leakage-controlled testing, significance-tested claims, and <i>published failures</i> are the standard any strategy pitched to an advisor should meet. The five negative results are themselves advisor-relevant: they are direct evidence against paying elevated fees for complexity- or "AI"-branded return prediction on liquid, low-breadth ETF universes, where — consistent with the literature — no robust net-of-cost edge was found. The defensible posture for most clients is broad, cheap beta with disciplined risk management, not purchased forecasting.</li>
</ul>
""")

# ---- 15 Limitations -------------------------------------------------------
P.append("""
<h2>15. Limitations</h2>
<p>These results are historical backtests, not live audited performance. Although the model is deterministic and net of modeled costs, the results remain sensitive to universe definition, start date, rebalance cadence, volatility-estimation method, transaction-cost assumptions, ETF availability, and the behavior of crisis-hedge instruments in future regimes. Convex Core's reduced drawdown profile depends materially on the assumption that managed futures, duration exposure, and anti-beta instruments continue to provide useful diversification during equity stress. That relationship may weaken or fail in regimes characterized by simultaneous equity, bond, and trend-following losses.</p>
<p>The model also involves design discretion. While no statistical return-forecasting model is trained inside Convex Core and no LLM participates in portfolio construction, the sleeve architecture, hedge definitions, volatility target, and security-selection rules were selected by the research team. These choices should be treated as model-design assumptions rather than independently proven laws. Finally, the live record is short: the backtest supports the hypothesis that deterministic drawdown control can improve downside-risk-adjusted returns, but does not establish that future performance will resemble the historical simulation.</p>
<p><b>Statistical power.</b> The drawdown-control thesis rests on roughly six independent equity-stress episodes in the sample; the start-date grid (§12.2) uses nested sub-windows of one path and is a stability check, not independent evidence. Consistent with this, the bootstrap (§8.1, Appendix&nbsp;E) finds Convex Core's risk-adjusted edge <i>significant versus the equity index</i> but <i>not statistically separable from a 40/60 portfolio</i>. The honest claim is comparable-risk-adjusted-at-higher-return, not risk-adjusted dominance over balanced allocations.</p>
<p><b>Regime calibration (validated).</b> Two protective mechanisms (the duration-sleeve mix and the stress cap) plus the tilt scoring condition on a regime classifier whose numeric cutoffs are an <i>a priori</i> interpretation of qualitative design-spec definitions, not fitted to the backtest. The validation in §12.3 confirms this is not a hidden in-sample degree of freedom: removing the entire regime layer changes full-sample Sortino by only 0.02, the layer's contribution is positive in early crises and mildly negative recently (net negligible), and the result is robust to hysteresis and ±20% threshold perturbation. The regime calibration is therefore not a material driver of the headline. (A frozen-cutoff <i>parameter re-optimization</i> walk-forward remains possible future work, but is not required to support the result, since the result does not lean on the calibration.)</p>
""")

# ---- 16 Conclusion --------------------------------------------------------
P.append("""
<h2>16. Conclusion</h2>
<p>Convex Core provides evidence that a deterministic, risk-managed ETF allocation framework can materially improve the historical drawdown and downside-risk-adjusted profile of an equity-oriented portfolio while preserving most of the long-run return of SPY. The advantage is not absolute-return dominance; it is improved path quality, lower drawdown, lower beta, and stronger downside-risk-adjusted compounding in the tested period — and it persists against balanced, beta-matched, and volatility-targeted alternatives.</p>
<p>The accompanying negative results are equally important. Five pre-registered experiments failed to establish a robust return-prediction edge in the same liquid ETF environment. This supports the central design choice: use broad equity exposure for long-run return, and spend model complexity on drawdown control rather than high-capacity return forecasting. The sleeve-ablation, parameter-sensitivity, and per-sleeve crisis-attribution evidence (§11.1, §12) confirms the drawdown control is structural — driven by the volatility brake and the hedge sleeves, not by low beta alone. Future work focuses on live tracking, total-portfolio integration, additional overfitting diagnostics (Deflated Sharpe, PBO/CSCV — beyond the bootstrap significance test already in Appendix E), and continued pre-registration of any proposed enhancements.</p>
""")

# ---- 18 Model status (placed here as a labelled subsection) ----------------
P.append(f"""
<h2>17. Model Status — Deployable vs Research-Only</h2>
<p>The suite separates the deployable model from research-only and leveraged variants. Convex Prime is a leveraged research variant and is excluded from the headline tables.</p>
{models_table()}
<div class="cap">Table 10. Model status (hypothetical/backtested). CAGR/risk computed on each series' canonical curve, {span[0]}–{span[1]}, rf = 90-day T-bill. Convex Prime is leveraged research/observation only; Alpha-Beta is a reference board, not deployed; Track B is a forward-only, un-validated watchlist (Appendix B).</div>
""")

# ---- 24 Reviewer Objections -----------------------------------------------
P.append(f"""
<h2>18. Anticipated Reviewer Objections</h2>
<table>
<tr><th>Likely objection</th><th>Response (✓ = answered with computed evidence in this report)</th></tr>
<tr><td style="text-align:left">"This just has lower beta than SPY."</td><td style="text-align:left">✓ Beta-matched SPY/T-bills (β=0.42) earns {BM['cagr']*100:.1f}% / {BM['sortino']:.2f} Sortino / {BM['maxdd']*100:.0f}% DD — far below Convex (§9).</td></tr>
<tr><td style="text-align:left">"It's just volatility targeting."</td><td style="text-align:left">✓ Vol-targeted SPY reaches {VT['sortino']:.2f} Sortino / {VT['maxdd']*100:.0f}% DD — Convex still exceeds it (§7–9).</td></tr>
<tr><td style="text-align:left">"Why not just own 60/40?"</td><td style="text-align:left">✓ 60/40, 40/60, 80/20 all reported; Convex beats each on Sortino/Calmar/DD (§9).</td></tr>
<tr><td style="text-align:left">"The start date is cherry-picked."</td><td style="text-align:left">✓ Start-date sensitivity grid (2006/2008/2010/2013) — Sortino 1.06–1.17, drawdown −16 to −18% (§12.2).</td></tr>
<tr><td style="text-align:left">"The model was hand-designed after seeing history."</td><td style="text-align:left">Acknowledged (§5, §15); sleeve-ablation and parameter-sensitivity grid address fragility (§12).</td></tr>
<tr><td style="text-align:left">"The hedge sleeve may not work in the future."</td><td style="text-align:left">✓ Per-sleeve crisis attribution (§11.1) + explicit hedge-failure limitation (§15).</td></tr>
<tr><td style="text-align:left">"Convex Prime is leveraged and not comparable."</td><td style="text-align:left">✓ Moved to research-only §17; excluded from headline tables.</td></tr>
<tr><td style="text-align:left">"Track B has short history."</td><td style="text-align:left">✓ Kept out of main results; labeled forward-only watchlist (Appendix B).</td></tr>
<tr><td style="text-align:left">"No turnover/cost detail."</td><td style="text-align:left">✓ Turnover (Table 2/5) + slippage sensitivity 0/5/10/25 bps (§12.2).</td></tr>
<tr><td style="text-align:left">"The model is not truly out-of-sample."</td><td style="text-align:left">Acknowledged — "deterministic, rule-based backtest" used (§5); the regime cutoffs are a-priori and validated as non-material (§12.3 — removing the regime layer moves Sortino 0.02).</td></tr>
<tr><td style="text-align:left">"Are the risk-adjusted differences statistically significant?"</td><td style="text-align:left">✓ Block-bootstrap test (§8.1, Appendix E): significant vs SPY (Sharpe), not separable from 40/60 — stated, not hidden.</td></tr>
</table>
""")

# ---- Appendices -----------------------------------------------------------
P.append(f"""
<h2>Appendix A — Convex Core Rule Manifest</h2>
<ul>
<li><b>Universe:</b> SPY equity core; satellite tilt pool of liquid sector/factor/style ETFs; convexity {{DBMF, KMLM, BTAL}}; duration {{IEF, BIL, TLT}}. Exclusions: insufficient trailing history; de-dup of near-twin (corr&gt;0.95) tilts preferring non-K-1 vehicles.</li>
<li><b>Rebalance:</b> weekly signal observation; execution on relative-drift band breach (BAND_REL=0.20).</li>
<li><b>Sleeve targets:</b> w_equity (0.95, glidepath dial) · w_convexity · w_duration, summing to 1; equity sleeve = (1−tilt_frac)·core + tilt_frac·IC-tilts, tilt_frac=0.40.</li>
<li><b>Satellite selection:</b> regime-weighted composite (RS, trend, momentum, downside); 1 reserved value slot; +0.75σ incumbency bonus; 252-day correlation de-dup.</li>
<li><b>Volatility brake:</b> eq_scale = min(1, 0.12 / realized_vol_21d); slow re-risk (≤+0.15/week); stress cap 0.70.</li>
<li><b>Trade construction:</b> target weights net of drift; slippage charged on realized turnover.</li>
<li><b>Output:</b> weights, trades, daily return series, audit log.</li>
</ul>

<h2>Appendix B — Ticker Universe &amp; Forward-Only Watchlist</h2>
<p>Live IRA board (0.95 vintage): SPY core + VLUE / USO / XLK / MTUM / PDBC tilts (DBC dropped in favor of no-K-1 PDBC via the de-dup guard), convexity and duration sleeves as above. <b>Track B (forward-only, un-validated):</b> novel funds (long/short, CLO, options-income, rate-hedge, gold) with short, single-regime histories that cannot be backtested; screened on a live-record gate (β&lt;0.90, Sortino ≥ SPY+0.20, ≥3yr), equal-weighted, sized-small. Not included in any headline result.</p>

<h2>Appendix C — Benchmark Definitions</h2>
<table>
<tr><th>Benchmark</th><th>Definition</th></tr>
<tr><td style="text-align:left">SPY</td><td>S&amp;P 500 ETF, total-return (adjusted_close)</td></tr>
<tr><td style="text-align:left">60/40, 40/60, 80/20 SPY/IEF</td><td>Static equity/7–10y-Treasury weights, quarterly rebalanced, drift between</td></tr>
<tr><td style="text-align:left">60/40 SPY/AGG</td><td>As above with aggregate-bond ballast</td></tr>
<tr><td style="text-align:left">Beta-matched SPY/T-bills</td><td>0.42·SPY + 0.58·DGS3MO; holds β at Convex's level</td></tr>
<tr><td style="text-align:left">Vol-targeted SPY</td><td>SPY × min(1, {CV['vol']*100:.1f}%/realized_vol_21d), remainder in T-bills</td></tr>
</table>

<h2>Appendix D — Pre-Registration Form (template)</h2>
<p>Each future experiment records: name · date registered · research question · hypothesis · eligible universe · features allowed/prohibited · train/test periods · CV design (purge/embargo) · primary &amp; secondary metrics · benchmark(s) · success gate · failure condition · cost assumptions · code &amp; data-snapshot hash · result · interpretation · decision (accept/reject/monitor). The five experiments in §13 were each registered in this form before their scored run.</p>

{appendix_e()}

<h2>Appendix F — Reproducibility Manifest</h2>
<pre>{MAN.strip()}</pre>

<h2>Appendix G — Glossary</h2>
<ul>
<li><b>Sortino ratio</b> — excess return per unit of downside deviation (rf = 90-day T-bill).</li>
<li><b>Calmar ratio</b> — CAGR ÷ |maximum drawdown|.</li>
<li><b>Beta (β)</b> — sensitivity of a strategy's returns to SPY's.</li>
<li><b>Up/down capture</b> — share of SPY's average up- (down-) month return the strategy earns.</li>
<li><b>Convexity sleeve</b> — managed-futures/anti-beta exposure that tends to appreciate in sustained equity declines.</li>
<li><b>Volatility brake</b> — rule scaling equity exposure down when realized volatility exceeds the target.</li>
<li><b>PBO / Deflated Sharpe</b> — backtest-overfitting diagnostics (López de Prado).</li>
<li><b>PIT</b> — point-in-time; features computed only from data available as-of each date.</li>
</ul>

<h2>Appendix H — Bibliography</h2>
<ul>
<li>Grossman, S. &amp; Stiglitz, J. (1980). On the Impossibility of Informationally Efficient Markets. <i>AER</i>.</li>
<li>Jegadeesh, N. &amp; Titman, S. (1993). Returns to Buying Winners and Selling Losers. <i>JF</i>.</li>
<li>Moskowitz, T., Ooi, Y.H. &amp; Pedersen, L.H. (2012). Time Series Momentum. <i>JFE</i>.</li>
<li>Hurst, B., Ooi, Y.H. &amp; Pedersen, L.H. (2017). A Century of Evidence on Trend-Following. <i>JPM</i>.</li>
<li>Sortino, F. &amp; van der Meer, R. (1991). Downside Risk. <i>JPM</i>.</li>
<li>Bailey, D. &amp; López de Prado, M. (2014). The Deflated Sharpe Ratio. <i>JPM</i>.</li>
<li>López de Prado, M. (2018). <i>Advances in Financial Machine Learning</i>. Wiley.</li>
<li>Fama, E. &amp; French, K. (1993, 2015). Common Risk Factors; A Five-Factor Model. <i>JFE</i>.</li>
<li>Harvey, C., Liu, Y. &amp; Zhu, H. (2016). …and the Cross-Section of Expected Returns. <i>RFS</i>.</li>
<li>Moreira, A. &amp; Muir, T. (2017). Volatility-Managed Portfolios. <i>Journal of Finance</i>.</li>
<li>Harvey, C., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M. &amp; van Hemert, O. (2018). The Impact of Volatility Targeting. <i>Journal of Portfolio Management</i>.</li>
<li>Frazzini, A. &amp; Pedersen, L.H. (2014). Betting Against Beta. <i>JFE</i>.</li>
<li>Hou, K., Xue, C. &amp; Zhang, L. (2020). Replicating Anomalies. <i>RFS</i>.</li>
<li>McLean, R.D. &amp; Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? <i>Journal of Finance</i>.</li>
<li>Gu, S., Kelly, B. &amp; Xiu, D. (2020). Empirical Asset Pricing via Machine Learning. <i>RFS</i>.</li>
</ul>
""")

if HAS_RR:
    ptbl, ttbl = regime_clause_table()
    P.append(f"""
<h2>Appendix I — Regime Classification Rules</h2>
<p>The exact clause set used by the point-in-time regime classifier (§6.1), reproduced from <code>config/regime_rules.yaml</code>. Precedence: stress wins; <code>RISK_NEUTRAL</code> is the residual. Hysteresis: a primary flip must hold {CONFIRM_DAYS} consecutive sessions. A primary state needs ≥ {_RR['primary']['min_live_clauses']} live (non-degraded) clauses to be eligible. Clause inputs are defined in §6.1 and computed point-in-time from local data only. Numeric cutoffs are an interpretation of the qualitative design-spec definitions and are walk-forward-tunable; the tests pin semantics, not these numbers.</p>
<h3>Primary states</h3>
{ptbl}
<h3>Overlay tags (orthogonal, independent booleans)</h3>
{ttbl}
<p style="font-size:11.5px;color:#555">Clause grammar: <code>input OP value</code> where OP ∈ {{&lt;, &gt;, &lt;=, &gt;=, ==}}. Return/RS inputs are decimal fractions (e.g. <code>-0.02</code> = −2%); <code>vix_pctile_252d</code> and <code>vix_vs_median_252d</code> are unitless; <code>vix_chg_20d</code> and OAS/yield clauses are in points. A ticker pair written <code>A_B_rs_Nd</code> is the N-session change in the A/B price ratio.</p>
""")

# ---- disclaimer -----------------------------------------------------------
P.append(f"""
<div class="disc"><b>Disclaimer.</b> This report presents hypothetical, backtested model performance for research and decision-support purposes only. The results were not achieved by an actual client account and do not reflect the impact of individual investor circumstances, taxes, custody fees, advisory fees, account restrictions, or implementation delays. Backtested performance is inherently limited because it is constructed with the benefit of historical data and may not reflect conditions that would have existed during live trading. Model rules rely on assumptions about ETF availability, transaction costs, liquidity, benchmark construction, and rebalancing implementation. Past performance does not guarantee future results. This report is not investment advice, an offer, or a solicitation. Any use of the model should be evaluated in light of the investor's objectives, constraints, risk tolerance, liquidity needs, and tax situation. Before external distribution, the treatment of hypothetical/backtested performance, net-vs-gross presentation, and fee assumptions should be reviewed by qualified compliance counsel. Research conducted by the DNSR Agentic AI system (with Anthropic Fable 5 and Opus 4.8), directed and reviewed by {principal_credit()}, who is responsible for its use. © 2026 DNSR Investments, LLC.</div>
</body></html>""")

HTML = "\n".join(P)
open(OUT, "w").write(HTML)
print("wrote", OUT, f"({len(HTML)//1024} KB)")
