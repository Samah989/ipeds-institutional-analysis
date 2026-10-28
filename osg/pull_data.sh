#!/bin/bash
# ---------------------------------------------------------------------------
# Download every IPEDS panel the three RQs need, into <repo>/data/.
#
# RUN THIS DIRECTLY ON THE ACCESS POINT (ap40)  -  do NOT condor_submit it.
# It makes live HTTPS calls to educationdata.urban.org, and OSPool execute
# nodes are opportunistic machines that generally do NOT have general
# outbound internet (only a proxy scoped to software repos like CVMFS/PyPI).
# A job needing an arbitrary third-party API belongs on the access point,
# where you already have normal internet. `launch.sh pull` runs this for you.
#
# Takes 20-40 minutes. Everything is cached to parquet, so if it is
# interrupted just run it again  -  completed years are skipped instantly.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root: src/ and data/ live here
export PS4='+ [pull $(date +%H:%M:%S)] '
set -x

mkdir -p data osg/deps
python3 -m ensurepip --user 2>/dev/null || true
python3 -m pip install --target=osg/deps -r osg/requirements-osg.txt
export PYTHONPATH="$PWD/osg/deps:${PYTHONPATH:-}"

python3 osg/pull_all_panels.py

set +x
echo "[pull] done $(date -Iseconds). data/ now holds:"
ls -lh data | tail -5
echo "[pull] $(ls data/*.parquet | wc -l) parquet files."
