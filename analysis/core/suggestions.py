"""Automated fit-optimization suggestion generator.

After all evaluation checks have been run, this module analyses the results
and produces a prioritised, actionable list of suggestions for the next
round of fits.  Each suggestion carries:

  priority  : 'P0' (critical) | 'P1' (important) | 'P2' (optional)
  category  : thematic grouping (convergence / degeneracy / model / physics / stats)
  action    : one-line description of what to do
  reason    : why this matters physically or statistically
  formula   : optional quantitative reference (LaTeX-style plain text)
  evidence  : key numbers extracted from the check results

Suggestions are deterministic given the check results, so re-running the
script always produces the same list for the same fit output.
"""

from __future__ import annotations
import math
import re
from .job import JobData
from .checks import STATUS_FAIL, STATUS_WARN


# ── helpers ────────────────────────────────────────────────────────────────────

def _flat_checks(check_results: dict) -> list[dict]:
    items = []
    for v in check_results.values():
        if isinstance(v, list):
            items.extend(v)
        else:
            items.append(v)
    return items


def _count_ls_per_resonance(job: JobData) -> dict[str, int]:
    """Return {resonance_key: n_ls_groups} by parsing parameter names.

    LS coupling parameters are named like:
      Jpsi->phi.f2(1270)_flatte_g_ls_1r  →  group 1 real
      Jpsi->phi.f2(1270)_flatte_g_ls_1i  →  group 1 imag
    We count unique (resonance_key, group_index) pairs.
    """
    pattern = re.compile(r"^(.+?)_g_ls_(\d+)[ri]$")
    seen: dict[str, set] = {}
    for pname in job.params_value:
        m = pattern.match(pname)
        if m:
            key, idx = m.group(1), int(m.group(2))
            seen.setdefault(key, set()).add(idx)
    return {k: len(v) for k, v in seen.items()}


def _needed_loops(conv_fraction: float, target_prob: float = 0.95) -> int:
    """Minimum loop count to reach target probability of finding global min."""
    if conv_fraction <= 0:
        return 50
    if conv_fraction >= 1:
        return 1
    return max(1, math.ceil(math.log(1 - target_prob) / math.log(1 - conv_fraction)))


# ── individual suggestion factories ────────────────────────────────────────────

def _s_convergence(job: JobData, cr: dict) -> list[dict]:
    sugg = []
    item = cr.get("nll_stability", {})
    if item.get("status") not in (STATUS_WARN, STATUS_FAIL):
        return sugg
    val = item.get("value") or {}
    spread = val.get("spread", 0)
    n_loops = val.get("n_loops", 0)
    conv_frac = val.get("conv_fraction", 0)
    needed = _needed_loops(conv_frac)

    sugg.append(dict(
        priority = "P0",
        category = "收敛性",
        action   = f"将 LOOP 次数从 {n_loops} 增加至 ≥ {needed} 次",
        reason   = (f"当前 NLL 散布 {spread:.1f}，{conv_frac:.0%} 的起点落在 best+1 范围内，"
                    f"找到全局最优的概率仅 {1-(1-conv_frac)**n_loops:.0%}"),
        formula  = f"P(全局最优) = 1-(1-{conv_frac:.2f})^N ≥ 95%  →  N ≥ {needed}",
        evidence = {"spread": spread, "conv_fraction": conv_frac,
                    "current_loops": n_loops, "needed_loops": needed},
    ))
    return sugg


def _s_error_matrix(job: JobData, cr: dict) -> list[dict]:
    sugg = []
    em = cr.get("error_matrix", {})
    if em.get("status") != STATUS_FAIL:
        return sugg
    val = em.get("value") or {}
    n_neg  = val.get("n_neg_eigenvalues", 0)
    cond   = val.get("condition_number", 0)

    # Identify culprit from correlations
    pc = cr.get("parameter_correlations", {})
    top_pairs = (pc.get("value") or {}).get("top_pairs", [])
    max_corr  = (pc.get("value") or {}).get("max_corr", 0)

    sugg.append(dict(
        priority = "P0",
        category = "参数简并",
        action   = "诊断并消除导致 Hessian 奇异的参数简并",
        reason   = (f"误差矩阵有 {n_neg} 个负特征值（条件数 {cond:.2e}），"
                    f"最大 |ρ|={max_corr:.3f}（物理上不可能 >1），"
                    "说明拟合停留在鞍点，参数误差估计完全无效"),
        formula  = "H = ∂²(-ln L)/∂θᵢ∂θⱼ 应正定；|ρᵢⱼ| = |Hᵢⱼ|/√(HᵢᵢHⱼⱼ) ≤ 1",
        evidence = {"n_neg_eigenvalues": n_neg, "condition_number": cond,
                    "max_correlation": max_corr},
    ))

    # Pinpoint the primary culprit parameter
    if top_pairs:
        culprit = top_pairs[0][0]
        sugg.append(dict(
            priority = "P0",
            category = "参数简并",
            action   = f"优先检查并固定/移除参数 `{culprit}`",
            reason   = (f"该参数与 {len(top_pairs)} 个参数的 |ρ| > 0.9，"
                        f"最大相关系数 {abs(top_pairs[0][2]):.3f}，是简并的主要来源"),
            formula  = "固定简并参数 → 降低参数空间维度 → Hessian 条件数改善",
            evidence = {"culprit": culprit, "n_high_corr": len(top_pairs),
                        "top_pair": top_pairs[0]},
        ))
    return sugg


