"""Generate a self-contained, visually polished HTML report.

Design goals
------------
- Modern dark-gradient header with summary statistics.
- Sticky sidebar TOC with per-section status icons.
- Best-job card expanded by default; all other jobs collapsed.
- Suggestions rendered as a priority-colour timeline.
- Responsive plot grid with hover zoom.
- Pure CSS + vanilla JS (no external dependencies → truly self-contained).
"""

from __future__ import annotations
import base64
from datetime import datetime
from pathlib import Path

from ..core.job import JobData
from ..core.checks import STATUS_OK, STATUS_WARN, STATUS_FAIL

# ── status helpers ─────────────────────────────────────────────────────────────
_BADGE = {
    STATUS_OK:   '<span class="badge ok">✓ OK</span>',
    STATUS_WARN: '<span class="badge warn">! WARN</span>',
    STATUS_FAIL: '<span class="badge fail">✗ FAIL</span>',
}
_DOT = {
    STATUS_OK:   '<span class="dot ok"></span>',
    STATUS_WARN: '<span class="dot warn"></span>',
    STATUS_FAIL: '<span class="dot fail"></span>',
}
_PRI_COLOR = {"P0": "#e74c3c", "P1": "#f39c12", "P2": "#27ae60"}


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
_CSS = """
/* ── reset & base ──────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
  background: #eef1f7;
  color: #2d3748;
  font-size: 14px;
  line-height: 1.6;
}

/* ── layout ─────────────────────────────────────────────────────────── */
.layout   { display: flex; min-height: 100vh; }
.sidebar  {
  width: 230px; flex-shrink: 0;
  background: #1a2540;
  position: sticky; top: 0; height: 100vh;
  overflow-y: auto; padding: 24px 0 32px;
  box-shadow: 2px 0 12px rgba(0,0,0,.25);
}
.main { flex: 1; min-width: 0; padding: 32px 36px 60px; }

/* ── sidebar internals ───────────────────────────────────────────────── */
.sidebar-logo {
  padding: 0 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,.1);
  margin-bottom: 12px;
}
.sidebar-logo .logo-title {
  font-size: 13px; font-weight: 700; color: #90cdf4; letter-spacing: .5px;
}
.sidebar-logo .logo-sub { font-size: 11px; color: #718096; margin-top: 2px; }
.nav-section { padding: 6px 20px 2px; font-size: 10px; color: #4a5568;
               text-transform: uppercase; letter-spacing: 1px; font-weight: 700; }
.nav-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 20px; color: #a0aec0; font-size: 12.5px;
  text-decoration: none; border-left: 3px solid transparent;
  transition: all .18s;
}
.nav-item:hover, .nav-item.active {
  color: #fff; background: rgba(255,255,255,.07);
  border-left-color: #4299e1;
}
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.ok   { background: #48bb78; }
.dot.warn { background: #f6ad55; }
.dot.fail { background: #fc8181; }

/* ── header ──────────────────────────────────────────────────────────── */
.page-header {
  background: linear-gradient(135deg, #1a2540 0%, #1e3a5f 55%, #2c5282 100%);
  border-radius: 14px; padding: 32px 36px;
  margin-bottom: 28px; color: white; position: relative; overflow: hidden;
}
.page-header::before {
  content: ''; position: absolute; right: -60px; top: -60px;
  width: 240px; height: 240px; border-radius: 50%;
  background: rgba(255,255,255,.04);
}
.page-header h1 { margin: 0 0 6px; font-size: 22px; font-weight: 700; letter-spacing: .3px; }
.page-header .meta { font-size: 12px; color: rgba(255,255,255,.6); margin-bottom: 22px; }
.stat-row { display: flex; gap: 16px; flex-wrap: wrap; }
.stat-box {
  background: rgba(255,255,255,.1); border-radius: 10px;
  padding: 12px 20px; min-width: 110px;
  backdrop-filter: blur(4px);
}
.stat-box .stat-val { font-size: 22px; font-weight: 700; }
.stat-box .stat-lbl { font-size: 11px; color: rgba(255,255,255,.65); margin-top: 2px; }
.stat-box.green { background: rgba(72,187,120,.25); }
.stat-box.amber { background: rgba(246,173,85,.25); }
.stat-box.red   { background: rgba(252,129,129,.25); }
.stat-box.blue  { background: rgba(99,179,237,.25); }

/* ── section title ───────────────────────────────────────────────────── */
.section-title {
  font-size: 16px; font-weight: 700; color: #1a2540;
  border-left: 4px solid #4299e1; padding-left: 12px;
  margin: 32px 0 14px;
}

/* ── card ────────────────────────────────────────────────────────────── */
.card {
  background: white; border-radius: 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,.07);
  padding: 22px 24px; margin-bottom: 16px;
  border: 1px solid #e2e8f0;
  transition: box-shadow .2s;
}
.card:hover { box-shadow: 0 4px 18px rgba(0,0,0,.11); }
.card.best-card { border-left: 5px solid #4299e1; background: #f7fbff; }

/* ── job header bar ──────────────────────────────────────────────────── */
.job-header {
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap; margin-bottom: 14px;
}
.job-name { font-size: 15px; font-weight: 700; color: #1a2540; }
.job-meta span { color: #718096; font-size: 12px; margin-right: 14px; }
.job-meta b { color: #2d3748; }
.best-star {
  background: linear-gradient(135deg,#f6d365,#fda085);
  color: white; font-size: 11px; font-weight: 700;
  padding: 3px 10px; border-radius: 20px; letter-spacing: .3px;
}

/* ── score pills ─────────────────────────────────────────────────────── */
.score-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.score-pill {
  font-size: 11.5px; font-weight: 600; padding: 4px 12px;
  border-radius: 20px; border: 1.5px solid;
}
.score-pill.ok   { color: #276749; background: #f0fff4; border-color: #9ae6b4; }
.score-pill.warn { color: #7b341e; background: #fffaf0; border-color: #fbd38d; }
.score-pill.fail { color: #742a2a; background: #fff5f5; border-color: #feb2b2; }

/* ── badge ───────────────────────────────────────────────────────────── */
.badge {
  display: inline-block; padding: 2px 9px; border-radius: 10px;
  font-weight: 700; font-size: 11.5px; white-space: nowrap;
}
.badge.ok   { background: #48bb78; color: white; }
.badge.warn { background: #f6ad55; color: white; }
.badge.fail { background: #fc8181; color: white; }

/* ── table ───────────────────────────────────────────────────────────── */
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 12.5px; }
th {
  background: #2a4365; color: white;
  padding: 9px 13px; text-align: left; font-weight: 600; font-size: 12px;
}
td { padding: 7px 13px; border-bottom: 1px solid #edf2f7; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:nth-child(even) td { background: #f7fafc; }
tr:hover td { background: #ebf4ff; }
.nll-best td { font-weight: 700; color: #2b6cb0; background: #ebf8ff !important; }

/* ── details / summary ───────────────────────────────────────────────── */
details { border-radius: 8px; overflow: hidden; margin: 10px 0; }
details > summary {
  cursor: pointer; list-style: none;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; font-weight: 600; font-size: 13px;
  background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px;
  user-select: none; color: #2a4365;
  transition: background .15s;
}
details > summary:hover { background: #ebf4ff; }
details > summary::before {
  content: '▶'; font-size: 10px; color: #a0aec0;
  transition: transform .2s; display: inline-block; width: 12px;
}
details[open] > summary { border-radius: 8px 8px 0 0; border-bottom: none; }
details[open] > summary::before { transform: rotate(90deg); }
details > .details-body {
  border: 1px solid #e2e8f0; border-top: none;
  border-radius: 0 0 8px 8px; padding: 14px;
  background: white;
}

/* ── suggestions timeline ────────────────────────────────────────────── */
.timeline { position: relative; padding: 4px 0; }
.timeline::before {
  content: ''; position: absolute; left: 20px; top: 0; bottom: 0;
  width: 2px; background: #e2e8f0;
}
.tl-item {
  display: flex; gap: 16px; align-items: flex-start;
  margin-bottom: 14px; position: relative;
}
.tl-badge {
  flex-shrink: 0; width: 42px; height: 42px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 800; color: white;
  box-shadow: 0 2px 6px rgba(0,0,0,.2); z-index: 1;
}
.tl-body {
  flex: 1; background: white; border-radius: 10px;
  border: 1px solid #e2e8f0; padding: 11px 15px;
  box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.tl-cat { font-size: 10.5px; color: #718096; font-weight: 600;
           text-transform: uppercase; letter-spacing: .5px; margin-bottom: 3px; }
.tl-action { font-size: 13px; font-weight: 700; color: #1a2540; margin-bottom: 4px; }
.tl-reason { font-size: 12px; color: #4a5568; }
.tl-formula { font-size: 11px; color: #718096; font-family: 'Courier New', monospace;
               margin-top: 5px; background: #f7fafc; padding: 4px 8px;
               border-radius: 4px; display: inline-block; }

/* ── AIC table extras ────────────────────────────────────────────────── */
.aic-info { font-size: 11.5px; color: #718096; margin-top: 10px;
             padding: 8px 12px; background: #f7fafc; border-radius: 6px;
             border-left: 3px solid #90cdf4; }

/* ── plot grid ───────────────────────────────────────────────────────── */
.plot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
  gap: 20px; margin-top: 14px;
}
.plot-card {
  background: white; border-radius: 10px; padding: 14px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 6px rgba(0,0,0,.06);
}
.plot-card h4 { margin: 0 0 10px; font-size: 13px; color: #2a4365; }
.plot-card img {
  width: 100%; height: auto; border-radius: 6px;
  cursor: zoom-in; transition: transform .2s;
}
.plot-card img:hover { transform: scale(1.02); }

/* ── lightbox ────────────────────────────────────────────────────────── */
#lb-overlay {
  display: none; position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.85); align-items: center; justify-content: center;
}
#lb-overlay.active { display: flex; }
#lb-overlay img {
  max-width: 92vw; max-height: 90vh; border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0,0,0,.6);
}
#lb-close {
  position: absolute; top: 20px; right: 28px; font-size: 32px;
  color: white; cursor: pointer; line-height: 1; user-select: none;
}

/* ── cross-channel ───────────────────────────────────────────────────── */
.cc-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px; margin: 10px 0;
}
.cc-card {
  border-radius: 8px; padding: 10px 14px;
  border: 1px solid #e2e8f0; font-size: 12px;
}
.cc-card.ok   { background: #f0fff4; border-color: #9ae6b4; }
.cc-card.warn { background: #fffaf0; border-color: #fbd38d; }
.cc-card.fail { background: #fff5f5; border-color: #feb2b2; }

/* ── footer ──────────────────────────────────────────────────────────── */
.footer {
  text-align: center; color: #a0aec0; font-size: 11.5px;
  margin-top: 48px; padding-top: 24px;
  border-top: 1px solid #e2e8f0;
}
"""

