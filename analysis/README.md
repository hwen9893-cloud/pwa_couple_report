# BESIII 609 Analysis

这个目录包含 BESIII `J/ψ → φπ⁺π⁻` 与 `J/ψ → φK⁺K⁻` 耦合道振幅拟合结果的批量后处理工具。它不负责执行拟合本身，而是读取上游 `Jobs/job_*` 目录中的拟合输出，完成 NLL 对比、误差矩阵检查、PDG Pull、拟合分数检查、干涉完备性检查、参数相关性分析、**跨通道一致性检查**，并生成图像、HTML 报告和结构化 `results.json`。

## 目录结构

```text
analysis/
├── analyze.py                  # 命令行入口
├── core/
│   ├── config.py               # 所有检查阈值（集中管理）
│   ├── job.py                  # 单个 job 的输出数据加载器
│   ├── checks.py               # 8 类评估检查项
│   └── pdg.py                  # PDG 2024 参考值
├── plots/
│   └── summary_plots.py        # matplotlib 摘要图（含跨通道 FF 图）
└── reports/
    └── html_report.py          # 自包含 HTML 报告生成器
```

典型上游数据位于父目录：

```text
../Jobs/job_phihh_*/            # 拟合作业输出
../analysis_output/             # 默认分析输出目录
```

## 环境依赖

分析脚本只依赖轻量 Python 科学计算环境，不需要 TensorFlow 或 tf-pwa。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # numpy, scipy, matplotlib
```

建议使用 Python 3.10 或更新版本（macOS 系统命令为 `python3`，无 `python`）。`requirements.txt` 位于 `609/` 根目录。

## 快速运行

推荐从父目录 `609/` 运行：

```bash
cd /path/to/609
python3 analysis/analyze.py --jobs Jobs
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--jobs <path>` | 指定 job 根目录（默认 `../Jobs`，与代码中 `__file__` 位置一致） |
| `--output <path>` | 指定输出目录（默认 `<jobs_dir>/../analysis_output`） |
| `--best-only` | 仅对 NLL 最优的 job 做详细检查 |
| `--no-report` | 跳过 HTML 报告，只生成图片和 `results.json` |

也可以从 `analysis/` 目录内运行：

```bash
python3 analyze.py --jobs ../Jobs
```

## 输入文件约定

每个作业目录必须包含：

```text
Jobs/
└── job_*/
    └── final_params.json       # 必需，用于发现有效 job
