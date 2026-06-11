"""Evaluation checks implementing the 8-point assessment framework.

Each check returns a structured result dict with keys:
  name, status ('ok'|'warn'|'fail'), value, message
"""

from __future__ import annotations
import numpy as np
from scipy import stats
from .job import JobData
from .pdg import pdg_lookup
from .config import (
    NLL_SPREAD_OK, NLL_SPREAD_WARN, CONV_FRACTION_WARN,
    TWO_DELTA_NLL_WARN, TWO_DELTA_NLL_FAIL,
    PULL_WARN, PULL_FAIL,
    FF_SIG_CAUTION, FF_SIG_WARN,
    INTERFERENCE_DEV_OK, INTERFERENCE_DEV_WARN,
    CORR_WARN, CORR_FAIL,
    FF_CROSS_TOTAL_WARN,
)

STATUS_OK   = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"


def _result(name, status, value, message):
    return dict(name=name, status=status, value=value, message=message)


# ═══════════════════════════════════════════════════════════════
# CHECK 1: NLL convergence (single job)
# ═══════════════════════════════════════════════════════════════

def check_nll_stability(job: JobData) -> dict:
    """Check how spread the per-loop NLL values are."""
    nlls = np.array(job.loop_nlls)
    if len(nlls) == 0:
        return _result("NLL稳定性", STATUS_WARN, None, "无法解析循环 NLL（日志缺失）")

    best          = float(np.min(nlls))
    spread        = float(np.max(nlls) - best)
    conv_fraction = float(np.mean(nlls < best + 1.0))

    if spread < NLL_SPREAD_OK:
        status = STATUS_OK
        msg = f"NLL 散布 {spread:.2f}，收敛良好（best={best:.2f}，{len(nlls)} 次）"
    elif spread < NLL_SPREAD_WARN:
        status = STATUS_WARN
        msg = f"NLL 散布 {spread:.2f}，可能存在局部极小值，建议增加 LOOP 次数"
    else:
        status = STATUS_FAIL
        msg = f"NLL 散布 {spread:.2f}（>{NLL_SPREAD_WARN}），似然面复杂，全局最优可疑"

    if conv_fraction < CONV_FRACTION_WARN and status != STATUS_FAIL:
        status = STATUS_WARN
        msg += f"；仅 {conv_fraction:.0%} 循环落在 best+1 范围内"

    return _result(
        "NLL稳定性",
        status,
        {"nlls": nlls.tolist(), "best": best, "spread": spread,
         "conv_fraction": conv_fraction, "n_loops": len(nlls)},
        msg,
    )


# ═══════════════════════════════════════════════════════════════
# CHECK 2: ΔNLL significance (between jobs)
# ═══════════════════════════════════════════════════════════════

def check_delta_nll(jobs: list[JobData]) -> list[dict]:
    """Compare all jobs vs. the best and compute ΔNLL significance.

    Degrees of freedom for the χ² test are estimated from the absolute
    difference in Ndf between each job and the best (Wilks' theorem for
    nested models). Falls back to df=1 when Ndf is equal or unknown.
    """
    nlls = np.array([j.status.nll for j in jobs], dtype=float)
    finite_mask = np.isfinite(nlls)

    if not np.any(finite_mask):
        return [_result("ΔNLL", STATUS_FAIL, None, "所有 job 的 NLL 均为 NaN，无法比较")]

    best_idx  = int(np.where(finite_mask, nlls, np.inf).argmin())
    best_nll  = float(nlls[best_idx])
    best_ndf  = jobs[best_idx].status.ndf

    results = []
    for i, job in enumerate(jobs):
        if not np.isfinite(job.status.nll):
            results.append(_result(
                f"ΔNLL [{job.name}]", STATUS_FAIL,
                {"nll": None},
                "NLL 为 NaN，拟合可能未完成或输出文件损坏",
            ))
            continue

        delta     = float(job.status.nll - best_nll)
        two_delta = 2.0 * abs(delta)
        df        = max(1, abs(best_ndf - job.status.ndf))

        p_value = float(stats.chi2.sf(two_delta, df=df)) if i != best_idx else 1.0
        sigma   = float(stats.norm.isf(p_value / 2)) if 0 < p_value < 1 else 99.0

        if i == best_idx:
            status, msg = STATUS_OK, "当前最优拟合"
        elif two_delta > TWO_DELTA_NLL_FAIL:
            status = STATUS_FAIL
            msg = f"2ΔNLL={two_delta:.1f} (df={df})，劣于最优 >{sigma:.1f}σ"
        elif two_delta > TWO_DELTA_NLL_WARN:
            status = STATUS_WARN
            msg = f"2ΔNLL={two_delta:.1f} (df={df})，差异显著（{sigma:.1f}σ）"
        else:
            status = STATUS_OK
            msg = f"2ΔNLL={two_delta:.1f} (df={df})，差异不显著"

        results.append(_result(
            f"ΔNLL [{job.name}]",
            status,
            {"nll": job.status.nll, "delta_nll": delta,
             "two_delta_nll": two_delta, "sigma": sigma, "df": df},
            msg,
        ))
    return results


