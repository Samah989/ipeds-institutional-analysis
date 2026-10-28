#!/bin/bash
# Preflight  -  run before condor_submit to catch common mistakes.
set -u
cd "$(dirname "$0")"

ok=0; fail=0
check() { if eval "$1"; then echo "  [ok] $2"; ((ok++)); else echo "  [FAIL] $2  →  $3"; ((fail++)); fi; }

echo "==> Preflight checks"
check '[ -d logs ]'                           'logs/ exists'               'mkdir -p logs'
check '[ -x run.sh ]'                        'wrapper is executable'       'chmod +x run.sh'
check '[ -r requirements.txt ]'              'requirements present'        'check file exists'
check '[ -r run_analysis.py ]'               'analysis script present'     'check file exists'
check '[ -d src ] && [ -f src/__init__.py ]'  'src/ package OK'            'touch src/__init__.py'
check '[ -d data ] && ls data/*.parquet >/dev/null 2>&1'  'data/ has parquet files'  'run: bash pull_data.sh'
check 'grep -qE "^[a-z]==" requirements.txt'  'deps are pinned (==)'      'pin versions in requirements.txt'
check 'command -v condor_submit >/dev/null'   'condor_submit in PATH'      'are you on the access point?'

echo
if [ $fail -eq 0 ]; then echo "==> All $ok checks passed."; exit 0
else echo "==> $fail problem(s). Fix and re-run."; exit 1; fi
