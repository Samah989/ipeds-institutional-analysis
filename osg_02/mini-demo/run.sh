#!/bin/bash
set -euo pipefail

mkdir -p deps
python3 -m pip install --target=deps scipy pandas 2>&1 | tail -1
export PYTHONPATH="$PWD/deps"

python3 regression.py
