"""Does institution size predict graduation rate?

Run locally:   python run_analysis.py --out results/
On OSG:        (submitted via run.submit → run.sh runs this)

Output:
  results/panel.csv            -  the analysis data
  results/regression.csv       -  regression table
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parent)]

from src.panels import build_panel, save
from src.regression import run_ols


def bootstrap(panel, y, x, n=200):
    """Resample institutions with replacement for confidence intervals."""
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
    ap.add_argument("--bootstrap", type=int, default=0,
                    help="Number of bootstrap replicates (0 = skip)")
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    # Build the panel
    panel, sector_cols = build_panel()
    print(f"[panel] {len(panel):,} rows, {panel.unitid.nunique():,} institutions, "
          f"{panel.year.min()}-{panel.year.max()}", flush=True)

    # Save the panel
    path = save(panel, "panel", a.out)
    print(f"[panel] wrote {path}", flush=True)

    # Run the regression
    x_cols = ["log_enrollment"] + sector_cols
    res = run_ols(panel, "grad_rate", x_cols,
                  name="Graduation Rate ~ Institution Size + Sector")
    print(res.summary(), flush=True)

    # Bootstrap (if requested)
    if a.bootstrap:
        print(f"[bootstrap] running {a.bootstrap} replicates...", flush=True)
        res.bootstrap = bootstrap(panel, "grad_rate", x_cols, a.bootstrap)

    # Save regression output
    csv_path = res.to_csv(a.out / "regression.csv")
    print(f"[regression] wrote {csv_path}", flush=True)


if __name__ == "__main__":
    main()
