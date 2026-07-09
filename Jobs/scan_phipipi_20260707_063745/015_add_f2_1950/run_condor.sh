#!/bin/bash
set -euo pipefail

cd "/afs/cern.ch/work/h/hwen/public/pwa/auto-init/Jobs/scan_phipipi_20260707_063745/015_add_f2_1950"

export MPLCONFIGDIR=/tmp/matplotlib_cache_${USER:-condor}_$$
mkdir -p "${MPLCONFIGDIR}"
export PYTHON_BIN="/afs/cern.ch/work/h/hwen/public/conda/envs/tfpwa/bin/python3.12"

bash run_fit_witherr_fs.sh