```

`final_params.json` 最小 schema：

```json
{
  "status": { "NLL": -12345.6, "Ndf": 80, "success": true },
  "value":  { "f0_980_mass": 0.990, "f0_980_width": 0.060 },
  "error":  { "f0_980_mass": 0.005, "f0_980_width": 0.010 }
}
```

可选但推荐提供的文件：

| 文件 | 说明 |
|------|------|
| `error_matrix.npy` | 协方差矩阵（优先） |
| `error_matrix.txt` | 协方差矩阵纯文本格式 |
| `fit_frac_channel0.csv` | φπ⁺π⁻ 通道拟合分数矩阵（制表符或逗号分隔均可） |
| `fit_frac_channel0_err.csv` | 对应误差 |
| `fit_frac_channel1.csv` | φK⁺K⁻ 通道拟合分数矩阵 |
| `fit_frac_channel1_err.csv` | 对应误差 |
| `States_phipipi.yaml` | channel0 态标签列表 |
| `States_phikk.yaml` | channel1 态标签列表 |
| `slurm_logs/*.out` | 从 `fun:` 行提取每轮 NLL（支持正负及科学计数法） |

## 分析流程

```
discover_jobs()       → 扫描 job_* 目录，加载 final_params.json
    ↓
check_delta_nll()     → 跨 job NLL 排名与 2ΔNLL 显著性（使用 Ndf 差作为 χ² 自由度）
    ↓
run_all_checks()      → 逐 job 执行 8 类检查（见下表）
    ↓
plot_*()              → 生成 7 张图（见输出文件节）
    ↓
dump_results_json()   → 写出 results.json
    ↓
generate_report()     → 写出 report.html（含内嵌图片）
```

## 评估检查项与阈值

所有阈值集中在 `core/config.py`，修改一处即全局生效。

| 检查项 | ok | warn | fail |
|--------|-----|------|------|
| NLL 稳定性（散布） | < 5 | 5–20 | ≥ 20 |
| NLL 稳定性（收敛率） | ≥ 50% loops 在 best+1 内 | — | — |
| ΔNLL 显著性（2ΔNLL） | < 9 (≈3σ) | 9–25 | ≥ 25 (≈5σ) |
| 误差矩阵正定性 | 全正定 | 半正定（零特征值） | 负特征值 |
| 参数 Pull vs PDG | \|pull\| < 2 | 2–3σ | ≥ 3σ |
| 拟合分数显著性 | ≥ 3σ | 2–3σ 或 FF>1 | FF < 0 |
| 干涉完备性（\|ΣFF−1\|） | < 0.05 | 0.05–0.15 | ≥ 0.15 |
| 参数相关性（\|ρ\|） | < 0.90 | 0.90–0.95 | ≥ 0.95 |
| 跨通道耦合约束 | 无通道分离参数 | 发现通道分离参数 | — |
| 共享共振 FF 合计 | < 1.5 | ≥ 1.5 | 出现负值 |

> **ΔNLL 自由度说明**：`2ΔNLL ~ χ²(Δk)` 其中 `Δk = |Ndf_best − Ndf_job|`（即自由参数数目之差），
> 而非固定的 1。对等参数数的 job 退化为 `df=1`（保守估计）。

## PDG 参数名匹配规则

`core/pdg.py` 的 `pdg_lookup()` 对参数名与 PDG 共振名**双侧归一化**后再做子串匹配：去掉所有非字母数字字符、统一小写。因此以下命名方式均能正确匹配：

| 参数名示例 | 匹配共振 |
|-----------|---------|
| `f0_980_mass` | `f0(980)` |
| `F0980_Mass` | `f0(980)` |
| `f0(980)_mass` | `f0(980)` |
| `f2_1270_width` | `f2(1270)` |

## 耦合道作业分析策略

### 推荐 job 命名约定（model scan）

将 job 组织为「基准模型 + 单变体」网格，通过命名区分，便于框架未来支持自动配对显著性计算：

```
job_phihh_base                  基准模型
job_phihh_minus_f01710          去掉 f0(1710)
job_phihh_plus_f01500           新增 f0(1500)
job_phihh_spin2_f21270          将某共振改为自旋-2
```

### 跨通道共享共振检查

`check_cross_channel_consistency()` 执行以下三项：

1. **共振统计**：统计仅出现在 ch0、仅出现在 ch1、以及两通道共享的共振数目。
2. **耦合约束检测**：若参数名含 `ch0`/`ch1`/`phipipi`/`phikk` 等通道标识，则报 warn——这意味着本应共享的质量/宽度被分别参数化，破坏了耦合道约束。
3. **共享共振 FF 合理性**：对同时出现在两通道的共振，检查 `FF_ch0 + FF_ch1` 是否在合理范围内。

### 系统不确定度（model scan 完成后手动汇总）

将变体 job 的参数/FF 散布（max−min 或 RMS）作为模型系统误差：

```python
import numpy as np
from analysis.core.job import JobData
from pathlib import Path

jobs = [JobData.load(p) for p in Path("Jobs").glob("job_phihh_*")
        if (p / "final_params.json").exists()]
param = "f0_980_mass"
vals  = [j.params_value[param] for j in jobs if param in j.params_value]
print(f"{param}: mean={np.mean(vals):.4f}, syst_err={np.std(vals):.4f}")
```

## 输出文件

默认输出到 `<jobs_dir>/../analysis_output/`：

```text
analysis_output/
├── report.html                 # 自包含 HTML 报告（内嵌所有图片）
├── results.json                # 结构化检查结果（可供脚本/表格复用）
└── plots/
    ├── nll_comparison.png          # NLL 绝对值 + 2ΔNLL 条形图
    ├── nll_stability.png           # 每 loop NLL 分布
    ├── fit_fractions_*.png         # 最优 job 两通道拟合分数
    ├── ff_comparison_ch0.png       # ch0 FF 跨作业对比
    ├── ff_comparison_ch1.png       # ch1 FF 跨作业对比
    ├── corr_matrix_*.png           # 参数相关矩阵热图（含参数名标签）
    ├── cross_channel_ff_*.png      # 共享共振跨通道 FF 对比（新增）
    └── checklist_*.png             # 红绿灯评估总清单
```

`report.html` 内嵌所有图片（base64），可直接用浏览器打开，无需额外文件。

## 与上游拟合的关系

上游拟合在 `Jobs/job_phihh_*` 中完成，依赖 TensorFlow、tf-pwa 和 Slurm。当前 `analysis` 工具只读取已生成的输出文件，可在本地轻量环境独立运行。

推荐 workflow：

```bash
# 1. 完成上游拟合，生成 Jobs/job_phihh_*/final_params.json 等文件

# 2. 运行后处理评估
cd /path/to/609
python3 analysis/analyze.py --jobs Jobs

# 3. 查看报告
open analysis_output/report.html
```

## 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| `No valid job directories found` | `--jobs` 路径错误或目录内无 `final_params.json` | 检查路径；确认上游拟合已完成 |
| Pull 检查全部 warn「参数名未匹配 PDG」 | 参数名不含 `_mass`/`_width` 后缀或共振名差异过大 | 在 `core/pdg.py` 中添加别名条目 |
| NLL 为 NaN | `final_params.json` 缺 `status.NLL` 或拟合崩溃 | 检查上游日志；该 job 会被跳过排名 |
| 误差矩阵非正定 | 拟合未真正收敛（Hessian 计算在鞍点附近） | 增加 LOOP 次数或检查模型自由度 |
| `fit_frac_channel*.csv` 全为 0 | 文件为逗号分隔但旧版本硬编码 `\t` | 已修复（自动嗅探分隔符） |
| 跨通道图未生成 | 两通道 `States_*.yaml` 无共同共振名 | 检查 yaml 文件中的共振标签是否一致 |

## 已知限制

- `States_*.yaml` 使用简化文本解析，不依赖 PyYAML；复杂嵌套 YAML 可能解析不完整。
- PDG 参数匹配为模糊子串匹配，命名差异极大时仍可能漏检（此时 warn 会提示 `n_floated` 数目）。
- 无单元测试；重构后建议用一个合成 mini job 目录验证。
- 系统误差汇总需手动脚本完成（见上方示例）。
