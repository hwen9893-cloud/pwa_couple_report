"""HTML report generator for the φhh amplitude analysis evaluation framework.

Generates a self-contained ``report.html`` at ``out_dir/report.html``.
Plots are referenced via relative paths (``plots/<name>.png``) so the file
can be opened directly in any browser from the output directory.

Design: modern editorial / cinematic minimal (Apple × Awwwards × Notion).
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── constants ─────────────────────────────────────────────────────────────────

_STATUS_ICON  = {"ok": "✓", "warn": "⚠", "fail": "✗"}
_STATUS_LABEL = {"ok": "正常", "warn": "警告", "fail": "失败"}

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_PRIORITY_COLOR = {"P0": "#ef4444", "P1": "#f59e0b", "P2": "#3b82f6"}

# Physical parameters that identify f-state resonances (mass / width / Flatté)
_F_STATE_PAT = re.compile(
    r"^(f0\(|f2\(|f0_|f2_|sigma|rho\(|K\d?\().*?(mass|width|g_[01]$)",
    re.I,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _badge(status: str) -> str:
    icon = _STATUS_ICON.get(status, "?")
    label = _STATUS_LABEL.get(status, status)
    return f'<span class="badge badge-{status}">{icon} {label}</span>'


def _overall_status(check_results: dict) -> str:
    worst = "ok"
    for v in check_results.values():
        items = v if isinstance(v, list) else [v]
        for item in items:
            s = item.get("status", "ok")
            if s == "fail":
                return "fail"
            if s == "warn":
                worst = "warn"
    return worst


def _img(path: Optional[Path], out_dir: Path, alt: str = "", caption: str = "") -> str:
    """Return a gallery-card <figure> with lazy-load and lightbox trigger."""
    if path is None or not path.exists():
        return f'<div class="missing-plot">图表未生成：{alt or "—"}</div>'
    try:
        rel = path.relative_to(out_dir)
        src = str(rel).replace("\\", "/")
    except ValueError:
        src = str(path)
    cap = caption or alt
    return (
        f'<figure class="img-card" data-src="{src}" data-caption="{cap}" '
        f'onclick="openLightbox(this)">'
        f'<div class="img-skeleton"></div>'
        f'<img src="{src}" alt="{alt}" loading="lazy" '
        f'onload="this.previousElementSibling.style.display=\'none\';this.style.opacity=1" '
        f'style="opacity:0;transition:opacity .4s ease;" />'
        f'<figcaption>{cap}</figcaption>'
        f'</figure>'
    )


def _fmt_nll(nll: float) -> str:
    return f"{nll:.4f}" if math.isfinite(nll) else "NaN"


def _fmt_float(x, digits: int = 4) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
        return f"{v:.{digits}f}" if math.isfinite(v) else "NaN"
    except (TypeError, ValueError):
        return str(x)


def _fmt_param(val, err=None) -> str:
    """Format a parameter value ± error (unified tabular display).

    • Has error  → '<val> ± <err>'
    • No error   → '<val> ± none'
    All values formatted to 3 decimal places.
    """
    if val is None:
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if not math.isfinite(v):
        return "NaN"
    v_str = f"{v:.3f}"
    if err is not None:
        try:
            e = float(err)
            if math.isfinite(e) and e > 0:
                return f"{v_str} <span class='pv-err'>± {e:.3f}</span>"
        except (TypeError, ValueError):
            pass
    return f"{v_str} <span class='pv-none'>± none</span>"


def _section_id(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:40]


def _is_f_state_param(name: str) -> bool:
    """Return True for resonance physical parameters (mass / width / g coupling)."""
    nl = name.lower()
    has_resonance = any(k in nl for k in (
        "f0(", "f2(", "f0_flatte", "f2_flatte", "f0(500", "f0(980", "f0(1370",
        "f0(1500", "f0(1710", "f0(1770", "f2(1270", "f2(1430", "f2(1525",
        "f2(1565", "f2(1810", "f2(1950", "rho(1450", "rho(1570", "rho(1690",
    ))
    has_type = any(k in nl for k in ("_mass", "_width", "_g_0", "_g_1"))
    return has_resonance and has_type


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
/* ════════════════════════════════════════
   Design tokens
   ════════════════════════════════════════ */
:root {
  /* Palette */
  --bg:         #f9f9f9;
  --surface:    #ffffff;
  --surface-2:  #f3f4f6;
  --border:     #e5e7eb;
  --text:       #111827;
  --text-2:     #4b5563;
  --text-3:     #9ca3af;
  --accent:     #1e3a5f;
  --accent-2:   #2563eb;
  --ok:         #16a34a;
  --warn:       #d97706;
  --fail:       #dc2626;

  /* Spacing */
  --r-sm:  8px;
  --r-md:  14px;
  --r-lg:  20px;
  --r-xl:  28px;

  /* Shadow */
  --sh-sm: 0 1px 4px rgba(0,0,0,.06);
  --sh-md: 0 4px 16px rgba(0,0,0,.08);
  --sh-lg: 0 12px 40px rgba(0,0,0,.12);
}

/* ════════════════════════════════════════
   Reset & base
   ════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI",
               Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent-2); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ════════════════════════════════════════
   Page layout
   ════════════════════════════════════════ */
#layout { display: flex; min-height: 100vh; }

/* ── Sidebar ── */
#sidebar {
  width: 240px; min-width: 240px;
  background: var(--accent);
  color: #e2e8f0;
  position: sticky; top: 0; height: 100vh;
  overflow-y: auto; overflow-x: hidden;
  display: flex; flex-direction: column;
  padding-bottom: 24px;
  z-index: 100;
}
.sidebar-brand {
  padding: 28px 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,.12);
  margin-bottom: 8px;
}
.sidebar-brand .brand-title {
  font-size: 17px; font-weight: 700; color: #fff;
  letter-spacing: -.3px; line-height: 1.3;
}
.sidebar-brand .brand-sub {
  font-size: 11px; color: rgba(255,255,255,.45);
  margin-top: 4px; letter-spacing: .4px; text-transform: uppercase;
}
.sidebar-section { padding: 16px 0 0; }
.sidebar-section-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1px;
  text-transform: uppercase; color: rgba(255,255,255,.35);
  padding: 0 20px 6px;
}
#sidebar a {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 20px; color: rgba(255,255,255,.65);
  font-size: 13px; font-weight: 500;
  border-left: 3px solid transparent;
  transition: all .2s ease;
}
#sidebar a:hover, #sidebar a.active {
  background: rgba(255,255,255,.08);
  color: #fff;
  border-left-color: #60a5fa;
  text-decoration: none;
}
#sidebar a .nav-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; opacity: .4; flex-shrink: 0;
}

/* ── Main content ── */
#content {
  flex: 1; min-width: 0;
  padding: 0 0 60px;
}

/* ════════════════════════════════════════
   Hero
   ════════════════════════════════════════ */
.hero {
  background: linear-gradient(135deg, #0f1f3d 0%, #1e3a5f 50%, #1e40af 100%);
  color: #fff;
  padding: 52px 48px 44px;
  position: relative;
  overflow: hidden;
}
.hero::before {
  content: "";
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 70% 50%, rgba(96,165,250,.15) 0%, transparent 70%);
  pointer-events: none;
}
.hero-eyebrow {
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: rgba(255,255,255,.5);
  margin-bottom: 12px;
}
.hero-title {
  font-size: 32px; font-weight: 700; letter-spacing: -.5px;
  line-height: 1.2; color: #fff;
  margin-bottom: 16px;
}
.hero-meta {
  display: flex; flex-wrap: wrap; gap: 24px;
  margin-top: 24px;
}
.hero-stat {
  display: flex; flex-direction: column; gap: 2px;
}
.hero-stat .stat-val {
  font-size: 26px; font-weight: 700; color: #fff;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.hero-stat .stat-label {
  font-size: 11px; color: rgba(255,255,255,.5);
  letter-spacing: .5px; text-transform: uppercase;
}
.hero-divider {
  width: 1px; height: 40px; background: rgba(255,255,255,.15);
  align-self: center;
}
.hero-badge {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(34,197,94,.2); color: #86efac;
  border: 1px solid rgba(34,197,94,.3);
  border-radius: 20px; padding: 4px 12px;
  font-size: 12px; font-weight: 600;
  margin-top: 16px;
}
.hero-badge.fail {
  background: rgba(239,68,68,.2); color: #fca5a5;
  border-color: rgba(239,68,68,.3);
}

/* ════════════════════════════════════════
   Content area padding
   ════════════════════════════════════════ */
.content-inner { padding: 40px 48px; }

/* ════════════════════════════════════════
   Sections
   ════════════════════════════════════════ */
.section { margin-bottom: 52px; }
.section-header {
  display: flex; align-items: baseline; gap: 12px;
  margin-bottom: 24px;
}
.section-title {
  font-size: 22px; font-weight: 700; letter-spacing: -.4px;
  color: var(--text);
}
.section-subtitle {
  font-size: 13px; color: var(--text-3);
}
.section-divider {
  height: 1px; background: var(--border);
  margin: 0 0 24px;
}

/* ════════════════════════════════════════
   Cards
   ════════════════════════════════════════ */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 24px;
  margin-bottom: 16px;
  box-shadow: var(--sh-sm);
  transition: box-shadow .2s ease;
}
.card:hover { box-shadow: var(--sh-md); }
.card-title {
  font-size: 15px; font-weight: 700;
  color: var(--text); margin-bottom: 16px;
}

/* ════════════════════════════════════════
   Stat cards row
   ════════════════════════════════════════ */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px; margin-bottom: 32px;
}
.stat-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-md); padding: 20px;
  box-shadow: var(--sh-sm);
  display: flex; flex-direction: column; gap: 4px;
}
.stat-card .sc-val {
  font-size: 28px; font-weight: 700;
  color: var(--text); font-variant-numeric: tabular-nums;
  letter-spacing: -.5px; line-height: 1;
}
.stat-card .sc-label {
  font-size: 11px; color: var(--text-3);
  text-transform: uppercase; letter-spacing: .6px;
}
.stat-card .sc-sub {
  font-size: 12px; color: var(--text-2);
  margin-top: 4px;
}

/* ════════════════════════════════════════
   Badges
   ════════════════════════════════════════ */
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 700; white-space: nowrap;
}
.badge-ok   { background: #dcfce7; color: var(--ok); }
.badge-warn { background: #fef9c3; color: var(--warn); }
.badge-fail { background: #fee2e2; color: var(--fail); }

/* ════════════════════════════════════════
   Tables
   ════════════════════════════════════════ */
.table-wrap { overflow-x: auto; border-radius: var(--r-md); border: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
  background: var(--surface-2); color: var(--text-2);
  text-align: left; padding: 11px 14px;
  font-size: 11px; font-weight: 700; letter-spacing: .6px; text-transform: uppercase;
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
tbody td { padding: 10px 14px; border-bottom: 1px solid #f3f4f6; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: #f8faff; }
tr.best-row td { background: #f0fdf4; }
tr.best-row td:first-child { border-left: 3px solid var(--ok); }
tr.fail-row td { background: #fff5f5; }
tr.warn-row td { background: #fffbeb; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.err { color: var(--text-3); font-size: .9em; }

/* ════════════════════════════════════════
   Check items
   ════════════════════════════════════════ */
.check-list { list-style: none; }
.check-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 9px 0; border-bottom: 1px solid #f3f4f6;
}
.check-item:last-child { border-bottom: none; }
.check-icon { font-size: 14px; min-width: 18px; margin-top: 1px; }
.check-icon.ok   { color: var(--ok); }
.check-icon.warn { color: var(--warn); }
.check-icon.fail { color: var(--fail); }
.check-name  { font-weight: 600; font-size: 11px; color: var(--text-3); text-transform: uppercase; letter-spacing: .4px; }
.check-msg   { font-size: 13px; color: var(--text); margin-top: 2px; }

/* ════════════════════════════════════════
   Suggestions
   ════════════════════════════════════════ */
.sugg-item {
  border-left: 3px solid #e5e7eb;
  padding: 12px 16px; margin-bottom: 10px;
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  background: var(--surface-2);
  transition: box-shadow .2s;
}
.sugg-item:hover { box-shadow: var(--sh-sm); }
.sugg-P0 { border-color: var(--fail); background: #fff5f5; }
.sugg-P1 { border-color: var(--warn); background: #fffbeb; }
.sugg-P2 { border-color: var(--accent-2); background: #eff6ff; }
.sugg-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.sugg-priority { font-weight: 800; font-size: 11px; padding: 2px 8px;
  border-radius: 4px; }
.sugg-P0 .sugg-priority { background: #fee2e2; color: var(--fail); }
.sugg-P1 .sugg-priority { background: #fef3c7; color: var(--warn); }
.sugg-P2 .sugg-priority { background: #dbeafe; color: var(--accent-2); }
.sugg-category { font-size: 11px; color: var(--text-3); padding: 2px 8px;
  background: rgba(0,0,0,.05); border-radius: 4px; }
.sugg-action { font-weight: 600; font-size: 13px; }
.sugg-reason { font-size: 12px; color: var(--text-2); margin-top: 4px; }
.sugg-formula { font-size: 11px; color: #555; margin-top: 4px;
  font-family: "SF Mono", "Fira Code", "Courier New", monospace; }

/* ════════════════════════════════════════
   Gallery / Bento grid
   ════════════════════════════════════════ */
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}
.img-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  overflow: hidden;
  cursor: zoom-in;
  box-shadow: var(--sh-sm);
  transition: transform .3s cubic-bezier(.25,.46,.45,.94),
              box-shadow .3s ease;
  position: relative;
}
.img-card:hover {
  transform: translateY(-4px) scale(1.01);
  box-shadow: var(--sh-lg);
}
.img-card:hover img { filter: none; }
.img-card:hover figcaption { opacity: 1; transform: translateY(0); }
.img-card img {
  width: 100%; display: block;
  filter: brightness(.98);
  transition: filter .3s ease;
}
.img-card figcaption {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,.7));
  color: #fff; font-size: 12px; font-weight: 600;
  padding: 32px 14px 12px;
  opacity: 0; transform: translateY(6px);
  transition: opacity .3s ease, transform .3s ease;
}
.img-skeleton {
  width: 100%; aspect-ratio: 4/3;
  background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Slideshow sub-grid */
.img-card-group {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-lg); overflow: hidden; box-shadow: var(--sh-sm);
}
.img-card-group-label {
  padding: 14px 18px; font-size: 13px; font-weight: 700;
  background: var(--surface-2); border-bottom: 1px solid var(--border);
  color: var(--text);
}
.img-card-group-body {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 2px; padding: 2px;
}
.img-card-group-body .img-card {
  border-radius: 0; border: none; box-shadow: none; margin: 0;
}

/* ════════════════════════════════════════
   Loop status indicator
   ════════════════════════════════════════ */
.loop-bar {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-top: 4px;
}
.loop-dot {
  width: 10px; height: 10px; border-radius: 2px;
  display: inline-block;
}
.loop-dot.ok   { background: #86efac; }
.loop-dot.fail { background: #fca5a5; }
.loop-dot.best { background: #fbbf24; box-shadow: 0 0 4px #fbbf24; }

/* ════════════════════════════════════════
   Scan significance  (HEP / CERN style)
   ════════════════════════════════════════ */
.sigma-high  { color: var(--ok);   font-weight: 800; letter-spacing: -.3px; }
.sigma-mid   { color: var(--warn); font-weight: 700; }
.sigma-low   { color: var(--fail); font-weight: 600; }

/* Scrollable scan table wrapper */
.scan-table-outer {
  overflow-x: auto;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  box-shadow: var(--sh-sm);
  margin-top: 4px;
}

/* Scan table */
.scan-table {
  width: 100%; border-collapse: collapse;
  font-size: 14.5px;
  font-variant-numeric: tabular-nums;
  min-width: 860px;
}

/* Sticky header */
.scan-table thead th {
  position: sticky; top: 0; z-index: 2;
  background: linear-gradient(180deg, #1e3a5f 0%, #1e40af 100%);
  color: #fff; font-weight: 700;
  padding: 13px 16px;
  font-size: 12px; letter-spacing: .5px; text-transform: uppercase;
  border-bottom: 2px solid #3b82f6; white-space: nowrap;
  text-align: left;
}
.scan-table thead th.num { text-align: right; }

/* Body rows */
.scan-table tbody tr { transition: background .12s ease; }
.scan-table tbody tr:nth-child(even) { background: #f8faff; }
.scan-table tbody tr:nth-child(odd)  { background: #ffffff; }
.scan-table tbody tr:hover td { background: #eef4ff !important; }
.scan-table tbody tr.best-row td { background: #f0fdf4; }
.scan-table tbody tr.best-row:hover td { background: #dcfce7 !important; }

.scan-table td {
  padding: 11px 16px;
  border-bottom: 1px solid #f1f5f9;
  font-size: 14px;
  vertical-align: middle;
  line-height: 1.5;
}
.scan-table td.num { text-align: right; font-size: 14px; }
.scan-table td:first-child { white-space: nowrap; }

/* Fail-details collapsible block */
.fail-details-toggle {
  display: flex; align-items: center; gap: 10px;
  width: 100%; background: none; border: none;
  padding: 12px 18px; cursor: pointer;
  color: var(--text-2); font-size: 13px; font-weight: 600;
  border-top: 1px solid var(--border);
  transition: background .15s ease, color .15s ease;
  text-align: left;
}
.fail-details-toggle:hover {
  background: rgba(37,99,235,.05); color: var(--accent-2);
}
.fail-details-toggle:focus-visible {
  outline: 2px solid var(--accent-2); outline-offset: -2px;
}
.fail-details-toggle .fdt-icon { font-size: 15px; flex-shrink: 0; }
.fail-details-toggle .fdt-chevron {
  margin-left: auto; font-size: 12px; color: var(--text-3);
  transition: transform .2s ease;
}
.fail-details-toggle[aria-expanded="true"] .fdt-chevron { transform: rotate(180deg); }
.fail-details-toggle .fdt-hint {
  font-size: 11px; color: var(--text-3); font-weight: 400; margin-left: 4px;
}

.fail-details-body {
  overflow: hidden;
  max-height: 0;
  transition: max-height .22s ease, opacity .2s ease;
  opacity: 0;
}
.fail-details-body.open {
  max-height: 2000px;
  opacity: 1;
}
.fail-details-inner {
  background: linear-gradient(135deg, #f8faff 0%, #f0fdf4 100%);
  border-top: 1px solid var(--border);
  padding: 18px 22px 20px;
}
.fail-details-inner h4 {
  font-size: 12px; font-weight: 700; letter-spacing: .7px;
  text-transform: uppercase; color: var(--text-2);
  margin-bottom: 14px;
}
.fail-conditions-list {
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: 8px;
}
.fail-conditions-list li {
  display: flex; align-items: flex-start; gap: 10px;
  font-size: 13px; line-height: 1.55; color: var(--text);
}
.fail-conditions-list li .fc-num {
  flex-shrink: 0; width: 22px; height: 22px;
  background: var(--accent); color: #fff;
  border-radius: 50%; font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  margin-top: 1px;
}
.fail-conditions-list li .fc-name {
  font-weight: 700; color: var(--fail); margin-right: 5px;
}
.fail-conditions-list li .fc-cond {
  color: var(--text-2);
}

/* ════════════════════════════════════════
   Misc utilities
   ════════════════════════════════════════ */
.meta { font-size: 12px; color: var(--text-3); margin-bottom: 16px; }
.tag-best {
  font-size: 10px; background: var(--ok); color: #fff;
  border-radius: 4px; padding: 1px 6px; margin-left: 6px;
  font-weight: 700; letter-spacing: .3px;
}
.tag-questionable {
  font-size: 10px; background: #e67e22; color: #fff;
  border-radius: 4px; padding: 1px 6px; margin-left: 6px;
  font-weight: 700; letter-spacing: .3px;
}
.tag-aic { background: var(--accent-2); }
.empty-state { color: var(--text-3); font-style: italic; padding: 12px 0; }
code {
  background: var(--surface-2); padding: 2px 6px; border-radius: 4px;
  font-family: "SF Mono", "Fira Code", "Courier New", monospace; font-size: 12px;
}
.collapsible { cursor: pointer; user-select: none; }
.collapsible::after { content: " ▾"; font-size: 11px; color: var(--text-3); }
.collapsible.open::after { content: " ▴"; }
.collapse-body { display: none; }
.collapse-body.open { display: block; }

/* ════════════════════════════════════════
   Param comparison table (redesigned)
   ════════════════════════════════════════ */

/* Info card above table */
.param-info-card {
  display: flex; align-items: flex-start; gap: 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
  border: 1px solid #bfdbfe; border-radius: var(--r-md);
  padding: 14px 18px; margin-bottom: 20px;
  font-size: 12.5px; color: var(--text-2);
}
.param-info-card .pic-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
.param-info-card b { color: var(--text); }
.param-info-card code {
  background: rgba(37,99,235,.08); color: var(--accent-2);
  border-radius: 4px; padding: 1px 5px; font-size: 11.5px;
}

/* Wrapper */
.param-table-wrap {
  overflow-x: auto;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  box-shadow: var(--sh-sm);
}

/* Table base */
.param-table {
  width: 100%; border-collapse: collapse;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
}

/* Header rows */
.param-table thead tr:first-child th {
  background: linear-gradient(180deg, #1e3a5f 0%, #1e40af 100%);
  color: #fff; font-weight: 700;
  padding: 12px 14px; text-align: center;
  font-size: 11px; letter-spacing: .5px; text-transform: uppercase;
  border-bottom: none; white-space: nowrap;
}
.param-table thead tr:first-child th:first-child {
  text-align: left; min-width: 200px;
}
.param-table thead tr:nth-child(2) th {
  background: #1e3a8a; color: rgba(255,255,255,.75);
  font-size: 10px; font-weight: 600; text-align: right;
  padding: 7px 14px; border-bottom: 2px solid #3b82f6;
  letter-spacing: .3px;
}
.param-table thead tr:nth-child(2) th:first-child { text-align: left; }

/* Best column header badge */
.th-best-badge {
  display: inline-flex; align-items: center; gap: 4px;
  background: rgba(34,197,94,.25); color: #86efac;
  border: 1px solid rgba(34,197,94,.35);
  border-radius: 10px; padding: 2px 8px;
  font-size: 10px; font-weight: 700;
  margin-left: 6px; vertical-align: middle;
}

/* Column header helpers */
.pt-name-hdr {
  text-align: left !important; min-width: 200px;
  background: linear-gradient(180deg, #1e3a5f 0%, #1e40af 100%) !important;
}
.pt-job-hdr {
  background: linear-gradient(180deg, #1e3a5f 0%, #1e40af 100%);
  color: #fff; font-weight: 700; text-align: center;
  padding: 12px 14px; font-size: 11px; letter-spacing: .4px;
  white-space: nowrap; border-left: 1px solid rgba(255,255,255,.12);
}
.pt-best-hdr {
  background: linear-gradient(180deg, #14532d 0%, #166534 100%) !important;
  border-left: 2px solid #22c55e !important;
}
.pt-sub-hdr {
  background: #1e3a8a; color: rgba(255,255,255,.75);
  font-size: 10px; font-weight: 600; text-align: right;
  padding: 7px 14px; border-bottom: 2px solid #3b82f6;
  border-left: 1px solid rgba(255,255,255,.1);
}
.pt-sub-hdr.pt-best-hdr {
  background: #14532d !important; border-bottom-color: #22c55e !important;
}

/* Body rows */
.param-table tbody tr:nth-child(even) { background: #f8faff; }
.param-table tbody tr:nth-child(odd)  { background: #ffffff; }
.param-table tbody tr:hover td { background: #eef4ff !important; }

.param-table td {
  padding: 9px 14px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}
.param-table td:first-child {
  font-family: 'SF Mono', 'JetBrains Mono', 'Courier New', monospace;
  font-size: 11.5px; color: var(--text); font-weight: 500;
  min-width: 200px; white-space: nowrap;
  border-right: 1px solid #e2e8f0;
}
.param-table td.pv-cell {
  text-align: right; min-width: 160px;
}

/* Value display */
.pv-val {
  font-weight: 600; color: var(--text);
  font-size: 12.5px;
}
.pv-err {
  color: var(--text-3); font-size: 11px; margin-left: 2px;
}
.pv-none {
  color: var(--text-3); font-size: 11px; font-style: italic; margin-left: 2px;
}
.pv-missing { color: var(--text-3); font-style: italic; }

/* Init column: lighter tone */
.pv-init-col {
  color: var(--text-2);
  font-size: 12px;
  border-right: 1px dashed #e2e8f0;
}

/* Diff highlight: value changed from best */
.pv-diff td.pv-cell { background: #fffbeb !important; }
.pv-diff td.pv-cell .pv-val { color: #b45309; }

/* Best column highlight */
.pv-best-col { border-left: 2px solid #22c55e !important; }
.pv-best-col .pv-val { color: #15803d; }

/* Tooltip */
.pv-tip {
  position: relative; display: inline-block;
}
.pv-tip:hover .pv-tip-box { display: block; }
.pv-tip-box {
  display: none; position: absolute; bottom: calc(100% + 6px); right: 0;
  background: #1e293b; color: #e2e8f0;
  border-radius: 8px; padding: 8px 12px; width: 220px;
  font-size: 11px; line-height: 1.7; z-index: 200;
  box-shadow: 0 8px 24px rgba(0,0,0,.25);
  white-space: normal; text-align: left;
  font-variant-numeric: tabular-nums;
}
.pv-tip-box::after {
  content: ""; position: absolute; top: 100%; right: 16px;
  border: 6px solid transparent; border-top-color: #1e293b;
}
.pv-tip-label { color: #94a3b8; font-size: 10px; text-transform: uppercase;
  letter-spacing: .6px; margin-bottom: 2px; }

/* Param highlight (legacy kept for compat) */
.param-init    { color: var(--text-3); }
.param-final   { color: var(--text); font-weight: 600; }
.param-changed { color: var(--accent-2); }

/* ════════════════════════════════════════
   Lightbox
   ════════════════════════════════════════ */
.lb-overlay {
  display: none; position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.88);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  align-items: center; justify-content: center;
  animation: lb-in .25s ease;
}
.lb-overlay.open { display: flex; }
@keyframes lb-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.lb-inner {
  position: relative; max-width: 90vw; max-height: 90vh;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  animation: lb-scale .25s cubic-bezier(.25,.46,.45,.94);
}
@keyframes lb-scale {
  from { transform: scale(.95); opacity: 0; }
  to   { transform: scale(1);   opacity: 1; }
}
.lb-inner img {
  max-width: 90vw; max-height: 80vh;
  border-radius: var(--r-lg); object-fit: contain;
  box-shadow: 0 32px 80px rgba(0,0,0,.6);
}
.lb-caption {
  color: rgba(255,255,255,.75); font-size: 13px; font-weight: 600;
  text-align: center; max-width: 600px; letter-spacing: .3px;
}
.lb-close {
  position: absolute; top: -44px; right: 0;
  background: rgba(255,255,255,.15); border: none;
  color: #fff; font-size: 18px; width: 36px; height: 36px;
  border-radius: 50%; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  transition: background .2s;
}
.lb-close:hover { background: rgba(255,255,255,.3); }
.lb-nav {
  position: fixed; top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,.12); border: none;
  color: #fff; font-size: 28px; width: 48px; height: 64px;
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .2s;
  z-index: 10000;
}
.lb-nav:hover { background: rgba(255,255,255,.25); }
.lb-prev { left: 12px; }
.lb-next { right: 12px; }

/* ════════════════════════════════════════
   Scrollbar
   ════════════════════════════════════════ */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #9ca3af; }

/* ════════════════════════════════════════
   Gallery tabs (分析图表)
   ════════════════════════════════════════ */
.gallery-tab-bar {
  display: flex; gap: 0; margin-bottom: 20px;
  border-bottom: 2px solid var(--border);
}
.gallery-tab-btn {
  padding: 10px 22px; border: none; background: none;
  font-size: 13px; font-weight: 600; color: var(--text-2);
  cursor: pointer; border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: color .2s, border-color .2s;
}
.gallery-tab-btn:hover { color: var(--accent-2); }
.gallery-tab-btn.active { color: var(--accent-2); border-bottom-color: var(--accent-2); }
.gallery-tab-btn.active span { color: var(--text-3); }
.gallery-tab-panel { display: none; }
.gallery-tab-panel.active { display: block; }

/* Best-solution pair layout */
.best-gallery { display: flex !important; flex-direction: column; gap: 28px; }
.best-pair-label {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px;
}
.channel-tag {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 700; letter-spacing: .4px;
}
.ch-pipi  { background: #dbeafe; color: #1d4ed8; }
.ch-phikk { background: #fce7f3; color: #9d174d; }
.pair-var {
  font-size: 13px; font-weight: 600; color: var(--text-2);
  margin-left: 4px;
}
.best-pair-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 760px) {
  .best-pair-cards { grid-template-columns: 1fr; }
}
"""

