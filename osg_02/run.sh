#!/bin/bash
set -euo pipefail

echo "[job] host=$(hostname) start=$(date -Iseconds)"

# Install Python dependencies
mkdir -p results deps
python3 -m pip install --target=deps -r requirements.txt 2>&1 | tail -1
export PYTHONPATH="$PWD/deps"

# Run the analysis
python3 run_analysis.py --bootstrap 200 --out results/

echo "[job] done=$(date -Iseconds)"
ls -lh results/
