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
from ..core.scan import ScanGroup

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


def _save(fig, out_path: Path, name: str, dpi: int = 150) -> Path:
    out_path.mkdir(parents=True, exist_ok=True)
    fpath = out_path / name
    fig.savefig(fpath, bbox_inches="tight", dpi=dpi)
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

def plot_nll_stability(jobs: list[JobData], out_path: Path) -> list[Path]:
    """Return one PNG per job showing the per-loop NLL trace.

    Returns a list of saved Paths (one per job with loop data).  An empty
    list is returned when no job has loop data.  Each file is named
    ``nll_stability_<safe_job_name>.png`` so the HTML slideshow can display
    them one at a time.
    """
    paths: list[Path] = []
    for job in jobs:
        nlls = np.array(job.loop_nlls)
        fig, ax = plt.subplots(figsize=(6, 4))

        if len(nlls) == 0:
            ax.text(0.5, 0.5, "No loop data", ha="center", va="center",
                    transform=ax.transAxes, color="grey", fontsize=12)
        else:
            best = float(np.min(nlls))
            x    = range(1, len(nlls) + 1)
            ax.plot(x, nlls, "o-", color=C_BEST, ms=6, zorder=3)
            ax.axhline(best, color=C_OK, ls="--", lw=1.4,
                       label=f"best = {best:.2f}")
            ax.fill_between(x, [best] * len(nlls), nlls,
                            alpha=0.18, color=C_FAIL, zorder=2)
            ax.set_xlabel("Loop #", fontsize=10)
            ax.set_ylabel("NLL", fontsize=10)
            ax.set_xticks(list(x))
            ax.legend(fontsize=9)

        ax.set_title(job.name[-28:], fontsize=9, fontweight="bold")
        fig.tight_layout()

        safe = job.name.replace("/", "_").replace(" ", "_")
        p = _save(fig, out_path, f"nll_stability_{safe}.png", dpi=180)
        paths.append(p)

    return paths


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
    return _save(fig, out_path, f"fit_fractions_{job.name[-12:]}.png", dpi=200)


# ══════════════════════════════════════════════════════════════
# Plot 4: Fit fraction comparison across jobs (diagonal FF)
# ══════════════════════════════════════════════════════════════

def plot_ff_comparison(jobs: list[JobData], out_path: Path, channel: int = 0) -> Path:
    ch_title = ["J/ψ→φπ⁺π⁻", "J/ψ→φK⁺K⁻"][channel]
    nlls = [j.status.nll for j in jobs]
    finite_pairs = [(i, v) for i, v in enumerate(nlls) if np.isfinite(v)]
    if not finite_pairs:
        return None
    best_idx = min(finite_pairs, key=lambda x: x[1])[0]
    best_job = jobs[best_idx]
    ref_states = best_job.states[channel] if channel < len(best_job.states) else []

    if channel >= len(best_job.frac):
        return None
    n_comp = len(np.diag(best_job.frac[channel]))
    if n_comp == 0:
        return None

    fig, ax = plt.subplots(figsize=(max(12, n_comp * 1.2), 5))
    width = 0.8 / len(jobs)
    x     = np.arange(n_comp)

    best_nll = min(v for _, v in finite_pairs)
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

    if np.iscomplexobj(M):
        M = np.real(M)

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
    return _save(fig, out_path, f"corr_matrix_{job.name[-12:]}.png", dpi=200)


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

