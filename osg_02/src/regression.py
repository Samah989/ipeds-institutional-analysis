"""Simple OLS regression with publication-quality output.

Workshop edition  -  standard OLS via statsmodels (no panel fixed effects).
Keeps it simple: one regression, clear output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    coefs: pd.DataFrame  # columns: coef, se, t, p
    bootstrap: pd.DataFrame | None = None

    def summary(self) -> str:
        lines = [
            f"\n{'=' * 60}",
            f"  {self.name}",
            f"{'=' * 60}",
            f"  N = {self.nobs:,}    R² = {self.r2:.4f}    Adj R² = {self.r2_adj:.4f}",
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

    def to_csv(self, path) -> str:
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
    """Ordinary Least Squares with heteroskedasticity-robust standard errors."""
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
        name=name,
        nobs=int(model.nobs),
        r2=model.rsquared,
        r2_adj=model.rsquared_adj,
        f_stat=model.fvalue,
        f_pvalue=model.f_pvalue,
        coefs=coefs,
    )
