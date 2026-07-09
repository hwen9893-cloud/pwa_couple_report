#!/bin/bash
set -euo pipefail

########################################
# User settings: directly set here
########################################

PYTHON_BIN="${PYTHON_BIN:-/hpcfs/bes/gpupwa/wenhw/miniconda3/envs/tf-pwa/bin/python3.12}"
FIT_SCRIPT="fit_witherr_fs.py"
INIT_PARAMS="${INIT_PARAMS:-init_params.json}"

# 联合拟合的两个 yaml（φπ⁺π⁻ 和 φK⁺K⁻）
YAML_1="config_phipipi.yaml"
YAML_2="config_phikk.yaml"

# 是否共享全部总系数（一般保持 false，只共享产生侧参数）
TOTAL_SAME=false

# fit settings
LOOP=5
MAXITER=50000

########################################
# Checks
########################################

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: python executable '$PYTHON_BIN' not found or not executable"
  exit 1
fi

if [[ ! -f "$FIT_SCRIPT" ]]; then
  echo "Error: fit script '$FIT_SCRIPT' not found in $(pwd)"
  exit 2
fi

INIT_ARGS=()
if [[ -f "$INIT_PARAMS" ]]; then
  INIT_ARGS=(-i "$INIT_PARAMS")
  INIT_STATUS="found, will use ${INIT_PARAMS}"
else
  INIT_STATUS="not found, will use random initial parameters"
fi

for YAML in "$YAML_1" "$YAML_2"; do
  if [[ ! -f "$YAML" ]]; then
    echo "Error: YAML file '$YAML' not found in $(pwd)"
    exit 3
  fi
done

CONFIG_ARG="${YAML_1},${YAML_2}"

########################################
# Node / environment info
########################################

echo "========== NODE / ENVIRONMENT INFO =========="
echo "DATE          : $(date)"
echo "HOSTNAME      : $(hostname)"
echo "PWD           : $(pwd)"
echo "FIT SCRIPT    : ${FIT_SCRIPT}"
echo "INIT PARAMS   : ${INIT_PARAMS}"
echo "INIT STATUS   : ${INIT_STATUS}"
echo "PYTHON BIN    : ${PYTHON_BIN}"
echo "YAML 1        : ${YAML_1}"
echo "YAML 2        : ${YAML_2}"
echo "CONFIG ARG    : ${CONFIG_ARG}"
echo "TOTAL_SAME    : ${TOTAL_SAME}"
echo "LOOP          : ${LOOP}"
echo "MAXITER       : ${MAXITER}"

# Avoid CUDA stub libraries shadowing the real NVIDIA driver libraries on batch nodes.
if [[ "${LD_LIBRARY_PATH:-}" == *"/stubs"* ]]; then
  _clean_ld=""
  IFS=':' read -r -a _ld_parts <<< "${LD_LIBRARY_PATH}"
  for _ld_part in "${_ld_parts[@]}"; do
    [[ "$_ld_part" == *"/stubs"* ]] && continue
    if [[ -z "$_clean_ld" ]]; then
      _clean_ld="$_ld_part"
    else
      _clean_ld="${_clean_ld}:${_ld_part}"
    fi
  done
  export LD_LIBRARY_PATH="$_clean_ld"
  unset _clean_ld _ld_part _ld_parts
  echo "LD_LIBRARY_PATH: removed CUDA stub library paths"
fi

echo
echo "---------- CPU INFO ----------"
if command -v lscpu >/dev/null 2>&1; then
  lscpu | grep -E 'Model name|CPU\(s\)|Thread|Core|Socket' || true
else
  echo "lscpu not found"
fi

echo
echo "---------- MEMORY INFO ----------"
if command -v free >/dev/null 2>&1; then
  free -h || true
else
  echo "free not found"
fi

echo
echo "---------- GPU / CUDA INFO ----------"
echo "CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "CONDOR GPUs        : ${_CONDOR_AssignedGPUs:-${AssignedGPUs:-<unset>}}"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[nvidia-smi -L]"
  nvidia-smi -L || true
  echo
  echo "[nvidia-smi summary]"
  nvidia-smi || true
else
  echo "WARNING: nvidia-smi not found -> 此节点可能没有 GPU"
fi

echo
echo "---------- PYTHON / TF INFO ----------"
echo "PYTHON_BIN  : $PYTHON_BIN"
"$PYTHON_BIN" -V 2>/dev/null || echo "python not found"

"$PYTHON_BIN" - << 'EOF' 2>/dev/null || true
import sys
print("Python exec:", sys.executable)
try:
    import tensorflow as tf
    print("TensorFlow version:", tf.__version__)
    gpus = tf.config.list_physical_devices("GPU")
    print("TF visible GPUs:", gpus)
except Exception as e:
    print("TensorFlow import failed:", e)
EOF

echo "=============================================="
echo

########################################
# Cleanup old outputs
########################################

mkdir -p figure

rm -f asy.csv gls.csv fit_fracerror.csv
rm -f fit_frac.csv fit_frac_err.csv
rm -f fit_frac_channel*.csv fit_frac_channel*_err.csv
rm -f par.root error_matrix.txt final_params.json break_params.json .run_start
rm -f figure/*.png figure/*.pdf figure/*.root || true

########################################
# Run joint fit
########################################

echo "========== START JOINT FIT (φhh) =========="
START_TIME=$(date +%s)

if [[ "$TOTAL_SAME" == "true" ]]; then
  "$PYTHON_BIN" "$FIT_SCRIPT" \
    --config "$CONFIG_ARG" \
    "${INIT_ARGS[@]}" \
    --total-same \
    -l "$LOOP" \
    -x "$MAXITER"
else
  "$PYTHON_BIN" "$FIT_SCRIPT" \
    --config "$CONFIG_ARG" \
    "${INIT_ARGS[@]}" \
    -l "$LOOP" \
    -x "$MAXITER"
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo
echo "========== JOINT FIT FINISHED =========="
echo "END TIME   : $(date)"
echo "ELAPSED    : ${ELAPSED} s"
echo "========================================"
