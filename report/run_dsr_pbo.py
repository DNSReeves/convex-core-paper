#!/usr/bin/env python3
"""Statistical-robustness addendum: Deflated Sharpe Ratio (DSR) and Probability
of Backtest Overfitting (PBO / CSCV) for Convex Core.

This is a COMPANION ADDENDUM to the v1.0.2 paper — it does not modify the paper.
It addresses the one piece of "future work" the review board left open: quantify
how much of Convex Core's risk-adjusted performance could be a multiple-testing /
overfitting artifact.

Method (Bailey & Lopez de Prado):
  * Trial set  — the genuine configuration search space of the model: the two
    continuous dials, w_equity x vol_target (7 x 4 = 28 configs). The deployed
    paper config is (w_equity=0.95, vol_target=0.12). Each config is run through
    the SAME deterministic engine; full monthly return streams are collected.
  * DSR        — deflate the deployed config's Sharpe for (a) the number of trials
    N and the dispersion of Sharpe across them, and (b) the non-normality (skew,
    kurtosis) of its own returns. DSR is the probability the true Sharpe exceeds
    the expected-maximum-Sharpe-under-the-null, i.e. that the result is not a
    selection artifact. (Deflated Sharpe Ratio, Bailey & Lopez de Prado 2014.)
  * PBO        — Combinatorially-Symmetric Cross-Validation (CSCV): split the
    monthly panel into S blocks, for every split of S/2 blocks in-sample vs the
    rest out-of-sample, pick the in-sample-best config and measure its OOS rank.
    PBO = P(the IS-best lands below the OOS median). (Bailey, Borwein,
    Lopez de Prado & Zhu 2017.)

Honest prior: the model is parameter-minimal and the dials were fixed a-priori
(not optimized), so we EXPECT a small effective number of trials -> low PBO and a
DSR that survives. A clean result here corroborates the paper's determinism claim;
it does not manufacture a new one.

Emits dnsr-agent/workspace/pub_report/dsr_pbo.json. Read-only DB; live config untouched.
Run from the dnsr-agent venv:
  python etf-trade-classifier/scripts/research/pub_tier2/run_dsr_pbo.py
"""
from __future__ import annotations
import sys, json, sqlite3
from itertools import combinations
from math import comb, e as E_CONST
import numpy as np, pandas as pd, yaml
from scipy.stats import norm, skew as _skew, kurtosis as _kurt

REPO = "${PAPER_ROOT}/engine"
AGENT = "${PAPER_ROOT}"
sys.path.insert(0, REPO)
from tradeclassifier.config import load_config
from tradeclassifier.loaders import Warehouse
from tradeclassifier.portfolio import MODEL_FILE, UNIVERSE_FILE
from tradeclassifier.alpha_backtest import precompute_alpha_data
from tradeclassifier.convex_core import (DEFAULTS, V2_BRAKE, V2_DEDUP_CORR, V2_DEDUP_PREFER_DROP,
                                         V2_N_TILTS, V2_PERSISTENCE, V2_TILT_POOL, V2_VALUE_SLOTS,
                                         precompute_scores, simulate_convex)

OUT = f"{AGENT}/workspace/pub_report/dsr_pbo.json"
EULER_GAMMA = 0.5772156649015329

# ----- trial set: the genuine config search space (two continuous dials) --------
W_EQUITY = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
VOL_TGT  = (0.10, 0.12, 0.14, 0.16)
DEPLOYED = (0.95, 0.12)          # the paper headline config
S_BLOCKS = 16                    # CSCV blocks -> C(16,8) = 12870 symmetric splits

# ------------------------------------------------------------------ panel + cache
cfg = load_config(f"{REPO}/config/classifier.yaml")
ucfg = yaml.safe_load(open(UNIVERSE_FILE)); mcfg = yaml.safe_load(open(MODEL_FILE))
wh = Warehouse(cfg["data"]["db_path"])
print("precomputing panel …", flush=True)
data = precompute_alpha_data(wh, ucfg, "2005-01-01", "2026-06-10",
                             confirm_days=int(cfg["regime"]["confirm_days"]))
print("precomputing scores …", flush=True)
scores = precompute_scores(data, mcfg)

BASE = dict(brake_cfg=V2_BRAKE, tilt_pool=V2_TILT_POOL, n_tilts=V2_N_TILTS,
            value_slots=V2_VALUE_SLOTS, persistence_margin=V2_PERSISTENCE,
            dedup_corr=V2_DEDUP_CORR, dedup_prefer_drop=V2_DEDUP_PREFER_DROP,
            scores_cache=scores, collect_returns=True)

