"""Self-contained model config for the engine tests (extracted from the private
test suite so the companion repo runs standalone, without the broader app)."""
MCFG = {
    "regime_weight_templates": {
        k: {f: w for f, w in zip(
            ("mom_12_1", "vol_adj_mom_63", "rs_63", "ma_dist_200",
             "rolling_alpha_252", "down_capture_inv", "dd_improve",
             "rsi_centered"),
            (0.25, 0.20, 0.20, 0.15, 0.10, 0.0, 0.05, 0.05))}
        for k in ("RISK_ON", "RISK_NEUTRAL", "RECOVERY", "RISK_OFF",
                  "LIQUIDITY_STRESS")},
    "beta": {"raw_blend": {"short_window": 63, "long_window": 252,
                           "short_weight": 0.5},
             "shrink_to_prior": 0.30,
             "stress": {"bench_ret_threshold": -0.01,
                        "window_sessions": 504, "min_stress_days": 15},
             "band_halfwidth": 0.05, "stress_band_excess": 0.15},
    "optimizer": {"max_names": 25, "min_position": 0.01, "min_trade": 0.005,
                  "z_clip": 3.0},
    "display": {"score_center": 50.0, "score_scale": 16.7},
}