# ══════════════════════════════════════════════════════════════════════════════
# JS
# ══════════════════════════════════════════════════════════════════════════════
_JS = """
// Lightbox
document.querySelectorAll('.plot-card img').forEach(img => {
  img.addEventListener('click', () => {
    const ol = document.getElementById('lb-overlay');
    document.getElementById('lb-img').src = img.src;
    ol.classList.add('active');
  });
});
document.getElementById('lb-overlay').addEventListener('click', e => {
  if (e.target !== document.getElementById('lb-img'))
    e.currentTarget.classList.remove('active');
});
document.getElementById('lb-close').addEventListener('click', () =>
  document.getElementById('lb-overlay').classList.remove('active')
);

// Sidebar active tracking
const sections = document.querySelectorAll('[data-sec]');
const navItems = document.querySelectorAll('.nav-item[href^="#"]');
const obs = new IntersectionObserver(entries => {
  entries.forEach(en => {
    if (en.isIntersecting) {
      navItems.forEach(a => {
        a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id);
      });
    }
  });
}, { rootMargin: '-40% 0px -55% 0px' });
sections.forEach(s => obs.observe(s));
"""


# ══════════════════════════════════════════════════════════════════════════════
# Helper renderers
# ══════════════════════════════════════════════════════════════════════════════