# ═══════════════════════════════════════════════════════════════
# CHECK 3: Error matrix positive definiteness
# ═══════════════════════════════════════════════════════════════

def check_error_matrix(job: JobData) -> dict:
    """Check that the error (covariance) matrix is positive definite."""
    M = job.error_matrix
    if M is None:
        return _result("误差矩阵", STATUS_WARN, None, "未找到误差矩阵文件")

    try:
        eigvals = np.linalg.eigvalsh(M)
    except np.linalg.LinAlgError:
        return _result("误差矩阵", STATUS_FAIL, None, "误差矩阵奇异，无法分解")

    n_neg   = int(np.sum(eigvals < 0))
    n_zero  = int(np.sum(np.abs(eigvals) < 1e-10))
    min_eig = float(np.min(eigvals))
    nonzero = np.abs(eigvals[eigvals != 0])
    cond    = float(np.max(np.abs(eigvals)) / max(np.min(nonzero) if len(nonzero) else 1, 1e-30))

    if n_neg == 0 and n_zero == 0:
        status = STATUS_OK
        msg = f"正定 ✓（最小特征值={min_eig:.2e}，条件数={cond:.2e}）"
    elif n_neg == 0:
        status = STATUS_WARN
        msg = f"半正定（{n_zero} 个零特征值），部分参数未约束"
    else:
        status = STATUS_FAIL
        msg = f"非正定！{n_neg} 个负特征值（最小={min_eig:.2e}），拟合未真正收敛"

    return _result(
        "误差矩阵正定性", status,
        {"n_neg_eigenvalues": n_neg, "n_zero_eigenvalues": n_zero,
         "min_eigenvalue": min_eig, "condition_number": cond},
        msg,
    )


# ═══════════════════════════════════════════════════════════════
# CHECK 4: Parameter Pull vs PDG
# ═══════════════════════════════════════════════════════════════

def check_parameter_pulls(job: JobData) -> list[dict]:
    """Check mass/width parameters against PDG values."""
    results  = []
    n_floated = 0

    for pname, pval in job.params_value.items():
        is_mass  = "_mass"  in pname or pname.endswith("mass")
        is_width = "_width" in pname or pname.endswith("width")
        if not (is_mass or is_width):
            continue

        perr = job.params_error.get(pname, 0.0)
        if perr == 0 or abs(perr) < 1e-10:
            continue
        n_floated += 1

        ref = pdg_lookup(pname)
        if ref is None:
            continue

        pdg_val, pdg_err = ref
        pull = (pval - pdg_val) / perr

        if abs(pull) < PULL_WARN:
            status = STATUS_OK
        elif abs(pull) < PULL_FAIL:
            status = STATUS_WARN
        else:
            status = STATUS_FAIL

        msg = (
            f"拟合={pval:.4f}±{perr:.4f} GeV，"
            f"PDG={pdg_val:.4f}±{pdg_err:.4f} GeV，"
            f"Pull={pull:.2f}"
        )
        results.append(_result(
            f"Pull [{pname}]", status,
            {"fit_value": pval, "fit_error": perr,
             "pdg_value": pdg_val, "pdg_error": pdg_err, "pull": pull},
            msg,
        ))

    if not results:
        if n_floated == 0:
            msg = "无浮动质量/宽度参数（全部固定）"
        else:
            msg = (f"找到 {n_floated} 个浮动参数，但均未匹配到 PDG 共振；"
                   "请检查参数命名是否包含 _mass/_width 并含共振名称")
        results.append(_result("参数Pull检验", STATUS_WARN, {"n_floated": n_floated}, msg))

    return results


# ═══════════════════════════════════════════════════════════════
# CHECK 5: Fit Fraction significance & physical sanity
# ═══════════════════════════════════════════════════════════════

