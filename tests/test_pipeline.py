"""Offline tests for the whole IPEDS pipeline.

Nothing here touches the network: the API client is exercised against a fake
`requests`, and the panel builders against hand-written parquet fixtures whose
answers can be worked out on paper.  Run with:

    python -m pytest tests -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import data_pull, panels
from src.regression import CPI, deflate, panel_ols


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Point the cache at a scratch dir so tests never see real pulls."""
    monkeypatch.setattr(data_pull, "DATA_DIR", tmp_path)
    return tmp_path


def write(tmp_path, stem, year, slug, df):
    df.to_parquet(tmp_path / f"{stem}__{year}__{slug}__deadbeef01.parquet", index=False)


# --------------------------------------------------------------------- client

def test_cache_path_separates_nested_and_filters(tmp_data):
    a = data_pull._cache_path("fall-enrollment", 2021, None, {"fips": 53})
    b = data_pull._cache_path("fall-enrollment", 2021, "race", {"fips": 53})
    c = data_pull._cache_path("fall-enrollment", 2021, None, {"sector": 1})
    assert len({a, b, c}) == 3, "different URLs must not share a cache file"
    assert b.name.startswith("fall-enrollment-race__")


def test_fetch_follows_next_and_never_builds_page_numbers(tmp_data, monkeypatch):
    seen = []

    class Resp:
        status_code = 200

        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            pass

        def json(self):
            seen.append(self.url)
            if "cursor" in self.url:
                return {"results": [{"unitid": 2, "year": 2016}], "next": None}
            return {"results": [{"unitid": 1, "year": 2016}], "next": "http://x/?cursor=2"}

    monkeypatch.setitem(sys.modules, "requests",
                        type(sys)("requests"))
    sys.modules["requests"].get = lambda url, timeout=None: Resp(url)

    df = data_pull.fetch("directory", 2016, fips=53)
    assert len(df) == 2 and len(seen) == 2
    assert seen[1] == "http://x/?cursor=2", "must follow `next`, not guess ?page=N"
    assert "fips=53" in seen[0]


def test_get_retries_then_succeeds(monkeypatch):
    calls = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("connection reset")

        def json(self):
            return {"results": [], "next": None}

    monkeypatch.setitem(sys.modules, "requests", type(sys)("requests"))
    sys.modules["requests"].get = lambda url, timeout=None: Resp()
    monkeypatch.setattr(data_pull.time, "sleep", lambda s: None)
    assert data_pull._get("http://x/") == {"results": [], "next": None}
    assert len(calls) == 3, "should have retried twice before succeeding"


def test_get_gives_up_after_max_retries(monkeypatch):
    class Resp:
        def raise_for_status(self):
            raise ConnectionError("down")

    monkeypatch.setitem(sys.modules, "requests", type(sys)("requests"))
    sys.modules["requests"].get = lambda url, timeout=None: Resp()
    monkeypatch.setattr(data_pull.time, "sleep", lambda s: None)
    with pytest.raises(ConnectionError):
        data_pull._get("http://x/")


def test_fetch_uses_cache_second_time(tmp_data, monkeypatch):
    write(tmp_data, "directory", 2016, "all", pd.DataFrame({"unitid": [1], "year": [2016]}))
    path = data_pull._cache_path("directory", 2016, None, {})
    pd.DataFrame({"unitid": [7], "year": [2016]}).to_parquet(path, index=False)

    def boom(*a, **k):
        raise AssertionError("cache hit must not hit the network")

    monkeypatch.setattr(data_pull, "_get", boom)
    assert data_pull.fetch("directory", 2016).unitid.tolist() == [7]


def test_fetch_years_skips_a_broken_year(tmp_data, monkeypatch):
    def flaky(topic, year, **kw):
        if year == 2005:
            raise RuntimeError("HTTP 500")
        return pd.DataFrame({"unitid": [1], "year": [year]})

    monkeypatch.setattr(data_pull, "fetch", flaky)
    out = data_pull.fetch_years("finance", [2004, 2005, 2006])
    assert out.year.tolist() == [2004, 2006]


def test_fetch_years_warns_but_keeps_going_on_an_empty_year(tmp_data, monkeypatch, caplog):
    """finance returns count=0 for 2018+.  That is coverage, not an error, so
    it must warn and carry on rather than raise or return the empty frame."""
    monkeypatch.setattr(data_pull, "fetch", lambda topic, year, **kw:
                        pd.DataFrame() if year == 2018
                        else pd.DataFrame({"unitid": [1], "year": [year]}))
    with caplog.at_level("WARNING"):
        out = data_pull.fetch_years("finance", [2017, 2018])
    assert out.year.tolist() == [2017]
    assert "0 rows" in caplog.text