def _img_tag(path: Path | None, alt: str = "") -> str:
    if path is None or not Path(path).exists():
        return f'<p style="color:#a0aec0;font-size:12px;text-align:center">图像未生成：{alt}</p>'
    data = base64.b64encode(Path(path).read_bytes()).decode()
    ext  = Path(path).suffix.lstrip(".")
    return f'<img src="data:image/{ext};base64,{data}" alt="{alt}">'


def _all_check_items(check_results: dict) -> list[dict]:
    items = []
    for v in check_results.values():
        if isinstance(v, list):
            items.extend(v)
        elif isinstance(v, dict) and "name" in v:
            items.append(v)
    return items


def _status_counts(items: list[dict]) -> dict:
    c = {STATUS_OK: 0, STATUS_WARN: 0, STATUS_FAIL: 0}
    for it in items:
        s = it.get("status", STATUS_WARN)
        c[s] = c.get(s, 0) + 1
    return c


def _render_checks_table(check_results: dict, open_by_default: bool = False) -> str:
    items = _all_check_items(check_results)
    counts = _status_counts(items)
    rows = ""
    for item in items:
        s   = item.get("status", STATUS_WARN)
        val = item.get("value")
        if isinstance(val, dict):
            val_str = "; ".join(
                f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
                for k, v in list(val.items())[:4]
                if not isinstance(v, list)
            )
        elif val is not None:
            val_str = str(val)[:100]
        else:
            val_str = ""
        rows += f"""
        <tr>
          <td style="width:80px">{_BADGE.get(s, s)}</td>
          <td style="white-space:nowrap">{item.get('name','')}</td>
          <td style="max-width:380px">{item.get('message','')}</td>
          <td style="font-size:11px;color:#718096">{val_str}</td>
        </tr>"""

    summary_pills = (
        f'<span class="score-pill ok">{counts[STATUS_OK]} OK</span> '
        f'<span class="score-pill warn">{counts[STATUS_WARN]} WARN</span> '
        f'<span class="score-pill fail">{counts[STATUS_FAIL]} FAIL</span>'
    )
    open_attr = " open" if open_by_default else ""
    return f"""
    <details{open_attr}>
      <summary>
        完整评估检验结果 &nbsp;
        <span style="font-weight:400;font-size:12px">{summary_pills}</span>
      </summary>
      <div class="details-body">
        <table>
          <tr><th style="width:80px">状态</th><th>检验项目</th><th>说明</th><th>数值</th></tr>
          {rows}
        </table>
      </div>
    </details>"""


