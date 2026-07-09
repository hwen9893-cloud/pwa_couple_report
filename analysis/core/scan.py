"""Scan-group data structures and analysis for significance scanning.

A *scan* is a collection of jobs that share one baseline model and vary it
one component at a time (add-one / replace strategy).  Each scan directory
contains a ``scan_summary.txt`` that records:

- Scan metadata (generated timestamp, strategy, baseline states)
- A table with one row per sub-job: tag, action, added resonance, replaces

This module provides:

``ScanEntry``
    One row of the scan table.

``ScanSummary``
    Full parsed content of scan_summary.txt; loaded with
    ``ScanSummary.load(scan_dir)``.

``ScanGroup``
    Pairs a ``ScanSummary`` with loaded ``JobData`` objects and exposes
    ΔNLL / significance tables relative to the scan's own baseline.
"""

from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats

from .job import JobData


# ── data classes ───────────────────────────────────────────────────────────────

@dataclass
class ScanEntry:
    """One row of the scan table."""
    tag: str
    action: str           # 'baseline' | 'add' | 'replace'
    added: Optional[str]   # resonance added (None for baseline)
    replaces: Optional[str]  # resonance replaced (None for add/baseline)
    jobdir: str           # original HPC path (informational only)

    @property
    def delta_ndf(self) -> int:
        """Expected change in free parameters vs baseline.

        'add'     → +2 (real + imag of new production coupling)
        'replace' → 0  (same number, different parameterisation)
        'baseline'→ 0
        """
        if self.action == "add":
            return 2
        return 0


@dataclass
class ScanSummary:
    """Parsed content of a scan_summary.txt file."""
    scan_name: str                  # directory name, e.g. scan_phipipi_20260614_211047
    scan_dir: Path
    generated: str                  # timestamp string
    strategy: str
    baseline_pipi: list[str]        # resonances in baseline ππ model
    baseline_kk: list[str]          # KK model states (may be empty if FIXED)
    total_jobs: int
    entries: list[ScanEntry]

    @property
    def baseline_entry(self) -> Optional[ScanEntry]:
        return next((e for e in self.entries if e.action == "baseline"), None)

    @property
    def baseline_tag(self) -> Optional[str]:
        e = self.baseline_entry
        return e.tag if e else None

    # ── loader ────────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, scan_dir: Path) -> "ScanSummary":
        """Parse scan_summary.txt in *scan_dir* and return a ScanSummary.

        Raises FileNotFoundError if scan_summary.txt does not exist.
        """
        summary_file = scan_dir / "scan_summary.txt"
        if not summary_file.exists():
            raise FileNotFoundError(summary_file)

        text = summary_file.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        generated      = ""
        strategy       = ""
        baseline_pipi  = []
        baseline_kk    = []
        total_jobs     = 0
        entries        = []

        # ── parse comment-block metadata ──────────────────────────────────
        for line in lines:
            s = line.strip()
            if not s.startswith("#"):
                continue
            body = s[1:].strip()  # strip leading '#'

            m_gen   = re.match(r"Scan generated\s*:\s*(.+)", body, re.I)
            m_strat = re.match(r"Strategy\s*:\s*(.+)", body, re.I)
            m_total = re.match(r"Total jobs\s*:\s*(\d+)", body, re.I)
            m_pipi  = re.match(r"baseline pipi\s*:\s*(.+)", body, re.I)
            m_kk    = re.match(r"baseline kk\s*:\s*(.+)", body, re.I)

            if m_gen:   generated = m_gen.group(1).strip()
            if m_strat: strategy  = m_strat.group(1).strip()
            if m_total: total_jobs = int(m_total.group(1))
            if m_pipi:
                baseline_pipi = [r.strip() for r in m_pipi.group(1).split(",") if r.strip()]
            if m_kk:
                baseline_kk = [r.strip() for r in m_kk.group(1).split(",") if r.strip()]

        # ── parse data table ──────────────────────────────────────────────
        # Skip comment lines and the dashed separator; data lines are those
        # where the first token is NOT "tag" (header) and not all dashes.
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("tag") or re.match(r"^-{10,}", s):
                continue
            parts = s.split()
            if len(parts) < 5:
                continue
            # Columns: tag  action  added  replaces  jobdir
            # "None" is stored literally as the string "None"
            tag      = parts[0]
            action   = parts[1].lower()
            added    = None if parts[2] == "None" else parts[2]
            replaces = None if parts[3] == "None" else parts[3]
            jobdir   = parts[4]  # may have spaces? use last field
            if len(parts) > 5:
                jobdir = parts[-1]  # robustness: take last token
            entries.append(ScanEntry(
                tag=tag, action=action,
                added=added, replaces=replaces, jobdir=jobdir,
            ))

        return cls(
            scan_name     = scan_dir.name,
            scan_dir      = scan_dir,
            generated     = generated,
            strategy      = strategy,
            baseline_pipi = baseline_pipi,
            baseline_kk   = baseline_kk,
            total_jobs    = total_jobs,
            entries       = entries,
        )