# ── JavaScript ────────────────────────────────────────────────────────────────

_JS = r"""
(function () {
  'use strict';

  /* ── Collapsible ── */
  document.querySelectorAll('.collapsible').forEach(function (el) {
    el.addEventListener('click', function () {
      el.classList.toggle('open');
      var body = el.nextElementSibling;
      if (body && body.classList.contains('collapse-body')) {
        body.classList.toggle('open');
      }
    });
  });

  /* ── Active nav link on scroll ── */
  var sections = document.querySelectorAll('section[id]');
  var navLinks  = document.querySelectorAll('#sidebar a[href^="#"]');
  var observer  = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        navLinks.forEach(function (a) {
          a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id);
        });
      }
    });
  }, { threshold: 0.3 });
  sections.forEach(function (s) { observer.observe(s); });

  /* ── Lightbox ── */
  var lb        = document.getElementById('lightbox');
  var lbImg     = document.getElementById('lb-img');
  var lbCaption = document.getElementById('lb-caption');
  var lbImages  = [];   // [{src, caption}]
  var lbCurrent = 0;

  function buildIndex() {
    lbImages = [];
    document.querySelectorAll('.img-card[data-src]').forEach(function (card, i) {
      card._lbIndex = lbImages.length;
      lbImages.push({ src: card.dataset.src, caption: card.dataset.caption || '' });
    });
  }

  window.openLightbox = function (card) {
    buildIndex();
    lbCurrent = card._lbIndex || 0;
    lbShow(lbCurrent);
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
  };

  window.closeLightbox = function () {
    lb.classList.remove('open');
    document.body.style.overflow = '';
  };

  window.lbNav = function (dir) {
    lbCurrent = (lbCurrent + dir + lbImages.length) % lbImages.length;
    lbShow(lbCurrent);
  };

  function lbShow(idx) {
    if (!lbImages[idx]) return;
    lbImg.style.opacity = '0';
    lbImg.src = lbImages[idx].src;
    lbCaption.textContent = lbImages[idx].caption;
    lbImg.onload = function () {
      lbImg.style.transition = 'opacity .2s ease';
      lbImg.style.opacity = '1';
    };
  }

  lb.addEventListener('click', function (e) {
    if (e.target === lb) closeLightbox();
  });
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape')      closeLightbox();
    if (e.key === 'ArrowRight')  lbNav(1);
    if (e.key === 'ArrowLeft')   lbNav(-1);
  });

  /* ── Gallery tab switcher ── */
  window.switchGalleryTab = function(tabId) {
    document.querySelectorAll('.gallery-tab-btn').forEach(function(b){
      b.classList.toggle('active', b.dataset.tab === tabId);
    });
    document.querySelectorAll('.gallery-tab-panel').forEach(function(p){
      p.classList.toggle('active', p.id === tabId);
    });
  };

  /* ── Fail-details collapsible toggle ── */
  window.toggleFailDetails = function(btn) {
    var expanded = btn.getAttribute('aria-expanded') === 'true';
    var bodyId   = btn.getAttribute('aria-controls');
    var body     = bodyId ? document.getElementById(bodyId) : btn.nextElementSibling;
    if (!body) return;
    if (expanded) {
      btn.setAttribute('aria-expanded', 'false');
      body.classList.remove('open');
      var hint = btn.querySelector('.fdt-hint');
      if (hint) hint.textContent = '（点击展开）';
    } else {
      btn.setAttribute('aria-expanded', 'true');
      body.classList.add('open');
      var hint = btn.querySelector('.fdt-hint');
      if (hint) hint.textContent = '（点击收起）';
    }
  };
})();
"""


