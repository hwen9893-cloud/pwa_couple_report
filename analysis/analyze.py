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
from analysis.core.scan import ScanGroup, discover_scans
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
    plot_f0980_interference_table,
    plot_scan_significance,
)
from analysis.reports.html_report import generate_report


# ═══════════════════════════════════════════════════════════════
def _collect_job_paths(jobs_dir: Path) -> list[tuple[Path, str]]:
    """Collect (job_path, scan_tag) pairs from jobs_dir.

    Supports three layouts that reflect the actual directory structure:

      1. Direct job dirs at depth 1:
           <jobs_dir>/job_*/final_params.json

      2. Scan sub-jobs at depth 2 (scan dir is direct child):
           <jobs_dir>/scan_*/NNN_sub/final_params.json

      3. Scan sub-jobs at depth 3 (scan dir inside a "Jobs" sub-folder):
           <jobs_dir>/Jobs/scan_*/NNN_sub/final_params.json

    Returns a sorted list of (path, scan_tag) tuples.  scan_tag is empty
    for direct jobs, or "<scan_dir>/<sub_name>" for scan entries.
    """
    found: list[tuple[Path, str]] = []

    def _scan_subdirs(scan_dir: Path, tag_prefix: str) -> None:
        """Walk one scan_* directory and collect its sub-job paths."""
        for sub in sorted(scan_dir.iterdir()):
            if sub.is_dir() and (sub / "final_params.json").exists():
                found.append((sub, f"{tag_prefix}/{sub.name}"))

    for entry in sorted(jobs_dir.iterdir()):
        if not entry.is_dir():
            continue

        # ── depth 1: direct job directory ───────────────────────────────────
        if (entry / "final_params.json").exists():
            found.append((entry, ""))
            continue

        # ── depth 2: scan_* directory directly under jobs_dir ───────────────
        if entry.name.startswith("scan_"):
            _scan_subdirs(entry, entry.name)
            continue

        # ── depth 3: "Jobs/" sub-folder containing scan_* dirs ──────────────
        if entry.name == "Jobs" or entry.name.lower() == "jobs":
            for scan_dir in sorted(entry.iterdir()):
                if scan_dir.is_dir() and scan_dir.name.startswith("scan_"):
                    _scan_subdirs(scan_dir, f"{entry.name}/{scan_dir.name}")

    return found


def discover_jobs(
    jobs_dir: Path,
    include_scan: bool = False,
    allow_empty: bool = False,
) -> list[JobData]:
    """Load all valid job directories under *jobs_dir*.

    When *include_scan* is False (default) only direct top-level ``job_*``
    directories are loaded; scan sub-jobs are left for ``discover_scans``.
    Set *include_scan* to True to also load scan sub-jobs into the returned
    list (legacy behaviour, causes double-loading if ``discover_scans`` is
    also called).

    When *allow_empty* is True the function returns an empty list instead of
    calling ``sys.exit`` when no directories are found.
    """
    pairs = _collect_job_paths(jobs_dir)

    if not include_scan:
        pairs = [(p, t) for p, t in pairs if not t]

    if not pairs:
        if allow_empty:
            return []
        print(f"[ERROR] No valid job directories found in {jobs_dir}")
        sys.exit(1)

    print(f"Found {len(pairs)} direct jobs:")
    jobs = []
    for p, tag in pairs:
        label = tag if tag else p.name
        print(f"  Loading {label} …", end=" ", flush=True)
        job = JobData.load(p, scan_tag=tag)
        if tag:
            job.name = f"{p.parent.name}/{p.name}"
        nll_str = f"{job.status.nll:.2f}" if not _is_nan(job.status.nll) else "NaN"
        print(f"NLL={nll_str}, Ndf={job.status.ndf}, loops={len(job.loop_nlls)}")
        if _is_nan(job.status.nll):
            print(f"  [WARN] {label}: NLL is NaN – job will be excluded from ranking")
        jobs.append(job)
    return jobs


def _is_nan(x: float) -> bool:
    """Return True when *x* is NaN (avoids the confusing ``x != x`` idiom)."""
    import math
    return math.isnan(x)


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

    # Sort with NaN pushed to the end
    sorted_pairs = sorted(
        zip(jobs, delta_results),
        key=lambda x: (not np.isfinite(x[0].status.nll), x[0].status.nll),
    )
    for job, dr in sorted_pairs:
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


