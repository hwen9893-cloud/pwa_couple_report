#!/usr/bin/env python3
"""
振幅分析作业批量评估主程序

Usage:
    # from the 609/ parent directory (recommended):
    python analysis/analyze.py --jobs Jobs
    python analysis/analyze.py --jobs Jobs --best-only
    python analysis/analyze.py --jobs Jobs --output /path/to/out
    python analysis/analyze.py --jobs Jobs --no-report

    # or directly from the analysis/ directory:
    python analyze.py --jobs ../Jobs
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Allow running as a script from any location
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.core.job import JobData
from analysis.core.checks import run_all_checks, check_delta_nll
from analysis.core.model_selection import compare_aic
from analysis.core.suggestions import generate_suggestions
from analysis.plots.summary_plots import (
    plot_nll_comparison,
    plot_nll_stability,
    plot_fit_fractions,
    plot_ff_comparison,
    plot_error_matrix,
    plot_checklist_summary,
    plot_cross_channel_ff,
    plot_aic_comparison,
    plot_suggestions,
)
from analysis.reports.html_report import generate_report


# ═══════════════════════════════════════════════════════════════
def discover_jobs(jobs_dir: Path) -> list[JobData]:
    """Load all job_* subdirectories that contain final_params.json."""
    job_paths = sorted(
        p for p in jobs_dir.iterdir()
        if p.is_dir() and p.name.startswith("job_") and (p / "final_params.json").exists()
    )
    if not job_paths:
        print(f"[ERROR] No valid job directories found in {jobs_dir}")
        sys.exit(1)

    print(f"Found {len(job_paths)} jobs:")
    jobs = []
    for p in job_paths:
        print(f"  Loading {p.name} …", end=" ", flush=True)
        job = JobData.load(p)
        nll_str = f"{job.status.nll:.2f}" if job.status.nll == job.status.nll else "NaN"
        print(f"NLL={nll_str}, Ndf={job.status.ndf}, loops={len(job.loop_nlls)}")
        if not (job.status.nll == job.status.nll):  # NaN check
            print(f"  [WARN] {p.name}: NLL is NaN – job will be excluded from ranking")
        jobs.append(job)
    return jobs


# ═══════════════════════════════════════════════════════════════
def print_summary_table(jobs: list[JobData], delta_results: list[dict]):
    import numpy as np
    print("\n" + "═" * 75)
    print("  NLL COMPARISON TABLE")
    print("═" * 75)
    print(f"  {'Job':<38} {'NLL':>14} {'ΔNLL':>9} {'2ΔNLL':>9} {'Ndf':>5}")
    print("─" * 75)

    valid_nlls = [j.status.nll for j in jobs if np.isfinite(j.status.nll)]
    best = min(valid_nlls) if valid_nlls else float("nan")

    for job, dr in sorted(zip(jobs, delta_results), key=lambda x: x[0].status.nll):
        flag = "★" if job.status.nll == best else " "
        v    = dr["value"]
        if v is None:
            print(f"  {flag} {job.name:<36} {'NaN':>14} {'—':>9} {'—':>9} {job.status.ndf:>5}")
        else:
            print(f"  {flag} {job.name:<36} {job.status.nll:>14.4f} "
                  f"{v['delta_nll']:>9.2f} {v['two_delta_nll']:>9.1f} {job.status.ndf:>5}")
    print("═" * 75)


def print_check_summary(job: JobData, check_results: dict):
    print(f"\n  ── Checks for {job.name} ──")
    icons = {"ok": "✓", "warn": "⚠", "fail": "✗"}

    def _print_item(item):
        s    = item.get("status", "warn")
        icon = icons.get(s, "?")
        print(f"    [{icon}] {item['name']:<42} {item['message'][:68]}")

    for key, val in check_results.items():
        if isinstance(val, list):
            for item in val:
                _print_item(item)
        else:
            _print_item(val)


# ═══════════════════════════════════════════════════════════════
def dump_results_json(
    jobs: list[JobData],
    delta_results: list[dict],
    check_results_per_job: dict[str, dict],
    out_dir: Path,
    aic_results: list[dict] | None = None,
    suggestions_per_job: dict[str, list[dict]] | None = None,
) -> Path:
    """Serialise all check results + AIC + suggestions to results.json."""
    import numpy as np

    def _safe(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return None if not np.isfinite(obj) else float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    valid_nlls = [j.status.nll for j in jobs if np.isfinite(j.status.nll)]
    best_nll   = min(valid_nlls) if valid_nlls else None

    payload = {
        "jobs": [
            {
                "name":    j.name,
                "nll":     _safe(j.status.nll),
                "ndf":     j.status.ndf,
                "success": j.status.success,
                "is_best": (j.status.nll == best_nll) if best_nll is not None else False,
                "n_loops": len(j.loop_nlls),
            }
            for j in jobs
        ],
        "delta_nll":        delta_results,
        "checks":           check_results_per_job,
        "model_selection":  aic_results or [],
        "suggestions":      suggestions_per_job or {},
    }

    out_file = out_dir / "results.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(payload, default=_safe, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_file


# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Amplitude analysis job evaluator")
    parser.add_argument(
        "--jobs",
        type=Path,
        # Corrected default: __file__ is analysis/analyze.py → .parent.parent is 609/
        default=Path(__file__).parent.parent / "Jobs",
        help="Root directory containing job_* subdirectories (default: ../Jobs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for plots and report (default: <jobs_dir>/../analysis_output)",
    )
    parser.add_argument(
        "--best-only",
        action="store_true",
        help="Run detailed checks only on the best-NLL job",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip HTML report generation",
    )
    args = parser.parse_args()

    import numpy as np

    jobs_dir = args.jobs.resolve()
    out_dir  = args.output or jobs_dir.parent / "analysis_output"
    plots_dir = out_dir / "plots"

    print(f"\nJobs dir : {jobs_dir}")
    print(f"Output   : {out_dir}\n")

    # ── 1. Load jobs ───────────────────────────────────────────
    jobs = discover_jobs(jobs_dir)
    valid_jobs = [j for j in jobs if np.isfinite(j.status.nll)]
    if not valid_jobs:
        print("[ERROR] All jobs have NaN NLL. Nothing to analyse.")
        sys.exit(1)

    nlls     = [j.status.nll for j in valid_jobs]
    best_job = valid_jobs[int(np.argmin(nlls))]

    # ── 2. Cross-job checks ────────────────────────────────────
    delta_results = check_delta_nll(jobs)
    print_summary_table(jobs, delta_results)

    # ── 3. Per-job checks ──────────────────────────────────────
    check_results_per_job: dict[str, dict] = {}
    target_jobs = [best_job] if args.best_only else jobs
    for job in target_jobs:
        cr = run_all_checks(job)
        check_results_per_job[job.name] = cr
        print_check_summary(job, cr)

    # ── 4. Plots ───────────────────────────────────────────────
    print("\nGenerating plots …")
    plot_paths: dict[str, Path | None] = {}

    plot_paths["NLL 比较"] = plot_nll_comparison(jobs, plots_dir)
    print("  [ok] NLL comparison")

    plot_paths["NLL 稳定性"] = plot_nll_stability(jobs, plots_dir)
    print("  [ok] NLL stability")

    plot_paths["拟合分数（最优作业）"] = plot_fit_fractions(best_job, plots_dir)
    print(f"  [ok] Fit fractions ({best_job.name})")

    plot_paths["FF 跨作业对比 ch0"] = plot_ff_comparison(jobs, plots_dir, channel=0)
    plot_paths["FF 跨作业对比 ch1"] = plot_ff_comparison(jobs, plots_dir, channel=1)
    print("  [ok] FF comparison (ch0, ch1)")

    plot_paths["误差矩阵（最优）"] = plot_error_matrix(best_job, plots_dir)
    print("  [ok] Error matrix")

    cross_ff_path = plot_cross_channel_ff(best_job, plots_dir)
    if cross_ff_path:
        plot_paths["共享共振跨通道FF（最优）"] = cross_ff_path
        print("  [ok] Cross-channel FF")

    if best_job.name in check_results_per_job:
        plot_paths["评估清单（最优）"] = plot_checklist_summary(
            check_results_per_job[best_job.name], best_job, plots_dir
        )
        print("  [ok] Checklist summary")

    # ── 5. Model selection (AIC) ───────────────────────────────
    aic_results = compare_aic(jobs)
    aic_plot = plot_aic_comparison(aic_results, plots_dir)
    if aic_plot:
        plot_paths["模型选择（AIC）"] = aic_plot
        print("  [ok] AIC model comparison")

    # ── 6. Ensure all jobs have check results for report ───────
    for job in jobs:
        if job.name not in check_results_per_job:
            check_results_per_job[job.name] = run_all_checks(job)

    # ── 7. Generate optimisation suggestions ───────────────────
    suggestions_per_job: dict[str, list[dict]] = {}
    for job in jobs:
        cr   = check_results_per_job.get(job.name, {})
        sugg = generate_suggestions(job, cr, aic_results)
        suggestions_per_job[job.name] = sugg
        if job is best_job and sugg:
            sugg_plot = plot_suggestions(sugg, job, plots_dir)
            if sugg_plot:
                plot_paths["优化建议（最优）"] = sugg_plot
                print("  [ok] Optimisation suggestions")
            print(f"\n  ── Top suggestions for {job.name} ──")
            for s in sugg[:6]:
                print(f"    [{s['priority']}] [{s['category']}] {s['action'][:70]}")

    # ── 8. Dump structured results ─────────────────────────────
    json_path = dump_results_json(
        jobs, delta_results, check_results_per_job, out_dir,
        aic_results=aic_results,
        suggestions_per_job=suggestions_per_job,
    )
    print(f"\nResults JSON → {json_path}")

    # ── 9. HTML report ─────────────────────────────────────────
    if not args.no_report:
        print("Generating HTML report …")
        report_path = generate_report(
            jobs, check_results_per_job, plot_paths, out_dir,
            aic_results=aic_results,
            suggestions_per_job=suggestions_per_job,
        )
        print(f"  Report saved → {report_path}")

    print(f"\nDone. Best fit: {best_job.name}  (NLL={best_job.status.nll:.4f})\n")


if __name__ == "__main__":
    main()