# ── Section builders ──────────────────────────────────────────────────────────

def _build_summary_section(
    jobs: list,
    delta_results: list[dict],
    questionable_best_job=None,
) -> str:
    """NLL comparison table with loop statistics columns."""
    if not jobs:
        return '<p class="empty-state">无直接 job_* 作业</p>'

    valid_nlls = [j.status.nll for j in jobs if math.isfinite(j.status.nll)]
    best_nll = min(valid_nlls) if valid_nlls else None

    delta_map: dict[str, dict] = {}
    for dr in delta_results:
        name = dr.get("name", "")
        m = re.match(r"ΔNLL \[(.+)\]$", name)
        if m:
            delta_map[m.group(1)] = dr.get("value") or {}

    rows_html = []
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (not math.isfinite(j.status.nll), j.status.nll),
    )
    for job in sorted_jobs:
        nll = job.status.nll
        is_best = best_nll is not None and nll == best_nll
        is_questionable = (
            questionable_best_job is not None and job is questionable_best_job
        )
        dv = delta_map.get(job.name, {})
        d_nll   = dv.get("delta_nll")
        two_d   = dv.get("two_delta_nll")
        sigma   = dv.get("sigma")

        row_cls = "best-row" if is_best else ("fail-row" if not math.isfinite(nll) else "")
        best_tag = '<span class="tag-best">★ 最优</span>' if is_best else ""
        if is_questionable:
            best_tag += '<span class="tag-questionable">⚠ 存疑最优</span>'

        success_icon = "✓" if job.status.success else "✗"
        success_css  = "color:var(--ok)" if job.status.success else "color:var(--fail)"

        d_nll_str = f"{d_nll:+.2f}" if d_nll is not None else "—"
        two_d_str = f"{two_d:.1f}" if two_d is not None else "—"
        sigma_str = f"{sigma:.1f}σ" if sigma is not None else "—"

        n_loops   = len(job.loop_nlls)
        n_ok      = job.n_success_loops
        best_loop = job.best_loop
        loop_str  = f"{n_ok}/{n_loops}" if n_loops else "—"
        best_str  = str(best_loop) if best_loop else "—"

        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td>{job.name}{best_tag}</td>'
            f'<td class="num">{_fmt_nll(nll)}</td>'
            f'<td class="num">{d_nll_str}</td>'
            f'<td class="num">{two_d_str}</td>'
            f'<td class="num">{sigma_str}</td>'
            f'<td class="num">{job.status.ndf}</td>'
            f'<td class="num">{loop_str}</td>'
            f'<td class="num">{best_str}</td>'
            f'<td style="text-align:center;{success_css}">{success_icon}</td>'
            f'</tr>'
        )

    return (
        f'<div class="table-wrap"><table>'
        f'<thead><tr>'
        f'<th>作业名称</th><th class="num">NLL</th><th class="num">ΔNLL</th>'
        f'<th class="num">2ΔNLL</th><th class="num">σ</th>'
        f'<th class="num">Ndf</th>'
        f'<th class="num">成功/总循环</th>'
        f'<th class="num">最优Loop#</th>'
        f'<th>收敛</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table></div>'
    )


