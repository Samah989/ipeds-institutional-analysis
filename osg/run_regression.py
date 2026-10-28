"""Fit one research question and write its results.  This IS an HTCondor job:
it only reads parquet already in data/ and does pure local computation.

    python osg/run_regression.py --rq 1 --bootstrap 1000 --out results/

Writes <rq>_coefs.csv, <rq>_bootstrap.csv, and the analysis panel itself as
parquet + csv + dta so it can be re-opened in Stata.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Works both from the repo root (src/ is one level up from this file) and
# inside an HTCondor job, where inputs land flat next to the script.
sys.path[:0] = [str(Path(__file__).resolve().parent),
                str(Path(__file__).resolve().parents[1])]

from src.panels import BUILDERS, save, sector_dummies
from src.regression import panel_ols

# dependent variable, regressors, and whether institution fixed effects are
# identified.  RQ3's gap is only observed from 2015, so entity FE would eat
# most of the variation -- year effects only there.
SPECS = {
    1: ("log_net_tuition_per_fte", ["log_appr_per_fte", "log_fte"], True),
    2: ("grad_rate", ["log_instr_per_fte", "log_admin_per_fte", "pct_pell", "log_fte"], True),
    3: ("pell_gap", ["pct_pell", "log_avg_pell", "log_cohort"], False),
}


def bootstrap(panel, y, x, n, entity_fe):
    """Cluster bootstrap: resample whole institutions with replacement.

    An institution drawn twice must appear twice, under two different entity
    ids.  Selecting with `unitid.isin(draw)` instead looks right but silently
    de-duplicates, turning this into a ~63% subsample *without* replacement --
    which understated every standard error here by about a quarter.
    """
    rng = np.random.default_rng(0)
    ids = panel.unitid.unique()
    rows_for = [np.flatnonzero(panel.unitid.values == u) for u in ids]
    draws, failed = [], 0
    for i in range(n):
        picks = rng.choice(len(ids), len(ids), replace=True)
        sample = panel.iloc[np.concatenate([rows_for[p] for p in picks])].copy()
        sample["unitid"] = np.repeat(np.arange(len(picks)),
                                     [len(rows_for[p]) for p in picks])
        try:
            draws.append(panel_ols(sample, y, x, entity_effects=entity_fe,
                                   name=f"boot{i}").coefs["coef"])
        except Exception as e:  # noqa: BLE001 - a degenerate resample is expected
            failed += 1
            if failed == 1:
                print(f"[boot] first failure: {type(e).__name__}: {e}", flush=True)
    print(f"[boot] {len(draws)}/{n} replicates fit ({failed} failed)", flush=True)
    if not draws:
        raise RuntimeError("every bootstrap replicate failed")
    return pd.DataFrame(draws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rq", type=int, required=True, choices=[1, 2, 3])
    ap.add_argument("--bootstrap", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()
    name = f"rq{a.rq}"

    panel = BUILDERS[a.rq]()
    y, x, entity_fe = SPECS[a.rq]
    # Sector barely ever changes within an institution, so with institution
    # fixed effects the sector dummies are collinear and get absorbed -- they
    # only carry information in RQ3, which has year effects only.
    if not entity_fe:
        panel, dummies = sector_dummies(panel)
        x = x + dummies

    print(f"[{name}] {len(panel):,} rows, {panel.unitid.nunique():,} institutions, "
          f"{panel.year.min()}-{panel.year.max()}", flush=True)
    for p in save(panel, f"{name}_panel", a.out):
        print(f"[{name}] wrote {p}", flush=True)

    res = panel_ols(panel, y, x, entity_effects=entity_fe, name=name.upper())
    res.coefs.to_csv(a.out / f"{name}_coefs.csv")
    print(res.summary(), flush=True)

    if a.bootstrap:
        b = bootstrap(panel, y, x, a.bootstrap, entity_fe)
        pd.DataFrame({"boot_mean": b.mean(), "boot_sd": b.std(),
                      "ci_low": b.quantile(.025), "ci_high": b.quantile(.975)}
                     ).to_csv(a.out / f"{name}_bootstrap.csv")
        print(f"[{name}] wrote {name}_bootstrap.csv", flush=True)


if __name__ == "__main__":
    main()