def trial_label(we, vt):
    return f"we{we:.2f}_vt{vt:.2f}"

# ------------------------------------------------------------- run the trial grid
print(f"running {len(W_EQUITY)*len(VOL_TGT)} trials …", flush=True)
monthly = {}     # label -> monthly return Series
for we in W_EQUITY:
    for vt in VOL_TGT:
        cx = simulate_convex(data, mcfg, params={**DEFAULTS, "w_equity": we, "vol_target": vt}, **BASE)
        s = pd.Series(cx.daily_returns, index=pd.to_datetime([str(d) for d in cx.dates]))
        m = (1.0 + s).resample("ME").prod() - 1.0
        monthly[trial_label(we, vt)] = m
        tag = "  <-- DEPLOYED" if (we, vt) == DEPLOYED else ""
        print(f"  {trial_label(we, vt)}  months={len(m)}{tag}", flush=True)

M = pd.DataFrame(monthly).dropna(how="any")     # common-month panel, T x N
labels = list(M.columns)
dep_lbl = trial_label(*DEPLOYED)
R = M.values                                    # (T, N) monthly returns
T, N = R.shape
print(f"panel: T={T} months  x  N={N} trials  ({M.index[0].date()} -> {M.index[-1].date()})", flush=True)

def sharpe_cols(a):
    """Per-column (per-trial) non-annualized Sharpe of a (rows x N) block."""
    mu = a.mean(axis=0)
    sd = a.std(axis=0, ddof=1)
    out = np.where(sd > 0, mu / sd, 0.0)
    return out

# ===================================================================== DSR =======
dep = R[:, labels.index(dep_lbl)]
sr_hat = float(dep.mean() / dep.std(ddof=1))             # deployed monthly Sharpe
g3 = float(_skew(dep, bias=False))                       # skewness
g4 = float(_kurt(dep, fisher=False, bias=False))         # kurtosis (normal = 3)
sr_all = sharpe_cols(R)                                  # monthly Sharpe per trial
var_sr = float(np.var(sr_all, ddof=1))                   # dispersion of Sharpe across trials

# expected maximum Sharpe under the null (true SR = 0), given N trials
emax = np.sqrt(var_sr) * ((1 - EULER_GAMMA) * norm.ppf(1 - 1.0 / N)
                          + EULER_GAMMA * norm.ppf(1 - 1.0 / (N * E_CONST)))

def psr(sr, sr_star):
    """Probabilistic Sharpe Ratio: P(true SR > sr_star) given skew/kurt/T."""
    denom = np.sqrt(1 - g3 * sr + ((g4 - 1) / 4.0) * sr * sr)
    return float(norm.cdf((sr - sr_star) * np.sqrt(T - 1) / denom))

dsr = psr(sr_hat, emax)            # deflated: benchmark = expected-max-under-null
psr0 = psr(sr_hat, 0.0)            # vanilla PSR vs SR*=0 (ignoring multiplicity)

# minimum track-record length to call sr_hat > emax at 95%
z95 = norm.ppf(0.95)
denom = (1 - g3 * sr_hat + ((g4 - 1) / 4.0) * sr_hat ** 2)
mintrl = float(1 + denom * (z95 / (sr_hat - emax)) ** 2) if sr_hat > emax else None

ann = np.sqrt(12)
dsr_block = dict(
    deployed_config=dict(w_equity=DEPLOYED[0], vol_target=DEPLOYED[1]),
    n_trials=N, T_months=T,
    sharpe_monthly=sr_hat, sharpe_annualized=sr_hat * ann,
    skew=g3, kurtosis=g4,
    var_sharpe_across_trials=var_sr,
    expected_max_sharpe_null_monthly=float(emax),
    expected_max_sharpe_null_annualized=float(emax * ann),
    deflated_sharpe_ratio=dsr,
    psr_vs_zero=psr0,
    min_track_record_length_months_95=mintrl,
    note="DSR is P(true Sharpe > expected-max-Sharpe-under-the-null at N trials). "
         ">0.95 => the deployed Sharpe survives multiple-testing deflation.")
print(f"\nDSR: SR(monthly)={sr_hat:.3f} (ann {sr_hat*ann:.2f})  skew={g3:.2f}  kurt={g4:.2f}  "
      f"E[maxSR|null]={emax:.3f}  -> DSR={dsr:.3f}  (PSR vs0={psr0:.3f})", flush=True)

