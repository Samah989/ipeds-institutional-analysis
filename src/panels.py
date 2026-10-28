"""Build the three research-question panels from cached IPEDS parquet.

This is the single source of truth: the notebooks and the OSG batch job both
import from here, so a fix lands in both at once.

Study windows are set by what the portal actually has (see data_pull.COVERAGE),
not by what we'd like:

  RQ1 affordability  2004-2017  finance x sfa      public 4-year (sector 1)
  RQ2 completion     2004-2017  finance x sfa      4-year (sectors 1,2,3)
  RQ3 equity         2015-2021  grad-rates-pell x sfa   4-year

RQ3 deliberately excludes finance regressors: `finance` stops in 2017 and
`grad-rates-pell` starts in 2015, so adding endowment or student-services
spending would collapse a 7-year panel to 3 years.  Pass `with_finance=True`
if you want that trade.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data_pull import load_cached, to_na
from .regression import deflate

# `type_of_aid` codes carry no labels in the API.  Identified empirically from
# the 2016 national pull (medians): 3 -> 69% of students, $4,729 (any grant or
# scholarship); 5 -> 46%, $4,100 (Pell -- matches the published national
# average award); 11 -> 54%, $6,791 (federal loans).  Re-check if a future
# year's profile stops lining up.
AID = {"grant": 3, "pell": 5, "loan": 11}

# `fed_aid_type` in grad-rates-pell, identified the same way (4-year, 2016):
# 1 -> 45% of the cohort, 44% grad rate (Pell recipients); 2 -> 18%, 53%
# (subsidised loan, no Pell); 3 -> 32%, 56% (neither); 99 -> total.
PELL, NONPELL = 1, (2, 3)

# `subcohort` splits an institution's cohort; 99 is the total, but institutions
# reporting a single cohort type use -2 instead.  Prefer 99, fall back to -2.
SUBCOHORT_PREF = [99, -2, 1, 2]

# Every per-student measure here is X / FTE, so a wrong FTE is catastrophic.
# IPEDS reports a handful of graduate-only and professional schools with an
# FTE in the single digits next to tens of millions in tuition revenue --
# e.g. Northeast Ohio Medical University, 2011: $24.6m over est_fte=4, giving
# "net tuition per student" of $6.1 million.  Left in, those few rows swamp
# the regression.  Institutions under 100 FTE are excluded, and that
# restriction is stated in the results rather than hidden.
MIN_FTE = 100

# Same idea for the Pell gap.  55 institution-years have a gap of exactly
# -1.00 because a cohort of 2-14 students happened to split "every Pell
# student graduated, no non-Pell student did".  That is noise, not inequity,
# and it carries the same weight as a 20,000-student university.  Both groups
# must have at least this many students for the gap to be meaningful.
MIN_COHORT = 30


def _one_row_per(df: pd.DataFrame, keys, pref_col="subcohort", pref=SUBCOHORT_PREF):
    """Collapse to one row per `keys`, preferring the total-subcohort row."""
    rank = {v: i for i, v in enumerate(pref)}
    return (df.assign(_r=df[pref_col].map(rank).fillna(len(pref)))
              .sort_values("_r").drop_duplicates(list(keys)).drop(columns="_r"))


def aid_panel() -> pd.DataFrame:
    """sfa-all-undergraduates is long (one row per type_of_aid).  Pivot to one
    row per institution-year with pct_pell / avg_pell / pct_grant / pct_loan."""
    aid = to_na(load_cached("sfa-all-undergraduates"),
                ["percent_of_students", "average_amount"])
    out = aid[["unitid", "year"]].drop_duplicates()
    for label, code in AID.items():
        sub = (aid[aid.type_of_aid == code]
               .groupby(["unitid", "year"], as_index=False)
               [["percent_of_students", "average_amount"]].mean()
               .rename(columns={"percent_of_students": f"pct_{label}",
                                "average_amount": f"avg_{label}"}))
        out = out.merge(sub, on=["unitid", "year"], how="left")
    return out


def grad_panel() -> pd.DataFrame:
    """6-year completion rate, one row per institution-year (race/sex totals)."""
    g = _one_row_per(load_cached("grad-rates", race=99, sex=99), ["unitid", "year"])
    g = to_na(g, ["completion_rate_150pct", "cohort_adj_150pct", "cohort_rev"])
    # Cohort size comes from `cohort_adj_150pct`, not `cohort_rev`: on the
    # subcohort=99 (institution total) rows -- the ones we keep -- cohort_rev
    # is missing 100% of the time, while the adjusted cohort is always there.
    # It is also the correct denominator for the 150%-of-normal-time rate.
    g["cohort"] = g.cohort_adj_150pct.fillna(g.cohort_rev)
    return g[["unitid", "year", "completion_rate_150pct", "cohort"]].rename(
        columns={"completion_rate_150pct": "grad_rate"})


def pell_gap_panel() -> pd.DataFrame:
    """Pell vs non-Pell completion gap, in percentage points.

    Non-Pell is rebuilt from counts (completers / cohort) across fed_aid_type
    2 and 3 rather than averaging their two rates, so it is properly weighted.
    """
    p = _one_row_per(load_cached("grad-rates-pell"),
                     ["unitid", "year", "fed_aid_type"])
    p = to_na(p, ["completers_150pct", "cohort_adj", "cohort_rev"])
    p["cohort"] = p.cohort_adj.fillna(p.cohort_rev)

    def totals(mask):
        s = p[mask].groupby(["unitid", "year"])[["completers_150pct", "cohort"]].sum()
        return s.completers_150pct / s.cohort.replace(0, np.nan), s.cohort

    pell_rate, pell_n = totals(p.fed_aid_type == PELL)
    other_rate, other_n = totals(p.fed_aid_type.isin(NONPELL))
    gap = pd.concat([pell_rate.rename("grad_rate_pell"),
                     other_rate.rename("grad_rate_nonpell"),
                     (pell_n + other_n).rename("cohort"),
                     (pell_n / (pell_n + other_n)).rename("pell_share")],
                    axis=1).reset_index()
    gap["pell_gap"] = gap.grad_rate_nonpell - gap.grad_rate_pell
    big = (pell_n >= MIN_COHORT) & (other_n >= MIN_COHORT)
    return gap[gap.set_index(["unitid", "year"]).index.isin(big[big].index)].dropna(
        subset=["pell_gap"])


def _base(sectors, years) -> pd.DataFrame:
    d = load_cached("directory")[["unitid", "year", "sector", "state_abbr", "inst_name"]]
    d = d[d.sector.isin(sectors) & d.year.isin(years)].drop_duplicates(["unitid", "year"])
    return d.merge(aid_panel(), on=["unitid", "year"], how="left")


def _log(s: pd.Series) -> pd.Series:
    """log() that turns zeros and negatives into NaN instead of -inf."""
    return np.log(pd.to_numeric(s, errors="coerce").where(lambda v: v > 0))


def _fte(fin: pd.DataFrame) -> pd.Series:
    """Enrolment denominator: reported FTE, falling back to the estimate.

    The two agree to r=0.99; `rep_fte` is what the institution filed, so it
    wins where both exist.  Values below MIN_FTE become NaN and drop out.
    """
    fte = fin.rep_fte.fillna(fin.est_fte)
    return fte.where(fte >= MIN_FTE)


def rq1(base_year: int = 2017) -> pd.DataFrame:
    """Affordability: net tuition revenue per FTE vs state appropriations.

    IPEDS has no per-student net price in these endpoints, so we use net
    tuition & fee revenue per FTE -- the standard institution-level proxy.
    """
    fin = to_na(load_cached("finance"),
                ["rev_tuition_fees_net", "rev_appropriations_state",
                 "est_fte", "rep_fte"])
    fin["fte"] = _fte(fin)
    p = _base([1], range(2004, 2018)).merge(
        fin[["unitid", "year", "rev_tuition_fees_net",
             "rev_appropriations_state", "fte"]], on=["unitid", "year"])
    p["net_tuition_per_fte"] = p.rev_tuition_fees_net / p.fte
    p["appropriations_per_fte"] = p.rev_appropriations_state / p.fte
    p = deflate(p, ["net_tuition_per_fte", "appropriations_per_fte"], base_year)
    # Both sides in logs, so the coefficient reads as an elasticity: "a 1%
    # cut in state support raises net tuition per student by b%".  That is
    # both the policy-relevant quantity and far less outlier-sensitive than
    # a dollar-level regression.
    p["log_net_tuition_per_fte"] = _log(p.net_tuition_per_fte_real)
    p["log_appr_per_fte"] = _log(p.appropriations_per_fte_real)
    p["log_fte"] = _log(p.fte)
    return p.dropna(subset=["log_net_tuition_per_fte", "log_appr_per_fte", "log_fte"])


def rq2(base_year: int = 2017) -> pd.DataFrame:
    """Completion: does the instruction/administration spending mix matter?"""
    fin = to_na(load_cached("finance"),
                ["exp_instruc_total", "exp_inst_supp_total",
                 "exp_acad_supp_total", "est_fte", "rep_fte"])
    fin["fte"] = _fte(fin)
    p = (_base([1, 2, 3], range(2004, 2018))
         .merge(grad_panel(), on=["unitid", "year"])
         .merge(fin[["unitid", "year", "exp_instruc_total", "exp_inst_supp_total",
                     "exp_acad_supp_total", "fte"]], on=["unitid", "year"]))
    p["admin_exp"] = p.exp_inst_supp_total + p.exp_acad_supp_total
    p["instr_per_fte"] = p.exp_instruc_total / p.fte
    p["admin_per_fte"] = p.admin_exp / p.fte
    p = deflate(p, ["instr_per_fte", "admin_per_fte"], base_year)
    p["log_instr_per_fte"] = _log(p.instr_per_fte_real)
    p["log_admin_per_fte"] = _log(p.admin_per_fte_real)
    p["log_fte"] = _log(p.fte)
    return p.dropna(subset=["grad_rate", "log_instr_per_fte", "log_admin_per_fte"])


def rq3(base_year: int = 2017, with_finance: bool = False) -> pd.DataFrame:
    """Equity: what moves the Pell / non-Pell completion gap?"""
    # Cohort size comes from grad-rates-pell itself (Pell + non-Pell), so this
    # panel needs no second graduation-rate join.
    p = _base([1, 2, 3], range(2015, 2022)).merge(pell_gap_panel(), on=["unitid", "year"])
    p["log_cohort"] = _log(p.cohort)
    p["log_avg_pell"] = _log(p.avg_pell)
    if with_finance:  # collapses the window to 2015-2017; see module docstring
        fin = to_na(load_cached("finance"),
                    ["endowment_end", "exp_student_serv_total", "est_fte", "rep_fte"])
        fin["fte"] = _fte(fin)
        p = p.merge(fin[["unitid", "year", "endowment_end",
                         "exp_student_serv_total", "fte"]], on=["unitid", "year"])
        p["endow_per_fte"] = p.endowment_end / p.fte
        p["stusvc_per_fte"] = p.exp_student_serv_total / p.fte
        p = deflate(p, ["endow_per_fte", "stusvc_per_fte"], base_year)
        p["log_endow_per_fte"] = _log(p.endow_per_fte_real)
        p["log_stusvc_per_fte"] = _log(p.stusvc_per_fte_real)
    return p.dropna(subset=["pell_gap", "pct_pell", "log_cohort"])


def sector_dummies(p: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Add sector_2 / sector_3 indicators (sector 1 is the reference)."""
    d = pd.get_dummies(p.sector.astype(int), prefix="sector").astype(float)
    d = d.drop(columns=d.columns[0])
    return pd.concat([p, d], axis=1), list(d.columns)