def check_fit_fractions(job: JobData) -> list[dict]:
    """Check individual component fit fractions for significance and physical validity."""
    results   = []
    ch_labels = ["φπ⁺π⁻ (ch0)", "φK⁺K⁻ (ch1)"]

    for ch in range(2):
        ff, ff_err = job.fit_fracs(ch)
        if len(ff) == 0:
            continue
        states = job.states[ch] if ch < len(job.states) else []

        for i, (f, fe) in enumerate(zip(ff, ff_err)):
            label = states[i] if i < len(states) else f"comp{i}"
            sig   = float(f / fe) if fe > 0 else float("inf")

            if f < 0:
                status = STATUS_FAIL
                msg = f"FF={f:.4f} < 0，物理上不合理"
            elif f > 1.0:
                status = STATUS_WARN
                msg = f"FF={f:.4f} > 1，存在强干涉或参数异常，请仔细检查"
            elif fe == 0:
                status = STATUS_WARN
                msg = f"FF={f:.4f}，误差为 0（参数未浮动？）"
            elif sig < FF_SIG_CAUTION:
                status = STATUS_WARN
                msg = f"FF={f:.4f}±{fe:.4f}，显著性 {sig:.1f}σ < {FF_SIG_CAUTION}σ（建议检查是否需要保留）"
            elif sig < FF_SIG_WARN:
                status = STATUS_WARN
                msg = f"FF={f:.4f}±{fe:.4f}，显著性 {sig:.1f}σ（边界，介于 {FF_SIG_CAUTION}–{FF_SIG_WARN}σ）"
            else:
                status = STATUS_OK
                msg = f"FF={f:.4f}±{fe:.4f}，显著性 {sig:.1f}σ ✓"

            results.append(_result(
                f"FF [{ch_labels[ch]}] {label}",
                status,
                {"fit_frac": float(f), "fit_frac_err": float(fe),
                 "significance": sig, "channel": ch},
                msg,
            ))
    return results


# ═══════════════════════════════════════════════════════════════
# CHECK 6: Interference completeness (sum of full matrix ≈ 1)
# ═══════════════════════════════════════════════════════════════

def check_interference_completeness(job: JobData) -> list[dict]:
    """Verify ∑ FF_matrix ≈ 1 for each channel."""
    results   = []
    ch_labels = ["φπ⁺π⁻ (ch0)", "φK⁺K⁻ (ch1)"]

    for ch in range(len(job.frac)):
        total    = float(np.sum(job.frac[ch]))
        dev      = abs(total - 1.0)
        diag_sum = float(np.sum(np.diag(job.frac[ch])))

        if dev < INTERFERENCE_DEV_OK:
            status = STATUS_OK
            msg = f"∑FF_matrix={total:.4f} ≈ 1 ✓（对角线和={diag_sum:.4f}）"
        elif dev < INTERFERENCE_DEV_WARN:
            status = STATUS_WARN
            msg = f"∑FF_matrix={total:.4f}，偏差 {dev:.4f}（可能有数值误差）"
        else:
            status = STATUS_FAIL
            msg = f"∑FF_matrix={total:.4f}，严重偏离 1！（对角线和={diag_sum:.4f}）"

        results.append(_result(
            f"干涉完备性 [{ch_labels[ch]}]",
            status,
            {"matrix_sum": total, "diagonal_sum": diag_sum, "deviation_from_1": dev},
            msg,
        ))
    return results


# ═══════════════════════════════════════════════════════════════
# CHECK 7: Parameter correlation (from error matrix)
# ═══════════════════════════════════════════════════════════════

