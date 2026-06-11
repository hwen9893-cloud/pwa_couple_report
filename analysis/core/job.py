"""Single-job data loader: reads all output files and exposes typed accessors."""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class FitStatus:
    success: bool
    nll: float
    ndf: int


@dataclass
class JobData:
    name: str
    path: Path

    # Populated by load()
    status: FitStatus = field(default=None)
    params_value: dict = field(default_factory=dict)
    params_error: dict = field(default_factory=dict)
    error_matrix: Optional[np.ndarray] = None
    frac: list[np.ndarray] = field(default_factory=list)    # [ch0_matrix, ch1_matrix]
    frac_err: list[np.ndarray] = field(default_factory=list)
    states: list[list[str]] = field(default_factory=list)   # [ch0_states, ch1_states]
    loop_nlls: list[float] = field(default_factory=list)    # per-loop NLL values
    model_diff: dict = field(default_factory=dict)          # vs baseline

    @classmethod
    def load(cls, job_path: str | Path) -> "JobData":
        path = Path(job_path)
        job = cls(name=path.name, path=path)
        job._load_params()
        job._load_error_matrix()
        job._load_fit_fracs()
        job._load_states()
        job._load_loop_nlls()
        return job

    # ------------------------------------------------------------------ #
    @property
    def param_names(self) -> list[str]:
        """Ordered parameter names; index matches error matrix rows/columns."""
        return list(self.params_value.keys())

    # ------------------------------------------------------------------ #
    def _load_params(self):
        with open(self.path / "final_params.json") as f:
            d = json.load(f)
        self.params_value = d.get("value", {})
        self.params_error = d.get("error", {})
        s = d.get("status", {})
        self.status = FitStatus(
            success=s.get("success", False),
            nll=s.get("NLL", float("nan")),
            ndf=s.get("Ndf", 0),
        )

    def _load_error_matrix(self):
        npy = self.path / "error_matrix.npy"
        txt = self.path / "error_matrix.txt"
        if npy.exists():
            self.error_matrix = np.load(npy)
        elif txt.exists():
            self.error_matrix = np.loadtxt(txt)

    def _load_fit_fracs(self):
        self.frac, self.frac_err = [], []
        for ch in range(2):
            f_path  = self.path / f"fit_frac_channel{ch}.csv"
            fe_path = self.path / f"fit_frac_channel{ch}_err.csv"
            if not f_path.exists():
                continue
            delim = _sniff_delimiter(f_path)
            self.frac.append(np.genfromtxt(f_path, delimiter=delim, filling_values=0.0))
            self.frac_err.append(
                np.genfromtxt(fe_path, delimiter=delim, filling_values=0.0)
                if fe_path.exists() else np.zeros_like(self.frac[-1])
            )

    def _load_states(self):
        """Parse States_*.yaml for resonance labels (no yaml dependency)."""
        self.states = []
        for yaml_file in [
            self.path / "States_phipipi.yaml",
            self.path / "States_phikk.yaml",
        ]:
            states = []
            if yaml_file.exists():
                for line in yaml_file.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- ") and not stripped.startswith("# "):
                        states.append(stripped[2:].strip())
            self.states.append(states)

    def _load_loop_nlls(self):
        """Extract per-loop NLL from all slurm log files."""
        logs = sorted((self.path / "slurm_logs").glob("*.out"))
        if not logs:
            return
        # Concatenate all logs; support negative, positive, and sci-notation NLL
        text = "\n".join(p.read_text(errors="replace") for p in logs)
        self.loop_nlls = [
            float(m) for m in re.findall(r"fun:\s*(-?[\d.]+(?:[eE][+\-]?\d+)?)", text)
        ]

    # ------------------------------------------------------------------ helpers
    def fit_fracs(self, channel: int) -> tuple[np.ndarray, np.ndarray]:
        """Return (diagonal FF, diagonal FF error) for given channel."""
        if channel >= len(self.frac):
            return np.array([]), np.array([])
        return np.diag(self.frac[channel]), np.diag(self.frac_err[channel])

    def interference_sum(self, channel: int) -> float:
        """Sum of all elements in fit fraction matrix (should ≈ 1)."""
        if channel >= len(self.frac):
            return float("nan")
        return float(np.sum(self.frac[channel]))


# ── helpers ────────────────────────────────────────────────────────────────────

def _sniff_delimiter(path: Path) -> str:
    """Detect CSV delimiter from the first non-empty line."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            if "\t" in line:
                return "\t"
            if "," in line:
                return ","
            break
    return "\t"  # safe default
