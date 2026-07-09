# BESIII φhh 振幅分析评估框架

BESIII 实验 `J/ψ → φπ⁺π⁻` 与 `J/ψ → φK⁺K⁻` 耦合道振幅拟合的**批量后处理评估工具**。

读取上游拟合产生的 `Jobs/` 输出，自动执行 10 项检查、**以各 scan 自身 baseline 为基准评估逐共振显著性**、生成图像、HTML 报告和结构化 `results.json`。

---

## 目录结构

```text
609/
├── run_analysis.sh             # 一键执行脚本（推荐入口）
├── requirements.txt            # Python 依赖（numpy / scipy / matplotlib）
├── Jobs/                       # 上游拟合作业输出（支持多种布局，见下）
├── analysis/                   # 评估框架源码
│   ├── analyze.py              # 命令行主入口 & 流程编排
│   ├── core/
│   │   ├── config.py           # 全局阈值配置（集中管理）
│   │   ├── job.py              # 作业数据加载（JobData / FitStatus）
│   │   ├── scan.py             # 扫描组数据（ScanGroup / ScanEntry / ScanSummary）
│   │   ├── checks.py           # 10 项评估检查函数
│   │   ├── model_selection.py  # AIC / BIC 模型选择
│   │   ├── suggestions.py      # 自动优化建议生成（P0/P1/P2）
│   │   ├── plot_catalog.py     # §6 图片说明/公式/标注元数据
│   │   └── pdg.py              # PDG 2024 参考值查询
│   ├── plots/
│   │   └── summary_plots.py    # 所有 matplotlib 图像（NLL / FF / 相关矩阵 / 扫描等）
│   └── reports/
│       └── html_report.py      # 自包含 HTML 报告生成器（§1–§7）
├── docs/
│   └── index.html              # 最新报告的发布副本（由脚本自动同步）
└── analysis_output/            # 默认输出目录（自动创建）
    ├── report.html             # HTML 报告（内嵌所有图片，§1–§7）
    ├── results.json            # 结构化检查结果
    └── plots/                  # 分析图像（.png）
```

### Jobs 目录布局

框架同时支持三种目录层次，并**自动识别 `scan_summary.txt` 以确定各 scan 的 baseline**：

```text
Jobs/                                          # --jobs 根目录
├── job_phihh_<timestamp>/                     # 布局①：直接 job 目录
│   └── final_params.json
├── scan_phipipi_<timestamp>/                  # 布局②：scan 目录（depth 2）
│   ├── scan_summary.txt                       #   ← baseline 识别来源
│   ├── 000_baseline/
│   │   └── final_params.json
│   ├── 001_add_NR_pipi_0/
│   │   └── final_params.json
│   └── ...
└── Jobs/                                      # 布局③：嵌套 Jobs 子文件夹（depth 3）
    └── scan_phipipi_<timestamp>/
        ├── scan_summary.txt
        ├── 000_baseline/
        │   └── final_params.json
        └── ...
```

`scan_summary.txt` 由上游 HPC 自动化脚本生成，记录扫描策略、基准共振列表以及每个子作业的动作类型（add / replace）。框架利用它：

1. 自动确定各扫描组的 **`000_baseline`** 作业
2. 以该 baseline NLL 为参照，计算每个 add / replace 子作业的 **ΔNLL 与统计显著性**（Wilks 定理，add 取 Δk=2，replace 取 Δk=1）
3. 在 HTML 报告 §4 和 `scan_significance_*.png` 图中集中呈现

用 `--no-scan` 参数可排除所有 scan 子作业，只分析顶层 `job_*` 目录；`--scans-only` 仅运行扫描显著性分析，跳过全局对比。

---

## 运行分析

### 推荐方式：`run_analysis.sh`

```bash
cd /path/to/609
chmod +x run_analysis.sh   # 首次使用

./run_analysis.sh                              # 默认分析 Jobs/
./run_analysis.sh --best-only                  # 只详细检查 NLL 最优 job
./run_analysis.sh --open                       # 完成后自动打开报告
./run_analysis.sh --jobs /path/to/Jobs         # 自定义 job 目录
./run_analysis.sh --output /path/to/out        # 自定义输出目录
./run_analysis.sh --no-report                  # 跳过 HTML，只输出图片和 JSON
./run_analysis.sh --help
```

脚本完整执行流程及日志输出如下：