# ===================================================================== PBO =======
# trim to a multiple of S, keeping the most-recent rows; contiguous equal blocks
L = T // S_BLOCKS
T_used = L * S_BLOCKS
Rb = R[T - T_used:]                                  # (T_used, N)
block_id = np.repeat(np.arange(S_BLOCKS), L)
# per-block sufficient stats: count, sum, sum-of-squares  (per trial)
S1 = np.array([Rb[block_id == b].sum(axis=0) for b in range(S_BLOCKS)])      # (S, N)
S2 = np.array([(Rb[block_id == b] ** 2).sum(axis=0) for b in range(S_BLOCKS)])
NB = np.array([int((block_id == b).sum()) for b in range(S_BLOCKS)])         # (S,)

def block_sharpe(blocks):
    n = NB[list(blocks)].sum()
    s1 = S1[list(blocks)].sum(axis=0)
    s2 = S2[list(blocks)].sum(axis=0)
    mu = s1 / n
    var = (s2 - n * mu * mu) / (n - 1)
    sd = np.sqrt(np.maximum(var, 0.0))
    return np.where(sd > 0, mu / sd, 0.0)

all_blocks = set(range(S_BLOCKS))
logits, oos_of_best, is_best_sr, oos_of_best_sr = [], [], [], []
n_combos = comb(S_BLOCKS, S_BLOCKS // 2)
print(f"\nCSCV: S={S_BLOCKS} blocks of {L} months, {n_combos} symmetric splits …", flush=True)
for is_blocks in combinations(range(S_BLOCKS), S_BLOCKS // 2):
    oos_blocks = tuple(all_blocks - set(is_blocks))
    sr_is = block_sharpe(is_blocks)
    sr_oos = block_sharpe(oos_blocks)
    n_star = int(np.argmax(sr_is))
    # relative OOS rank of the IS-best (1 = best OOS, 0 = worst)
    rank = float((sr_oos <= sr_oos[n_star]).sum()) / N          # in (0,1]
    w = min(max(rank, 1.0 / (N + 1)), N / (N + 1))              # clamp off 0/1
    logits.append(np.log(w / (1 - w)))
    oos_of_best.append(rank)
    is_best_sr.append(float(sr_is[n_star]))
    oos_of_best_sr.append(float(sr_oos[n_star]))

logits = np.array(logits)
pbo = float((logits <= 0).mean())                       # P(IS-best below OOS median)
prob_oos_loss = float((np.array(oos_of_best_sr) < 0).mean())
# performance degradation: OLS slope of OOS Sharpe on IS Sharpe of the selected config
xb = np.array(is_best_sr); yb = np.array(oos_of_best_sr)
slope = float(np.polyfit(xb, yb, 1)[0]) if xb.std() > 0 else None

pbo_block = dict(
    method="Combinatorially-Symmetric Cross-Validation (CSCV)",
    n_trials=N, S_blocks=S_BLOCKS, block_len_months=L, months_used=T_used, n_splits=n_combos,
    pbo=pbo,
    median_oos_rank_of_is_best=float(np.median(oos_of_best)),
    prob_oos_sharpe_below_zero=prob_oos_loss,
    oos_is_degradation_slope=slope,
    note="PBO = fraction of splits where the in-sample-best config lands below the "
         "out-of-sample median. <0.5 acceptable; the deterministic, a-priori design "
         "predicts a low value.")
print(f"PBO={pbo:.3f}  median OOS rank(IS-best)={np.median(oos_of_best):.2f}  "
      f"P(OOS Sharpe<0)={prob_oos_loss:.3f}  degradation slope={slope:.2f}", flush=True)

# ===================================================================== emit =======
out = dict(
    meta=dict(
        title="Statistical-Robustness Addendum — DSR & PBO",
        relation="companion addendum to the v1.0.2 paper (paper unchanged)",
        trial_set="w_equity x vol_target config grid (the model's continuous dials)",
        w_equity_grid=list(W_EQUITY), vol_target_grid=list(VOL_TGT),
        deployed=dict(w_equity=DEPLOYED[0], vol_target=DEPLOYED[1]),
        panel=dict(T_months=T, N_trials=N,
                   start=str(M.index[0].date()), end=str(M.index[-1].date())),
        risk_free="none (raw Sharpe on monthly total returns; DSR/PBO are scale-free in rf)",
        references=[
            "Bailey, D. & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. J. Portfolio Management.",
            "Bailey, Borwein, Lopez de Prado & Zhu (2017). The Probability of Backtest Overfitting. J. Computational Finance."]),
    dsr=dsr_block, pbo=pbo_block,
    trials={lbl: dict(sharpe_monthly=float(sr_all[i]),
                      sharpe_annualized=float(sr_all[i] * ann))
            for i, lbl in enumerate(labels)})
json.dump(out, open(OUT, "w"), indent=1)
print("\nwrote", OUT)