# ── ScanGroup ──────────────────────────────────────────────────────────────────

@dataclass
class ScanGroup:
    """A scan directory together with its loaded job data.

    Attributes
    ----------
    summary      : parsed ScanSummary
    jobs         : all loaded JobData objects (baseline + variants)
    baseline_job : the baseline JobData (None if not found / NLL=NaN)
    """
    summary:      ScanSummary
    jobs:         list[JobData]
    baseline_job: Optional[JobData]

    # ── computed property ──────────────────────────────────────────────────
    @property
    def name(self) -> str:
        return self.summary.scan_name

    # ── factory ────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, scan_dir: Path) -> "ScanGroup":
        """Load a ScanGroup from *scan_dir*.

        Sub-jobs that do not have a local ``final_params.json`` are silently
        skipped (they may still be running on the cluster).
        """
        summary = ScanSummary.load(scan_dir)
        jobs: list[JobData] = []
        baseline_job: Optional[JobData] = None

        for entry in summary.entries:
            sub_path = scan_dir / entry.tag
            if not (sub_path / "final_params.json").exists():
                continue
            job = JobData.load(sub_path, scan_tag=summary.scan_name)
            job.name = f"{summary.scan_name}/{entry.tag}"
            jobs.append(job)
            if entry.action == "baseline":
                baseline_job = job

        return cls(summary=summary, jobs=jobs, baseline_job=baseline_job)

    # ── ΔNLL analysis ──────────────────────────────────────────────────────
    def delta_nll_table(self) -> list[dict]:
        """Compute ΔNLL of every job relative to the scan's own baseline.

        Returns a list of dicts (one per job), sorted by ΔNLL ascending.
        Each dict contains:

          tag, action, added, replaces, nll, delta_nll, two_delta_nll,
          delta_ndf, p_value, sigma, is_baseline, is_best, status, message
        """
        if not self.jobs:
            return []

        # Build tag → entry lookup
        entry_map = {e.tag: e for e in self.summary.entries}
        # Extract tag from job name (last component after '/')
        def _tag(job: JobData) -> str:
            return job.name.split("/")[-1]

        valid_jobs = [j for j in self.jobs if math.isfinite(j.status.nll)]
        if not valid_jobs:
            return []

        best_nll   = min(j.status.nll for j in valid_jobs)
        base_nll   = (self.baseline_job.status.nll
                      if self.baseline_job and math.isfinite(self.baseline_job.status.nll)
                      else best_nll)

        rows = []
        for job in self.jobs:
            tag   = _tag(job)
            entry = entry_map.get(tag)
            action   = entry.action   if entry else "unknown"
            added    = entry.added    if entry else None
            replaces = entry.replaces if entry else None
            d_ndf    = entry.delta_ndf if entry else 1

            is_baseline = (job is self.baseline_job)
            is_best     = math.isfinite(job.status.nll) and job.status.nll == best_nll

            if not math.isfinite(job.status.nll):
                rows.append(dict(
                    tag=tag, action=action, added=added, replaces=replaces,
                    nll=float("nan"), delta_nll=float("nan"),
                    two_delta_nll=float("nan"), delta_ndf=d_ndf,
                    p_value=float("nan"), sigma=float("nan"),
                    is_baseline=is_baseline, is_best=is_best,
                    status="fail",
                    message="NLL 为 NaN，作业可能未完成",
                ))
                continue

            delta     = float(job.status.nll - base_nll)
            two_delta = 2.0 * abs(delta)
            # For 'add': df = delta_ndf (usually 2); 'replace': df = 1
            df = max(1, d_ndf if action in ("add", "replace") else 1)

            if is_baseline:
                p_value = 1.0
                sigma   = 0.0
                status  = "ok"
                message = "基准模型"
            else:
                # Significance of improvement vs baseline
                if delta < 0:  # improved
                    p_value = float(stats.chi2.sf(two_delta, df=df))
                    sigma   = float(stats.norm.isf(p_value / 2)) if 0 < p_value < 1 else 99.0
                    if sigma >= 3.0:
                        status  = "ok"
                        message = f"改善显著 {sigma:.1f}σ (2ΔNLL={two_delta:.1f}, df={df})"
                    elif sigma >= 2.0:
                        status  = "warn"
                        message = f"改善边缘 {sigma:.1f}σ (2ΔNLL={two_delta:.1f}, df={df})"
                    else:
                        status  = "fail"
                        message = f"改善不显著 {sigma:.1f}σ (2ΔNLL={two_delta:.1f}, df={df})"
                else:  # worse
                    sigma   = 0.0
                    p_value = 1.0
                    status  = "fail"
                    message = f"NLL 变差 ΔNLL={delta:+.2f}"

            rows.append(dict(
                tag=tag, action=action, added=added, replaces=replaces,
                nll=float(job.status.nll),
                delta_nll=delta,
                two_delta_nll=two_delta,
                delta_ndf=d_ndf,
                p_value=p_value,
                sigma=sigma,
                is_baseline=is_baseline,
                is_best=is_best,
                status=status,
                message=message,
            ))

        rows.sort(key=lambda r: (not r["is_baseline"], r["delta_nll"]))
        return rows


