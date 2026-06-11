#!/bin/bash
#SBATCH -J job_phihh_20260608_220622
#SBATCH -p gpu
#SBATCH --qos=pwanormal
#SBATCH --account=gpupwa
#SBATCH --gres=gpu:v100:1
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=4
#SBATCH --mem=30G
#SBATCH -o /hpcfs/bes/gpupwa/wenhw/hwen_couple/Jobs/job_phihh_20260608_220622/slurm_logs/slurm_%j.out
#SBATCH -e /hpcfs/bes/gpupwa/wenhw/hwen_couple/Jobs/job_phihh_20260608_220622/slurm_logs/slurm_%j.err

set -euo pipefail

# 切换到工作目录（所有相对路径都基于此）
cd /hpcfs/bes/gpupwa/wenhw/hwen_couple/Jobs/job_phihh_20260608_220622

# 避免 matplotlib 写入 home 目录（集群上 HOME 可能不可写）
export MPLCONFIGDIR=/tmp/matplotlib_cache_${SLURM_JOB_ID}

# Python 路径透传给拟合脚本
export PYTHON_BIN="/hpcfs/bes/gpupwa/wenhw/miniconda3/envs/tf-pwa/bin/python3.12"

bash phihh_run_fit_witherr_fs.sh
