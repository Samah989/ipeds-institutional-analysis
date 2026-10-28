"""Panel-regression helpers shared by the notebooks and the OSG jobs.

Two conventions everywhere: entity = `unitid`, time = `year`, and standard
errors clustered at the institution level (Petersen 2009).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from linearmodels.panel import PanelOLS

# CPI-U, annual average, US city average, 1982-84 = 100 (BLS).  Starts at
# 1987 so the series covers every year IPEDS finance data exists.
CPI = {
    1987: 113.6, 1988: 118.3, 1989: 124.0, 1990: 130.7, 1991: 136.2,
    1992: 140.3, 1993: 144.5, 1994: 148.2, 1995: 152.4, 1996: 156.9,
    1997: 160.5, 1998: 163.0, 1999: 166.6, 2000: 172.2, 2001: 177.1,
    2002: 179.9, 2003: 184.0, 2004: 188.9, 2005: 195.3, 2006: 201.6,
    2007: 207.3, 2008: 215.3, 2009: 214.5, 2010: 218.1, 2011: 224.9,
    2012: 229.6, 2013: 233.0, 2014: 236.7, 2015: 237.0, 2016: 240.0,
    2017: 245.1, 2018: 251.1, 2019: 255.7, 2020: 258.8, 2021: 271.0,
    2022: 292.7, 2023: 304.7, 2024: 313.7,
}


@dataclass
class Result:
    name: str
    n_obs: int
    n_entities: int
    r2_within: float
    coefs: pd.DataFrame  # index=variable; coef, stderr, tstat, pvalue, ci_low, ci_high

    def summary(self) -> str:
        return (f"{self.name}: {self.n_obs:,} obs, {self.n_entities:,} institutions, "
                f"within R2={self.r2_within:.3f}\n{self.coefs.round(4).to_string()}")


def deflate(df: pd.DataFrame, cols, base_year: int = 2017,
            year_col: str = "year") -> pd.DataFrame:
    """Add `<col>_real`: nominal dollars restated in constant `base_year` dollars.

    Raises on a base year we have no CPI for, and *warns loudly* on data years
    we can't deflate -- silently emitting NaN there would drop those rows from
    the regression with no trace.
    """
    if base_year not in CPI:
        raise KeyError(f"no CPI for base_year={base_year}; have {min(CPI)}-{max(CPI)}")
    year = pd.to_numeric(df[year_col], errors="coerce")
    unmapped = sorted(set(year.dropna().astype(int)) - set(CPI))
    if unmapped:
        raise KeyError(f"no CPI for year(s) {unmapped}; extend regression.CPI")
    scale = year.map({y: CPI[base_year] / v for y, v in CPI.items()})
    return df.assign(**{f"{c}_real": pd.to_numeric(df[c], errors="coerce") * scale
                        for c in cols})


def panel_ols(df: pd.DataFrame, y: str, x, entity_effects: bool = True,
              time_effects: bool = True, name: str = "panel") -> Result:
    """Two-way fixed-effects panel OLS with cluster-robust SEs."""
    x = list(x)
    d = df.dropna(subset=["unitid", "year"]).copy()
    d["year"] = pd.to_numeric(d["year"], errors="coerce").astype(int)
    d = d.set_index(["unitid", "year"])[[y, *x]].dropna().astype(float)
    if d.empty:
        raise ValueError(f"{name}: no complete cases for {y} ~ {x}")

    res = PanelOLS(d[y], d[x], entity_effects=entity_effects,
                   time_effects=time_effects, drop_absorbed=True).fit(
        cov_type="clustered", cluster_entity=True)
    ci = res.conf_int()
    return Result(
        name=name, n_obs=int(res.nobs), n_entities=int(res.entity_info.total),
        r2_within=float(res.rsquared_within),
        coefs=pd.DataFrame({"coef": res.params, "stderr": res.std_errors,
                            "tstat": res.tstats, "pvalue": res.pvalues,
                            "ci_low": ci["lower"], "ci_high": ci["upper"]}))