def test_to_na_is_scoped_to_named_columns():
    df = pd.DataFrame({"rate": [0.5, -1.0, -2.0], "subcohort": [99, -2, -2]})
    out = data_pull.to_na(df, ["rate"])
    assert out.rate.isna().tolist() == [False, True, True]
    assert out.subcohort.tolist() == [99, -2, -2], "-2 is a real subcohort code"


def test_load_cached_refuses_to_mix_filter_slices(tmp_data):
    write(tmp_data, "directory", 2016, "sector-1", pd.DataFrame({"unitid": [1], "year": [2016]}))
    write(tmp_data, "directory", 2016, "fips-53", pd.DataFrame({"unitid": [1], "year": [2016]}))
    assert len(data_pull.load_cached("directory", sector=1)) == 1
    with pytest.raises(FileNotFoundError):
        data_pull.load_cached("directory")


# ------------------------------------------------------------------ deflating

def test_deflate_matches_hand_calculation():
    df = pd.DataFrame({"year": [2010, 2017], "x": [100.0, 100.0]})
    out = deflate(df, ["x"], base_year=2017)
    assert out.x_real.iloc[1] == pytest.approx(100.0)
    assert out.x_real.iloc[0] == pytest.approx(100 * CPI[2017] / CPI[2010])


def test_deflate_raises_instead_of_silently_nanning():
    with pytest.raises(KeyError, match="1980"):
        deflate(pd.DataFrame({"year": [1980], "x": [1.0]}), ["x"], base_year=2017)
    with pytest.raises(KeyError, match="base_year"):
        deflate(pd.DataFrame({"year": [2010], "x": [1.0]}), ["x"], base_year=2099)


def test_deflate_handles_string_years():
    out = deflate(pd.DataFrame({"year": ["2017"], "x": [50.0]}), ["x"], base_year=2017)
    assert out.x_real.iloc[0] == pytest.approx(50.0)


# ----------------------------------------------------------------- regression

def test_panel_ols_recovers_a_known_slope():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(60):                     # 60 institutions x 8 years
        fe = rng.normal(0, 5)
        for y in range(2010, 2018):
            x = rng.normal(0, 1)
            rows.append({"unitid": i, "year": y, "x": x, "y": 2.0 * x + fe})
    res = panel_ols(pd.DataFrame(rows), "y", ["x"], name="known")
    assert res.coefs.loc["x", "coef"] == pytest.approx(2.0, abs=1e-6)
    assert res.n_entities == 60 and res.n_obs == 480


def test_result_summary_is_printable():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"unitid": np.repeat(range(20), 5), "year": list(range(2010, 2015)) * 20,
                       "x": rng.normal(size=100)})
    df["y"] = 3 * df.x
    text = panel_ols(df, "y", ["x"], name="RQ0").summary()
    assert "RQ0" in text and "100 obs" in text and "20 institutions" in text


def test_panel_ols_errors_loudly_when_nothing_is_left():
    df = pd.DataFrame({"unitid": [1, 2], "year": [2010, 2011], "y": [np.nan] * 2, "x": [1.0, 2.0]})
    with pytest.raises(ValueError, match="no complete cases"):
        panel_ols(df, "y", ["x"])


# --------------------------------------------------------------------- panels

def test_one_row_per_prefers_the_total_subcohort():
    df = pd.DataFrame({"unitid": [1, 1, 2], "year": [2016] * 3,
                       "subcohort": [1, 99, -2], "v": [10, 20, 30]})
    out = panels._one_row_per(df, ["unitid", "year"]).sort_values("unitid")
    assert out.v.tolist() == [20, 30], "99 wins for inst 1; -2 is the fallback for inst 2"


def test_log_kills_zero_and_negative():
    out = panels._log(pd.Series([np.e, 0.0, -5.0]))
    assert out.iloc[0] == pytest.approx(1.0)
    assert out.iloc[1:].isna().all(), "log(0) must be NaN, not -inf"


def test_aid_panel_pivots_long_to_wide(tmp_data):
    write(tmp_data, "sfa-all-undergraduates", 2016, "all", pd.DataFrame({
        "unitid": [1, 1, 1, 2], "year": [2016] * 4,
        "type_of_aid": [3, 5, 11, 5],
        "percent_of_students": [0.7, 0.4, 0.5, -1],   # -1 is the missing sentinel
        "average_amount": [4700.0, 4100.0, 6800.0, 3000.0]}))
    out = panels.aid_panel().set_index("unitid")
    assert out.loc[1, "pct_pell"] == pytest.approx(0.4)
    assert out.loc[1, "avg_grant"] == pytest.approx(4700.0)
    assert np.isnan(out.loc[2, "pct_pell"]), "-1 must become NaN"