BUILDERS = {1: rq1, 2: rq2, 3: rq3}


def save(p: pd.DataFrame, name: str, outdir="results") -> list[str]:
    """Write the panel as parquet (Python), CSV (anything) and .dta (Stata 14+).

    Stata is fussy: names must be <=32 chars, and pandas' nullable/boolean
    dtypes have no Stata equivalent, so we cast those to plain float first.
    """
    from pathlib import Path
    # Anchor a relative outdir to the repo root, so a notebook (cwd=notebooks/)
    # and a script (cwd=repo root) write to the same results/ directory.
    out = Path(outdir)
    if not out.is_absolute():
        out = Path(__file__).resolve().parents[1] / out
    out.mkdir(parents=True, exist_ok=True)
    d = p.rename(columns=lambda c: c[:32]).loc[:, lambda f: ~f.columns.duplicated()]
    for c in d.columns:
        if d[c].dtype == bool or str(d[c].dtype) in {"Int64", "Float64", "boolean"}:
            d[c] = d[c].astype(float)
    paths = [out / f"{name}.parquet", out / f"{name}.csv", out / f"{name}.dta"]
    d.to_parquet(paths[0], index=False)
    d.to_csv(paths[1], index=False)
    d.to_stata(paths[2], write_index=False, version=118)
    return [str(x) for x in paths]
