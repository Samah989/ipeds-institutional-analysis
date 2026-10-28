#!/bin/bash
# EXERCISE: Fill in the blanks to create a wrapper script.
# Hint: the wrapper installs packages, then runs your Python script.

set -euo pipefail

echo "[job] host=$(hostname) start=$(date -Iseconds)"

# 1. Create directories for output and packages
mkdir -p _______ _______

# 2. Install Python packages from requirements.txt into the deps/ folder
python3 -m pip install --target=_______ -r _______ 2>&1 | tail -1

# 3. Tell Python where to find the installed packages
export PYTHONPATH="$PWD/_______"

# 4. Run your analysis script, saving output to results/
python3 _______ --out _______/

echo "[job] done=$(date -Iseconds)"
ls -lh results/