def _render_cross_channel(check_results: dict, open_by_default: bool = False) -> str:
    cc_items = check_results.get("cross_channel_consistency", [])
    if not isinstance(cc_items, list):
        cc_items = [cc_items] if cc_items else []
    if not cc_items:
        return ""

    cards = ""
    for item in cc_items:
        s   = item.get("status", STATUS_WARN)
        cls = {STATUS_OK: "ok", STATUS_WARN: "warn", STATUS_FAIL: "fail"}.get(s, "warn")
        val = item.get("value") or {}
        val_bits = "; ".join(
            f"<b>{k}</b>={v:.4g}" if isinstance(v, float) else f"<b>{k}</b>={v}"
            for k, v in val.items() if not isinstance(v, list)
        )
        cards += f"""
        <div class="cc-card {cls}">
          <div style="font-weight:700;margin-bottom:4px">{_BADGE.get(s,s)} {item.get('name','')}</div>
          <div style="color:#4a5568">{item.get('message','')}</div>
          {f'<div style="font-size:11px;color:#718096;margin-top:4px">{val_bits}</div>' if val_bits else ''}
        </div>"""

    open_attr = " open" if open_by_default else ""
    return f"""
    <details{open_attr}>
      <summary>耦合道一致性检查</summary>
      <div class="details-body">
        <div class="cc-grid">{cards}</div>
      </div>
    </details>"""