def _build_loop_stats_section(jobs: list) -> str:
    """Detailed loop convergence panel for each job."""
    if not jobs:
        return '<p class="empty-state">无作业数据</p>'

    parts: list[str] = []
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (not math.isfinite(j.status.nll), j.status.nll),
    )

    for job in sorted_jobs:
        nlls    = job.loop_nlls
        succ    = job.loop_success
        best_lp = job.best_loop
        n       = len(nlls)

        if n == 0:
            parts.append(
                f'<div class="card">'
                f'<div class="card-title">{job.name}</div>'
                f'<p class="empty-state">未找到循环日志（slurm_logs / condor_logs）</p>'
                f'</div>'
            )
            continue

        # Build loop dots
        dots_html = []
        for i, nll_v in enumerate(nlls):
            loop_no = i + 1
            if loop_no == best_lp:
                cls = "loop-dot best"
                title = f"Loop {loop_no}: NLL={nll_v:.4f} ★ 最优"
            elif i < len(succ):
                cls = f"loop-dot {'ok' if succ[i] else 'fail'}"
                st  = "✓" if succ[i] else "✗"
                title = f"Loop {loop_no}: NLL={nll_v:.4f} {st}"
            else:
                cls = "loop-dot ok"
                title = f"Loop {loop_no}: NLL={nll_v:.4f}"
            dots_html.append(f'<span class="{cls}" title="{title}"></span>')

        n_ok    = job.n_success_loops
        rate    = f"{100 * n_ok / n:.0f}%" if n else "—"
        nll_spread = max(nlls) - min(nlls) if n > 1 else 0.0
        best_nll_v = nlls[best_lp - 1] if best_lp and best_lp <= n else None

        parts.append(
            f'<div class="card">'
            f'<div class="card-title collapsible">'
            f'{job.name}'
            f'  <span style="font-size:11px;font-weight:400;color:var(--text-3);margin-left:8px;">'
            f'NLL={_fmt_nll(job.status.nll)} &nbsp; '
            f'成功率 {rate} ({n_ok}/{n}) &nbsp; '
            f'最优 Loop#{best_lp or "—"}'
            f'</span>'
            f'</div>'
            f'<div class="collapse-body">'
            f'<div style="display:flex;gap:32px;flex-wrap:wrap;margin-bottom:16px;">'
            f'<div class="stat-card" style="flex:1;min-width:120px;">'
            f'<div class="sc-val">{n}</div><div class="sc-label">总循环数</div></div>'
            f'<div class="stat-card" style="flex:1;min-width:120px;">'
            f'<div class="sc-val" style="color:var(--ok)">{n_ok}</div>'
            f'<div class="sc-label">收敛次数</div></div>'
            f'<div class="stat-card" style="flex:1;min-width:120px;">'
            f'<div class="sc-val" style="color:var(--warn)">{best_lp or "—"}</div>'
            f'<div class="sc-label">最优Loop#</div>'
            f'{"<div class=sc-sub>NLL=" + _fmt_nll(best_nll_v) + "</div>" if best_nll_v is not None else ""}'
            f'</div>'
            f'<div class="stat-card" style="flex:1;min-width:120px;">'
            f'<div class="sc-val">{nll_spread:.2f}</div>'
            f'<div class="sc-label">NLL 极差</div></div>'
            f'</div>'
            f'<div class="loop-bar">{"".join(dots_html)}</div>'
            f'<p style="font-size:11px;color:var(--text-3);margin-top:8px;">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;'
            f'background:#86efac;vertical-align:middle;margin-right:4px;"></span>收敛 &nbsp;'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;'
            f'background:#fca5a5;vertical-align:middle;margin-right:4px;"></span>未收敛 &nbsp;'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;'
            f'background:#fbbf24;vertical-align:middle;margin-right:4px;"></span>最优 (★)</p>'
            f'</div>'
            f'</div>'
        )

    return "".join(parts)