def _s_ls_overcounting(job: JobData, cr: dict) -> list[dict]:
    """Detect LS coupling over-parameterization."""
    sugg = []
    ls_counts = _count_ls_per_resonance(job)
    # Flag resonances with > 3 LS groups (conservative threshold for J/psi→phi+R)
    overfit = sorted(
        [(k, n) for k, n in ls_counts.items() if n > 3],
        key=lambda x: -x[1]
    )
    if not overfit:
        return sugg

    # Also check if any of these are in the high-correlation top pairs
    pc = cr.get("parameter_correlations", {})
    top_pairs = (pc.get("value") or {}).get("top_pairs", [])
    culprit_params = {p for triple in top_pairs[:20] for p in triple[:2]}

    for res_key, n_ls in overfit[:5]:
        in_culprit = any(res_key in cp for cp in culprit_params)
        priority = "P0" if in_culprit else "P1"
        sugg.append(dict(
            priority = priority,
            category = "LS 参数化",
            action   = f"精简 `{res_key}` 的 LS 耦合（当前 {n_ls} 组，建议只保留 ≤ 2 组）",
            reason   = (f"J/ψ(J=1)→φ(J=1)+R 的允许 LS 组合受角动量守恒和宇称守恒约束，"
                        f"超出限制的 LS 参数引入额外自由度并导致参数简并"),
            formula  = ("允许 L: (-1)^L = P_ψ·P_φ·P_R，|L-S| ≤ J_ψ=1 ≤ L+S，"
                        "S = |J_φ-J_R|…J_φ+J_R"),
            evidence = {"resonance": res_key, "current_ls_groups": n_ls,
                        "is_primary_culprit": in_culprit},
        ))
    return sugg


def _s_low_significance(job: JobData, cr: dict) -> list[dict]:
    sugg = []
    for item in cr.get("fit_fractions", []):
        if item.get("status") not in (STATUS_WARN,):
            continue
        val = item.get("value") or {}
        sig = val.get("significance", 99)
        ff  = val.get("fit_frac", 0)
        ch  = val.get("channel", 0)
        ch_label = ["φπ⁺π⁻ (ch0)", "φK⁺K⁻ (ch1)"][ch]
        name_full = item.get("name", "")
        # Extract component name from "FF [ch_label] comp_name"
        comp = name_full.replace(f"FF [{ch_label}] ", "").strip()

        if sig < 2.0:
            priority = "P1"
            action   = f"对 {ch_label} 中的 {comp} 执行显著性 scan（去掉后看 2ΔNLL）"
            reason   = f"FF = {ff:.4f}，显著性仅 {sig:.1f}σ < 2σ；保留该成分可能只是拟合随机起伏"
        elif sig < 3.0:
            priority = "P2"
            action   = f"评估 {ch_label} 中的 {comp} 是否有独立物理动机"
            reason   = f"FF = {ff:.4f}，显著性 {sig:.1f}σ 处于 2–3σ 边界，需结合理论预期判断"
        else:
            continue

        sugg.append(dict(
            priority = priority,
            category = "模型精简",
            action   = action,
            reason   = reason,
            formula  = ("2ΔNLL_remove = 2×(NLL_without - NLL_best) ~ χ²(Δk)"
                        f"  where Δk = 移除 {comp} 的参数数目"),
            evidence = {"component": comp, "channel": ch, "ff": ff, "significance": sig},
        ))
    return sugg


