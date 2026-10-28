#!/bin/bash
# ONE-PASTE SETUP  -  creates all osg_02 workshop files.
# Usage: mkdir -p ~/osg_02 && cd ~/osg_02 && bash setup.sh
set -euo pipefail

echo "==> Creating workshop files..."
mkdir -p src data logs results mini-demo templates

# ─── mini-demo ───────────────────────────────────────────

echo "  Creating mini-demo/students.csv"
cat > 'mini-demo/students.csv' << 'EOF_STUDENTS'
hours,score
1,35
2,45
3,50
4,60
5,65
6,70
7,80
8,85
9,90
10,95
EOF_STUDENTS

echo "  Creating mini-demo/regression.py"
cat > 'mini-demo/regression.py' << 'EOF_REGRESSION'
import pandas as pd
from scipy import stats

df = pd.read_csv("students.csv")
slope, intercept, r, p, se = stats.linregress(df["hours"], df["score"])

print(f"slope     = {slope:.2f}")
print(f"intercept = {intercept:.2f}")
print(f"R-squared = {r**2:.3f}")
print(f"p-value   = {p:.4f}")

with open("result.csv", "w") as f:
    f.write("slope,intercept,r_squared,p_value\n")
    f.write(f"{slope:.2f},{intercept:.2f},{r**2:.3f},{p:.4f}\n")
print("Saved result.csv")
EOF_REGRESSION

echo "  Creating mini-demo/run.sh"
cat > 'mini-demo/run.sh' << 'EOF_MINI_RUN'
#!/bin/bash
set -euo pipefail

mkdir -p deps
python3 -m pip install --target=deps scipy pandas 2>&1 | tail -1
export PYTHONPATH="$PWD/deps"

python3 regression.py
EOF_MINI_RUN

echo "  Creating mini-demo/run.submit"
cat > 'mini-demo/run.submit' << 'EOF_MINI_SUBMIT'
container_image = /cvmfs/singularity.opensciencegrid.org/htc/ubuntu:22.04

executable = run.sh

transfer_input_files = regression.py, students.csv
transfer_output_files = result.csv
should_transfer_files = YES
when_to_transfer_output = ON_EXIT

request_cpus   = 1
request_memory = 1 GB
request_disk   = 1 GB

+JobDurationCategory = "Medium"

log    = logs/demo.$(Cluster).log
output = logs/demo.$(Cluster).out
error  = logs/demo.$(Cluster).err

queue 1
EOF_MINI_SUBMIT

mkdir -p mini-demo/logs

# ─── main project ────────────────────────────────────────

echo "  Creating requirements.txt"
cat > 'requirements.txt' << 'EOF_REQS'
pandas==2.2.3
numpy==2.1.3
scipy==1.14.1
statsmodels==0.14.4
EOF_REQS