def check_parameter_correlations(job: JobData) -> dict:
    """Find highly correlated parameter pairs from error matrix."""
    M = job.error_matrix
    if M is None:
        return _result("参数相关性", STATUS_WARN, None, "无误差矩阵")

    diag = np.sqrt(np.maximum(np.diag(M), 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = M / np.outer(diag, diag)

    n           = corr.shape[0]
    param_names = job.param_names
    high_pairs  = []

    for i in range(n):
        for j in range(i + 1, n):
            c = abs(float(corr[i, j]))
            if not np.isfinite(c):
                continue
            if c > CORR_WARN:
                name_i = param_names[i] if i < len(param_names) else str(i)
                name_j = param_names[j] if j < len(param_names) else str(j)
                high_pairs.append((name_i, name_j, float(corr[i, j])))

    high_pairs.sort(key=lambda x: -abs(x[2]))
    max_corr = max((abs(p[2]) for p in high_pairs), default=0.0)

    if len(high_pairs) == 0:
        status = STATUS_OK
        msg = f"无高相关参数对（|ρ| < {CORR_WARN}）✓"
    elif max_corr > CORR_FAIL:
        status = STATUS_FAIL
        msg = f"发现 {len(high_pairs)} 对 |ρ| > {CORR_WARN}，最大 |ρ|={max_corr:.3f}，参数可能简并"
    else:
        status = STATUS_WARN
        msg = f"发现 {len(high_pairs)} 对 |ρ| > {CORR_WARN}，注意参数简并"

    return _result(
        "参数相关性", status,
        {"n_high_corr_pairs": len(high_pairs),
         "top_pairs": high_pairs[:10],
         "max_corr": max_corr},
        msg,
    )


# ═══════════════════════════════════════════════════════════════
# CHECK 8: Cross-channel resonance consistency (coupled-channel)
# ═══════════════════════════════════════════════════════════════

def check_cross_channel_consistency(job: JobData) -> list[dict]:
    """Coupled-channel constraints:

    1. Report shared vs channel-specific resonances from state lists.
    2. Warn on accidentally-split parameters (parameters with channel
       identifiers in their names for mass/width, which would break the
       coupled-channel constraint).
    3. Compare fit fractions of shared resonances across channels and flag
       physically unreasonable combinations.
    """
    results = []

    if len(job.states) < 2:
        return [_result("跨通道一致性", STATUS_WARN, None,
                        "态标签不完整（需 ch0 + ch1），跳过跨通道检查")]

    def _norm(s: str) -> str:
        import re as _re
        return _re.sub(r"[^a-z0-9]", "", s.lower())

    states_ch0, states_ch1 = job.states[0], job.states[1]
    norm_map_ch0 = {_norm(s): s for s in states_ch0}
    norm_map_ch1 = {_norm(s): s for s in states_ch1}
    shared_norm  = set(norm_map_ch0) & set(norm_map_ch1)

    n_ch0, n_ch1 = len(states_ch0), len(states_ch1)
    n_shared = len(shared_norm)

    results.append(_result(
        "耦合道共振统计",
        STATUS_OK,
        {"ch0_total": n_ch0, "ch1_total": n_ch1, "shared": n_shared,
         "ch0_only": n_ch0 - n_shared, "ch1_only": n_ch1 - n_shared},
        (f"ch0={n_ch0} 个, ch1={n_ch1} 个, 共享={n_shared} 个"
         f"（仅ch0={n_ch0 - n_shared}, 仅ch1={n_ch1 - n_shared}）"),
    ))

    # Detect accidentally-split mass/width parameters
    channel_keywords = {"ch0", "ch1", "channel0", "channel1", "phipipi", "phikk"}
    split_found = False
    for pname in job.params_value:
        plow = pname.lower()
        if any(k in plow for k in channel_keywords) and ("mass" in plow or "width" in plow):
            split_found = True
            results.append(_result(
                f"通道分离参数警告 [{pname}]",
                STATUS_WARN,
                {"param": pname},
                "参数名含通道标识，可能破坏耦合道约束，请确认是否符合物理预期",
            ))
    if not split_found:
        results.append(_result(
            "耦合道参数约束",
            STATUS_OK,
            None,
            "未发现通道分离的质量/宽度参数，耦合道约束完整 ✓",
        ))

    # Compare FF of shared resonances across channels
    if len(job.frac) >= 2 and shared_norm:
        ff0, ff0_err = job.fit_fracs(0)
        ff1, ff1_err = job.fit_fracs(1)

        for norm_name in sorted(shared_norm):
            orig_name = norm_map_ch0[norm_name]
            idx0 = next((i for i, s in enumerate(states_ch0) if _norm(s) == norm_name), None)
            idx1 = next((i for i, s in enumerate(states_ch1) if _norm(s) == norm_name), None)

            if idx0 is None or idx1 is None:
                continue
            if idx0 >= len(ff0) or idx1 >= len(ff1):
                continue

            f0_val, f0_e = float(ff0[idx0]), float(ff0_err[idx0])
            f1_val, f1_e = float(ff1[idx1]), float(ff1_err[idx1])
            total = f0_val + f1_val

            if f0_val < 0 or f1_val < 0:
                status = STATUS_FAIL
                msg = f"共享共振 FF 出现负值：ch0={f0_val:.4f}, ch1={f1_val:.4f}"
            elif total > FF_CROSS_TOTAL_WARN:
                status = STATUS_WARN
                msg = (f"总 FF 异常偏大：ch0={f0_val:.4f}+ch1={f1_val:.4f}={total:.4f}"
                       f" > {FF_CROSS_TOTAL_WARN}")
            else:
                status = STATUS_OK
                msg = (f"FF ch0={f0_val:.4f}±{f0_e:.4f}, ch1={f1_val:.4f}±{f1_e:.4f}, "
                       f"合计={total:.4f}")

            results.append(_result(
                f"共享共振FF [{orig_name}]",
                status,
                {"ff_ch0": f0_val, "ff_ch0_err": f0_e,
                 "ff_ch1": f1_val, "ff_ch1_err": f1_e, "total": total},
                msg,
            ))

    return results


# ═══════════════════════════════════════════════════════════════
# Convenience: run all single-job checks
# ═══════════════════════════════════════════════════════════════

def run_all_checks(job: JobData) -> dict:
    """Run all single-job checks and return structured result dict."""
    return {
        "nll_stability":             check_nll_stability(job),
        "error_matrix":              check_error_matrix(job),
        "parameter_pulls":           check_parameter_pulls(job),
        "fit_fractions":             check_fit_fractions(job),
        "interference_completeness": check_interference_completeness(job),
        "parameter_correlations":    check_parameter_correlations(job),
        "cross_channel_consistency": check_cross_channel_consistency(job),
    }