def _build_param_comparison_section(jobs: list) -> str:
    """Cross-job table of f-state physical parameters.

    Each job column shows: final_value ± error (or ± none).
    Tooltip reveals initial value.  Diff-highlight when a value diverges from best job.
    """
    if not jobs:
        return '<p class="empty-state">无作业数据</p>'

    # Collect all f-state parameter names across all jobs
    all_params: list[str] = []
    seen: set[str] = set()
    for job in jobs:
        for k in job.params_value:
            if _is_f_state_param(k) and k not in seen:
                all_params.append(k)
                seen.add(k)

    if not all_params:
        return '<p class="empty-state">未检测到 f-态物理参数（质量 / 宽度 / Flatté 耦合）</p>'

    # Sort jobs by NLL (best first)
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (not math.isfinite(j.status.nll), j.status.nll),
    )
    best_job = sorted_jobs[0] if sorted_jobs else None

    # Sort params: mass → width → g_0 → g_1
    def _param_sort_key(p: str) -> tuple:
        pl = p.lower()
        if "_mass" in pl:   return (0, p)
        if "_width" in pl:  return (1, p)
        if "_g_0" in pl:    return (2, p)
        if "_g_1" in pl:    return (3, p)
        return (4, p)

    all_params = sorted(all_params, key=_param_sort_key)

    # ── Header rows ───────────────────────────────────────────────────────────
    header1_cells = ['<th rowspan="2" class="pt-name-hdr">参数名</th>']
    header2_cells: list[str] = []
    for j in sorted_jobs:
        is_best = j is best_job and math.isfinite(j.status.nll)
        badge = '<span class="th-best-badge">⭐ Best</span>' if is_best else ''
        header1_cells.append(
            f'<th colspan="2" class="pt-job-hdr{"  pt-best-hdr" if is_best else ""}">'
            f'{j.name[:30]}{badge}</th>'
        )
        header2_cells.append(
            f'<th class="pt-sub-hdr{"  pt-best-hdr" if is_best else ""}">初始值</th>'
            f'<th class="pt-sub-hdr{"  pt-best-hdr" if is_best else ""}">最终值 ± 误差</th>'
        )

    # ── Body rows ─────────────────────────────────────────────────────────────
    rows_html: list[str] = []
    for pname in all_params:
        # Gather values
        job_data: list[dict] = []
        for j in sorted_jobs:
            init_val  = j.init_params_value.get(pname)
            final_val = j.params_value.get(pname)
            final_err = j.params_error.get(pname)
            job_data.append({"init": init_val, "final": final_val, "err": final_err, "job": j})

        # Best job reference value for diff highlight
        best_val: float | None = None
        if best_job is not None:
            bv = best_job.params_value.get(pname)
            if bv is not None:
                try:
                    best_val = float(bv)
                except (TypeError, ValueError):
                    pass

        # Check if any value differs from best
        any_diff = False
        for d in job_data:
            if d["job"] is best_job or d["final"] is None or best_val is None:
                continue
            try:
                if abs(float(d["final"]) - best_val) > 1e-6:
                    any_diff = True
                    break
            except (TypeError, ValueError):
                pass

        # Build cells (2 td per job: init + final)
        cells: list[str] = []
        for idx, d in enumerate(job_data):
            is_best_col = d["job"] is best_job
            final_val = d["final"]
            final_err = d["err"]
            init_val  = d["init"]

            # ── Init cell ────────────────────────────────────────────────────
            if init_val is not None:
                try:
                    iv = float(init_val)
                    init_str = f"{iv:.3f}"
                except (TypeError, ValueError):
                    init_str = str(init_val)
            else:
                init_str = '<span class="pv-missing" title="无初始值">✗</span>'

            init_cell_cls = "pv-cell pv-init-col"
            if is_best_col:
                init_cell_cls += " pv-best-col"
            cells.append(f'<td class="{init_cell_cls}">{init_str}</td>')

            # ── Final cell ───────────────────────────────────────────────────
            # Diff from best?
            is_diff = False
            if not is_best_col and final_val is not None and best_val is not None:
                try:
                    if abs(float(final_val) - best_val) > 1e-6:
                        is_diff = True
                except (TypeError, ValueError):
                    pass

            if final_val is not None:
                formatted = _fmt_param(final_val, final_err)
            else:
                formatted = '<span class="pv-missing">—</span>'

            final_cell_cls = "pv-cell"
            if is_best_col:
                final_cell_cls += " pv-best-col"

            cells.append(
                f'<td class="{final_cell_cls}" style="{"color:#b45309;" if is_diff else ""}">'
                f'{formatted}'
                f'</td>'
            )

        row_cls = "pv-diff" if any_diff else ""
        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td>{pname}</td>'
            + "".join(cells)
            + '</tr>'
        )

    # ── Info card ─────────────────────────────────────────────────────────────
    info_card = (
        '<div class="param-info-card">'
        '<span class="pic-icon">ℹ️</span>'
        '<div>'
        '<b>数据格式说明</b><br>'
        '每作业显示两列：<code>初始值</code>（无初始值时显示 ✗）和 <code>最终值 ± 误差</code>（若无误差则显示 <code>± none</code>），'
        '所有数值保留 3 位小数，等宽数字排版。'
        '&nbsp;·&nbsp; '
        '<span style="color:#b45309;font-weight:600;">橙色</span> = 与最优解存在差异。'
        '</div>'
        '</div>'
    )

    # ── Assemble ──────────────────────────────────────────────────────────────
    thead = (
        f'<tr>{"".join(header1_cells)}</tr>'
        f'<tr>{"".join(header2_cells)}</tr>'
    )

    return (
        info_card
        + '<div class="param-table-wrap">'
        + '<table class="param-table">'
        + f'<thead>{thead}</thead>'
        + f'<tbody>{"".join(rows_html)}</tbody>'
        + '</table></div>'
    )