def plot_f0980_interference_table(job: JobData, out_path: Path) -> Path | None:
    """Render a detailed table of f0(980) interference fractions for both channels.

    Layout
    ------
    One sub-table per channel (φπ⁺π⁻ / φK⁺K⁻).  Each row = one resonance.
    Columns:
      Resonance | FF_diag | FF_interf(f0) | Phase diff (deg) | Sign bar
    Colour coding:
      FF_interf > 0  → warm red  (constructive)
      FF_interf < 0  → cool blue (destructive)
      |FF_interf| colour saturation proportional to |value|
    """
    # Collect data for both channels
    ch_labels = ["φπ⁺π⁻ (ch0)", "φK⁺K⁻ (ch1)"]
    ch_data   = []
    has_data  = False

    for ch in range(2):
        idx = job.f0980_index(ch)
        if idx is None or ch >= len(job.frac):
            ch_data.append(None)
            continue
        interf = job.f0980_interference(ch)
        if not interf:
            ch_data.append(None)
            continue
        has_data = True
        # Also grab f0(980) own diagonal FF
        ff_diag_all, _ = job.fit_fracs(ch)
        f0_ff = float(ff_diag_all[idx]) if idx < len(ff_diag_all) else float("nan")
        ch_data.append({"interf": interf, "f0_ff": f0_ff,
                        "f0_name": (job.states[ch][idx] if ch < len(job.states) else "f0(980)")})

    if not has_data:
        return None

    n_active = sum(1 for d in ch_data if d is not None)
    fig_w  = 13
    fig_h  = max(5, sum(len(d["interf"]) for d in ch_data if d) * 0.38 + 2.5)
    fig, axes = plt.subplots(1, n_active, figsize=(fig_w, fig_h))
    if n_active == 1:
        axes = [axes]

    ax_idx = 0
    for ch, data in enumerate(ch_data):
        if data is None:
            continue
        ax     = axes[ax_idx]; ax_idx += 1
        interf = data["interf"]
        f0_ff  = data["f0_ff"]
        f0_name = data["f0_name"]

        # Sort: large |FF_interf| first, then by sign (constructive first)
        interf_s = sorted(interf, key=lambda x: (-abs(x["ff_interf"]), -x["ff_interf"]))

        names   = [e["name"]           for e in interf_s]
        ff_self = [e["ff_self"]        for e in interf_s]
        ff_int  = [e["ff_interf"]      for e in interf_s]
        ff_err  = [e["ff_interf_err"]  for e in interf_s]
        phases  = [e["phase_deg"]      for e in interf_s]
        n       = len(names)

        ax.set_xlim(-0.05, 1.0)
        ax.set_ylim(-0.7, n + 0.3)
        ax.axis("off")
        ax.set_facecolor("#f8f9fa")
        fig.patch.set_facecolor("#f8f9fa")

        # Title row
        ax.text(0.5, n + 0.1,
                f"{ch_labels[ch]}\nf0(980) 干涉项表   [FF_diag(f0)={f0_ff:.4f}]",
                ha="center", va="bottom", fontsize=10, fontweight="bold", color="#1a2540")
        ax.text(0.5, n - 0.15,
                f"干涉基准：{f0_name}",
                ha="center", va="bottom", fontsize=8, color="#718096", style="italic")

        # Column headers
        col_x = [0.01, 0.35, 0.56, 0.75, 0.89]
        col_labels = ["共振态", "FF(自身)", "FF(干涉·f0)", "相位差/°", ""]
        for cx, cl in zip(col_x, col_labels):
            ax.text(cx, n - 0.45, cl, va="center", fontsize=7.5,
                    fontweight="bold", color="#2a4365")
        ax.axhline(n - 0.55, color="#a0aec0", lw=1.0)

        # Max |FF_interf| for colour normalisation
        max_abs = max(abs(v) for v in ff_int) if ff_int else 1.0
        max_abs = max(max_abs, 0.01)

        for i, (name, fself, fint, ferr, phase) in enumerate(
                zip(names, ff_self, ff_int, ff_err, phases)):
            y = n - 1 - i

            # Row background (alternating)
            if i % 2 == 0:
                from matplotlib.patches import FancyBboxPatch as _FBP
                rect = _FBP((0.0, y - 0.42), 1.0, 0.82,
                             boxstyle="square,pad=0", facecolor="#edf2f7", alpha=0.5,
                             linewidth=0)
                ax.add_patch(rect)

            # Resonance name
            short = name if len(name) <= 18 else name[:16] + "…"
            ax.text(col_x[0], y, short, va="center", fontsize=8, color="#2d3748")

            # FF self
            ax.text(col_x[1], y, f"{fself:.4f}", va="center", fontsize=8,
                    color="#4a5568", ha="left")

            # FF interf with error – coloured
            sign_color = "#c53030" if fint > 0 else "#2b6cb0"
            sign_sym   = "+" if fint >= 0 else ""
            err_str    = f" ±{ferr:.4f}" if ferr > 0 else ""
            ax.text(col_x[2], y, f"{sign_sym}{fint:.4f}{err_str}",
                    va="center", fontsize=8, color=sign_color, fontweight="bold",
                    ha="left")

            # Phase diff
            phase_str = f"{phase:+.1f}°" if phase is not None else "—"
            ax.text(col_x[3], y, phase_str, va="center", fontsize=8,
                    color="#4a5568", ha="left")

            # Colour bar (normalised to max |FF_interf|)
            bar_len = abs(fint) / max_abs * 0.09
            bar_col = "#fc8181" if fint > 0 else "#90cdf4"
            bar_x   = col_x[4]
            if fint < 0:
                bar_x = col_x[4] - bar_len
            from matplotlib.patches import FancyBboxPatch as _FBP2
            bar = _FBP2((bar_x, y - 0.28), bar_len, 0.56,
                        boxstyle="square,pad=0", facecolor=bar_col,
                        linewidth=0, alpha=0.85)
            ax.add_patch(bar)

        ax.axhline(0, color="#a0aec0", lw=0.5, ls="--")

        # Legend
        from matplotlib.patches import Patch
        legend_patches = [
            Patch(facecolor="#fc8181", alpha=0.85, label="建设性干涉 (FF>0)"),
            Patch(facecolor="#90cdf4", alpha=0.85, label="破坏性干涉 (FF<0)"),
        ]
        ax.legend(handles=legend_patches, loc="lower right",
                  fontsize=7.5, framealpha=0.8)

    fig.suptitle(f"f0(980) 干涉分数详表 — {job.name}", fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    return _save(fig, out_path, f"f0980_interference_{job.name[-12:]}.png")


def plot_suggestions(suggestions: list[dict], job: JobData, out_path: Path) -> Path | None:
    """Traffic-light list of optimisation suggestions with priority badges."""
    if not suggestions:
        return None

    PRIORITY_COLOR = {"P0": C_FAIL, "P1": C_WARN, "P2": C_BEST}
    CAT_ICON = {
        "收敛性":   "↺",
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


# ── plot_scan_significance ──────────────────────────────────────────────────────

def plot_scan_significance(sg: ScanGroup, out_path: Path) -> "Path | None":
    """Horizontal bar chart of 2ΔNLL vs scan's own baseline, per sub-job.

    Bars are colour-coded:
      * add     → blue
      * replace → green
      * baseline→ grey (centred at 0)

    A vertical dashed line marks the 5σ / 2σ thresholds (chi2, df=2 for add).
    Returns the saved Path or None if the scan has <2 usable entries.
    """
    # _setup_cjk_font() is already called at module import time; no repeat needed.

    rows = sg.delta_nll_table()
    if len(rows) < 2:
        return None

    import math
    from scipy import stats as _stats

    # Filter to rows with finite NLL
    rows = [r for r in rows if math.isfinite(r["two_delta_nll"])]
    if not rows:
        return None

    # Chi2 thresholds for df=2 (add) and df=1 (replace)
    thresh_5s_df2 = float(_stats.chi2.ppf(1 - 2 * _stats.norm.sf(5), df=2))
    thresh_3s_df2 = float(_stats.chi2.ppf(1 - 2 * _stats.norm.sf(3), df=2))
    thresh_5s_df1 = float(_stats.chi2.ppf(1 - 2 * _stats.norm.sf(5), df=1))
    thresh_3s_df1 = float(_stats.chi2.ppf(1 - 2 * _stats.norm.sf(3), df=1))

    # Sort: baseline at top, rest by improving ΔNLL
    baseline_rows = [r for r in rows if r["is_baseline"]]
    variant_rows  = [r for r in rows if not r["is_baseline"]]
    variant_rows.sort(key=lambda r: r["delta_nll"])   # most improved first
    ordered = baseline_rows + variant_rows

    n = len(ordered)
    fig_h = max(3.0, 0.55 * n + 1.5)
    fig, ax = plt.subplots(figsize=(9, fig_h))

    C_ADD     = "#2980b9"
    C_REPLACE = "#27ae60"
    C_BASE    = "#95a5a6"
    C_WORSE   = "#e74c3c"

    for i, row in enumerate(ordered):
        action    = row["action"]
        val       = row["two_delta_nll"]   # positive = improvement
        delta_nll = row["delta_nll"]       # negative = NLL went down

        if row["is_baseline"]:
            color = C_BASE
            bar_val = 0.0
        elif delta_nll < 0:
            # NLL improved → positive bar value
            bar_val = val
            color   = C_ADD if action == "add" else C_REPLACE
        else:
            # NLL worsened → use negative bar value to show below baseline
            bar_val = -val
            color   = C_WORSE

        bar = ax.barh(i, bar_val, height=0.6, color=color, alpha=0.85, zorder=3)

        # Annotation: tag / added / σ
        added_lbl = row["added"] or row["replaces"] or "(baseline)"
        if row["is_baseline"]:
            label_right = "基准模型"
        elif math.isfinite(row["sigma"]) and row["sigma"] > 0:
            label_right = f"{row['sigma']:.1f}σ"
        else:
            label_right = ""

        ax.text(-0.5, i, f"{row['tag']}  {added_lbl}",
                va="center", ha="right", fontsize=7.5, color="#2c3e50")
        if label_right:
            x_text = max(bar_val, 0) + 0.3 if bar_val >= 0 else bar_val - 0.3
            ha = "left" if bar_val >= 0 else "right"
            ax.text(x_text, i, label_right,
                    va="center", ha=ha, fontsize=7.5, color="#2c3e50", fontweight="bold")

    # ── threshold lines ────────────────────────────────────────────────────
    ax.axvline(thresh_3s_df2, color="#e67e22", lw=1.2, ls="--", zorder=2,
               label=f"3σ (add, df=2): {thresh_3s_df2:.1f}")
    ax.axvline(thresh_5s_df2, color="#e74c3c", lw=1.2, ls="--", zorder=2,
               label=f"5σ (add, df=2): {thresh_5s_df2:.1f}")

    ax.axvline(0, color="#34495e", lw=0.8, zorder=4)
    ax.set_yticks([])
    ax.set_xlabel("2ΔNLL vs baseline  (正值 = 改善)")
    ax.set_title(f"扫描显著性分析: {sg.name}\n"
                 f"基准: {sg.summary.baseline_pipi}",
                 fontsize=9, pad=6)

    # Legend for colours
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=C_ADD,     label="add   (加入共振)"),
        Patch(facecolor=C_REPLACE, label="replace (替换共振)"),
        Patch(facecolor=C_BASE,    label="baseline"),
        Patch(facecolor=C_WORSE,   label="变差"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=7)

    ax.set_xlim(left=None, right=None)
    ax.grid(axis="x", color="#ecf0f1", zorder=1)
    fig.tight_layout()

    fname = f"scan_significance_{sg.name}.png"
    out_path.mkdir(parents=True, exist_ok=True)
    fpath = out_path / fname
    fig.savefig(fpath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return fpath