echo "  Creating pull_data.sh"
cat > 'pull_data.sh' << 'EOF_PULL'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p deps data
python3 -m pip install --target=deps requests pandas pyarrow 2>&1 | tail -1
PYTHONPATH="$PWD/deps" python3 -c "from src.data_pull import fetch_all; fetch_all()"
echo "==> Data ready in data/"
ls -lh data/*.parquet
EOF_PULL

echo "  Creating preflight.sh"
cat > 'preflight.sh' << 'EOF_PREFLIGHT'
#!/bin/bash
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
EOF_PREFLIGHT

echo "  Creating run.sh"
cat > 'run.sh' << 'EOF_RUN'
#!/bin/bash
set -euo pipefail

echo "[job] host=$(hostname) start=$(date -Iseconds)"

mkdir -p results deps
python3 -m pip install --target=deps -r requirements.txt 2>&1 | tail -1
export PYTHONPATH="$PWD/deps"

python3 run_analysis.py --bootstrap 200 --out results/

echo "[job] done=$(date -Iseconds)"
ls -lh results/
EOF_RUN

echo "  Creating run.submit"
cat > 'run.submit' << 'EOF_SUBMIT'
container_image = /cvmfs/singularity.opensciencegrid.org/htc/ubuntu:22.04

executable = run.sh

transfer_input_files = run_analysis.py, requirements.txt, src, data
transfer_output_files = results
should_transfer_files = YES
when_to_transfer_output = ON_EXIT

request_cpus   = 1
request_memory = 2 GB
request_disk   = 2 GB

+JobDurationCategory = "Medium"

max_retries = 2

log    = logs/job.$(Cluster).log
output = logs/job.$(Cluster).out
error  = logs/job.$(Cluster).err

queue 1
EOF_SUBMIT

echo "  Creating run_analysis.py"
cat > 'run_analysis.py' << 'EOF_ANALYSIS'
"""Does institution size predict graduation rate?"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parent)]

from src.panels import build_panel, save
from src.regression import run_ols


def bootstrap(panel, y, x, n=200):
    rng = np.random.default_rng(42)
    ids = panel.unitid.unique()
    draws = []
    for i in range(n):
        sample_ids = rng.choice(ids, len(ids), replace=True)
        sample = pd.concat([panel[panel.unitid == u] for u in sample_ids],
                           ignore_index=True)
        try:
            res = run_ols(sample, y, x, name=f"boot{i}")
            draws.append(res.coefs["coef"])
        except Exception:
            pass
    if draws:
        print(f"[bootstrap] {len(draws)}/{n} replicates succeeded", flush=True)
    return pd.DataFrame(draws) if draws else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    panel, sector_cols = build_panel()
    print(f"[panel] {len(panel):,} rows, {panel.unitid.nunique():,} institutions, "
          f"{panel.year.min()}-{panel.year.max()}", flush=True)

    path = save(panel, "panel", a.out)
    print(f"[panel] wrote {path}", flush=True)

    x_cols = ["log_enrollment"] + sector_cols
    res = run_ols(panel, "grad_rate", x_cols,
                  name="Graduation Rate ~ Institution Size + Sector")
    print(res.summary(), flush=True)

    if a.bootstrap:
        print(f"[bootstrap] running {a.bootstrap} replicates...", flush=True)
        res.bootstrap = bootstrap(panel, "grad_rate", x_cols, a.bootstrap)

    csv_path = res.to_csv(a.out / "regression.csv")
    print(f"[regression] wrote {csv_path}", flush=True)


if __name__ == "__main__":
    main()
EOF_ANALYSIS

echo "  Creating src/__init__.py"
touch src/__init__.py

echo "  Creating src/data_pull.py"
cat > 'src/data_pull.py' << 'EOF_DATAPULL'
"""Lightweight IPEDS data client  -  workshop edition."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

log = logging.getLogger(__name__)

BASE = "https://educationdata.urban.org/api/v1/college-university/ipeds"
DATA_DIR = Path(os.environ.get("IPEDS_DATA")
                or Path(__file__).resolve().parents[1] / "data")
TIMEOUT = 300
RETRIES = 5
MISSING = (-1, -2, -3)

COVERAGE = {
    "directory": range(2020, 2023),
    "grad-rates": range(2020, 2023),
}


def _cache_path(topic, year, nested, filters):
    key = json.dumps([topic, year, nested or "", sorted(filters.items())])
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    stem = f"{topic}-{nested}" if nested else topic
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    return DATA_DIR / f"{stem}__{year}__{slug}__{digest}.parquet"


def _get(url):
    import requests
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == RETRIES:
                raise
            wait = 2**attempt
            log.warning("%s (try %d/%d), sleeping %ds", e, attempt, RETRIES, wait)
            time.sleep(wait)


def to_na(df, cols=None):
    import numpy as np
    target = cols or df.select_dtypes("number").columns
    for c in target:
        if c in df.columns:
            df[c] = df[c].replace(list(MISSING), np.nan)
    return df


def fetch(topic, year, nested=None, use_cache=True, **filters):
    cache = _cache_path(topic, year, nested, filters)
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    url = f"{BASE}/{topic}/{year}/" + (f"{nested}/" if nested else "")
    url += "?" + urlencode(filters) if filters else ""
    rows = []
    while url:
        page = _get(url)
        rows += page["results"]
        url = page.get("next")
        log.info("%s %s: %d rows so far", topic, year, len(rows))

    df = pd.DataFrame(rows)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def fetch_years(topic, years, nested=None, **filters):
    frames = []
    for y in years:
        try:
            frames.append(fetch(topic, y, nested, **filters))
        except Exception as e:
            log.warning("skip %s %s: %s", topic, y, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_cached(prefix, **filters):
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    files = sorted(DATA_DIR.glob(f"{prefix}__*__{slug}__*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"no cached {prefix} in {DATA_DIR}; run `bash pull_data.sh` first")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def fetch_all():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for topic, years in COVERAGE.items():
        log.info("==> Fetching %s (%d-%d)", topic, years.start, years.stop - 1)
        if topic == "grad-rates":
            fetch_years(topic, years, race=99, sex=99)
        else:
            fetch_years(topic, years)
    log.info("==> All panels cached in %s", DATA_DIR)
EOF_DATAPULL

echo "  Creating src/panels.py"
cat > 'src/panels.py' << 'EOF_PANELS'
"""Build the analysis panel: institution size vs graduation rate."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data_pull import load_cached, to_na

MIN_FTE = 100


def build_panel():
    d = load_cached("directory")
    d = d[["unitid", "year", "inst_name", "sector", "state_abbr",
           "enrollment_fte"]].drop_duplicates(["unitid", "year"])
    d = to_na(d, ["enrollment_fte"])
    d = d[d.sector.isin([1, 2, 3])]
    d = d[d.enrollment_fte >= MIN_FTE]

    g = load_cached("grad-rates", race=99, sex=99)
    g = (g.assign(_r=g.subcohort.map({99: 0, -2: 1}).fillna(2))
          .sort_values("_r").drop_duplicates(["unitid", "year"]).drop(columns="_r"))
    g = to_na(g, ["completion_rate_150pct"])
    g = g[["unitid", "year", "completion_rate_150pct"]].rename(
        columns={"completion_rate_150pct": "grad_rate"})

    panel = d.merge(g, on=["unitid", "year"], how="inner")
    panel["log_enrollment"] = np.log(panel.enrollment_fte.where(lambda v: v > 0))
    panel = panel.dropna(subset=["grad_rate", "log_enrollment"])

    dummies = pd.get_dummies(panel.sector.astype(int), prefix="sector").astype(float)
    dummies = dummies.drop(columns=dummies.columns[0])
    panel = pd.concat([panel, dummies], axis=1)

    return panel, list(dummies.columns)


def save(panel, name, outdir="results"):
    from pathlib import Path
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{name}.csv"
    panel.to_csv(path, index=False)
    return str(path)
EOF_PANELS

echo "  Creating src/regression.py"
cat > 'src/regression.py' << 'EOF_REGRESSION'
"""Simple OLS regression with publication-quality output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass
class Result:
    name: str
    nobs: int
    r2: float
    r2_adj: float
    f_stat: float
    f_pvalue: float
    coefs: pd.DataFrame
    bootstrap: pd.DataFrame | None = None

    def summary(self):
        lines = [
            f"\n{'=' * 60}",
            f"  {self.name}",
            f"{'=' * 60}",
            f"  N = {self.nobs:,}    R2 = {self.r2:.4f}    Adj R2 = {self.r2_adj:.4f}",
            f"  F = {self.f_stat:.2f}   p = {self.f_pvalue:.2e}",
            f"{'-' * 60}",
            f"  {'Variable':<25s} {'Coef':>8s} {'SE':>8s} {'t':>8s} {'p':>8s}",
            f"{'-' * 60}",
        ]
        for var, row in self.coefs.iterrows():
            sig = ""
            if row.p < 0.001: sig = "***"
            elif row.p < 0.01: sig = "**"
            elif row.p < 0.05: sig = "*"
            lines.append(f"  {var:<25s} {row.coef:>8.4f} {row.se:>8.4f} "
                         f"{row.t:>8.2f} {row.p:>8.4f} {sig}")
        lines.append(f"{'=' * 60}\n")
        return "\n".join(lines)

    def to_csv(self, path):
        path = Path(path)
        rows = [
            ["Model", self.name, "", "", ""],
            ["N", self.nobs, "", "", ""],
            ["R-squared", f"{self.r2:.4f}", "", "", ""],
            ["Adj R-squared", f"{self.r2_adj:.4f}", "", "", ""],
            ["F-statistic", f"{self.f_stat:.2f}", "", "", ""],
            ["F p-value", f"{self.f_pvalue:.2e}", "", "", ""],
            ["", "", "", "", ""],
            ["Variable", "Coef", "SE", "t", "p"],
        ]
        for var, row in self.coefs.iterrows():
            rows.append([var, f"{row.coef:.4f}", f"{row.se:.4f}",
                         f"{row.t:.2f}", f"{row.p:.4f}"])
        if self.bootstrap is not None:
            rows.append(["", "", "", "", ""])
            rows.append(["Bootstrap 95% CI", "Lower", "Upper", "", ""])
            lo = self.bootstrap.quantile(0.025)
            hi = self.bootstrap.quantile(0.975)
            for var in self.coefs.index:
                if var in lo.index:
                    rows.append([var, f"{lo[var]:.4f}", f"{hi[var]:.4f}", "", ""])
        pd.DataFrame(rows).to_csv(path, index=False, header=False)
        return str(path)


def run_ols(panel, y_col, x_cols, name="OLS"):
    y = panel[y_col].astype(float)
    X = sm.add_constant(panel[x_cols].astype(float))
    model = sm.OLS(y, X).fit(cov_type="HC1")
    coefs = pd.DataFrame({
        "coef": model.params,
        "se": model.bse,
        "t": model.tvalues,
        "p": model.pvalues,
    })
    return Result(
        name=name, nobs=int(model.nobs),
        r2=model.rsquared, r2_adj=model.rsquared_adj,
        f_stat=model.fvalue, f_pvalue=model.f_pvalue, coefs=coefs,
    )
EOF_REGRESSION

# ─── templates ───────────────────────────────────────────

echo "  Creating templates/my_wrapper.sh"
cat > 'templates/my_wrapper.sh' << 'EOF_TEMPLATE_SH'
#!/bin/bash
# EXERCISE: Fill in the blanks to create a wrapper script.
set -euo pipefail

echo "[job] host=$(hostname) start=$(date -Iseconds)"

mkdir -p _______ _______

python3 -m pip install --target=_______ -r _______ 2>&1 | tail -1

export PYTHONPATH="$PWD/_______"

python3 _______ --out _______/

echo "[job] done=$(date -Iseconds)"
ls -lh results/
EOF_TEMPLATE_SH

echo "  Creating templates/my_job.submit"
cat > 'templates/my_job.submit' << 'EOF_TEMPLATE_SUB'
# EXERCISE: Fill in the blanks to create a submit file.

container_image = /cvmfs/singularity.opensciencegrid.org/opensciencegrid/_______

executable = _______

transfer_input_files = _______, _______, _______, _______
transfer_output_files = _______
should_transfer_files = YES
when_to_transfer_output = ON_EXIT

request_cpus   = _______
request_memory = _______ GB
request_disk   = _______ GB

+JobDurationCategory = "_______"

log    = _______/job.$(Cluster).log
output = _______/job.$(Cluster).out
error  = _______/job.$(Cluster).err

queue 1
EOF_TEMPLATE_SUB

echo "  Creating templates/ANSWER_KEY.md"
cat > 'templates/ANSWER_KEY.md' << 'EOF_ANSWERS'
# Answer Key (Presenter Only)

## my_wrapper.sh
1. `mkdir -p results deps`
2. `--target=deps -r requirements.txt`
3. `PYTHONPATH="$PWD/deps"`
4. `python3 run_analysis.py --out results/`

## my_job.submit
1. `htc/ubuntu:22.04`
2. `run.sh`
3. `run_analysis.py, requirements.txt, src, data`
4. `transfer_output_files = results`
5. `1`, `2 GB`, `2 GB`
6. `Short`
7. `logs`
EOF_ANSWERS

# ─── finish ──────────────────────────────────────────────

chmod +x *.sh mini-demo/*.sh

echo
echo "==> All files created!"
echo
ls -la
echo
ls -la src/
echo
echo "Next steps:"
echo "  1. Mini demo:  cd mini-demo && condor_submit run.submit"
echo "  2. Pull data:  bash pull_data.sh        (~2 minutes)"
echo "  3. Preflight:  bash preflight.sh"
echo "  4. Submit:     condor_submit run.submit"