def _build_aic_section(aic_results: list[dict]) -> str:
    if not aic_results:
        return '<p class="empty-state">AIC 结果不可用</p>'

    rows_html = []
    for r in aic_results:
        is_best = r.get("is_best_aic") and r.get("is_best_nll")
        row_cls = "best-row" if is_best else ("warn-row" if r.get("delta_aic", 0) < 7 else "fail-row")
        nll_star = '<span class="tag-best">NLL★</span>' if r.get("is_best_nll") else ""
        aic_star = '<span class="tag-best tag-aic">AIC★</span>' if r.get("is_best_aic") else ""
        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td>{r["name"]}{nll_star}{aic_star}</td>'
            f'<td class="num">{_fmt_nll(r["nll"])}</td>'
            f'<td class="num">{r.get("n_free", "—")}</td>'
            f'<td class="num">{_fmt_float(r.get("aic"))}</td>'
            f'<td class="num">{_fmt_float(r.get("delta_aic"))}</td>'
            f'<td class="num">{r.get("aic_weight", 0):.3f}</td>'
            f'<td class="num">{_fmt_float(r.get("two_delta_nll"))}</td>'
            f'<td class="num">{_fmt_float(r.get("sigma_wilks"))}σ</td>'
            f'<td>{r.get("message", "")}</td>'
            f'</tr>'
        )

    return (
        f'<div class="table-wrap"><table>'
        f'<thead><tr>'
        f'<th>作业名称</th><th class="num">NLL</th><th class="num">k(自由参)</th>'
        f'<th class="num">AIC</th><th class="num">ΔAIC</th>'
        f'<th class="num">AIC 权重</th><th class="num">2ΔNLL</th>'
        f'<th class="num">σ(Wilks)</th><th>结论</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table></div>'
        f'<p class="meta" style="margin-top:10px;">'
        f'ΔAIC < 2 → 实质等价；2–7 → 明显弱支持；> 7 → 基本无支持</p>'
    )


def _build_best_projection_tab(best_job, out_dir: Path) -> str:
    """Build page-1 gallery tab with paired φππ / φKK projection plots from best job."""
    if best_job is None:
        return '<p class="empty-state">无最优作业</p>'

    fig_dir: Path = Path(best_job.path) / "figure"
    if not fig_dir.is_dir():
        return '<p class="empty-state">最优作业 figure/ 目录不存在</p>'

    # Pairs: (pipi_filename, pipi_caption, phikk_filename, phikk_caption, var_label)
    pairs = [
        ("s0_m_pipi.png",                   "φππ: m(ππ)",            "s1_m_kk.png",                    "φKK: m(KK)",            "m(ππ) / m(KK)"),
        ("s0_m_bm.png",                     "φππ: m(b⁻)",            "s1_m_kstm.png",                  "φKK: m(K*⁻)",           "m(b⁻) / m(K*⁻)"),
        ("s0_m_bp.png",                     "φππ: m(b⁺)",            "s1_m_kstp.png",                  "φKK: m(K*⁺)",           "m(b⁺) / m(K*⁺)"),
        ("s0_Jpsi_bp_pip_alpha.png",        "φππ: α(b⁺, π⁺)",       "s1_Jpsi_kstp_kp_alpha.png",      "φKK: α(K*⁺, K⁺)",      "α(b⁺/K*⁺, π⁺/K⁺)"),
        ("s0_Jpsi_bp_pip_cos(beta).png",    "φππ: cos β(b⁺, π⁺)",   "s1_Jpsi_kstp_kp_cos(beta).png",  "φKK: cos β(K*⁺, K⁺)",  "cos β(b⁺/K*⁺, π⁺/K⁺)"),
        ("s0_Jpsi_pipi_pip_cos(beta).png",  "φππ: cos β(ππ, π⁺)",   "s1_Jpsi_kk_kp_cos(beta).png",    "φKK: cos β(KK, K⁺)",   "cos β(ππ/KK, π⁺/K⁺)"),
    ]

    # Copy figures to out_dir/plots/ and build rows
    plots_out = out_dir / "plots"
    plots_out.mkdir(parents=True, exist_ok=True)

    row_htmls: list[str] = []
    for p0, cap0, p1, cap1, var_lbl in pairs:
        src0_abs = fig_dir / p0
        src1_abs = fig_dir / p1
        dest0 = plots_out / f"best_{p0}"
        dest1 = plots_out / f"best_{p1}"
        for src, dst in [(src0_abs, dest0), (src1_abs, dest1)]:
            if src.exists() and not dst.exists():
                import shutil as _shutil
                _shutil.copy2(src, dst)
        rel0 = f"plots/best_{p0}"
        rel1 = f"plots/best_{p1}"
        card0 = _img(dest0, out_dir, alt=cap0, caption=cap0) if dest0.exists() else f'<div class="missing-plot">{cap0}</div>'
        card1 = _img(dest1, out_dir, alt=cap1, caption=cap1) if dest1.exists() else f'<div class="missing-plot">{cap1}</div>'
        row_htmls.append(
            f'<div class="best-pair-row">'
            f'<div class="best-pair-label">'
            f'<span class="channel-tag ch-pipi">φππ</span>'
            f'<span class="channel-tag ch-phikk">φKK</span>'
            f'<span class="pair-var">{var_lbl}</span>'
            f'</div>'
            f'<div class="best-pair-cards">{card0}{card1}</div>'
            f'</div>'
        )

    return '<div class="gallery-grid best-gallery">' + "".join(row_htmls) + '</div>'


def _build_plots_section(plot_paths: dict, scan_plot_paths: dict, out_dir: Path, best_job=None) -> str:
    all_plots = dict(plot_paths)
    all_plots.update(scan_plot_paths or {})

    # ── NLL tab (existing plots) ──────────────────────────────────────────────
    nll_parts: list[str] = ['<div class="gallery-grid">']
    for title, val in all_plots.items():
        if val is None:
            continue
        if isinstance(val, list):
            sub = "".join(
                _img(p, out_dir, alt=f"{title} {i+1}", caption=f"{title} ({i+1}/{len(val)})")
                for i, p in enumerate(val) if p is not None
            )
            if not sub:
                continue
            nll_parts.append(
                f'<div class="img-card-group">'
                f'<div class="img-card-group-label">{title}</div>'
                f'<div class="img-card-group-body">{sub}</div>'
                f'</div>'
            )
        else:
            nll_parts.append(_img(val, out_dir, alt=title, caption=title))
    nll_parts.append("</div>")
    nll_gallery = "".join(nll_parts)

    if not all_plots and best_job is None:
        return '<p class="empty-state">无图表生成</p>'

    # ── Best-solution projection tab ──────────────────────────────────────────
    best_gallery = _build_best_projection_tab(best_job, out_dir)

    best_job_label = best_job.name if best_job is not None else "—"
    tab_bar = (
        '<div class="gallery-tab-bar">'
        '<button class="gallery-tab-btn active" data-tab="gtab-best" '
        f'onclick="switchGalleryTab(\'gtab-best\')">'
        f'最优解投影图'
        f'<span style="font-size:11px;font-weight:400;color:rgba(255,255,255,.6);margin-left:8px;">'
        f'{best_job_label}</span>'
        f'</button>'
        '<button class="gallery-tab-btn" data-tab="gtab-nll" '
        'onclick="switchGalleryTab(\'gtab-nll\')">NLL 分析图</button>'
        '</div>'
    )
    return (
        tab_bar
        + f'<div id="gtab-best" class="gallery-tab-panel active">{best_gallery}</div>'
        + f'<div id="gtab-nll" class="gallery-tab-panel">{nll_gallery}</div>'
    )


def _build_check_items_html(check_results: dict) -> str:
    items_html: list[str] = []
    for key, val in check_results.items():
        items = val if isinstance(val, list) else [val]
        for item in items:
            s = item.get("status", "ok")
            icon = _STATUS_ICON.get(s, "?")
            items_html.append(
                f'<li class="check-item">'
                f'<span class="check-icon {s}">{icon}</span>'
                f'<div>'
                f'<div class="check-name">{item.get("name", key)}</div>'
                f'<div class="check-msg">{item.get("message", "")}</div>'
                f'</div></li>'
            )
    return f'<ul class="check-list">{"".join(items_html)}</ul>'


