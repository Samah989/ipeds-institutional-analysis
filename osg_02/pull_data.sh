#!/bin/bash
# Pull IPEDS data  -  run on the ACCESS POINT only (needs internet).
# Downloads 3 years of directory + grad-rates (~2 minutes).
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p deps data
python3 -m pip install --target=deps requests pandas pyarrow 2>&1 | tail -1
PYTHONPATH="$PWD/deps" python3 -c "from src.data_pull import fetch_all; fetch_all()"
echo "==> Data ready in data/"
ls -lh data/*.parquet