```
══════════════════════════════════════════
   BESIII φhh 振幅分析评估框架
══════════════════════════════════════════

[INFO]  Jobs 目录 : .../Jobs
[INFO]  输出目录  : .../analysis_output
[INFO]  有效 jobs : N 个

... Python 分析输出 ...

[OK]    分析完成（耗时 Xs）
[INFO]  输出目录：.../analysis_output

生成文件：
  ✓  report.html
  ✓  results.json
  ✓  plots/*.png（N 张）

[INFO]  同步报告：cp .../analysis_output/report.html → .../docs/index.html
[OK]    已更新 docs/index.html

[INFO]  查看报告：open analysis_output/report.html
```

> 若使用了 `--no-report` 跳过 HTML 生成，则最后会打印：
> `[WARN]  未找到 report.html，跳过 docs/index.html 同步`

### 直接调用 Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 analysis/analyze.py --jobs Jobs
python3 analysis/analyze.py --jobs Jobs --best-only
python3 analysis/analyze.py --jobs Jobs --no-scan        # 排除 scan 子作业
python3 analysis/analyze.py --jobs Jobs --scans-only     # 仅扫描显著性分析
python3 analysis/analyze.py --jobs Jobs --no-report
```

### 完整参数说明

| 参数 | 说明 |
|------|------|
| `--jobs <path>` | job 根目录（默认：`Jobs/`） |
| `--output <path>` | 输出目录（默认：`analysis_output/`） |
| `--best-only` | 只对 NLL 最优 job 做详细检查 |
| `--no-scan` | 排除嵌套 scan 子作业，只加载顶层 `job_*` 目录 |
| `--scans-only` | 仅运行扫描显著性分析（跳过全局 NLL 对比） |
| `--no-report` | 跳过 HTML 报告，只生成图片和 `results.json` |
| `--open` | 完成后自动打开 `report.html`（仅 `run_analysis.sh`） |

---

## 数据流

```
discover_jobs()            扫描 job_* 目录，加载 final_params.json → list[JobData]
discover_scans()           扫描 scan_* 目录，加载 scan_summary.txt → list[ScanGroup]
    ↓
check_delta_nll()          跨作业 NLL 排名与 2ΔNLL 显著性（Wilks 定理）
run_all_checks()           对每个作业执行 10 项检查（见下）
compare_aic()              AIC / Akaike 权重模型选择
    ↓
plot_nll_comparison()      NLL 绝对值 + 2ΔNLL 图
plot_nll_stability()       每作业 NLL 收敛曲线（每作业独立一张 PNG）
plot_ff_comparison()       跨作业拟合分数对比（ch0 / ch1）
plot_scan_significance()   每个 scan 组的显著性柱状图
... 其他 plot_*()
    ↓
