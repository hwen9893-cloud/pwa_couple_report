# analysis/ — 批量后处理评估模块

BESIII `J/ψ → φπ⁺π⁻` / `J/ψ → φK⁺K⁻` 耦合道振幅拟合后处理框架的核心源码目录。
读取上游拟合产生的 `Jobs/` 输出，执行 **10 项检查**、扫描显著性分析、图像生成与 HTML 报告。

> 推荐从父目录 `609/` 使用，详见 `../README.md`。本文档面向开发者，介绍模块内部结构。

---

## 目录结构

```text
analysis/
├── analyze.py              # 命令行主入口 & 流程编排
├── core/
│   ├── config.py           # 所有检查阈值（集中管理）
│   ├── job.py              # 单作业数据加载（JobData / FitStatus）
│   ├── scan.py             # 扫描组数据（ScanGroup / ScanEntry / ScanSummary）
│   ├── checks.py           # 10 项评估检查函数
│   ├── model_selection.py  # AIC / BIC 模型选择
│   ├── suggestions.py      # 自动优化建议生成（P0/P1/P2）
│   ├── plot_catalog.py     # §6 图片说明 / 公式 / 标注元数据
│   └── pdg.py              # PDG 2024 参考值查询
├── plots/
│   └── summary_plots.py    # 所有 matplotlib 图像（NLL / FF / 相关矩阵 / 扫描等）
└── reports/
    └── html_report.py      # 自包含 HTML 报告生成器（§1–§7）
```

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
plot_nll_stability()       每作业 NLL 收敛曲线（返回 list[Path]，一作业一 PNG）
plot_ff_comparison()       跨作业拟合分数对比（ch0 / ch1）
plot_scan_significance()   每个 scan 组的显著性柱状图
... 其他 plot_*()
    ↓
