#!/bin/bash
# ---------------------------------------------------------------------------
# One-command IPEDS launcher  -  run from your Mac.
#
# Usage:
#     ./launch.sh pull        # run the IPEDS data pull ON THE ACCESS POINT
#                              #   directly (NOT as a condor job  -  see the
#                              #   note in osg/pull_data.submit for why)
#     ./launch.sh regress     # submit run_regression.submit (all 3 RQs)
#     ./launch.sh status      # just show condor_q
#     ./launch.sh pull-back   # rsync data/ + results/ back to laptop
# ---------------------------------------------------------------------------
set -euo pipefail

REMOTE_HOST="samah.alshrief@ap40.uw.osg-htc.org"
REMOTE_DIR="~/ipeds-analysis"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
CMD="${1:-status}"

case "$CMD" in
  pull|regress|status|pull-back)
    ;;
  *)
    echo "Usage: $0 {pull|regress|status|pull-back}"
    exit 2
    ;;
esac

# --- Step 1: sync code up (skip venv, cached data, and results) ---
if [ "$CMD" = "pull" ] || [ "$CMD" = "regress" ]; then
  echo "==> rsync ${LOCAL_DIR}/ → ${REMOTE_HOST}:${REMOTE_DIR}/"
  rsync -avz --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.ipynb_checkpoints' \
    --exclude 'data/*.parquet' --exclude 'results/*' --exclude '.DS_Store' \
    "${LOCAL_DIR}/" "${REMOTE_HOST}:${REMOTE_DIR}/"
fi

# --- Step 2/3: ssh in, prep, preflight, submit ---
run_remote() {
  local script="$1"
  ssh "$REMOTE_HOST" "cd ${REMOTE_DIR}/osg && ${script}"
}

if [ "$CMD" = "pull" ]; then
  echo "==> Running the IPEDS pull directly on the access point (not a condor job  - "
  echo "    execute nodes generally can't reach educationdata.urban.org; see"
  echo "    osg/pull_data.submit for why). This runs in your ssh session and"
  echo "    streams output live; it typically takes 30-60 min."
  run_remote "chmod +x *.sh && bash pull_data.sh"
  echo "==> Pull complete. Data is in ${REMOTE_DIR}/data on the access point."
  echo "    Run './launch.sh pull-back' to sync it to your laptop, or go"
  echo "    straight to './launch.sh regress' (it ships that data/ dir up itself)."

elif [ "$CMD" = "regress" ]; then
  echo "==> Preparing OSG env and running preflight..."
  run_remote "chmod +x *.sh && mkdir -p logs && bash preflight.sh"
  echo "==> Submitting run_regression.submit (queues 3 RQs)..."
  CLUSTER=$(ssh "$REMOTE_HOST" "cd ${REMOTE_DIR}/osg && condor_submit run_regression.submit" | tee /dev/stderr | awk '/submitted to cluster/ {print $NF}' | tr -d '.')
  echo "==> Cluster ID = $CLUSTER (three jobs, .0 .1 .2)"
  echo "==> Tailing RQ1 stdout  -  Ctrl-C to detach:"
  ssh "$REMOTE_HOST" "cd ${REMOTE_DIR}/osg && tail -F logs/regress.${CLUSTER}.0.out logs/regress.${CLUSTER}.0.err 2>/dev/null"

elif [ "$CMD" = "status" ]; then
  echo "==> condor_q on ${REMOTE_HOST}:"
  ssh "$REMOTE_HOST" "condor_q; echo; echo '--- last 5 completed jobs ---'; condor_history samah.alshrief | head -6"

elif [ "$CMD" = "pull-back" ]; then
  echo "==> rsync results back to ${LOCAL_DIR}/..."
  rsync -avz "${REMOTE_HOST}:${REMOTE_DIR}/data/"        "${LOCAL_DIR}/data/"    || true
  rsync -avz "${REMOTE_HOST}:${REMOTE_DIR}/osg/results/" "${LOCAL_DIR}/results/" || true
  echo "==> Done."
fi
