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


# Canonical name fragments that identify f0(980) in state lists.
_F0980_KEYS = ("f0(980)", "f0980")


@dataclass
class JobData:
    name: str
    path: Path

    # Populated by load()
    status: FitStatus = field(default=None)
    params_value: dict = field(default_factory=dict)
    params_error: dict = field(default_factory=dict)
    init_params_value: dict = field(default_factory=dict)   # from init_params.json
    error_matrix: Optional[np.ndarray] = None
    frac: list[np.ndarray] = field(default_factory=list)    # [ch0_matrix, ch1_matrix]
    frac_err: list[np.ndarray] = field(default_factory=list)
    states: list[list[str]] = field(default_factory=list)   # [ch0_states, ch1_states]
    loop_nlls: list[float] = field(default_factory=list)    # per-loop NLL values
    loop_success: list[bool] = field(default_factory=list)  # per-loop convergence flag
    best_loop: Optional[int] = None                         # 1-indexed best loop number
    n_success_loops: int = 0                                # count of converged loops
    model_diff: dict = field(default_factory=dict)          # vs baseline
    # tag attached by discover_jobs when loaded from a scan sub-directory
    scan_tag: str = field(default="")

    @classmethod
    def load(cls, job_path: str | Path, scan_tag: str = "") -> "JobData":
        path = Path(job_path)
        job = cls(name=path.name, path=path, scan_tag=scan_tag)
        job._load_params()
        job._load_init_params()
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
        """Load fit fraction matrices, symmetrising the lower-triangular CSV."""
        self.frac, self.frac_err = [], []
        for ch in range(2):
            f_path  = self.path / f"fit_frac_channel{ch}.csv"
            fe_path = self.path / f"fit_frac_channel{ch}_err.csv"
            if not f_path.exists():
                continue
            delim = _sniff_delimiter(f_path)
            raw   = _read_lower_tri(f_path, delim)
            raw_e = (
                _read_lower_tri(fe_path, delim)
                if fe_path.exists() else np.zeros_like(raw)
            )
            # The CSVs are lower-triangular; symmetrise to full matrix.
            self.frac.append(_symmetrise(raw))
            self.frac_err.append(_symmetrise(raw_e))

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
        """Extract per-loop NLL and convergence status from all fit log files.

        Supports both ``slurm_logs/`` and ``condor_logs/`` directories.
        Parses scipy-style fit loop sections:
          ``========== Fit loop N/M ==========``
          ``  success: True``
          ``      fun: -12345.678``
        """
        logs_dir = None
        for candidate in ("slurm_logs", "condor_logs"):
            d = self.path / candidate
            if d.exists():
                logs_dir = d
                break
        if logs_dir is None:
            return
        logs = sorted(logs_dir.glob("*.out"))
        if not logs:
            return

        text = "\n".join(p.read_text(errors="replace") for p in logs)

        # Split text into per-loop sections using the header sentinel.
        sections = re.split(r"={3,}\s*Fit loop\s+\d+/\d+\s*={3,}", text)

        nlls: list[float] = []
        successes: list[bool] = []

        if len(sections) > 1:
            # sections[0] = preamble; sections[1:] = one section per loop
            for sec in sections[1:]:
                nll_m = re.search(
                    r"^\s*fun:\s*([+-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)", sec, re.M
                )
                suc_m = re.search(r"^\s*success:\s*(True|False)", sec, re.M | re.I)
                if nll_m:
                    nlls.append(float(nll_m.group(1)))
                if suc_m:
                    successes.append(suc_m.group(1).lower() == "true")
        else:
            # Fallback for logs without loop-header sentinels
            nlls = [
                float(m) for m in re.findall(
                    r"fun:\s*([+-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)", text
                )
            ]

        self.loop_nlls = nlls
        self.loop_success = successes
        self.n_success_loops = sum(successes) if successes else 0
        if nlls:
            self.best_loop = int(np.argmin(nlls)) + 1  # 1-indexed

    def _load_init_params(self):
        """Load initial parameter values from init_params.json (if present)."""
        init_path = self.path / "init_params.json"
        if not init_path.exists():
            return
        try:
            with open(init_path) as f:
                d = json.load(f)
            self.init_params_value = d.get("value", {})
        except (OSError, json.JSONDecodeError):
            pass

    # ------------------------------------------------------------------ slurm err
    def slurm_errors(self) -> list[dict]:
        """Parse all *.err files in slurm_logs/ and return structured issues.

        Each item is a dict with keys:
          severity  : 'fatal' | 'warn' | 'info'
          category  : short label, e.g. 'python_exception', 'matrix_not_pd', ...
          message   : representative first line or summary
          count     : number of occurrences in the file
          file      : filename (e.g. slurm_3543020.err)
        """
        logs_dir = self.path / "slurm_logs"
        if not logs_dir.exists():
            return []
        err_files = sorted(logs_dir.glob("*.err"))
        if not err_files:
            return []

        issues: list[dict] = []

        for err_path in err_files:
            try:
                text = err_path.read_text(errors="replace")
            except OSError:
                continue
            fname = err_path.name
            issues.extend(_parse_err_file(text, fname))

        return issues

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

    # ------------------------------------------------------------------ f0(980)
    def f0980_index(self, channel: int) -> int | None:
        """Return the index of f0(980) in *channel*'s state list, or None."""
        if channel >= len(self.states):
            return None
        for i, s in enumerate(self.states[channel]):
            sl = s.lower()
            if any(k in sl for k in _F0980_KEYS):
                return i
        return None

    def f0980_interference(self, channel: int) -> list[dict]:
        """Return interference FF entries for every component paired with f0(980).

        Each entry:
          {name, index, ff_self (diagonal), ff_interf, ff_interf_err,
           phase_deg (relative phase from production couplings, or None)}
        """
        idx_f0 = self.f0980_index(channel)
        if idx_f0 is None or channel >= len(self.frac):
            return []

        M    = self.frac[channel]
        M_e  = self.frac_err[channel]
        states = self.states[channel] if channel < len(self.states) else []
        n    = M.shape[0]

        # Production coupling vectors (complex) keyed by normalised resonance name
        prod = self._production_couplings(channel)

        result = []
        for j in range(n):
            if j == idx_f0:
                continue
            name  = states[j] if j < len(states) else f"comp{j}"
            ff_ij = float(M[idx_f0, j])
            fe_ij = float(M_e[idx_f0, j]) if M_e is not None else 0.0

            # Phase difference from production couplings (if available)
            phase_deg = _phase_diff_deg(prod, states[idx_f0] if idx_f0 < len(states) else "", name)

            result.append(dict(
                name        = name,
                index       = j,
                ff_self     = float(np.diag(M)[j]),
                ff_interf   = ff_ij,
                ff_interf_err = fe_ij,
                phase_deg   = phase_deg,
            ))

        return result

    def flatte_params(self) -> list[dict]:
        """Return Flatté coupling parameters with boundary-hit detection.

        Reads Resonances.yaml to compare fitted values against declared bounds.
        Returns list of {name, param, value, error, g_min, g_max, at_boundary}.
        """
        results = []
        res_yaml = self.path / "Resonances.yaml"
        bounds   = _parse_flatte_bounds(res_yaml)

        for pname, pval in self.params_value.items():
            # Match Flatté coupling params: ends with _g_0 or _g_1 (not _g_ls_*)
            if not re.search(r"_g_[01]$", pname):
                continue
            perr = self.params_error.get(pname, 0.0)

            # Derive resonance key from param name (strip trailing _g_0 / _g_1)
            res_key = re.sub(r"_g_[01]$", "", pname)
            b       = bounds.get(res_key, {})
            g_min   = b.get("g_min")
            g_max   = b.get("g_max")

            at_boundary = False
            if g_min is not None and abs(pval - g_min) < 1e-4:
                at_boundary = True
            if g_max is not None and abs(pval - g_max) < 1e-4:
                at_boundary = True
            # Machine-precision error is a strong signal of boundary hit
            if abs(perr) < 1e-10 and perr != 0:
                at_boundary = True

            results.append(dict(
                name        = res_key,
                param       = pname,
                value       = float(pval),
                error       = float(perr),
                g_min       = g_min,
                g_max       = g_max,
                at_boundary = at_boundary,
            ))
        return results

    def _production_couplings(self, channel: int) -> dict[str, complex]:
        """Extract production amplitude complex coefficients from params.

        Looks for parameters named like:
          Jpsi->phi.<Res><Res>->pip.pim_total_0r / _total_0i
          Jpsi->phi.<Res><Res>->kp.km_total_0r  / _total_0i
        Returns {normalised_res_name: complex_coeff}.
        """
        suffix_r = re.compile(r"_total_0r$")
        suffix_i = re.compile(r"_total_0i$")
        reals: dict[str, float] = {}
        imags: dict[str, float] = {}

        for k, v in self.params_value.items():
            if suffix_r.search(k):
                key = suffix_r.sub("", k)
                reals[key] = float(v)
            elif suffix_i.search(k):
                key = suffix_i.sub("", k)
                imags[key] = float(v)

        out: dict[str, complex] = {}
        for key in reals:
            out[key] = complex(reals[key], imags.get(key, 0.0))
        return out


