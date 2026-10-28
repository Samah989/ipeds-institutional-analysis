#!/bin/bash
# ---------------------------------------------------------------------------
# OSG wrapper: run one RQ regression at scale. Installs pip deps to a local
# target dir (works with osgvo-ubuntu-20.04 which lacks python3-venv).
# ---------------------------------------------------------------------------
set -euo pipefail
export PS4='+ [regress $(date +%H:%M:%S)] '
set -x

RQ="${1:?usage: run_regression.sh <rq_number 1|2|3>}"

echo "[regress] rq=$RQ host=$(hostname) start=$(date -Iseconds)"
echo "[regress] pwd=$(pwd)  data/ contents:"
ls -la data 2>/dev/null | head -20 || echo "  (no data/ dir yet)"

mkdir -p results deps
python3 -m ensurepip --user 2>/dev/null || true
python3 -m pip install --upgrade --target=deps pip 2>/dev/null || python3 -m pip install --user --upgrade pip
python3 -m pip install --target=deps -r requirements-osg.txt

export PYTHONPATH="$PWD/deps:${PYTHONPATH:-}"
python3 run_regression.py --rq "$RQ" --bootstrap 1000 --out results/

echo "[regress] rq=$RQ done=$(date -Iseconds)  outputs:"
ls -lh results