# ─── Best-job selection constants ───────────────────────────────────────────
_NLL_TOLERANCE  = 1.0   # ΔNLL < 1.0 counts as converging to the same minimum
_FREQ_THRESHOLD = 3     # minimum number of loops that must reach the best NLL
_EXPECTED_LOOPS = 30    # standard loop count; fewer loops → "questionable" flag


def _nll_convergence_count(job, tol: float = _NLL_TOLERANCE) -> int:
    """Return how many of a job's loop NLLs fall within *tol* of its minimum."""
    if not job.loop_nlls:
        return 0
    best = min(job.loop_nlls)
    return sum(1 for x in job.loop_nlls if x - best < tol)


def _select_best_job(
    valid_jobs: list,
) -> tuple:
    """Select the best job using a frequency-stability criterion.

    A job is considered *stable* when its minimum NLL was reproduced more
    than _FREQ_THRESHOLD times (within _NLL_TOLERANCE), regardless of
    total loop count.  Jobs with fewer than _EXPECTED_LOOPS that pass the
    frequency check are treated as fully confirmed.  Jobs with fewer loops
    that do NOT pass the frequency check but have a lower NLL than the
    confirmed best are flagged as *questionable*.

    Returns
    -------
    best_job : JobData | None
        The confirmed best job (frequency-stable + lowest NLL), or the
        absolute minimum-NLL fallback when no stable job exists.
    questionable_best_job : JobData | None
        Set when a short-loop job (< _EXPECTED_LOOPS, frequency <=
        _FREQ_THRESHOLD) has a lower NLL than *best_job*, indicating an
        under-sampled candidate that has not yet proven stability.
    """
    if not valid_jobs:
        return None, None

    # Stable: frequency criterion satisfied, regardless of loop count
    stable_jobs = [
        j for j in valid_jobs
        if _nll_convergence_count(j) > _FREQ_THRESHOLD
    ]

    if stable_jobs:
        best_job = min(stable_jobs, key=lambda j: j.status.nll)
    else:
        best_job = min(valid_jobs, key=lambda j: j.status.nll)
        n_loops_best = len(best_job.loop_nlls)
        freq_best    = _nll_convergence_count(best_job)
        print(
            f"[WARN] 无 job 满足收敛频率条件"
            f"（最低 NLL 需出现 >{_FREQ_THRESHOLD} 次，"
            f"最接近的 job '{best_job.name}' 频率={freq_best}/{n_loops_best}），"
            f"回退至绝对最低 NLL，全局最优可疑"
        )

    # Questionable: short-loop job that did NOT pass frequency check
    # but has a lower NLL than the confirmed best
    short_unconfirmed = [
        j for j in valid_jobs
        if len(j.loop_nlls) < _EXPECTED_LOOPS
        and _nll_convergence_count(j) <= _FREQ_THRESHOLD
    ]
    questionable_best_job = None
    if short_unconfirmed:
        best_short = min(short_unconfirmed, key=lambda j: j.status.nll)
        if best_job is None or best_short.status.nll < best_job.status.nll:
            questionable_best_job = best_short
            print(
                f"[INFO] 存疑最优候选：{best_short.name}  "
                f"NLL={best_short.status.nll:.4f}  "
                f"（仅 {len(best_short.loop_nlls)}/{_EXPECTED_LOOPS} 次拟合且频率不足，结果待确认）"
            )

    return best_job, questionable_best_job


# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Amplitude analysis job evaluator")
    parser.add_argument(
        "--jobs",
        type=Path,
        default=Path(__file__).parent.parent.parent / "Jobs",
        help="Root directory containing job_* subdirectories (default: ../Jobs relative to workspace root)",
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
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Exclude scan sub-jobs; analyse only top-level job_* directories",
    )
    parser.add_argument(
        "--scans-only",
        action="store_true",
        help="Only run per-scan significance analysis; skip global job comparison",
    )
    args = parser.parse_args()

    import numpy as np

    jobs_dir  = args.jobs.resolve()
    out_dir   = args.output or jobs_dir.parent / "analysis_output"
    plots_dir = out_dir / "plots"

    print(f"\nJobs dir : {jobs_dir}")
    print(f"Output   : {out_dir}\n")

    # ── 1. Load direct top-level jobs (never loads scan sub-dirs) ──────
    # Scan sub-jobs are loaded exclusively via discover_scans to avoid
    # reading the same files twice.
    jobs = discover_jobs(jobs_dir, include_scan=False, allow_empty=True)

    # ── 1b. Load scan groups ────────────────────────────────────────────
    if not args.no_scan:
        print("Discovering scan groups …")
        scan_groups = discover_scans(jobs_dir)
        if scan_groups:
            for sg in scan_groups:
                n_loaded = len(sg.jobs)
                n_total  = sg.summary.total_jobs
                bl_nll   = (sg.baseline_job.status.nll
                            if sg.baseline_job else float("nan"))
                bl_str   = f"{bl_nll:.2f}" if np.isfinite(bl_nll) else "NaN"
                print(f"  Scan: {sg.name}  ({n_loaded}/{n_total} jobs, "
                      f"baseline NLL={bl_str})")
        else:
            print("  (no scan_summary.txt found)")
    else:
        scan_groups = []

    # Exit if nothing was found at all
    if not jobs and not scan_groups:
        print(f"[ERROR] No valid job directories or scan groups found in {jobs_dir}")
        sys.exit(1)

    # When no top-level job_* directories exist, fall back to using all
    # scan sub-jobs as the analysis population so that §1/§2/§7 and all
    # per-job plots are still generated.  The scan significance section (§4)
    # continues to evaluate each sub-job relative to its scan's baseline.
    # This is different from --scans-only, which the user must request
    # explicitly to suppress per-job analysis entirely.
    if not jobs and scan_groups:
        jobs = [j for sg in scan_groups for j in sg.jobs]
        print(
            f"[INFO] No direct job_* directories found; using "
            f"{len(jobs)} scan sub-jobs for general analysis."
        )

    # --scans-only suppresses per-job analysis even when jobs are present
    scans_only = args.scans_only

    if args.scans_only and not scan_groups:
        print("[WARN] --scans-only requested but no scan groups found.")
        sys.exit(0)

    valid_jobs = [j for j in jobs if np.isfinite(j.status.nll)]
    if not valid_jobs and not scans_only:
        print("[ERROR] All jobs have NaN NLL. Nothing to analyse.")
        sys.exit(1)

    best_job, questionable_best_job = _select_best_job(valid_jobs)

    # ── 2. Cross-job checks (global NLL comparison) ────────────────────
    delta_results: list[dict] = []
    if not scans_only and jobs:
        delta_results = check_delta_nll(jobs)
        print_summary_table(jobs, delta_results)

    # ── 3. Per-job checks ──────────────────────────────────────────────
    check_results_per_job: dict[str, dict] = {}
    target_jobs = [best_job] if (args.best_only and best_job) else jobs
    for job in target_jobs:
        cr = run_all_checks(job)
        check_results_per_job[job.name] = cr
        if not scans_only:
            print_check_summary(job, cr)

    # ── 4. Plots ───────────────────────────────────────────────────────
    print("\nGenerating plots …")
    # Values may be Path (single image), list[Path] (slideshow), or None.
    plot_paths: dict[str, Path | list[Path] | None] = {}

    if not scans_only and jobs:
        plot_paths["NLL 比较"] = plot_nll_comparison(jobs, plots_dir)
        print("  [ok] NLL comparison")

        stability_paths = plot_nll_stability(jobs, plots_dir)
        if stability_paths:
            plot_paths["NLL 稳定性"] = stability_paths
            print(f"  [ok] NLL stability ({len(stability_paths)} plots)")

    if not scans_only and best_job is not None:
        plot_paths["拟合分数（最优作业）"] = plot_fit_fractions(best_job, plots_dir)
        print(f"  [ok] Fit fractions ({best_job.name})")

    if not scans_only and jobs:
        plot_paths["FF 跨作业对比 ch0"] = plot_ff_comparison(jobs, plots_dir, channel=0)
        plot_paths["FF 跨作业对比 ch1"] = plot_ff_comparison(jobs, plots_dir, channel=1)
        print("  [ok] FF comparison (ch0, ch1)")

    if not scans_only and best_job is not None:
        plot_paths["误差矩阵（最优）"] = plot_error_matrix(best_job, plots_dir)
        print("  [ok] Error matrix")

        cross_ff_path = plot_cross_channel_ff(best_job, plots_dir)
        if cross_ff_path:
            plot_paths["共享共振跨通道FF（最优）"] = cross_ff_path
            print("  [ok] Cross-channel FF")

        f0980_path = plot_f0980_interference_table(best_job, plots_dir)
        if f0980_path:
            plot_paths["f0(980)干涉项表（最优）"] = f0980_path
            print("  [ok] f0(980) interference table")

        if best_job.name in check_results_per_job:
            plot_paths["评估清单（最优）"] = plot_checklist_summary(
                check_results_per_job[best_job.name], best_job, plots_dir
            )
            print("  [ok] Checklist summary")

    # ── 4b. Scan significance plots ────────────────────────────────────
    scan_plot_paths: dict[str, Path | None] = {}
    for sg in scan_groups:
        sp = plot_scan_significance(sg, plots_dir)
        if sp:
            key = f"扫描显著性 {sg.name}"
            scan_plot_paths[key] = sp
            print(f"  [ok] Scan significance: {sg.name}")

    # ── 5. Model selection (AIC) ───────────────────────────────────────
    aic_results: list[dict] = []
    if not scans_only and jobs:
        aic_results = compare_aic(jobs)
        aic_plot = plot_aic_comparison(aic_results, plots_dir)
        if aic_plot:
            plot_paths["模型选择（AIC）"] = aic_plot
            print("  [ok] AIC model comparison")

    # ── 6. Ensure all jobs have check results for report ───────────────
    for job in jobs:
        if job.name not in check_results_per_job:
            check_results_per_job[job.name] = run_all_checks(job)
    for sg in scan_groups:
        for job in sg.jobs:
            if job.name not in check_results_per_job:
                check_results_per_job[job.name] = run_all_checks(job)

    # ── 7. Generate optimisation suggestions ───────────────────────────
    # Build deduplicated list of all analysed jobs (scan jobs + direct jobs)
    # using a dict to avoid O(n·m) set rebuilds.
    all_analysed: dict[str, JobData] = {
        j.name: j for sg in scan_groups for j in sg.jobs
    }
    for j in jobs:
        if j.name not in all_analysed:
            all_analysed[j.name] = j
    all_analysed_jobs = list(all_analysed.values())

    suggestions_per_job: dict[str, list[dict]] = {}
    for job in all_analysed_jobs:
        cr   = check_results_per_job.get(job.name, {})
        sugg = generate_suggestions(job, cr, aic_results)
        suggestions_per_job[job.name] = sugg
        if not scans_only and best_job and job is best_job and sugg:
            sugg_plot = plot_suggestions(sugg, job, plots_dir)
            if sugg_plot:
                plot_paths["优化建议（最优）"] = sugg_plot
                print("  [ok] Optimisation suggestions")
            print(f"\n  ── Top suggestions for {job.name} ──")
            for s in sugg[:6]:
                print(f"    [{s['priority']}] [{s['category']}] {s['action'][:70]}")

    # ── 8. Dump structured results ─────────────────────────────────────
    json_path = dump_results_json(
        jobs, delta_results, check_results_per_job, out_dir,
        aic_results=aic_results,
        suggestions_per_job=suggestions_per_job,
    )
    print(f"\nResults JSON → {json_path}")

    # ── 9. HTML report ─────────────────────────────────────────────────
    if not args.no_report:
        print("Generating HTML report …")
        report_path = generate_report(
            jobs, check_results_per_job, plot_paths, out_dir,
            aic_results=aic_results,
            suggestions_per_job=suggestions_per_job,
            best_job=best_job,
            questionable_best_job=questionable_best_job,
            reference_root=jobs_dir.parent,
            scan_groups=scan_groups,
            scan_plot_paths=scan_plot_paths,
        )
        print(f"  Report saved → {report_path}")

    if best_job:
        freq = _nll_convergence_count(best_job)
        n_loops = len(best_job.loop_nlls)
        stability = (
            f"收敛频率 {freq}/{n_loops}"
            if n_loops >= _EXPECTED_LOOPS
            else f"仅 {n_loops} 次拟合"
        )
        print(f"\nDone. 最优作业: {best_job.name}  (NLL={best_job.status.nll:.4f}, {stability})")
        if questionable_best_job:
            qn = len(questionable_best_job.loop_nlls)
            print(
                f"      存疑候选: {questionable_best_job.name}  "
                f"(NLL={questionable_best_job.status.nll:.4f}, "
                f"仅 {qn}/{_EXPECTED_LOOPS} 次拟合，结果待确认)"
            )
        print()
    else:
        print(f"\nDone. {len(scan_groups)} scan group(s) analysed.\n")


if __name__ == "__main__":
    main()
