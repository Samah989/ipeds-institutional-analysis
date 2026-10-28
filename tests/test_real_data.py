"""Integration checks against the real cached parquet in data/.

These are the guards that catch a bad *pull* rather than bad code, so they run
on whatever `python osg/pull_all_panels.py` actually downloaded.  If the cache
isn't there yet they skip rather than fail.

    python -m pytest tests/test_real_data.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import panels
from src.regression import panel_ols

SPECS = {
    1: ("log_net_tuition_per_fte", ["log_appr_per_fte", "log_fte"], True, (2004, 2017)),
    2: ("grad_rate", ["log_instr_per_fte", "log_admin_per_fte", "pct_pell", "log_fte"], True, (2004, 2017)),
    3: ("pell_gap", ["pct_pell", "log_avg_pell", "log_cohort"], False, (2015, 2021)),
}


@pytest.fixture(scope="module", params=[1, 2, 3])
def built(request):
    try:
        return request.param, panels.BUILDERS[request.param]()
    except FileNotFoundError as e:
        pytest.skip(f"no cached data yet: {e}")


def test_panel_has_one_row_per_institution_year(built):
    _, p = built
    assert not p.duplicated(["unitid", "year"]).any()


def test_panel_spans_the_expected_years(built):
    rq, p = built
    lo, hi = SPECS[rq][3]
    assert p.year.min() >= lo and p.year.max() <= hi
    assert p.year.nunique() >= (hi - lo) - 1, "a whole year is missing from the panel"


def test_panel_is_national_not_one_state(built):
    _, p = built
    assert p.state_abbr.nunique() > 45
    assert p.unitid.nunique() > 500


def test_no_missing_sentinels_survived(built):
    """-1/-2/-3 mean "missing" in the API.  Checked on the columns read
    straight from it -- not on `pell_gap`, which is a difference of two rates
    and can legitimately equal -1.00 (one real case: 239 Pell students all
    graduated, 43 non-Pell students none did)."""
    _, p = built
    num = p.select_dtypes("number").drop(
        columns=["unitid", "year", "sector", "pell_gap"], errors="ignore")
    leaked = [c for c in num.columns if num[c].isin([-1, -2, -3]).any()]
    assert not leaked, f"API sentinels leaked into {leaked}"


def test_rates_are_proportions(built):
    _, p = built
    for c in ["grad_rate", "pct_pell", "grad_rate_pell", "grad_rate_nonpell",
              "pell_share"]:
        if c in p:
            assert p[c].dropna().between(0, 1).all(), f"{c} outside [0,1]"
    if "pell_gap" in p:
        assert p.pell_gap.between(-1, 1).all()
        assert p.pell_gap.abs().gt(0.9).mean() < 0.001, "too many degenerate gaps"


def test_per_student_ratios_are_not_absurd(built):
    """Catches the est_fte=4 problem: a handful of professional schools report
    single-digit FTE next to tens of millions in revenue."""
    _, p = built
    if "fte" in p:
        assert p.fte.min() >= panels.MIN_FTE
    if "net_tuition_per_fte_real" in p:
        assert p.net_tuition_per_fte_real.max() < 200_000


def test_rq3_with_finance_shrinks_to_the_overlap_window():
    """Documented trade-off: finance ends in 2017 and the Pell gap starts in
    2015, so opting into the finance controls buys 3 years, not 7."""
    try:
        p = panels.rq3(with_finance=True)
    except FileNotFoundError as e:
        pytest.skip(f"no cached data yet: {e}")
    assert p.year.max() <= 2017
    assert {"log_endow_per_fte", "log_stusvc_per_fte"} <= set(p.columns)
    assert len(p) < len(panels.rq3())


def test_the_model_actually_fits(built):
    rq, p = built
    y, x, entity_fe, _ = SPECS[rq]
    if rq in (2, 3):
        p, dummies = panels.sector_dummies(p)
        x = x + dummies
    res = panel_ols(p, y, x, entity_effects=entity_fe, name=f"RQ{rq}")
    assert res.n_obs > 1000 and res.n_entities > 200
    assert res.coefs["coef"].notna().all()
