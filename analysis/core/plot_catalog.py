"""Metadata catalogue for all §6 visualisation plots.

Each entry in ``PLOT_META`` is keyed by the same label string used in the
``plot_paths`` dict produced by ``analyze.main()``.  Values supply:

  group        : thematic section shown as a small badge above the card title
  caption      : one-sentence plain-Chinese explanation of what the plot shows
  formula_html : HTML-formatted statistical formula (sub/sup tags + Unicode math)
  annotations  : list of short annotation strings rendered as tag chips

Prefix matching is also supported: keys starting with ``_`` act as fallbacks
matched by ``get_meta(label)`` via ``label.startswith(key[1:])`` after exact
lookup fails.
"""

from __future__ import annotations

PLOT_META: dict[str, dict] = {

    # ── Convergence diagnostics ──────────────────────────────────────────────
    "NLL 比较": {
        "group": "收敛性诊断",
        "caption": (
            "左图：各作业的绝对 NLL；右图：相对最优作业的 2ΔNLL，"
            "用于一次性判断哪个模型拟合最好以及差距的统计显著性。"
        ),
        "formula_html": (
            "2ΔNLL = 2(NLL<sub>j</sub> − NLL<sub>best</sub>)"
            " ~ χ²(Δk) &nbsp;"
            "<span class='fm-note'>Wilks 定理；"
            "Δk = 两作业自由参数差；嵌套模型时精确成立</span>"
        ),
        "annotations": [
            "★ = NLL 最优作业",
            "竖线 3.84 → 2σ（Δk=1）",
            "竖线 9.0 → 3σ",
            "竖线 25 → 5σ",
        ],
    },

    "NLL 稳定性": {
        "group": "收敛性诊断",
        "caption": (
            "每个作业在多次随机起点拟合中的 NLL 分布轨迹。"
            "散布越小、落在 best+1 内的比例越高，说明似然面越简单、全局最优越可信。"
            "点击左右箭头在各作业间翻页。"
        ),
        "formula_html": (
            "P<sub>global</sub> = 1 − (1 − f)<sup>N</sup> &nbsp;"
            "<span class='fm-note'>f = 落在 NLL<sub>best</sub>+1 内的循环比例；"
            "N = 总循环次数；目标 P ≥ 95%</span>"
        ),
        "annotations": [
            "虚线 = 全局最优 NLL",
            "阴影 = 各循环与最优的差值",
            "↔ 箭头翻页查看各作业",
        ],
    },

    # ── Fit fractions ────────────────────────────────────────────────────────
    "拟合分数（最优作业）": {
        "group": "拟合分数",
        "caption": (
            "最优作业两个衰变道中各共振态的对角拟合分数（FF）及 1σ 误差棒。"
            "颜色按显著性着色；标注数字为各分量的统计显著性。"
        ),
        "formula_html": (
            "FF<sub>i</sub> = ∫|A<sub>i</sub>|² dΦ / ∫|∑<sub>j</sub>A<sub>j</sub>|² dΦ"
            " &nbsp; Sig<sub>i</sub> = FF<sub>i</sub> / σ<sub>FF<sub>i</sub></sub>"
        ),
        "annotations": [
            "蓝色 Sig ≥ 3σ",
            "橙色 2σ ≤ Sig < 3σ",
            "红色 FF < 0（非物理）",
            "∑FF(diag) 标注在子图标题",
        ],
    },

    "FF 跨作业对比 ch0": {
        "group": "拟合分数",
        "caption": (
            "φπ⁺π⁻（ch0）道中各共振态拟合分数的跨作业对比，"
            "用于检验拟合结果对模型假设的稳健性。"
        ),
        "formula_html": (
            "FF<sub>i,ch</sub> = M<sub>ii</sub> &nbsp;"
            "<span class='fm-note'>M = 拟合分数矩阵（下三角 CSV 对称化得到）；"
            "对角元 M<sub>ii</sub> = 第 i 个共振态的独立贡献</span>"
        ),
        "annotations": ["★best = NLL 最优（完全不透明）", "其余作业 55% 透明度叠加"],
    },

    "FF 跨作业对比 ch1": {
        "group": "拟合分数",
        "caption": (
            "φK⁺K⁻（ch1）道中各共振态拟合分数的跨作业对比。"
        ),
        "formula_html": (
            "FF<sub>i,ch</sub> = M<sub>ii</sub> &nbsp;"
            "<span class='fm-note'>耦合道分析要求共享共振在两道中使用相同质量/宽度参数</span>"
        ),
        "annotations": ["★best = NLL 最优", "纵轴 = Fit Fraction（无量纲，通常 0–1）"],
    },

    # ── Parameter quality ────────────────────────────────────────────────────
    "误差矩阵（最优）": {
        "group": "参数质量",
        "caption": (
            "最优作业的参数相关矩阵热图（由 Hesse 误差矩阵归一化得到）。"
            "|ρ| 接近 ±1 表示两参数高度线性相关，可能存在简并，需诊断。"
        ),
        "formula_html": (
            "ρ<sub>ij</sub> = cov<sub>ij</sub>"
            " / √(cov<sub>ii</sub> · cov<sub>jj</sub>) &nbsp;"
            "<span class='fm-note'>cov = Hesse 矩阵的逆；"
            "|ρ| > 0.90 → warn；|ρ| > 0.95 → fail（参数可能简并）</span>"
        ),
        "annotations": [
            "红色 +1.0 = 完全正相关",
            "蓝色 −1.0 = 完全负相关",
            "白色 ≈ 0 = 不相关",
        ],
    },

    # ── Coupled-channel consistency ──────────────────────────────────────────
    "共享共振跨通道FF（最优）": {
        "group": "耦合道一致性",
        "caption": (
            "耦合道分析中，两道共有的共振态在 ch0 (φπ⁺π⁻) 与 ch1 (φK⁺K⁻) 中"
            "的拟合分数对比，检验耦合道约束的自洽性。"
        ),
        "formula_html": (
            "FF<sub>ch0</sub> + FF<sub>ch1</sub> ≲ 1.5 &nbsp;"
            "<span class='fm-note'>经验上限；若之和远超 1 说明存在强负干涉或参数异常</span>"
        ),
        "annotations": ["蓝色 = ch0 (φπ⁺π⁻)", "绿色 = ch1 (φK⁺K⁻)"],
    },

    # ── f0(980) physics ──────────────────────────────────────────────────────
    "f0(980)干涉项表（最优）": {
        "group": "f0(980) 物理",
        "caption": (
            "f0(980) 与各共振态的非对角拟合分数（干涉项）及相位差，"
            "正值为建设性干涉，负值为破坏性干涉。"
        ),
        "formula_html": (
            "∑<sub>i,j</sub> FF<sub>ij</sub> = 1 &nbsp;"
            "<span class='fm-note'>完备性条件；</span>"
            "FF<sub>ij</sub> = 2 Re[A<sub>i</sub>A<sup>*</sup><sub>j</sub>]"
            " / ∫|∑A|² dΦ"
        ),
        "annotations": ["红色 = 建设性干涉（FF > 0）", "蓝色 = 破坏性干涉（FF < 0）"],
    },

    # ── Model selection ──────────────────────────────────────────────────────
    "模型选择（AIC）": {
        "group": "模型选择",
        "caption": (
            "赤池信息量准则（AIC）综合惩罚参数复杂度与拟合质量。"
            "三面板分别为 ΔAIC、2ΔNLL 显著性和 Akaike 权重（相对模型概率）。"
        ),
        "formula_html": (
            "AIC = 2k + 2·NLL &nbsp; ; &nbsp; "
            "w<sub>i</sub> = "
            "e<sup>−ΔAIC<sub>i</sub>/2</sup>"
            " / ∑<sub>j</sub> e<sup>−ΔAIC<sub>j</sub>/2</sup> &nbsp;"
            "<span class='fm-note'>k = 自由参数数；"
            "ΔAIC < 2 实质等价；2–7 支持度明显较弱；> 7 基本无支持</span>"
        ),
        "annotations": ["绿色 ΔAIC < 2", "橙色 2 ≤ ΔAIC < 7", "红色 ΔAIC ≥ 7"],
    },

    # ── Comprehensive assessment ─────────────────────────────────────────────
    "评估清单（最优）": {
        "group": "综合评估",
        "caption": (
            "最优作业全部评估检验项的红绿灯总览，"
            "涵盖收敛性、误差矩阵正定性、参数 Pull、拟合分数、耦合道一致性等。"
        ),
        "formula_html": None,
        "annotations": ["✓ OK = 通过", "! WARN = 警告", "✗ FAIL = 失败"],
    },

    "优化建议（最优）": {
        "group": "综合评估",
        "caption": (
            "基于所有评估检验自动生成的优先级优化建议，"
            "P0（关键）→ P1（重要）→ P2（可选）排序。"
        ),
        "formula_html": None,
        "annotations": [
            "P0 = 关键，需立即处理",
            "P1 = 重要，建议下轮处理",
            "P2 = 可选改善",
        ],
    },

    # ── Prefix fallback for scan significance plots ──────────────────────────
    # Keys starting with "_" are treated as prefix matchers in get_meta():
    # label.startswith(key[1:]) is checked if exact match fails.
    "_扫描显著性": {
        "group": "扫描分析",
        "caption": (
            "各 scan 子作业相对本扫描自身基准模型（000_baseline）的 2ΔNLL 条形图。"
            "正值表示该模型改善了基准，负值表示变差。"
        ),
        "formula_html": (
            "σ = Φ<sup>−1</sup>(1 − p/2) &nbsp;"
            "<span class='fm-note'>p = P(χ²(df) ≥ 2ΔNLL)；"
            "add 操作 df = 2；replace 操作 df = 1；"
            "3σ 为重要阈值，5σ 为发现级</span>"
        ),
        "annotations": [
            "蓝色 = add（加入共振，df=2）",
            "绿色 = replace（替换共振，df=1）",
            "红色 = NLL 变差",
            "灰色 = 基准模型",
        ],
    },
}


def get_meta(label: str) -> dict:
    """Return metadata dict for *label*, falling back to prefix matches."""
    if label in PLOT_META:
        return PLOT_META[label]
    # Try prefix keys (key starts with "_", match if label starts with key[1:])
    for key, meta in PLOT_META.items():
        if key.startswith("_") and label.startswith(key[1:]):
            return meta
    return {}