dump_results_json()        写出 results.json
generate_report()          写出 report.html（内嵌所有图片，§1–§7）
```

---

## 评估检查项（10 项）

所有阈值集中在 `analysis/core/config.py`，修改一处全局生效。

| # | 检查项 | ok | warn | fail |
|---|--------|----|------|------|
| 1 | **NLL 稳定性** | NLL 散布 < 5 | 5–20 | ≥ 20 |
| 2 | **ΔNLL 显著性** | 2ΔNLL < 9 (≈3σ) | 9–25 | ≥ 25 (≈5σ) |
| 3 | **误差矩阵正定性** | 全正定 | 半正定（零特征值） | 负特征值 |
| 4 | **参数 Pull vs PDG** | \|pull\| < 2σ | 2–3σ | ≥ 3σ |
| 5 | **拟合分数显著性** | FF/σ ≥ 3σ | 2–3σ 或 FF>1 | FF < 0 |
| 6 | **干涉完备性** | \|ΣFF−1\| < 0.05 | 0.05–0.15 | ≥ 0.15 |
| 7 | **参数相关性** | \|ρ\| < 0.90 | 0.90–0.95 | ≥ 0.95 |
| 8 | **跨通道一致性** | 无通道分离参数 | 发现通道分离参数 | 共享 FF 出现负值 |
| 9 | **Flatté 参数边界** | g 参数远离边界 | 误差 < 1e⁻¹⁰（接近边界） | 误差 < 1e⁻¹³（触边界） |
| 10 | **f0(980) 干涉结构** | FF_diag ≤ 0.5 | 0.5–1.0 | > 1.0（非物理） |

> **检查 9、10** 专门针对 f0(980) Flatté 参数化问题。当 `g_ππ` 触达边界（误差 ~10⁻¹³）时自动标红，提示拟合被人为限制，可能在 980 MeV 附近产生 S 形 pull 残差。

---

## 输入数据格式

每个作业目录至少包含：

```text
job_phihh_<name>/
└── final_params.json          # 必需：NLL、Ndf、参数值与误差
```

可选文件（提供后解锁对应检查项）：

| 文件 | 解锁检查 |
|------|----------|
| `error_matrix.npy` / `.txt` | 检查 3、7（误差矩阵、相关性） |
| `fit_frac_channel0/1.csv` | 检查 5、6、8、10（FF、完备性、跨通道、f0(980)） |
| `fit_frac_channel0/1_err.csv` | 检查 5（FF 显著性） |
| `States_phipipi/phikk.yaml` | 共振态标签（f0(980) 定位、相位差计算） |
| `Resonances.yaml` | Flatté 耦合边界（`g_min/g_max`），用于检查 9 |
| `slurm_logs/*.out` | NLL 收敛曲线（检查 1） |

### `final_params.json` 格式

```json
{
  "status": { "NLL": -11931.8, "Ndf": 136, "success": true },
  "value":  { "f0(980)_flatte_g_0": 0.1975, ... },
  "error":  { "f0(980)_flatte_g_0": 1.73e-13, ... }
}
```

### 拟合分数 CSV 格式

下三角矩阵，行 `i` 有 `i+1` 个元素（对角 + 下三角干涉项）：

```
FF_00
FF_10  FF_11
FF_20  FF_21  FF_22
...
```

框架自动对称化为完整方阵后提取 f0(980) 行/列。

---

## 输出文件

| 文件 | 说明 |
|------|------|
| `report.html` | 自包含 HTML，**7 个章节**，可直接浏览器打开 |
| `results.json` | 结构化 JSON，含所有检查结果、AIC、建议 |
| `plots/nll_comparison.png` | 所有作业绝对 NLL + 2ΔNLL 对比 |
| `plots/nll_stability_<job>.png` | **每个作业一张** NLL 收敛曲线（180 DPI），§6 内置翻页控件 |
| `plots/fit_fractions_*.png` | 双通道拟合分数柱状图（200 DPI） |
| `plots/ff_comparison_ch0/1.png` | 跨作业拟合分数对比 |
| `plots/corr_matrix_*.png` | 参数相关矩阵热图（200 DPI） |
| `plots/cross_channel_ff_*.png` | 共享共振跨通道 FF 对比 |
| `plots/f0980_interference_*.png` | f0(980) 干涉分数详表 |
| `plots/scan_significance_<scan>.png` | 各 scan 显著性柱状图 |
| `plots/model_selection_aic.png` | ΔAIC / 2ΔNLL / Akaike 权重 |
| `plots/checklist_*.png` | 交通灯式检查总览 |
| `plots/suggestions_*.png` | 优化建议优先级图 |

### HTML 报告章节

| 章节 | 内容 |
|------|------|
| §1 NLL 总览 | 所有作业排序表，ΔNLL、收敛状态 |
| §2 模型选择 | AIC、Akaike 权重、Wilks 显著性 |
| §3 f0(980) 干涉分数 | 干涉 FF 表、Flatté 边界警告、相位差 |
| §4 扫描显著性分析 | 各 scan 的 ΔNLL vs baseline 表 + 显著性柱状图 |
| §5 谱形对比 | 耦合道 vs 单道质量谱（需 `figure/` 图像） |
| §6 可视化摘要 | 图片网格，含统计公式/标注；点击放大，← → 键翻页 |
| §7 逐作业详细评估 | 10 项检查结果 + 优化建议时间轴 |

### §6 画廊功能

| 功能 | 操作 |
|------|------|
| 放大任意图片 | 单击图片 → 全屏 Lightbox |
| 在所有图片间翻页 | Lightbox 内 **← →** 方向键，或屏幕左右箭头按钮 |
| 关闭 Lightbox | **Esc** 键，或点击图片外区域 |
| NLL 稳定性翻页 | 卡片内 ← → 箭头（每个作业一张，就地切换） |
| 查看统计公式 | 每张图卡片下方展示公式块（Wilks / AIC / 相关系数等） |

---

## 扫描显著性分析（§4）

**以各 scan 自身的 baseline 为参照评估每个添加/替换操作的物理必要性。**

### scan_summary.txt 格式

```
# Scan generated : 2026-06-14 21:10:47
# Strategy       : add-one / replace (BW↔Flatté互斥对自动替换)
# Total jobs      : 14
# baseline pipi  : f0(500)_E791, f0(980)_flatte, f2(1270)_flatte, ...

tag                  action    added           replaces    jobdir
-----------------------------------------------------------------
000_baseline         baseline  None            None        /hpcfs/...
001_add_NR_pipi_0    add       NR_pipi_0+      None        /hpcfs/...
005_rep_f0_1370_flatte replace f0(1370)_flatte f0(1370)    /hpcfs/...
```

### §4 显著性表字段说明

| 列 | 说明 |
|----|------|
| 作业标签 | 子目录名，★ 标记全局最优 |
| 动作 | `baseline`（灰）/ `add`（蓝）/ `replace`（绿） |
| 添加/替换 | 操作的共振态名称 |
| NLL | 该子作业的拟合对数似然值 |
| ΔNLL | 相对于 **scan 自身 baseline** 的 NLL 差（负值=改善） |
| 2ΔNLL | Wilks 检验统计量（add: df=2；replace: df=1） |
| 显著性 | 转换为等效高斯标准差（σ），≥ 3σ 为重要，≥ 5σ 为发现级 |
| 结论 | 自动文字总结 |

### Python API 示例

```python
from analysis.core.scan import ScanGroup
from pathlib import Path

sg = ScanGroup.load(Path("Jobs/scan_phipipi_20260614_211047"))
for row in sg.delta_nll_table():
    print(f"{row['tag']:40s} {row['sigma']:5.1f}σ  {row['message']}")
```

---

## f0(980) 干涉分数表（§3）

| 列 | 说明 |
|----|------|
| FF(自身) | 该共振态的对角拟合分数 |
| FF(干涉·f0) | 与 f0(980) 的非对角矩阵元（红=建设性/蓝=破坏性） |
| 误差 | 来自 `fit_frac_channel*_err.csv` |
| 相位差/° | 由产生振幅复系数（`*_total_0r/i`）计算的相对相位 |

**诊断逻辑**：

- `FF_interf ≈ 0` → flat NR 与 f0(980) 基本不干涉，不是 pull 残差的来源
- `FF_interf > 0.1` 且 `g_ππ` 触边界 → 拟合需要更强 f0(980) 但被参数范围限制
- Flatté 边界警告（红色横幅）：`g_0` 误差 < 10⁻¹⁰ 时自动触发，提示放宽 `g_max`

---

## 环境要求

- Python 3.10+
- 依赖：`numpy >= 1.24`、`scipy >= 1.10`、`matplotlib >= 3.7`
- 无需 TensorFlow 或 tf-pwa（仅读取上游输出文件）

---

## 常见问题

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| `未找到包含 final_params.json 的 job 目录` | Jobs 目录中 `final_params.json` 在第 3 层（scan 子目录内） | 确认 `run_analysis.sh` 使用 `-maxdepth 3` 查找 |
| 输出中无 `NLL 稳定性` 图 | 所有作业均无 `slurm_logs/*.out` 或日志中无 `fun:` 行 | 确认日志路径；检查正则 `fun:\s*[+-]?\d+` |
| `_symmetrise` 警告：upper triangle non-zero | 上游 CSV 已是完整方阵而非下三角 | 正常警告，框架自动原样使用 |
| 扫描组加载为 0 个作业 | `scan_summary.txt` 缺失或格式异常 | 检查文件是否存在；手动查看表头格式 |
| HTML 报告 §6 公式乱码 | 浏览器字符集设置问题 | 确认页面 `<meta charset="utf-8">` 存在 |
| `--no-scan` 导致退出码 1 | `Jobs/` 目录仅含 scan 子目录，无 `job_*` 顶层作业 | 改用不带 `--no-scan` 的命令或 `--scans-only` |

---

## 快速开始

```bash
cd /path/to/609
./run_analysis.sh --open
# 报告自动在浏览器打开：analysis_output/report.html
# 同时同步至 docs/index.html
```

详细技术文档见 [`analysis/README.md`](analysis/README.md)。
