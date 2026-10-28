"""Build the analysis panel: institution size vs graduation rate.

Workshop edition  -  one research question, minimal complexity.
Merges directory (institution info) with grad-rates (completion rates).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data_pull import load_cached, to_na


MIN_FTE = 100  # exclude tiny institutions with wild per-student ratios


def build_panel():
    """One row per institution-year: size, sector, state, graduation rate."""

    # Directory: institution name, sector, state, size
    d = load_cached("directory")
    d = d[["unitid", "year", "inst_name", "sector", "state_abbr",
           "enrollment_fte"]].drop_duplicates(["unitid", "year"])
    d = to_na(d, ["enrollment_fte"])
    d = d[d.sector.isin([1, 2, 3])]  # 4-year institutions only
    d = d[d.enrollment_fte >= MIN_FTE]

    # Grad rates: 6-year completion rate (race/sex totals)
    g = load_cached("grad-rates", race=99, sex=99)
    # Prefer subcohort 99 (total), fall back to -2
    g = (g.assign(_r=g.subcohort.map({99: 0, -2: 1}).fillna(2))
          .sort_values("_r").drop_duplicates(["unitid", "year"]).drop(columns="_r"))
    g = to_na(g, ["completion_rate_150pct"])
    g = g[["unitid", "year", "completion_rate_150pct"]].rename(
        columns={"completion_rate_150pct": "grad_rate"})

    # Merge
    panel = d.merge(g, on=["unitid", "year"], how="inner")
    panel["log_enrollment"] = np.log(panel.enrollment_fte.where(lambda v: v > 0))
    panel = panel.dropna(subset=["grad_rate", "log_enrollment"])

    # Sector dummies (sector 1 = public is the reference)
    dummies = pd.get_dummies(panel.sector.astype(int), prefix="sector").astype(float)
    dummies = dummies.drop(columns=dummies.columns[0])
    panel = pd.concat([panel, dummies], axis=1)

    return panel, list(dummies.columns)


def save(panel, name, outdir="results"):
    """Write the panel as CSV."""
    from pathlib import Path
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{name}.csv"
    panel.to_csv(path, index=False)
    return str(path)
