# BESIII φhh 振幅分析评估框架

BESIII 实验 `J/ψ → φπ⁺π⁻` 与 `J/ψ → φK⁺K⁻` 耦合道振幅拟合的**批量后处理评估工具**。

本工具读取上游拟合产生的 `Jobs/job_phihh_*/` 输出，自动执行 NLL 对比、误差矩阵检查、PDG Pull、拟合分数检查、干涉完备性检查、参数相关性分析、跨通道一致性检查，并生成图像、HTML 报告和结构化 `results.json`。

---

## 目录结构

```text
609/
├── run_analysis.sh             # 一键执行脚本（推荐入口）
├── requirements.txt            # Python 依赖（numpy / scipy / matplotlib）
├── Jobs/                       # 上游拟合作业输出（每个子目录含 final_params.json）
├── analysis/                   # 评估框架源码
│   ├── analyze.py              # 命令行主入口
│   ├── core/                   # 检查逻辑（config / job / checks / pdg 等）
│   ├── plots/                  # matplotlib 图像生成
│   └── reports/                # HTML 报告生成器
└── analysis_output/            # 默认输出目录（自动创建）
    ├── report.html             # 自包含 HTML 报告（内嵌所有图片）
    ├── results.json            # 结构化检查结果
    └── plots/                  # 分析图像（.png）