def _build_per_job_section(
    jobs: list,
    check_results_per_job: dict,
    best_job,
    questionable_best_job=None,
) -> str:
    if not jobs:
        return '<p class="empty-state">无作业数据</p>'

    parts: list[str] = []
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (not math.isfinite(j.status.nll), j.status.nll),
    )

    for job in sorted_jobs:
        cr      = check_results_per_job.get(job.name, {})
        overall = _overall_status(cr) if cr else "warn"
        is_best = best_job is not None and job is best_job
        is_questionable = (
            questionable_best_job is not None and job is questionable_best_job
        )
        best_tag = '<span class="tag-best">★ 最优</span>' if is_best else ""
        if is_questionable:
            best_tag += '<span class="tag-questionable">⚠ 存疑最优</span>'

        check_html = _build_check_items_html(cr) if cr else '<p class="empty-state">无检验结果</p>'
        n_loops    = len(job.loop_nlls)
        best_loop  = job.best_loop

        parts.append(
            f'<div class="card">'
            f'<div class="card-title collapsible">'
            f'{job.name}{best_tag} &nbsp; {_badge(overall)}'
            f'<span style="font-weight:400;color:var(--text-3);font-size:12px;margin-left:10px;">'
            f'NLL={_fmt_nll(job.status.nll)} &nbsp; Ndf={job.status.ndf}'
            f'{" &nbsp; Loop★#" + str(best_loop) if best_loop else ""}'
            f' &nbsp; 成功={job.n_success_loops}/{n_loops}'
            f'</span></div>'
            f'<div class="collapse-body">{check_html}</div>'
            f'</div>'
        )

    return "".join(parts)


_FAIL_CONDITIONS = [
    ("NLL 稳定性",       "NLL 散布超过阈值（全局最优可疑，似然面复杂）"),
    ("误差矩阵正定性",    "误差矩阵存在负特征值（Hesse 矩阵非正定，拟合未真正收敛）"),
    ("参数 Pull vs PDG", "质量/宽度参数与 PDG 偏差超过阈值（拟合值偏离已知物理结果）"),
    ("Fit Fraction",      "某分波的拟合分率 FF &lt; 0（数值非物理）"),
    ("干涉完备性",        "∑FF_matrix 严重偏离 1（干涉矩阵归一化破坏）"),
    ("参数相关性",        "最大参数相关系数 |ρ| 超过严格阈值（参数可能简并）"),
    ("Flatté 参数边界",   "f0(980) Flatté 耦合参数撞上声明边界（980 MeV 区域拟合被人为截断）"),
    ("f0(980) 干涉",      "f0(980) 对角拟合分率 FF_diag &gt; 1（非物理极小值）"),
    ("参数置信区间质量",   "误差达到机器精度或恰好为零（Hesse 奇异，置信区间无效）"),
    ("SLURM/Condor 日志", "存在 fatal 级别错误，或误差矩阵非正定（matrix_not_pd）"),
    ("跨通道一致性",       "共享共振在任一通道的拟合分率为负值（跨通道约束破坏）"),
]

# Unique ID counter for accessible aria
_scan_section_counter = [0]

def _build_scan_section(scan_groups: list, check_results_per_job: dict) -> str:
    if not scan_groups:
        return '<p class="empty-state">无扫描组数据</p>'

    # Build shared fail-conditions block (once, shared across all scan groups)
    cond_items = "".join(
        f'<li>'
        f'<span class="fc-num">{i+1}</span>'
        f'<span>'
        f'<span class="fc-name">{name}</span>'
        f'<span class="fc-cond">— {cond}</span>'
        f'</span>'
        f'</li>'
        for i, (name, cond) in enumerate(_FAIL_CONDITIONS)
    )
    fail_block = (
        '<div class="fail-details-toggle" role="button" tabindex="0" '
        'aria-expanded="false" aria-controls="fail-details-body" '
        'onclick="toggleFailDetails(this)" '
        'onkeydown="if(event.key===\'Enter\'||event.key===\' \'){toggleFailDetails(this);event.preventDefault();}">'
        '<span class="fdt-icon">⚠️</span>'
        '<span>11 项检验 fail 触发条件说明</span>'
        '<span class="fdt-hint">（点击展开）</span>'
        '<span class="fdt-chevron">▼</span>'
        '</div>'
        '<div class="fail-details-body" id="fail-details-body">'
        '<div class="fail-details-inner">'
        '<h4>✗ Fail 触发条件（以下任意一项成立即显示红色失败徽章）</h4>'
        f'<ul class="fail-conditions-list">{cond_items}</ul>'
        '</div>'
        '</div>'
    )

    parts: list[str] = []
    for sg in scan_groups:
        rows = sg.delta_nll_table()
        if not rows:
            parts.append(
                f'<div class="card"><div class="card-title">{sg.name}</div>'
                f'<p class="empty-state">ΔNLL 表为空（无有效 NLL）</p></div>'
            )
            continue

        row_html = []
        for r in rows:
            nll_s   = _fmt_nll(r["nll"]) if math.isfinite(r["nll"]) else "NaN"
            d_nll_s = f"{r['delta_nll']:+.2f}" if math.isfinite(r["delta_nll"]) else "—"
            two_d_s = f"{r['two_delta_nll']:.1f}" if math.isfinite(r["two_delta_nll"]) else "—"
            sigma   = r.get("sigma", 0)
            if math.isfinite(sigma):
                if sigma >= 3:   sig_s = f'<span class="sigma-high">{sigma:.1f}σ</span>'
                elif sigma >= 2: sig_s = f'<span class="sigma-mid">{sigma:.1f}σ</span>'
                else:            sig_s = f'<span class="sigma-low">{sigma:.1f}σ</span>'
            else:
                sig_s = "—"

            base_marker = " ⚑" if r.get("is_baseline") else ""
            best_marker = ' <span class="tag-best">★</span>' if r.get("is_best") else ""
            added       = r.get("added") or "—"
            row_cls     = "best-row" if r.get("is_baseline") else ""

            job_full     = f"{sg.name}/{r['tag']}"
            cr           = check_results_per_job.get(job_full, {})
            status_badge = _badge(_overall_status(cr)) if cr else ""

            row_html.append(
                f'<tr class="{row_cls}">'
                f'<td><code>{r["tag"]}</code>{base_marker}{best_marker}</td>'
                f'<td>{r.get("action","—")}</td>'
                f'<td>{added}</td>'
                f'<td class="num">{nll_s}</td>'
                f'<td class="num">{d_nll_s}</td>'
                f'<td class="num">{two_d_s}</td>'
                f'<td class="num">{sig_s}</td>'
                f'<td>{r.get("message","")}</td>'
                f'<td>{status_badge}</td>'
                f'</tr>'
            )

        meta = sg.summary
        pipi = ", ".join(meta.baseline_pipi) or "—"
        kk   = ", ".join(meta.baseline_kk)   or "—"
        parts.append(
            f'<div class="card">'
            f'<div class="card-title collapsible open">{sg.name}'
            f'  <span style="font-weight:400;font-size:12px;color:var(--text-3);">'
            f'  策略: {meta.strategy} | ππ 基准: {pipi} | KK 基准: {kk}'
            f'</span></div>'
            f'<div class="collapse-body open">'
            f'<div class="scan-table-outer">'
            f'<table class="scan-table">'
            f'<thead><tr>'
            f'<th>Tag</th><th>操作</th><th>添加共振</th>'
            f'<th class="num">NLL</th><th class="num">ΔNLL</th>'
            f'<th class="num">2ΔNLL</th><th class="num">σ</th>'
            f'<th>结论</th><th>检验</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(row_html)}</tbody>'
            f'</table></div>'
            + fail_block +
            f'</div></div>'
        )

    return "".join(parts)


def _build_suggestions_section(
    jobs: list,
    scan_groups: list,
    suggestions_per_job: dict,
    best_job,
) -> str:
    if not suggestions_per_job:
        return '<p class="empty-state">无优化建议</p>'

    all_jobs = list(jobs)
    for sg in (scan_groups or []):
        for j in sg.jobs:
            if j not in all_jobs:
                all_jobs.append(j)

    parts: list[str] = []
    for job in sorted(all_jobs, key=lambda j: (best_job is not j, _fmt_nll(j.status.nll))):
        suggs = suggestions_per_job.get(job.name, [])
        if not suggs:
            continue

        is_best  = best_job is not None and job is best_job
        best_tag = '<span class="tag-best">★</span> ' if is_best else ""

        sugg_items = []
        for s in suggs:
            prio     = s.get("priority", "P2")
            category = s.get("category", "")
            action   = s.get("action", "")
            reason   = s.get("reason", "")
            formula  = s.get("formula", "")
            sugg_items.append(
                f'<div class="sugg-item sugg-{prio}">'
                f'<div class="sugg-header">'
                f'<span class="sugg-priority">{prio}</span>'
                f'<span class="sugg-category">{category}</span>'
                f'</div>'
                f'<div class="sugg-action">{action}</div>'
                f'{"<div class=sugg-reason>" + reason + "</div>" if reason else ""}'
                f'{"<div class=sugg-formula>" + formula + "</div>" if formula else ""}'
                f'</div>'
            )

        parts.append(
            f'<div class="card">'
            f'<div class="card-title collapsible">'
            f'{best_tag}{job.name}'
            f'<span style="font-weight:400;font-size:12px;color:var(--text-3);margin-left:8px;">'
            f'({len(suggs)} 条建议)</span>'
            f'</div>'
            f'<div class="collapse-body">{"".join(sugg_items)}</div>'
            f'</div>'
        )

    return "".join(parts) if parts else '<p class="empty-state">无优化建议</p>'


# ── Navigation builder ────────────────────────────────────────────────────────