# ── module-level helpers ────────────────────────────────────────────────────────

def discover_scans(jobs_dir: Path) -> list[ScanGroup]:
    """Find and load all scan groups under *jobs_dir*.

    Looks for ``scan_*/scan_summary.txt`` at depths 1 and 2 below *jobs_dir*:

      <jobs_dir>/scan_*/scan_summary.txt          (depth 1)
      <jobs_dir>/Jobs/scan_*/scan_summary.txt      (depth 2, via "Jobs" subfolder)

    Returns a list of ``ScanGroup`` objects sorted by scan directory name.
    """
    scan_dirs: list[Path] = []

    for entry in sorted(jobs_dir.iterdir()):
        if not entry.is_dir():
            continue
        # Depth 1: jobs_dir/scan_*/
        if entry.name.startswith("scan_") and (entry / "scan_summary.txt").exists():
            scan_dirs.append(entry)
        # Depth 2: jobs_dir/Jobs/scan_*/
        elif entry.name.lower() == "jobs":
            for sub in sorted(entry.iterdir()):
                if (sub.is_dir() and sub.name.startswith("scan_")
                        and (sub / "scan_summary.txt").exists()):
                    scan_dirs.append(sub)

    groups = []
    for sd in scan_dirs:
        try:
            g = ScanGroup.load(sd)
            groups.append(g)
        except Exception as exc:
            import warnings
            warnings.warn(f"Failed to load scan group {sd}: {exc}")
    return groups