# ── module-level helpers ────────────────────────────────────────────────────────

def _read_lower_tri(path: Path, delim: str) -> np.ndarray:
    """Read a ragged lower-triangular CSV into a square numpy array.

    Each row i has exactly i+1 values (lower-triangle including diagonal).
    The upper triangle is left as zero; call _symmetrise() afterwards.
    """
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        vals = [float(x) for x in line.split(delim) if x.strip()]
        if vals:
            rows.append(vals)
    n = len(rows)
    M = np.zeros((n, n))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if j < n:
                M[i, j] = v

    return M


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


def _symmetrise(arr: np.ndarray) -> np.ndarray:
    """Return a symmetric matrix from a lower-triangular one.

    The CSV files store a lower-triangular matrix (upper triangle = 0).
    We add the transpose and subtract the diagonal to avoid double-counting.

    If the upper triangle is already non-zero the matrix is assumed to be a
    full symmetric matrix and is returned as-is to avoid doubling the
    off-diagonal elements, which would corrupt interference fractions.
    """
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        return arr
    if arr.shape[0] > 1 and np.any(np.triu(arr, k=1) != 0):
        import warnings
        warnings.warn(
            "_symmetrise: upper triangle is non-zero – CSV appears to be a "
            "full matrix already; returning as-is to avoid doubling "
            "off-diagonal elements.",
            stacklevel=2,
        )
        return arr
    return arr + arr.T - np.diag(np.diag(arr))


