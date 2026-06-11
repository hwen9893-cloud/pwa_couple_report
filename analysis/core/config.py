"""Centralized thresholds for all evaluation checks.

Modify values here to tune ok/warn/fail boundaries globally without
touching any check logic in checks.py.
"""

# ── NLL stability (spread across multi-start loops) ──────────────────────────
NLL_SPREAD_OK   = 5.0    # spread < this → ok
NLL_SPREAD_WARN = 20.0   # spread >= this → fail

# fraction of loops that must land within best+1 before triggering extra warn
CONV_FRACTION_WARN = 0.5

# ── Cross-job significance  2ΔNLL ~ χ²(df) under Wilks' theorem ──────────────
TWO_DELTA_NLL_WARN = 9.0    # ≈ 3σ for df=1
TWO_DELTA_NLL_FAIL = 25.0   # ≈ 5σ for df=1

# ── Parameter pull vs PDG reference ──────────────────────────────────────────
PULL_WARN = 2.0   # |pull| >= this → warn
PULL_FAIL = 3.0   # |pull| >= this → fail

# ── Fit fraction significance (FF / FF_err) ───────────────────────────────────
FF_SIG_CAUTION = 2.0   # below this → strong warn
FF_SIG_WARN    = 3.0   # below this → warn

# ── Interference completeness  |∑ FF_matrix − 1| ─────────────────────────────
INTERFERENCE_DEV_OK   = 0.05
INTERFERENCE_DEV_WARN = 0.15

# ── Parameter correlation |ρ| ─────────────────────────────────────────────────
CORR_WARN = 0.90   # |ρ| above this → warn
CORR_FAIL = 0.95   # |ρ| above this → fail

# ── Cross-channel shared resonance FF total ───────────────────────────────────
FF_CROSS_TOTAL_WARN = 1.5   # ch0_FF + ch1_FF above this → warn