def _render_suggestions(suggestions: list[dict], open_by_default: bool = True) -> str:
    if not suggestions:
        return ""

    timeline = ""
    for s in suggestions:
        pri    = s.get("priority", "P2")
        color  = _PRI_COLOR.get(pri, "#718096")
        cat    = s.get("category", "")
        action = s.get("action", "")
        reason = s.get("reason", "")
        formula = s.get("formula", "")
        formula_html = (
            f'<div class="tl-formula">{formula}</div>' if formula else ""
        )
        timeline += f"""
        <div class="tl-item">
          <div class="tl-badge" style="background:{color}">{pri}</div>
          <div class="tl-body">
            <div class="tl-cat">{cat}</div>
            <div class="tl-action">{action}</div>
            <div class="tl-reason">{reason}</div>
            {formula_html}
          </div>
        </div>"""

    open_attr = " open" if open_by_default else ""
    p0 = sum(1 for s in suggestions if s.get("priority") == "P0")
    p1 = sum(1 for s in suggestions if s.get("priority") == "P1")
    p2 = sum(1 for s in suggestions if s.get("priority") == "P2")
    pills = (
        f'<span style="background:{_PRI_COLOR["P0"]};color:white;'
        f'padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700">'
        f'P0×{p0}</span> '
        f'<span style="background:{_PRI_COLOR["P1"]};color:white;'
        f'padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700">'
        f'P1×{p1}</span> '
        f'<span style="background:{_PRI_COLOR["P2"]};color:white;'
        f'padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700">'
        f'P2×{p2}</span>'
    )
    return f"""
    <details{open_attr}>
      <summary>
        拟合优化建议 &nbsp;
        <span style="font-weight:400">{pills}</span>
      </summary>
      <div class="details-body">
        <div class="timeline">{timeline}</div>
      </div>
    </details>"""


