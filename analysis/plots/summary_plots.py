"""Matplotlib-based summary plots for the amplitude analysis job comparison."""

from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from ..core.job import JobData
from ..core.checks import check_nll_stability

# ── CJK font setup ─────────────────────────────────────────────────────────────
def _setup_cjk_font() -> None:
    """Select the first available CJK-capable font and set it as the default."""
    import matplotlib.font_manager as fm
    # Priority order:
    # 1. Arial Unicode MS  – covers CJK + superscripts (⁺⁻) + symbols (✓✗⚠) on macOS
    # 2. Noto Sans CJK SC  – full CJK; fallback to DejaVu Sans for missing symbols
    # 3. Others for Windows / Linux
    candidates = [
        "Arial Unicode MS",   # macOS – covers everything we need
        "Noto Sans CJK SC",   # Linux / macOS (via noto-fonts)
        "PingFang SC",        # macOS
        "Heiti SC",           # macOS legacy
        "STHeiti",            # macOS legacy
        "Hiragino Sans GB",   # macOS
        "Microsoft YaHei",    # Windows
        "SimHei",             # Windows fallback
        "WenQuanYi Micro Hei",# Linux fallback
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"]        = "sans-serif"
            plt.rcParams["font.sans-serif"]    = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return
    import warnings
    warnings.filterwarnings("ignore", message="Glyph .* missing from font")

_setup_cjk_font()

# ── colour scheme ──────────────────────────────────────────────────────────────
C_OK   = "#2ecc71"
C_WARN = "#f39c12"
C_FAIL = "#e74c3c"
C_BEST = "#2980b9"
C_GREY = "#95a5a6"

STATUS_COLOR = {"ok": C_OK, "warn": C_WARN, "fail": C_FAIL}


def _save(fig, out_path: Path, name: str) -> Path:
    out_path.mkdir(parents=True, exist_ok=True)
    fpath = out_path / name
    fig.savefig(fpath, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return fpath


# ══════════════════════════════════════════════════════════════
# Plot 1: NLL comparison bar chart
# ══════════════════════════════════════════════════════════════

def plot_nll_comparison(jobs: list[JobData], out_path: Path) -> Path:
    valid_jobs = [j for j in jobs if np.isfinite(j.status.nll)]
    if not valid_jobs:
        return None

    nlls  = np.array([j.status.nll for j in valid_jobs])
    best  = np.min(nlls)
    delta = nlls - best

    names  = [j.name.replace("job_phihh_", "").replace("2026060", "..") for j in valid_jobs]
    colors = [C_BEST if d == 0 else C_GREY for d in delta]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

    ax = axes[0]
    bars = ax.barh(names, nlls, color=colors, edgecolor="white", height=0.5)
    ax.set_xlabel("NLL", fontsize=12)
    ax.set_title("Absolute NLL per job", fontweight="bold")
    for bar, v in zip(bars, nlls):
        ax.text(v + 5, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}", va="center", fontsize=9)
    ax.invert_xaxis()

    ax2 = axes[1]
    two_delta = 2 * delta
    colors2 = [C_BEST if d == 0 else (C_FAIL if d > 50 else C_WARN) for d in two_delta]
    bars2 = ax2.barh(names, two_delta, color=colors2, edgecolor="white", height=0.5)
    for thresh, lbl, ls in [(3.84, "2σ", "-."), (9, "3σ", "--"), (25, "5σ", ":")]:
        ax2.axvline(thresh, color="grey", ls=ls, lw=1, alpha=0.6)
        ax2.text(thresh, -0.5, lbl, fontsize=8, color="grey", ha="center")
    ax2.set_xlabel("2ΔNLL", fontsize=12)
    ax2.set_title("2ΔNLL vs. best fit", fontweight="bold")
    for bar, v in zip(bars2, two_delta):
        ax2.text(v + 2, bar.get_y() + bar.get_height() / 2,
                 f"{v:.1f}", va="center", fontsize=9)

    fig.tight_layout()
    return _save(fig, out_path, "nll_comparison.png")


# ══════════════════════════════════════════════════════════════
# Plot 2: Per-loop NLL distribution (fit stability)
# ══════════════════════════════════════════════════════════════

def plot_nll_stability(jobs: list[JobData], out_path: Path) -> Path:
    n = len(jobs)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4), sharey=False)
    if n == 1:
        axes = [axes]

    for ax, job in zip(axes, jobs):
        nlls = np.array(job.loop_nlls)
        if len(nlls) == 0:
            ax.text(0.5, 0.5, "No loop data", ha="center", va="center",
                    transform=ax.transAxes, color="grey")
            ax.set_title(job.name[-12:])
            continue

        best = np.min(nlls)
        ax.plot(range(1, len(nlls) + 1), nlls, "o-", color=C_BEST, ms=6)
        ax.axhline(best, color=C_OK, ls="--", lw=1.2, label=f"best={best:.1f}")
        ax.fill_between(range(1, len(nlls) + 1),
                        [best] * len(nlls), nlls,
                        alpha=0.15, color=C_FAIL)
        ax.set_xlabel("Loop #", fontsize=10)
        ax.set_ylabel("NLL", fontsize=10)
        ax.set_title(job.name[-12:], fontsize=9, fontweight="bold")
        ax.legend(fontsize=8)
        ax.set_xticks(range(1, len(nlls) + 1))

    fig.suptitle("Per-loop NLL (fit stability)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    return _save(fig, out_path, "nll_stability.png")


# ══════════════════════════════════════════════════════════════
# Plot 3: Fit fractions (best job, both channels)
# ══════════════════════════════════════════════════════════════

def plot_fit_fractions(job: JobData, out_path: Path) -> Path:
    ch_info = [
        ("J/ψ→φπ⁺π⁻", 0),
        ("J/ψ→φK⁺K⁻", 1),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    for ax, (title, ch) in zip(axes, ch_info):
        ff, ff_err = job.fit_fracs(ch)
        if len(ff) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(title)
            continue

        states = job.states[ch] if ch < len(job.states) else [f"comp{i}" for i in range(len(ff))]
        labels = states[:len(ff)]
        x      = np.arange(len(ff))

        colors = []
        for f, fe in zip(ff, ff_err):
            if f < 0:
                colors.append(C_FAIL)
            elif fe > 0 and f / fe < 2:
                colors.append(C_WARN)
            else:
                colors.append(C_BEST)

        ax.bar(x, ff, yerr=ff_err, color=colors, edgecolor="white",
               capsize=3, error_kw={"elinewidth": 1.2})
        ax.axhline(0, color="black", lw=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Fit Fraction", fontsize=11)
        ax.set_title(f"{title}\n∑FF(diag)={np.sum(ff):.3f}", fontweight="bold")

        for xi, (f, fe) in enumerate(zip(ff, ff_err)):
            sig   = f / fe if fe > 0 else 0
            color = C_OK if sig >= 3 else C_WARN
            ax.text(xi, max(f + fe, 0) + 0.02, f"{sig:.1f}σ",
                    ha="center", va="bottom", fontsize=6.5, color=color)

    fig.tight_layout()
    return _save(fig, out_path, f"fit_fractions_{job.name[-12:]}.png")


# ══════════════════════════════════════════════════════════════
# Plot 4: Fit fraction comparison across jobs (diagonal FF)
# ══════════════════════════════════════════════════════════════

def plot_ff_comparison(jobs: list[JobData], out_path: Path, channel: int = 0) -> Path:
    ch_title = ["J/ψ→φπ⁺π⁻", "J/ψ→φK⁺K⁻"][channel]
    nlls = [j.status.nll for j in jobs]
    best_job = jobs[int(np.nanargmin(nlls))]
    ref_states = best_job.states[channel] if channel < len(best_job.states) else []

    if channel >= len(best_job.frac):
        return None
    n_comp = len(np.diag(best_job.frac[channel]))
    if n_comp == 0:
        return None

    fig, ax = plt.subplots(figsize=(max(12, n_comp * 1.2), 5))
    width = 0.8 / len(jobs)
    x     = np.arange(n_comp)

    best_nll = min(j.status.nll for j in jobs if np.isfinite(j.status.nll))
    for k, job in enumerate(jobs):
        ff, ff_err = job.fit_fracs(channel)
        n      = min(len(ff), n_comp)
        offset = (k - len(jobs) / 2 + 0.5) * width
        alpha  = 1.0 if job.status.nll == best_nll else 0.55
        label  = job.name[-12:] + (" ★best" if job.status.nll == best_nll else "")
        ax.bar(x[:n] + offset, ff[:n], width * 0.9,
               yerr=ff_err[:n], capsize=2,
               label=label, alpha=alpha, error_kw={"elinewidth": 1})

    ax.set_xticks(x)
    ax.set_xticklabels(ref_states[:n_comp], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Fit Fraction", fontsize=11)
    ax.set_title(f"Fit Fraction 跨作业对比：{ch_title}", fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.axhline(0, color="black", lw=0.5)
    fig.tight_layout()
    return _save(fig, out_path, f"ff_comparison_ch{channel}.png")


# ══════════════════════════════════════════════════════════════
# Plot 5: Error matrix heatmap with parameter names
# ══════════════════════════════════════════════════════════════

def plot_error_matrix(job: JobData, out_path: Path) -> Path:
    M = job.error_matrix
    if M is None:
        return None

    diag = np.sqrt(np.maximum(np.diag(M), 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = M / np.outer(diag + 1e-30, diag + 1e-30)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1, 1)

    n           = corr.shape[0]
    param_names = job.param_names

    # Scale figure to number of parameters
    side = max(8, n * 0.35)
    fig, ax = plt.subplots(figsize=(side, side * 0.85))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r", aspect="auto")
    plt.colorbar(im, ax=ax, label="Correlation ρ", fraction=0.046, pad=0.04)
    ax.set_title(f"参数相关矩阵\n{job.name}", fontweight="bold")

    if param_names and len(param_names) == n:
        # Shorten long names to fit on axis
        short = [p[-24:] if len(p) > 24 else p for p in param_names]
        tick_fs = max(4, min(8, 120 // n))
        ax.set_xticks(range(n))
        ax.set_xticklabels(short, rotation=90, fontsize=tick_fs)
        ax.set_yticks(range(n))
        ax.set_yticklabels(short, fontsize=tick_fs)
    else:
        ax.set_xlabel("Parameter index")
        ax.set_ylabel("Parameter index")

    fig.tight_layout()
    return _save(fig, out_path, f"corr_matrix_{job.name[-12:]}.png")


# ══════════════════════════════════════════════════════════════
# Plot 6: Cross-channel FF comparison for shared resonances
# ══════════════════════════════════════════════════════════════

def plot_cross_channel_ff(job: JobData, out_path: Path) -> Path | None:
    """Side-by-side bar chart of FF for resonances shared between ch0 and ch1."""
    import re as _re

    if len(job.states) < 2 or len(job.frac) < 2:
        return None

    def _norm(s: str) -> str:
        return _re.sub(r"[^a-z0-9]", "", s.lower())

    states0 = job.states[0]
    states1 = job.states[1]
    norm0   = {_norm(s): (i, s) for i, s in enumerate(states0)}
    norm1   = {_norm(s): (i, s) for i, s in enumerate(states1)}
    shared  = sorted(set(norm0) & set(norm1))

    if not shared:
        return None

    ff0, ff0_err = job.fit_fracs(0)
    ff1, ff1_err = job.fit_fracs(1)

    labels, vals0, errs0, vals1, errs1 = [], [], [], [], []
    for norm_name in shared:
        i0, orig = norm0[norm_name]
        i1, _    = norm1[norm_name]
        if i0 >= len(ff0) or i1 >= len(ff1):
            continue
        labels.append(orig)
        vals0.append(float(ff0[i0]));  errs0.append(float(ff0_err[i0]))
        vals1.append(float(ff1[i1]));  errs1.append(float(ff1_err[i1]))

    if not labels:
        return None

    x    = np.arange(len(labels))
    w    = 0.35
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.1), 5))

    ax.bar(x - w / 2, vals0, w, yerr=errs0, label="φπ⁺π⁻ (ch0)",
           color=C_BEST, alpha=0.85, capsize=3, error_kw={"elinewidth": 1.2})
    ax.bar(x + w / 2, vals1, w, yerr=errs1, label="φK⁺K⁻ (ch1)",
           color=C_OK,   alpha=0.85, capsize=3, error_kw={"elinewidth": 1.2})

    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Fit Fraction", fontsize=11)
    ax.set_title(f"共享共振跨通道 FF 对比\n{job.name}", fontweight="bold")
    ax.legend(fontsize=10)
    fig.tight_layout()
    return _save(fig, out_path, f"cross_channel_ff_{job.name[-12:]}.png")


# ══════════════════════════════════════════════════════════════
# Plot 7: Checklist traffic-light summary
# ══════════════════════════════════════════════════════════════

def plot_checklist_summary(all_check_results: dict, job: JobData, out_path: Path) -> Path:
    """Render a traffic-light grid of all check results."""
    rows = []
    for key, val in all_check_results.items():
        if isinstance(val, list):
            rows.extend(val)
        else:
            rows.append(val)

    n      = len(rows)
    fig_h  = max(6, n * 0.42)
    fig, ax = plt.subplots(figsize=(12, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.8, n)
    ax.axis("off")
    ax.set_facecolor("#f8f9fa")
    fig.patch.set_facecolor("#f8f9fa")

    ax.text(5, n + 0.2, f"评估总清单：{job.name}",
            ha="center", va="bottom", fontsize=13, fontweight="bold", color="#2c3e50")

    for i, row in enumerate(reversed(rows)):
        y      = i + 0.1
        status = row.get("status", "warn")
        color  = STATUS_COLOR.get(status, C_GREY)
        icon   = {"ok": "✓", "warn": "!", "fail": "✗"}.get(status, "?")

        rect = FancyBboxPatch((0.05, y), 0.7, 0.75,
                              boxstyle="round,pad=0.05",
                              facecolor=color, alpha=0.85)
        ax.add_patch(rect)
        ax.text(0.4, y + 0.38, icon, ha="center", va="center",
                fontsize=12, color="white", fontweight="bold")
        ax.text(0.9, y + 0.38, row.get("name", ""), va="center",
                fontsize=8.5, fontweight="bold", color="#2c3e50")
        msg = row.get("message", "")
        if len(msg) > 90:
            msg = msg[:87] + "…"
        ax.text(4.0, y + 0.38, msg, va="center", fontsize=7.5, color="#555555")
        ax.axhline(i + 0.92, color="#dee2e6", lw=0.5)

    for xi, (lbl, clr) in enumerate([("OK", C_OK), ("WARN", C_WARN), ("FAIL", C_FAIL)]):
        rect = FancyBboxPatch((0.1 + xi * 1.5, -0.7), 1.2, 0.45,
                              boxstyle="round,pad=0.05", facecolor=clr, alpha=0.8)
        ax.add_patch(rect)
        ax.text(0.7 + xi * 1.5, -0.47, lbl, ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")

    fig.tight_layout()
    return _save(fig, out_path, f"checklist_{job.name[-12:]}.png")


# ══════════════════════════════════════════════════════════════
# Plot 8: AIC / 2ΔNLL model comparison
# ══════════════════════════════════════════════════════════════

def plot_aic_comparison(aic_results: list[dict], out_path: Path) -> Path | None:
    """Side-by-side bar chart of ΔAIC and 2ΔNLL for all jobs."""
    if not aic_results:
        return None

    names    = [r["name"].replace("job_phihh_", "").replace("2026060", "..") for r in aic_results]
    delta_aic   = [r["delta_aic"]     for r in aic_results]
    two_dnll    = [r["two_delta_nll"] for r in aic_results]
    aic_weights = [r["aic_weight"]    for r in aic_results]
    n_free      = [r["n_free"]        for r in aic_results]

    fig, axes = plt.subplots(1, 3, figsize=(17, max(4, len(names) * 0.5 + 2)))

    # ── Panel 1: ΔAIC ─────────────────────────────────────────────
    ax = axes[0]
    colors = [C_OK if d < 2 else (C_WARN if d < 7 else C_FAIL) for d in delta_aic]
    bars = ax.barh(names, delta_aic, color=colors, edgecolor="white", height=0.55)
    for thresh, lbl, ls in [(2, "Δ2", "--"), (7, "Δ7", ":")]:
        ax.axvline(thresh, color="grey", ls=ls, lw=1, alpha=0.7)
        ax.text(thresh, -0.6, lbl, fontsize=8, color="grey", ha="center")
    ax.set_xlabel("ΔAIC", fontsize=11)
    ax.set_title("ΔAIC  (penalty: 2k)", fontweight="bold")
    for bar, v in zip(bars, delta_aic):
        ax.text(v + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}", va="center", fontsize=8)

    # ── Panel 2: 2ΔNLL ────────────────────────────────────────────
    ax2 = axes[1]
    colors2 = [C_OK if d < 9 else (C_WARN if d < 25 else C_FAIL) for d in two_dnll]
    bars2 = ax2.barh(names, two_dnll, color=colors2, edgecolor="white", height=0.55)
    for thresh, lbl, ls in [(3.84, "2σ", "-."), (9, "3σ", "--"), (25, "5σ", ":")]:
        ax2.axvline(thresh, color="grey", ls=ls, lw=1, alpha=0.7)
        ax2.text(thresh, -0.6, lbl, fontsize=8, color="grey", ha="center")
    ax2.set_xlabel("2ΔNLL", fontsize=11)
    ax2.set_title("2ΔNLL  (significance)", fontweight="bold")
    for bar, v in zip(bars2, two_dnll):
        ax2.text(v + 0.5, bar.get_y() + bar.get_height() / 2,
                 f"{v:.1f}", va="center", fontsize=8)

    # ── Panel 3: Akaike weights ────────────────────────────────────
    ax3 = axes[2]
    bars3 = ax3.barh(names, aic_weights, color=C_BEST, alpha=0.75,
                     edgecolor="white", height=0.55)
    ax3.set_xlabel("Akaike weight  w_i", fontsize=11)
    ax3.set_title("Akaike weight\n(relative model prob.)", fontweight="bold")
    for bar, w, k in zip(bars3, aic_weights, n_free):
        ax3.text(w + 0.005, bar.get_y() + bar.get_height() / 2,
                 f"{w:.3f}  (k={k})", va="center", fontsize=8)

    fig.suptitle("Model Selection: AIC vs 2ΔNLL", fontsize=13, fontweight="bold")
    fig.tight_layout()
    return _save(fig, out_path, "model_selection_aic.png")


# ══════════════════════════════════════════════════════════════
# Plot 9: Optimisation suggestions priority chart
# ══════════════════════════════════════════════════════════════

def plot_suggestions(suggestions: list[dict], job: JobData, out_path: Path) -> Path | None:
    """Traffic-light list of optimisation suggestions with priority badges."""
    if not suggestions:
        return None

    PRIORITY_COLOR = {"P0": C_FAIL, "P1": C_WARN, "P2": C_BEST}
    CAT_ICON = {
        "收敛性":   "⟳",
        "参数简并": "≈",
        "LS 参数化":"L",
        "模型精简": "−",
        "PDG 约束": "P",
        "耦合道物理":"⊕",
        "模型选择": "A",
    }

    n      = len(suggestions)
    fig_h  = max(5, n * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, n)
    ax.axis("off")
    ax.set_facecolor("#f8f9fa")
    fig.patch.set_facecolor("#f8f9fa")

    ax.text(5, n + 0.1, f"拟合优化建议：{job.name}",
            ha="center", va="bottom", fontsize=13, fontweight="bold", color="#2c3e50")

    for i, s in enumerate(reversed(suggestions)):
        y      = i + 0.05
        pri    = s.get("priority", "P2")
        cat    = s.get("category", "")
        color  = PRIORITY_COLOR.get(pri, C_GREY)
        icon   = CAT_ICON.get(cat, "•")

        # Priority badge
        rect = FancyBboxPatch((0.05, y), 0.55, 0.80,
                              boxstyle="round,pad=0.05", facecolor=color, alpha=0.9)
        ax.add_patch(rect)
        ax.text(0.325, y + 0.40, pri, ha="center", va="center",
                fontsize=9, color="white", fontweight="bold")

        # Category badge
        rect2 = FancyBboxPatch((0.65, y), 0.55, 0.80,
                               boxstyle="round,pad=0.05", facecolor="#7f8c8d", alpha=0.7)
        ax.add_patch(rect2)
        ax.text(0.925, y + 0.40, icon, ha="center", va="center",
                fontsize=10, color="white", fontweight="bold")

        # Category label + action
        ax.text(1.28, y + 0.57, cat, va="center",
                fontsize=7.5, color="#7f8c8d", style="italic")
        action = s.get("action", "")
        if len(action) > 95:
            action = action[:92] + "…"
        ax.text(1.28, y + 0.25, action, va="center",
                fontsize=8.5, fontweight="bold", color="#2c3e50")

        ax.axhline(i + 0.90, color="#dee2e6", lw=0.5)

    # Legend
    for xi, (lbl, clr) in enumerate([("P0 关键", C_FAIL), ("P1 重要", C_WARN), ("P2 可选", C_BEST)]):
        rect = FancyBboxPatch((0.1 + xi * 2.0, -0.45), 1.5, 0.38,
                              boxstyle="round,pad=0.05", facecolor=clr, alpha=0.8)
        ax.add_patch(rect)
        ax.text(0.85 + xi * 2.0, -0.26, lbl, ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")

    fig.tight_layout()
    return _save(fig, out_path, f"suggestions_{job.name[-12:]}.png")