def _phase_diff_deg(
    prod: dict[str, complex],
    name_a: str,
    name_b: str,
) -> float | None:
    """Compute phase difference (degrees) between two production amplitudes.

    Normalises both the resonance name and the production-coupling key to
    alphanumeric-only lowercase for fuzzy matching, allowing for differences
    in separators (underscores, dots, arrows, charge symbols such as +/-).
    Returns None when either amplitude is not found.
    """
    _alnum = re.compile(r"[^a-z0-9]")

    def _clean(s: str) -> str:
        return _alnum.sub("", s.lower().replace("_flatte", "").replace("_e791", ""))

    def _find(name: str) -> complex | None:
        needle = _clean(name)
        if not needle:
            return None
        for k, v in prod.items():
            if needle in _clean(k):
                return v
        return None

    ca = _find(name_a)
    cb = _find(name_b)
    if ca is None or cb is None:
        return None
    import cmath
    pa = cmath.phase(ca)
    pb = cmath.phase(cb)
    diff = (pa - pb) * 180.0 / 3.14159265358979
    while diff >  180: diff -= 360
    while diff <= -180: diff += 360
    return round(diff, 1)


def _parse_flatte_bounds(yaml_path: Path) -> dict[str, dict]:
    """Parse Resonances.yaml to extract g_min / g_max for Flatté resonances.

    Returns {res_name: {g_min: float, g_max: float}}.
    No yaml dependency – plain text parsing.
    """
    bounds: dict[str, dict] = {}
    if not yaml_path.exists():
        return bounds

    current_res = None
    for line in yaml_path.read_text().splitlines():
        stripped = line.strip()
        # Top-level resonance name (2-space indent key or no indent)
        m = re.match(r"^(\S[^:]+):\s*$", stripped)
        if m and not stripped.startswith("-"):
            current_res = m.group(1).strip()
            bounds.setdefault(current_res, {})
            continue
        if current_res is None:
            continue
        for key in ("g_min", "g_max"):
            m2 = re.match(rf"^\s*{key}\s*:\s*(.+)$", line)
            if m2:
                try:
                    bounds[current_res][key] = float(m2.group(1).strip())
                except ValueError:
                    pass
    return bounds


# ── slurm err file parser ──────────────────────────────────────────────────────

