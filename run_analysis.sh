#!/usr/bin/env bash
# 振幅分析一键执行脚本
# 用法：
#   ./run_analysis.sh                        # 默认分析 Jobs/ 目录
#   ./run_analysis.sh --best-only            # 只详细检查最优 job
#   ./run_analysis.sh --jobs /other/Jobs     # 指定 job 目录
#   ./run_analysis.sh --no-report            # 跳过 HTML 报告
#   ./run_analysis.sh --open                 # 分析完成后自动打开报告

set -euo pipefail

# ── 路径配置 ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
ANALYSIS="$SCRIPT_DIR/analysis/analyze.py"
DEFAULT_JOBS="$SCRIPT_DIR/Jobs"
DEFAULT_OUTPUT="$SCRIPT_DIR/analysis_output"

# ── 颜色输出 ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── 参数解析 ──────────────────────────────────────────────────
EXTRA_ARGS=()
OPEN_REPORT=0
JOBS_DIR=""
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --open)        OPEN_REPORT=1; shift ;;
        --jobs)        JOBS_DIR="$2"; EXTRA_ARGS+=(--jobs "$2"); shift 2 ;;
        --output)      OUTPUT_DIR="$2"; EXTRA_ARGS+=(--output "$2"); shift 2 ;;
        --best-only)   EXTRA_ARGS+=(--best-only); shift ;;
        --no-report)   OPEN_REPORT=0; EXTRA_ARGS+=(--no-report); shift ;;
        -h|--help)
            echo -e "${BOLD}用法：${RESET} $0 [选项]"
            echo    "  --jobs <path>    指定 job 根目录（默认：Jobs/）"
            echo    "  --output <path>  指定输出目录（默认：analysis_output/）"
            echo    "  --best-only      只对最优 job 做详细检查"
            echo    "  --no-report      跳过 HTML 报告生成"
            echo    "  --open           分析完成后自动打开 report.html"
            exit 0 ;;
        *) error "未知参数：$1（用 --help 查看帮助）" ;;
    esac
done

[[ -z "$JOBS_DIR"   ]] && JOBS_DIR="$DEFAULT_JOBS"
[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$DEFAULT_OUTPUT"

# ── 环境检查 ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo -e "${BOLD}   BESIII φhh 振幅分析评估框架${RESET}"
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo ""

# Python 检查
if [[ ! -f "$VENV/bin/python3" ]]; then
    warn "未找到虚拟环境 .venv，尝试创建并安装依赖 …"
    python3 -m venv "$VENV" || error "创建虚拟环境失败，请确认 python3 已安装"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt" \
        || error "依赖安装失败，请检查网络或手动运行 pip install -r requirements.txt"
    success "虚拟环境创建完成"
fi

PYTHON="$VENV/bin/python3"

# Jobs 目录检查
if [[ ! -d "$JOBS_DIR" ]]; then
    error "Jobs 目录不存在：$JOBS_DIR"
fi

N_JOBS=$(find "$JOBS_DIR" -maxdepth 3 -name "final_params.json" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$N_JOBS" -eq 0 ]]; then
    error "在 $JOBS_DIR 中未找到包含 final_params.json 的 job 目录"
fi

info "Jobs 目录 : $JOBS_DIR"
info "输出目录  : $OUTPUT_DIR"
info "有效 jobs : $N_JOBS 个"
echo ""

# ── 执行分析 ──────────────────────────────────────────────────
START=$(date +%s)

"$PYTHON" "$ANALYSIS" \
    --jobs    "$JOBS_DIR"   \
    --output  "$OUTPUT_DIR" \
    "${EXTRA_ARGS[@]}"

END=$(date +%s)
ELAPSED=$(( END - START ))

echo ""
success "分析完成（耗时 ${ELAPSED}s）"
info "输出目录：$OUTPUT_DIR"

# 列出生成文件
REPORT="$OUTPUT_DIR/report.html"
DOCS_DIR="$SCRIPT_DIR/docs"
DOCS_INDEX="$DOCS_DIR/index.html"

if [[ -d "$OUTPUT_DIR" ]]; then
    echo ""
    echo -e "${BOLD}生成文件：${RESET}"
    [[ -f "$REPORT"  ]] && echo "  ✓  report.html"
    [[ -f "$OUTPUT_DIR/results.json" ]] && echo "  ✓  results.json"
    N_PNG=$(find "$OUTPUT_DIR/plots" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
    [[ "$N_PNG" -gt 0 ]] && echo "  ✓  plots/*.png（$N_PNG 张）"
fi

# 同步报告到 docs/index.html
if [[ -f "$REPORT" ]]; then
    echo ""
    info "同步报告：cp $REPORT → $DOCS_INDEX"
    mkdir -p "$DOCS_DIR"
    cp "$REPORT" "$DOCS_INDEX"
    success "已更新 docs/index.html"
else
    warn "未找到 $REPORT，跳过 docs/index.html 同步"
fi

# 自动打开报告（lxplus 无 GUI，open 命令不可用，仅打印路径）
if [[ "$OPEN_REPORT" -eq 1 && -f "$REPORT" ]]; then
    echo ""
    info "报告路径：$REPORT"
elif [[ -f "$REPORT" ]]; then
    echo ""
    info "查看报告：$REPORT"
fi
echo ""