def _render_aic_table(aic_results: list[dict]) -> str:
    if not aic_results:
        return '<p style="color:#a0aec0">未进行模型选择分析</p>'
    rows = ""
    for r in aic_results:
        star_nll = ' <span class="badge ok" style="font-size:10px">NLL★</span>' if r.get("is_best_nll") else ""
        star_aic = ' <span class="badge blue" style="background:#3182ce;font-size:10px">AIC★</span>' if r.get("is_best_aic") else ""
        da  = r.get("delta_aic", 0)
        da_color = "#48bb78" if da < 2 else ("#f6ad55" if da < 7 else "#fc8181")
        rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:12px">{r['name']}{star_nll}{star_aic}</td>
          <td>{r['nll']:.4f}</td>
          <td style="text-align:center">{r['n_free']}</td>
          <td>{r['aic']:.2f}</td>
          <td style="font-weight:700;color:{da_color}">{da:.2f}</td>
          <td>{r.get('aic_weight', 0):.4f}</td>
          <td>{r.get('sigma_wilks', 0):.1f}σ</td>
          <td style="font-size:11.5px;color:#718096">{r.get('aic_verdict','')}</td>
        </tr>"""
    return f"""
    <table>
      <tr><th>作业名</th><th>NLL</th><th>k</th><th>AIC</th>
          <th>ΔAIC</th><th>Akaike 权重</th><th>Wilks 显著性</th><th>AIC 判断</th></tr>
      {rows}
    </table>
    <div class="aic-info">
      AIC = 2k + 2·NLL，对参数复杂度施加线性惩罚，适合非嵌套模型比较。
      ΔAIC &lt; 2：实质等价；2–7：支持度明显较弱；&gt; 7：基本无支持。
    </div>"""


# ══════════════════════════════════════════════════════════════════════════════
# Main generator
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(
    jobs: list[JobData],
    check_results_per_job: dict[str, dict],
    plot_paths: dict[str, Path],
    out_path: Path,
    aic_results: list[dict] | None = None,
    suggestions_per_job: dict[str, list[dict]] | None = None,
) -> Path:
    import numpy as np

    nlls     = [j.status.nll for j in jobs]
    best_idx = int(np.nanargmin(nlls))
    best_nll = nlls[best_idx]

    # ── global stats for header ────────────────────────────────────────────
    all_items   = []
    for cr in check_results_per_job.values():
        all_items.extend(_all_check_items(cr))
    gcounts = _status_counts(all_items)
    n_jobs  = len(jobs)

    # ── sidebar nav entries ────────────────────────────────────────────────
    def _job_dot(job: JobData) -> str:
        cr = check_results_per_job.get(job.name, {})
        items = _all_check_items(cr)
        c = _status_counts(items)
        s = STATUS_FAIL if c[STATUS_FAIL] else (STATUS_WARN if c[STATUS_WARN] else STATUS_OK)
        return _DOT.get(s, "")

    sidebar_jobs = "".join(
        f'<a class="nav-item" href="#job-{i}">'
        f'{_job_dot(job)} '
        f'{"★ " if job is jobs[best_idx] else ""}'
        f'{job.name[-14:]}</a>'
        for i, job in enumerate(jobs)
    )

    sidebar = f"""
    <aside class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-title">BESIII φhh 分析</div>
        <div class="logo-sub">耦合道振幅分析评估</div>
      </div>
      <div class="nav-section">概览</div>
      <a class="nav-item" href="#sec-nll">{_DOT[STATUS_OK]} NLL 总览</a>
      <a class="nav-item" href="#sec-aic">{_DOT[STATUS_OK]} 模型选择</a>
      <a class="nav-item" href="#sec-plots">{_DOT[STATUS_OK]} 可视化</a>
      <div class="nav-section">作业详情</div>
      {sidebar_jobs}
    </aside>"""

    # ── header stats ───────────────────────────────────────────────────────
    header = f"""
    <div class="page-header">
      <h1>振幅分析作业评估报告</h1>
      <div class="meta">
        生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;·&nbsp;
        共 {n_jobs} 个作业 &nbsp;·&nbsp;
        最优作业：<b>{jobs[best_idx].name}</b>
      </div>
      <div class="stat-row">
        <div class="stat-box blue">
          <div class="stat-val">{n_jobs}</div>
          <div class="stat-lbl">作业总数</div>
        </div>
        <div class="stat-box green">
          <div class="stat-val">{gcounts[STATUS_OK]}</div>
          <div class="stat-lbl">通过检验</div>
        </div>
        <div class="stat-box amber">
          <div class="stat-val">{gcounts[STATUS_WARN]}</div>
          <div class="stat-lbl">警告项目</div>
        </div>
        <div class="stat-box red">
          <div class="stat-val">{gcounts[STATUS_FAIL]}</div>
          <div class="stat-lbl">失败项目</div>
        </div>
        <div class="stat-box blue">
          <div class="stat-val">{best_nll:.2f}</div>
          <div class="stat-lbl">最优 NLL</div>
        </div>
      </div>
    </div>"""

    # ── §1 NLL overview ────────────────────────────────────────────────────
    nll_rows = ""
    for job in sorted(jobs, key=lambda j: (not np.isfinite(j.status.nll), j.status.nll)):
        is_best = np.isfinite(job.status.nll) and job.status.nll == best_nll
        delta   = job.status.nll - best_nll if np.isfinite(job.status.nll) else float("nan")
        two_d   = 2 * abs(delta)
        nll_str = f"{job.status.nll:.4f}" if np.isfinite(job.status.nll) else "NaN"
        d_str   = f"{delta:.4f}" if np.isfinite(delta) else "—"
        td_str  = f"{two_d:.2f}"  if np.isfinite(two_d)  else "—"
        conv    = '<span class="badge ok">✓</span>' if job.status.success else '<span class="badge warn">loop</span>'
        best_tag = '<span class="best-star">★ 最优</span>' if is_best else ""
        row_cls = ' class="nll-best"' if is_best else ""
        nll_rows += f"""
        <tr{row_cls}>
          <td style="font-family:monospace;font-size:12px">{job.name} {best_tag}</td>
          <td><b>{nll_str}</b></td>
          <td>{d_str}</td>
          <td>{td_str}</td>
          <td style="text-align:center">{job.status.ndf}</td>
          <td style="text-align:center">{len(job.loop_nlls)}</td>
          <td style="text-align:center">{conv}</td>
        </tr>"""

    sec_nll = f"""
    <div id="sec-nll" data-sec class="card">
      <div class="section-title">§1 &nbsp;NLL 总览对比</div>
      <table>
        <tr><th>作业名</th><th>NLL</th><th>ΔNLL</th><th>2ΔNLL</th>
            <th style="text-align:center">Ndf</th>
            <th style="text-align:center">循环数</th>
            <th style="text-align:center">收敛</th></tr>
        {nll_rows}
      </table>
    </div>"""

    # ── §2 Model selection ─────────────────────────────────────────────────
    sec_aic = f"""
    <div id="sec-aic" data-sec class="card">
      <div class="section-title">§2 &nbsp;模型选择（AIC）</div>
      {_render_aic_table(aic_results or [])}
    </div>"""

    # ── §3 Plots ───────────────────────────────────────────────────────────
    plot_cards = ""
    for label, path in plot_paths.items():
        if path and Path(path).exists():
            plot_cards += f"""
            <div class="plot-card">
              <h4>{label}</h4>
              {_img_tag(path, label)}
            </div>"""
    sec_plots = f"""
    <div id="sec-plots" data-sec class="card">
      <div class="section-title">§3 &nbsp;可视化摘要</div>
      <div class="plot-grid">{plot_cards}</div>
    </div>"""

    # ── §4 Per-job sections ────────────────────────────────────────────────
    job_cards = ""
    for i, job in enumerate(jobs):
        is_best  = np.isfinite(job.status.nll) and job.status.nll == best_nll
        cr       = check_results_per_job.get(job.name, {})
        items    = _all_check_items(cr)
        counts   = _status_counts(items)
        nll_str  = f"{job.status.nll:.4f}" if np.isfinite(job.status.nll) else "NaN"
        suggs    = (suggestions_per_job or {}).get(job.name, [])

        # Score pills
        score_pills = (
            f'<span class="score-pill ok">{counts[STATUS_OK]} OK</span>'
            f'<span class="score-pill warn">{counts[STATUS_WARN]} WARN</span>'
            f'<span class="score-pill fail">{counts[STATUS_FAIL]} FAIL</span>'
        )

        best_tag = '<span class="best-star">★ 最优作业</span>' if is_best else ""

        # Collapsed wrapper for non-best jobs
        inner = f"""
        <div class="job-header">
          <span class="job-name">{job.name}</span>
          {best_tag}
        </div>
        <div class="job-meta">
          <span>NLL = <b>{nll_str}</b></span>
          <span>Ndf = <b>{job.status.ndf}</b></span>
          <span>循环 = <b>{len(job.loop_nlls)}</b></span>
          <span>收敛 = <b>{'是' if job.status.success else '否（最优解来自循环）'}</b></span>
        </div>
        <div class="score-row">{score_pills}</div>
        {_render_suggestions(suggs, open_by_default=is_best)}
        {_render_cross_channel(cr, open_by_default=is_best)}
        {_render_checks_table(cr, open_by_default=False)}
        """

        card_cls = "card best-card" if is_best else "card"
        if is_best:
            job_cards += f'<div id="job-{i}" data-sec class="{card_cls}">{inner}</div>'
        else:
            # Wrap non-best in a collapsible details
            delta   = job.status.nll - best_nll if np.isfinite(job.status.nll) else float("nan")
            d_str   = f"ΔNLL={delta:.4f}" if np.isfinite(delta) else "NLL=NaN"
            fail_n  = counts[STATUS_FAIL]
            warn_n  = counts[STATUS_WARN]
            hint = (f' &nbsp; <span style="font-size:11.5px;font-weight:400;color:#718096">'
                    f'{d_str} &nbsp;·&nbsp; {fail_n} FAIL / {warn_n} WARN</span>')
            job_cards += f"""
            <div id="job-{i}" data-sec class="{card_cls}" style="padding:0">
              <details>
                <summary style="border-radius:12px;padding:14px 20px">
                  {job.name}{hint}
                </summary>
                <div class="details-body" style="border-radius:0 0 12px 12px;padding:18px 20px">
                  {inner}
                </div>
              </details>
            </div>"""

    sec_jobs = f"""
    <div class="section-title" style="margin-top:36px">
      §4 &nbsp;逐作业详细评估 + 优化建议
    </div>
    {job_cards}"""

    # ── Assemble ───────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>振幅分析评估报告 · BESIII</title>
  <style>{_CSS}</style>
</head>
<body>
<div id="lb-overlay">
  <span id="lb-close">&times;</span>
  <img id="lb-img" src="" alt="">
</div>

<div class="layout">
  {sidebar}
  <div class="main">
    {header}
    {sec_nll}
    {sec_aic}
    {sec_plots}
    {sec_jobs}
    <div class="footer">
      BESIII &phi;hh 耦合道振幅分析 &middot; 自动评估框架 &middot; {datetime.now().year}
    </div>
  </div>
</div>

<script>{_JS}</script>
</body>
</html>"""

    out_file = out_path / "report.html"
    out_path.mkdir(parents=True, exist_ok=True)
    out_file.write_text(html, encoding="utf-8")
    return out_file
