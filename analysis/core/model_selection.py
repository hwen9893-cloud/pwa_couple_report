"""Model selection criteria for amplitude analysis jobs.

Implements information-theoretic model comparison (AIC, ΔAIC) and
significance-based nested model testing, following the statistical
framework standard in partial wave analysis:

  AIC  = 2k + 2·NLL       (Akaike Information Criterion)
  BIC  = k·ln(N) + 2·NLL  (Bayesian IC, requires N_events)
  ΔAIC = AIC_j − AIC_best

For nested models (same data, different parameter sets), 2ΔNLL ~ χ²(Δk)
under Wilks' theorem.  The AIC penalises model complexity independently of
statistical significance, and is the recommended criterion when models are
not strictly nested.

References
----------
- Akaike, 1974, IEEE Trans. Autom. Control 19(6):716
- Tanabashi et al. (PDG), 2020, Phys. Rev. D, §40 Statistics
- M. Williams, JINST 5:P09004 (2010) – AIC/BIC in amplitude analysis
"""

from __future__ import annotations
import math
import numpy as np
from scipy import stats

from .job import JobData
from .checks import STATUS_OK, STATUS_WARN, STATUS_FAIL


def _n_free(job: JobData) -> int:
    """Number of floated (non-zero error) parameters."""
    return sum(1 for v in job.params_error.values() if abs(v) > 1e-10)


def compute_aic(job: JobData) -> float | None:
    """AIC = 2k − 2·ln L = 2k + 2·NLL  (we minimise NLL = −ln L)."""
    if not math.isfinite(job.status.nll):
        return None
    return 2 * _n_free(job) + 2 * job.status.nll


def compute_bic(job: JobData, n_events: int) -> float | None:
    """BIC = k·ln(N) − 2·ln L = k·ln(N) + 2·NLL."""
    if not math.isfinite(job.status.nll):
        return None
    return _n_free(job) * math.log(n_events) + 2 * job.status.nll


def compare_aic(jobs: list[JobData]) -> list[dict]:
    """Compare all jobs by AIC and 2ΔNLL significance.

    Returns a list of dicts (one per job), sorted by AIC ascending.
    Each dict contains:
      name, nll, ndf, n_free, aic, delta_aic, delta_nll, two_delta_nll,
      df_wilks, sigma_wilks, aic_weight, status, message
    """
    valid = [(j, compute_aic(j)) for j in jobs if compute_aic(j) is not None]
    if not valid:
        return []

    # Best by NLL
    best_job   = min(valid, key=lambda x: x[0].status.nll)[0]
    best_nll   = best_job.status.nll
    best_ndf   = best_job.status.ndf
    best_nfree = _n_free(best_job)

    # Best by AIC (may differ from best NLL if a simpler model is preferable)
    best_aic   = min(a for _, a in valid)

    # Akaike weights  w_i = exp(-0.5·ΔAIC_i) / Σ exp(-0.5·ΔAIC_j)
    # ΔAIC_i ≥ 0 by construction; clamp at 700 so exp(-350) ≈ 0 without overflow.
    aics       = [a for _, a in valid]
    delta_aics = [a - best_aic for a in aics]
    exp_terms  = [math.exp(-0.5 * min(d, 700.0)) for d in delta_aics]
    total      = sum(exp_terms) or 1.0
    weights    = [e / total for e in exp_terms]

    results = []
    for (job, aic), da, w in zip(valid, delta_aics, weights):
        k        = _n_free(job)
        delta_nll  = float(job.status.nll - best_nll)
        two_delta  = 2.0 * abs(delta_nll)
        df_wilks   = max(1, abs(best_ndf - job.status.ndf))
        p_value    = float(stats.chi2.sf(two_delta, df=df_wilks)) if job is not best_job else 1.0
        sigma      = float(stats.norm.isf(p_value / 2)) if 0 < p_value < 1 else 99.0

        # AIC decision
        if da < 2:
            aic_verdict = "substantial support"
        elif da < 7:
            aic_verdict = "considerably less support"
        else:
            aic_verdict = "essentially no support"

        is_best_nll = (job is best_job)
        is_best_aic = abs(da) < 1e-9

        if is_best_nll and is_best_aic:
            status = STATUS_OK
            msg    = "NLL 最优 & AIC 最优"
        elif is_best_nll and not is_best_aic:
            status = STATUS_WARN
            msg    = f"NLL 最优但 ΔAIC={da:.1f}，有更简洁模型"
        elif is_best_aic and not is_best_nll:
            status = STATUS_OK
            msg    = f"AIC 最优（更简洁），2ΔNLL={two_delta:.1f} vs NLL 最优"
        elif da < 2:
            status = STATUS_OK
            msg    = f"ΔAIC={da:.1f} < 2，与最优模型实质等价"
        elif da < 7:
            status = STATUS_WARN
            msg    = f"ΔAIC={da:.1f}，模型支持度明显较弱"
        else:
            status = STATUS_FAIL
            msg    = f"ΔAIC={da:.1f} > 7，基本无模型支持"

        results.append(dict(
            name          = job.name,
            nll           = job.status.nll,
            ndf           = job.status.ndf,
            n_free        = k,
            aic           = aic,
            delta_aic     = da,
            aic_weight    = w,
            aic_verdict   = aic_verdict,
            delta_nll     = delta_nll,
            two_delta_nll = two_delta,
            df_wilks      = df_wilks,
            sigma_wilks   = sigma,
            is_best_nll   = is_best_nll,
            is_best_aic   = is_best_aic,
            status        = status,
            message       = msg,
        ))

    results.sort(key=lambda x: x["aic"])
    return results