def _s_pdg_constraints(job: JobData, cr: dict) -> list[dict]:
    """Suggest PDG Gaussian penalties for floating width/mass parameters
    that are both physically constrained and highly correlated."""
    sugg = []
    pc = cr.get("parameter_correlations", {})
    top_pairs = (pc.get("value") or {}).get("top_pairs", [])
    if not top_pairs:
        return sugg

    # Find width/mass parameters appearing in high-correlation pairs
    from .pdg import pdg_lookup
    seen = set()
    for a, b, rho in top_pairs:
        for pname in (a, b):
            is_phys = "_width" in pname or pname.endswith("width") or \
                      "_mass"  in pname or pname.endswith("mass")
            if is_phys and pname not in seen:
                ref = pdg_lookup(pname)
                if ref is not None:
                    pdg_val, pdg_err = ref
                    seen.add(pname)
                    sugg.append(dict(
                        priority = "P1",
                        category = "PDG 约束",
                        action   = (f"对 `{pname}` 施加 PDG 高斯惩罚 "
                                    f"(中心值={pdg_val:.4f} GeV, σ={pdg_err:.4f} GeV)"),
                        reason   = (f"该参数在误差矩阵中与多个参数高度相关（|ρ|>{abs(rho):.2f}），"
                                    f"加入 PDG 约束可消除一个自由度并改善 Hessian 条件数"),
                        formula  = ("-ln L_total = -ln L_fit + "
                                    "(p - p_PDG)² / (2·σ_PDG²)"),
                        evidence = {"param": pname, "pdg_value": pdg_val,
                                    "pdg_error": pdg_err, "max_correlation": abs(rho)},
                    ))
                if len(seen) >= 3:
                    break
        if len(seen) >= 3:
            break
    return sugg


def _s_cross_channel(job: JobData, cr: dict) -> list[dict]:
    sugg = []
    cc_items = cr.get("cross_channel_consistency", [])
    if not isinstance(cc_items, list):
        cc_items = [cc_items]
    for item in cc_items:
        if item.get("status") == STATUS_FAIL:
            val = item.get("value") or {}
            sugg.append(dict(
                priority = "P0",
                category = "耦合道物理",
                action   = f"修复跨通道约束：{item.get('name','')}",
                reason   = item.get("message", ""),
                formula  = "耦合道分析要求共享共振使用同一质量/宽度参数",
                evidence = val,
            ))
        elif item.get("status") == STATUS_WARN:
            sugg.append(dict(
                priority = "P2",
                category = "耦合道物理",
                action   = f"确认 {item.get('name','')} 的物理合理性",
                reason   = item.get("message", ""),
                formula  = "共享共振 FF_ch0 + FF_ch1 应在 [0, 1.5] 范围内",
                evidence = item.get("value") or {},
            ))
    return sugg


def _s_model_selection(aic_results: list[dict]) -> list[dict]:
    """If AIC selects a different model than NLL, suggest investigating."""
    sugg = []
    if not aic_results:
        return sugg
    best_nll_entry = next((r for r in aic_results if r["is_best_nll"]), None)
    best_aic_entry = aic_results[0]  # sorted by AIC

    if best_nll_entry and not best_nll_entry["is_best_aic"]:
        delta_aic = best_nll_entry["delta_aic"]
        best_aic_name = best_aic_entry["name"]
        sugg.append(dict(
            priority = "P1",
            category = "模型选择",
            action   = (f"重点检查 AIC 最优作业 `{best_aic_name}`；"
                        f"当前 NLL 最优作业的 ΔAIC={delta_aic:.1f}，"
                        f"参数过多可能导致过拟合"),
            reason   = ("AIC 对参数数目施加线性惩罚 2k，当两个模型的 ΔAIC > 2 时，"
                        "更简洁的模型在同等数据下具有更高的信息论支持度"),
            formula  = ("AIC = 2k + 2·NLL；ΔAIC > 2 → 明显较弱的模型支持；"
                        "ΔAIC > 7 → 基本无模型支持"),
            evidence = {"nll_best": best_nll_entry["name"],
                        "aic_best": best_aic_name,
                        "delta_aic": delta_aic,
                        "aic_weight_nll_best": best_nll_entry["aic_weight"]},
        ))
    return sugg


# ── main entry point ───────────────────────────────────────────────────────────

def generate_suggestions(
    job: JobData,
    check_results: dict,
    aic_results: list[dict] | None = None,
) -> list[dict]:
    """Generate a prioritised list of optimisation suggestions.

    Parameters
    ----------
    job           : the job being evaluated
    check_results : output of run_all_checks(job)
    aic_results   : output of compare_aic(all_jobs), optional

    Returns
    -------
    List of suggestion dicts sorted by priority (P0 → P1 → P2).
    """
    suggestions: list[dict] = []

    suggestions += _s_convergence(job, check_results)
    suggestions += _s_error_matrix(job, check_results)
    suggestions += _s_ls_overcounting(job, check_results)
    suggestions += _s_low_significance(job, check_results)
    suggestions += _s_pdg_constraints(job, check_results)
    suggestions += _s_cross_channel(job, check_results)
    if aic_results:
        suggestions += _s_model_selection(aic_results)

    # Sort: P0 first, then P1, then P2; stable sort preserves generation order
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    suggestions.sort(key=lambda s: priority_order.get(s["priority"], 3))
    return suggestions
