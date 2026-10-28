#!/bin/bash
# ---------------------------------------------------------------------------
# Pre-submit sanity check. Run this on the OSG access point in the osg/ dir
# BEFORE condor_submit. Confirms the common gotchas are handled.
#
#     cd ~/ipeds-analysis/osg && bash preflight.sh
#
# Exits 0 if all clear, non-zero (and prints fixes) otherwise.
# ---------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"

problems=0
say_ok()   { echo "  [ok]    $1"; }
say_fail() { echo "  [FAIL]  $1"; problems=$((problems+1)); }
say_warn() { echo "  [warn]  $1"; }

echo "==> IPEDS preflight in $(pwd)"

# 1. logs/ directory  -  HTCondor won't create it and refuses to write there
if [ -d logs ]; then
  say_ok "logs/ directory exists"
else
  say_fail "logs/ directory missing         fix:  mkdir -p logs"
fi

# 2. Wrapper scripts executable  -  rsync from macOS often drops the +x bit
for w in pull_data.sh run_regression.sh; do
  if [ -f "$w" ]; then
    if [ -x "$w" ]; then
      say_ok "$w is executable"
    else
      say_fail "$w is not executable        fix:  chmod +x $w"
    fi
  fi
done

# 3. Required inputs present
[ -r requirements-osg.txt ]      && say_ok "requirements-osg.txt present"      || say_fail "requirements-osg.txt missing"
[ -r pull_all_panels.py ]        && say_ok "pull_all_panels.py present"        || say_fail "pull_all_panels.py missing"
[ -r run_regression.py ]         && say_ok "run_regression.py present"         || say_fail "run_regression.py missing"

# 4. ../src package (transfer_input_files = ..., ../src)
if [ -d ../src ] && [ -f ../src/__init__.py ]; then
  say_ok "../src package present with __init__.py"
elif [ -d ../src ]; then
  say_fail "../src exists but has no __init__.py    fix:  touch ../src/__init__.py"
else
  say_fail "../src not found                          fix:  rsync the full project up"
fi

# 5. ../data must hold the five topic slices run_regression actually reads.
#    Filenames are <topic>__<year>__<filter-slug>__<hash>.parquet, and the
#    filter slug matters: a sector-1 pull will not satisfy an unfiltered read.
if [ -d ../data ]; then
  missing=""
  for t in "directory__*__all__" "finance__*__all__" \
           "sfa-all-undergraduates__*__all__" "grad-rates__*__race-99_sex-99__" \
           "grad-rates-pell__*__all__"; do
    n=$(ls ../data/${t}*.parquet 2>/dev/null | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
      say_ok "../data has $n ${t%%__*} slice(s)"
    else
      missing="$missing ${t%%__*}"
    fi
  done
  [ -n "$missing" ] && say_fail "no cached data for:$missing    fix:  bash pull_data.sh"

  # Slices pulled with other filters are dead weight in transfer_input_files.
  stale=$(ls ../data/*sector-*.parquet ../data/*fips-*.parquet 2>/dev/null | wc -l | tr -d ' ')
  [ "${stale:-0}" -gt 0 ] && say_warn "$stale cached file(s) from other filter sets are unused, but still shipped to every job  -  delete them to shrink the transfer"

  # Pinned dependencies: version floors let two machines resolve differently.
  if grep -qE '^[a-z0-9-]+==' requirements-osg.txt; then
    say_ok "requirements-osg.txt uses exact pins"
  else
    say_fail "requirements-osg.txt is not pinned  -  laptop and OSPool results may differ"
  fi
else
  say_fail "../data does not exist                    fix:  bash pull_data.sh"
fi

# 6. OSG-side tools
command -v condor_submit >/dev/null 2>&1 \
  && say_ok "condor_submit in PATH" \
  || say_fail "condor_submit not in PATH  -  are you actually on the access point?"

command -v condor_status >/dev/null 2>&1 && {
  avail=$(condor_status -avail 2>/dev/null | grep -c "^slot" || true)
  if [ "${avail:-0}" -gt 100 ]; then
    say_ok "condor_status reports ${avail} available slots  -  pool looks healthy"
  else
    say_warn "condor_status reports only ${avail:-0} available slots  -  pool may be quiet"
  fi
}

# 7. Submit files parse cleanly
# (pull_data.submit is deliberately not submitted anymore  -  the data pull
# runs directly on the access point instead; see that file for why.)
for s in run_regression.submit; do
  if [ -f "$s" ]; then
    if condor_submit -dry-run /tmp/preflight.$s.dry "$s" >/dev/null 2>&1; then
      say_ok "$s parses cleanly (condor_submit -dry-run)"
    else
      say_fail "$s failed dry-run parse                fix:  condor_submit -dry-run /tmp/dry $s"
    fi
    rm -f /tmp/preflight.$s.dry
  fi
done

echo
if [ $problems -eq 0 ]; then
  echo "==> All checks passed. Safe to condor_submit."
  exit 0
else
  echo "==> $problems problem(s) above. Fix and re-run preflight."
  exit 1
fi