def test_pell_gap_is_count_weighted_not_a_mean_of_rates(tmp_data):
    # Pell: 50/200 = .25.  Non-Pell: (90+10)/(150+50) = .50.  Gap = .25.
    # Averaging the two non-Pell *rates* (.60 and .20) would give .40 -- the
    # counts are deliberately uneven so the two answers cannot coincide.
    write(tmp_data, "grad-rates-pell", 2016, "all", pd.DataFrame({
        "unitid": [1] * 3, "year": [2016] * 3, "subcohort": [99] * 3,
        "fed_aid_type": [1, 2, 3],
        "completers_150pct": [50.0, 90.0, 10.0],
        "cohort_adj": [200.0, 150.0, 50.0],
        "cohort_rev": [-1.0, -1.0, -1.0]}))
    g = panels.pell_gap_panel().iloc[0]
    assert g.grad_rate_pell == pytest.approx(0.25)
    assert g.grad_rate_nonpell == pytest.approx(0.50)
    assert g.pell_gap == pytest.approx(0.25)
    assert g.cohort == pytest.approx(400.0)
    assert g.pell_share == pytest.approx(0.50)


def test_pell_gap_drops_cohorts_too_small_to_mean_anything(tmp_data):
    # 3 Pell students all graduate, 2 non-Pell students both fail -> a "gap"
    # of exactly -1.00 that is pure sampling noise.  It must not survive.
    write(tmp_data, "grad-rates-pell", 2016, "all", pd.DataFrame({
        "unitid": [9] * 2, "year": [2016] * 2, "subcohort": [99] * 2,
        "fed_aid_type": [1, 2],
        "completers_150pct": [3.0, 0.0], "cohort_adj": [3.0, 2.0],
        "cohort_rev": [-1.0, -1.0]}))
    assert panels.pell_gap_panel().empty


def test_grad_panel_drops_sentinels_and_dedupes(tmp_data):
    # cohort_rev is -1 on exactly the subcohort=99 rows we keep, so the cohort
    # size has to come from cohort_adj_150pct or it is silently always NaN.
    write(tmp_data, "grad-rates", 2016, "race-99_sex-99", pd.DataFrame({
        "unitid": [1, 1, 2], "year": [2016] * 3, "subcohort": [1, 99, -2],
        "completion_rate_150pct": [0.9, 0.5, -1.0],
        "cohort_adj_150pct": [10.0, 100.0, 20.0],
        "cohort_rev": [10.0, -1.0, 20.0]}))
    out = panels.grad_panel().set_index("unitid")
    assert out.loc[1, "grad_rate"] == pytest.approx(0.5)
    assert out.loc[1, "cohort"] == pytest.approx(100.0)
    assert np.isnan(out.loc[2, "grad_rate"])


def test_sector_dummies_use_sector_1_as_reference():
    p = pd.DataFrame({"sector": [1, 2, 3]})
    out, cols = panels.sector_dummies(p)
    assert cols == ["sector_2", "sector_3"]
    assert out.sector_2.tolist() == [0.0, 1.0, 0.0]


def test_save_writes_a_stata_file_that_reads_back(tmp_path):
    p = pd.DataFrame({"unitid": [1, 2], "year": [2016, 2017],
                      "flag": [True, False],
                      "n": pd.array([1, None], dtype="Int64"),
                      "a_very_long_column_name_that_exceeds_stata_limit": [1.0, 2.0]})
    paths = panels.save(p, "demo", tmp_path)
    back = pd.read_stata(paths[2])
    assert len(back) == 2
    assert max(len(c) for c in back.columns) <= 32
    assert back.flag.tolist() == [1.0, 0.0]


# ------------------------------------------------------- the bootstrap itself

def test_cluster_bootstrap_resamples_with_replacement():
    """An institution drawn twice must appear twice, as two distinct entities.

    Selecting with `unitid.isin(draw)` looks equivalent but de-duplicates,
    which turns the cluster bootstrap into a ~63% subsample *without*
    replacement and shrinks every standard error by roughly a quarter.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "osg"))
    from run_regression import bootstrap

    rng = np.random.default_rng(7)
    rows = []
    for i in range(40):
        fe = rng.normal(0, 3)
        for y in range(2010, 2016):
            xv = rng.normal()
            rows.append({"unitid": i, "year": y, "x": xv, "y": xv + fe + rng.normal(0, 2)})
    panel = pd.DataFrame(rows)

    draws = bootstrap(panel, "y", ["x"], 60, entity_fe=True)
    assert len(draws) == 60
    # Each replicate must carry the full 40-institution sample size, not ~63%.
    assert draws["x"].std() > 0
    # And the bootstrap must centre on the point estimate.
    point = panel_ols(panel, "y", ["x"]).coefs.loc["x", "coef"]
    assert draws["x"].mean() == pytest.approx(point, abs=4 * draws["x"].std())
