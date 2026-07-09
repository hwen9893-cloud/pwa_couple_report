#!/bin/bash
set -euo pipefail

cd "/afs/cern.ch/work/h/hwen/public/pwa/auto-init/Jobs/scan_phipipi_20260705_135358/008_rep_f0_1710_flatte"

export MPLCONFIGDIR=/tmp/matplotlib_cache_${USER:-condor}_$$
mkdir -p "${MPLCONFIGDIR}"
export PYTHON_BIN="/afs/cern.ch/work/h/hwen/public/conda/envs/tfpwa/bin/python3.12"

bash run_fit_witherr_fs.sh