def _build_nav(sections: list[tuple[str, str]]) -> str:
    items = "\n".join(
        f'<a href="#{sid}"><span class="nav-dot"></span>{title}</a>'
        for title, sid in sections
    )
    return (
        f'<nav id="sidebar">'
        f'<div class="sidebar-brand">'
        f'<div class="brand-title">BESIII φhh<br>振幅分析</div>'
        f'<div class="brand-sub">评估报告</div>'
        f'</div>'
        f'<div class="sidebar-section">'
        f'<div class="sidebar-section-label">导航</div>'
        f'{items}'
        f'</div>'
        f'</nav>'
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_report(
    jobs: list,
    check_results_per_job: dict,
    plot_paths: dict,
    out_dir: Path,
    *,
    aic_results: Optional[list[dict]] = None,
    suggestions_per_job: Optional[dict] = None,
    best_job=None,
    questionable_best_job=None,
    reference_root: Optional[Path] = None,
    scan_groups: Optional[list] = None,
    scan_plot_paths: Optional[dict] = None,
) -> Path:
    """Generate an HTML evaluation report and write it to *out_dir/report.html*."""
    import math as _math

    out_dir    = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_jobs     = len(jobs)
    n_scans    = len(scan_groups or [])
    scan_groups      = scan_groups or []
    scan_plot_paths  = scan_plot_paths or {}

    # Reconstruct delta_results from aic_results for summary table
    delta_results: list[dict] = []
    if aic_results:
        for ar in aic_results:
            delta_results.append({
                "name": f"ΔNLL [{ar['name']}]",
                "status": ar.get("status", "ok"),
                "value": {
                    "nll":           ar.get("nll"),
                    "delta_nll":     ar.get("delta_nll"),
                    "two_delta_nll": ar.get("two_delta_nll"),
                    "sigma":         ar.get("sigma_wilks"),
                },
                "message": ar.get("message", ""),
            })

    # ── Build sections ────────────────────────────────────────────────────────

    summary_html   = _build_summary_section(
        jobs, delta_results, questionable_best_job=questionable_best_job
    )
    loop_html      = _build_loop_stats_section(jobs)
    param_cmp_html = _build_param_comparison_section(jobs)
    aic_html       = _build_aic_section(aic_results or [])
    plots_html     = _build_plots_section(plot_paths, scan_plot_paths, out_dir, best_job=best_job)
    per_job_html   = _build_per_job_section(
        jobs, check_results_per_job, best_job,
        questionable_best_job=questionable_best_job,
    )
    scan_html      = _build_scan_section(scan_groups, check_results_per_job)
    suggestions_html = _build_suggestions_section(
        jobs, scan_groups, suggestions_per_job or {}, best_job
    )

    # ── Navigation ────────────────────────────────────────────────────────────
    nav_sections = [
        ("NLL 概览",           "summary"),
        ("循环收敛统计",        "loop_stats"),
        ("f 态参数对比",        "param_cmp"),
        ("模型选择（AIC）",     "aic"),
        ("分析图表",            "plots"),
        ("逐作业检验",          "per_job"),
        ("扫描显著性",          "scans"),
        ("优化建议",            "suggestions"),
    ]
    nav_html = _build_nav(nav_sections)

    # ── Hero stats ────────────────────────────────────────────────────────────
    valid_nlls = [j.status.nll for j in jobs if _math.isfinite(j.status.nll)]
    total_loops  = sum(len(j.loop_nlls) for j in jobs)
    total_ok     = sum(j.n_success_loops for j in jobs)

    if best_job:
        best_nll_str = _fmt_nll(best_job.status.nll)
        success_badge = (
            '<div class="hero-badge">● 拟合成功</div>'
            if best_job.status.success
            else '<div class="hero-badge fail">● 未收敛</div>'
        )
        hero_body = f"""
<div class="hero-eyebrow">BESIII · φhh Amplitude Analysis</div>
<h1 class="hero-title">振幅分析评估报告</h1>
{success_badge}
<div class="hero-meta">
  <div class="hero-stat">
    <span class="stat-val">{n_jobs}</span>
    <span class="stat-label">总作业数</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{best_nll_str}</span>
    <span class="stat-label">最优 NLL</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{best_job.status.ndf}</span>
    <span class="stat-label">Ndf</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{total_ok}/{total_loops}</span>
    <span class="stat-label">Loop 收敛</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{n_scans}</span>
    <span class="stat-label">扫描组</span>
  </div>
</div>
<div style="margin-top:20px;font-size:12px;color:rgba(255,255,255,.4);">
  最优作业：{best_job.name} &nbsp;|&nbsp; 生成时间：{now}
  {f'&nbsp;|&nbsp; <span style="color:#e67e22;">⚠ 存疑候选：{questionable_best_job.name}（仅 {len(questionable_best_job.loop_nlls)} 次拟合）</span>' if questionable_best_job else ''}
</div>
"""
    elif scan_groups:
        n_sub = sum(len(sg.jobs) for sg in scan_groups)
        hero_body = f"""
<div class="hero-eyebrow">BESIII · φhh Amplitude Analysis</div>
<h1 class="hero-title">振幅分析评估报告</h1>
<div class="hero-meta">
  <div class="hero-stat">
    <span class="stat-val">{n_scans}</span>
    <span class="stat-label">扫描组</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{n_sub}</span>
    <span class="stat-label">子作业</span>
  </div>
  <div class="hero-divider"></div>
  <div class="hero-stat">
    <span class="stat-val">{total_ok}/{total_loops}</span>
    <span class="stat-label">Loop 收敛</span>
  </div>
</div>
<div style="margin-top:20px;font-size:12px;color:rgba(255,255,255,.4);">生成时间：{now}</div>
"""
    else:
        hero_body = f"""
<div class="hero-eyebrow">BESIII · φhh Amplitude Analysis</div>
<h1 class="hero-title">振幅分析评估报告</h1>
<div style="margin-top:20px;font-size:12px;color:rgba(255,255,255,.4);">无有效拟合作业 &nbsp;|&nbsp; 生成时间：{now}</div>
"""

    # ── Assemble page ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>BESIII φhh 振幅分析评估报告</title>
<style>{_CSS}</style>
</head>
<body>
<div id="layout">
{nav_html}
<main id="content">

<!-- Hero -->
<header class="hero">{hero_body}</header>

<div class="content-inner">

<section class="section" id="summary">
  <div class="section-header">
    <div class="section-title">NLL 比较概览</div>
  </div>
  <div class="section-divider"></div>
  {summary_html}
</section>

<section class="section" id="loop_stats">
  <div class="section-header">
    <div class="section-title">循环收敛统计</div>
    <div class="section-subtitle">各作业拟合循环的收敛情况及最优 Loop 编号</div>
  </div>
  <div class="section-divider"></div>
  {loop_html}
</section>

<section class="section" id="param_cmp">
  <div class="section-header">
    <div class="section-title">f 态物理参数对比</div>
    <div class="section-subtitle">各作业 f₀ / f₂ 共振态的初始值与最终拟合值对比</div>
  </div>
  <div class="section-divider"></div>
  {param_cmp_html}
</section>

<section class="section" id="aic">
  <div class="section-header">
    <div class="section-title">模型选择（AIC / Wilks）</div>
  </div>
  <div class="section-divider"></div>
  {aic_html}
</section>

<section class="section" id="plots">
  <div class="section-header">
    <div class="section-title">分析图表</div>
    <div class="section-subtitle">点击图片进入沉浸式预览模式 &nbsp;·&nbsp; 使用 ← → 键或点击箭头切换</div>
  </div>
  <div class="section-divider"></div>
  {plots_html}
</section>

<section class="section" id="per_job">
  <div class="section-header">
    <div class="section-title">逐作业评估结果</div>
    <div class="section-subtitle">点击作业名展开 / 收起检验详情</div>
  </div>
  <div class="section-divider"></div>
  {per_job_html}
</section>

<section class="section" id="scans">
  <div class="section-header">
    <div class="section-title">扫描显著性分析</div>
  </div>
  <div class="section-divider"></div>
  {scan_html}
</section>

<section class="section" id="suggestions">
  <div class="section-header">
    <div class="section-title">优化建议</div>
    <div class="section-subtitle">
      <span style="color:var(--fail);font-weight:700;">P0</span>=紧急 &nbsp;
      <span style="color:var(--warn);font-weight:700;">P1</span>=重要 &nbsp;
      <span style="color:var(--accent-2);font-weight:700;">P2</span>=可选
    </div>
  </div>
  <div class="section-divider"></div>
  {suggestions_html}
</section>

</div><!-- .content-inner -->
</main>
</div><!-- #layout -->

<!-- Lightbox -->
<div id="lightbox" class="lb-overlay" role="dialog" aria-modal="true">
  <button class="lb-close" onclick="closeLightbox()" title="关闭 (Esc)">✕</button>
  <button class="lb-nav lb-prev" onclick="lbNav(-1)" title="上一张 (←)">‹</button>
  <button class="lb-nav lb-next" onclick="lbNav(1)"  title="下一张 (→)">›</button>
  <div class="lb-inner">
    <img id="lb-img" src="" alt="" />
    <div id="lb-caption"></div>
  </div>
</div>

<script>{_JS}</script>
</body>
</html>
"""

    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