# Patterns for FATAL issues (Python exceptions / SLURM termination)
_ERR_FATAL_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("python_exception",  "Python 异常回溯",
     re.compile(r"^Traceback \(most recent call last\)", re.M)),
    ("runtime_error",     "RuntimeError",
     re.compile(r"\bRuntimeError\b")),
    ("value_error",       "ValueError",
     re.compile(r"\bValueError\b")),
    ("memory_error",      "内存错误",
     re.compile(r"\bMemoryError\b|\bOOM\b|out of memory", re.I)),
    ("slurm_killed",      "SLURM 节点终止作业",
     re.compile(r"slurmstepd: error:|DUE TO TIME LIMIT|Killed\b", re.I)),
    ("cuda_error",        "CUDA 错误",
     re.compile(r"CUDA error:|cudaError|NCCL error", re.I)),
    ("nan_inf",           "NaN / Inf 溢出",
     re.compile(r"\bnan\b|\binf\b", re.I)),
]

# Patterns for WARN issues (fit quality / configuration)
_ERR_WARN_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("matrix_not_pd",     "协方差矩阵非正定",
     re.compile(r"matrix is not positive definited", re.I)),
    ("matrix_forced_pd",  "Hessian 含负本征值（强制正定）",
     re.compile(r"Matrix forced pos-def by adding", re.I)),
    ("bound_overwrite",   "参数边界被覆写",
     re.compile(r"Overwrite bound of (.+?)!", re.I)),
    ("no_phsp_noeff",     "缺少 phsp_noeff 文件，使用 phsp 替代",
     re.compile(r"No data file as 'phsp_noeff'", re.I)),
    ("hesse_fail",        "Hesse 矩阵计算失败",
     re.compile(r"Hesse is not valid|hesse.*failed|Valid.*False", re.I)),
    ("unknown_model",     "振幅模型未识别，使用默认替代",
     re.compile(r"No model named .+? found, use default instead", re.I)),
]

# Patterns that are INFO-level (ignorable in most cases)
_ERR_INFO_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("param_not_found",   "参数初始化时未找到（可忽略）",
     re.compile(r"UserWarning: .+ not found")),
    ("neglect_params",    "参数设置时忽略部分键",
     re.compile(r"Neglect \[.+?\] when setting params", re.I)),
    ("ambiguous_decay",   "发现多个衰变分支（取第一个）",
     re.compile(r"\d+ decays find for", re.I)),
    ("no_width_constant", "共振宽度未设置，视为稳定（非共振项正常）",
     re.compile(r"No width provided for .+?, set it to constant", re.I)),
    ("tf_info",           "TensorFlow 初始化信息",
     re.compile(r"I tensorflow/|oneDNN custom operations")),
]


def _parse_err_file(text: str, fname: str) -> list[dict]:
    """Parse one .err file and return a list of structured issue dicts."""
    results: list[dict] = []
    lines = text.splitlines()

    # ── FATAL ──────────────────────────────────────────────────────────────
    for category, label, pat in _ERR_FATAL_PATTERNS:
        matches = pat.findall(text)
        if matches:
            # Grab the line context for the first match
            m = pat.search(text)
            first_line = text[max(0, m.start() - 0):].splitlines()[0][:120]
            results.append(dict(
                severity="fatal", category=category,
                message=first_line, count=len(matches), file=fname,
                label=label,
            ))

    # ── WARN ───────────────────────────────────────────────────────────────
    for category, label, pat in _ERR_WARN_PATTERNS:
        matches = pat.findall(text)
        if matches:
            m = pat.search(text)
            first_line = text[max(0, m.start()):].splitlines()[0][:120]
            if category == "bound_overwrite":
                # Collect unique parameter names
                names = sorted(set(matches))
                msg = f"覆写边界参数 ({len(names)} 个): " + ", ".join(names[:5])
                if len(names) > 5:
                    msg += f" … (+{len(names)-5})"
                results.append(dict(
                    severity="warn", category=category,
                    message=msg, count=len(matches), file=fname,
                    label=label,
                ))
            else:
                results.append(dict(
                    severity="warn", category=category,
                    message=first_line, count=len(matches), file=fname,
                    label=label,
                ))

    # ── INFO ───────────────────────────────────────────────────────────────
    for category, label, pat in _ERR_INFO_PATTERNS:
        matches = pat.findall(text)
        if matches:
            results.append(dict(
                severity="info", category=category,
                message=f"{label} ({len(matches)} 次)",
                count=len(matches), file=fname,
                label=label,
            ))

    return results