dump_results_json()        写出 results.json
generate_report()          写出 report.html（内嵌所有图片，§1–§7）
```

---

## 10 项评估检查（`core/checks.py`）

所有阈值集中在 `core/config.py`，修改一处全局生效。

| # | 检查函数 | ok | warn | fail |
|---|----------|----|------|------|
| 1 | `check_nll_stability` | NLL 散布 < 5 | 5–20 | ≥ 20 |
| 2 | `check_delta_nll` | 2ΔNLL < 9 (≈3σ) | 9–25 | ≥ 25 (≈5σ) |
| 3 | `check_error_matrix` | 全正定 | 半正定（零特征值） | 负特征值 |
| 4 | `check_parameter_pulls` | \|pull\| < 2σ | 2–3σ | ≥ 3σ |
| 5 | `check_fit_fraction_significance` | FF/σ ≥ 3σ | 2–3σ 或 FF>1 | FF < 0 |
| 6 | `check_interference_completeness` | \|ΣFF−1\| < 0.05 | 0.05–0.15 | ≥ 0.15 |
| 7 | `check_parameter_correlations` | \|ρ\| < 0.90 | 0.90–0.95 | ≥ 0.95 |
| 8 | `check_cross_channel_consistency` | 无通道分离参数 | 发现通道分离参数 | 共享 FF 出现负值 |
| 9 | `check_flatte_boundaries` | g 参数远离边界 | 误差 < 1e⁻¹⁰（接近边界） | 误差 < 1e⁻¹³（触边界） |
| 10 | `check_f0980_interference` | FF_diag ≤ 0.5 | 0.5–1.0 | > 1.0（非物理） |

---

## 模块说明

### `analyze.py`

主程序入口，负责：

- **作业发现**：`discover_jobs(jobs_dir, include_scan=False, allow_empty=True)`
  仅加载顶层 `job_*` 目录（不加载 scan 子作业，避免重复计数）
- **扫描发现**：`discover_scans(jobs_dir)` → `list[ScanGroup]`
  自动识别 `scan_*` 目录并寻找 `scan_summary.txt`
- **自适应模式**：若目录内无直接 `job_*` 目录，自动切换为 `scans-only` 模式
- **`plot_paths`** 类型为 `dict[str, Path | list[Path] | None]`，NLL 稳定性存储为 `list[Path]`

### `core/job.py`

- `JobData.load(path)` 加载单个作业目录的所有数据文件
- `_symmetrise(arr)` 将下三角 CSV 对称化为完整方阵；若输入已为全阵则警告并原样返回
- `_load_loop_nlls()` 解析 `slurm_logs/*.out`，正则支持正负号和科学计数法

### `core/scan.py`

- `ScanGroup.load(path)` 加载一个 scan 目录，解析 `scan_summary.txt` 确定 baseline
- `sg.delta_nll_table()` 返回相对 baseline NLL 的完整结果表
- 显著性计算：`add` 操作 Δk=2，`replace` 操作 Δk=1（Wilks 定理）

### `core/plot_catalog.py`

为 §6 每张图提供元数据，供 `html_report.py` 渲染增强卡片：

```python
from analysis.core.plot_catalog import get_meta

meta = get_meta("NLL 稳定性")
# meta["caption"]      → 中文说明
# meta["formula_html"] → HTML 格式统计公式（含 <sub>/<sup> 标记）
# meta["annotations"]  → 标注标签列表
# meta["group"]        → 分组徽章文字
```

`get_meta(label)` 先做精确匹配，失败后尝试前缀匹配（以 `_` 开头的键）。

### `core/checks.py`

- `check_parameter_correlations` 使用 `np.triu_indices` 向量化，避免 O(n²) Python 循环

### `plots/summary_plots.py`

- `_save(fig, out_path, name, dpi=150)` — 支持自定义 DPI
- `plot_nll_stability(jobs, out_path) → list[Path]` — **每作业一张 PNG**（180 DPI），不再合并为单图
- 误差矩阵、拟合分数图使用 200 DPI
- CJK 字体在模块导入时一次性配置（`_setup_cjk_font()`）

### `reports/html_report.py`

自包含 HTML 生成器，所有图片以 base64 内嵌：

- `_img_src(path)` — 返回裸 `data:image/...;base64,...` URI
- `_img_tag(path, alt, caption)` — 返回 `<img>` 标签，附 `data-caption` 属性
- `_render_enhanced_plot_card(label, paths)` — 支持单图（`Path`）和多图滑动窗（`list[Path]`）；从 `plot_catalog.get_meta()` 自动附加说明/公式/标注
- `_CSS_ENHANCED` — 公式块（`.fm-block`）、标注标签（`.plot-ann-tag`）、滑动窗（`.slideshow/.ss-arrow`）、升级版 Lightbox CSS
- `_JS` — 画廊 JS（`_initGallery`）、滑动窗 JS（`_initSlideshows`）、侧边栏高亮

#### §6 交互功能

| 功能 | 实现 |
|------|------|
| 点击放大 | `_initGallery()` 收集所有 `.plot-card img` 等，分配顺序 ID |
| Lightbox 翻页 | ← → 键盘 / `#lb-prev` `#lb-next` 按钮，计数显示 `n / total` |
| NLL 稳定性卡片内翻页 | `_initSlideshows()` 管理 `.slideshow` 内的 `.slide` 切换 |
| 公式渲染 | 纯 HTML `<sub>/<sup>` + Unicode 数学符号，无外部依赖 |

---

## 输入文件约定

每个作业目录最低需要：

```text
Jobs/job_*/
└── final_params.json    # NLL / Ndf / success / params value & error
```

可选文件（缺失时对应检查跳过）：

| 文件 | 解锁检查 |
|------|----------|
| `error_matrix.npy` 或 `.txt` | 检查 3、7（误差矩阵、相关性） |
| `fit_frac_channel0/1.csv` | 检查 5、6、8、10（FF、完备性、跨通道、f0(980)） |
| `fit_frac_channel0/1_err.csv` | 检查 5（FF 显著性） |
| `States_phipipi/phikk.yaml` | 共振态标签（f0(980) 定位、相位差计算） |
| `Resonances.yaml` | Flatté 参数边界（检查 9） |
| `slurm_logs/*.out` | NLL 收敛曲线（检查 1） |

---

## 环境要求

- Python 3.10+
- `numpy >= 1.24`、`scipy >= 1.10`、`matplotlib >= 3.7`
- 无需 TensorFlow 或 tf-pwa

```bash
cd /path/to/609
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 常见问题

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| 输出中无 `NLL 稳定性` 图 | 所有作业均无 `slurm_logs/*.out` 或日志中无 `fun:` 行 | 确认日志路径；检查正则 `fun:\s*[+-]?\d+` |
| `_symmetrise` 警告：upper triangle non-zero | 上游 CSV 已是完整方阵而非下三角 | 正常警告，框架自动原样使用 |
| 扫描组加载为 0 个作业 | `scan_summary.txt` 缺失或格式异常 | 检查文件是否存在；手动查看表头格式 |
| HTML 报告 §6 公式乱码 | 浏览器字符集设置问题 | 确认页面 `<meta charset="utf-8">` 存在 |
| `--no-scan` 导致退出码 1 | `Jobs/` 目录仅含 scan 子目录，无 `job_*` 顶层作业 | 正常行为；改用不带 `--no-scan` 的命令或 `--scans-only` |
