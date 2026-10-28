# IPEDS Institutional Analysis

Longitudinal panel research on U.S. postsecondary institutions, built on the
Urban Institute [Education Data Portal](https://educationdata.urban.org/documentation/)
(a free, no-key REST wrapper over IPEDS). Three research questions, each a
short notebook locally and an HTCondor job on the OSPool cluster at
`ap40.uw.osg-htc.org`.

**Author.** Samah Alshrief · [github.com/Samah989](https://github.com/Samah989)

## The three questions

| | Question | Sample | Years |
|---|---|---|---|
| **RQ1** | When state appropriations per student fall, does net tuition revenue per student rise? | public 4-year (sector 1) | 2004-2017 |
| **RQ2** | Does the instruction-vs-administration spending mix predict 6-year completion? | 4-year (sectors 1-3) | 2004-2017 |
| **RQ3** | What is associated with a narrower Pell / non-Pell completion gap? | 4-year (sectors 1-3) | 2015-2021 |

All three use institution-level panels with year fixed effects and standard
errors clustered by institution; RQ1 and RQ2 add institution fixed effects.

### Why those year ranges

They are set by what the portal actually has, verified endpoint by endpoint  - 
not by what we'd like. `finance` **returns zero rows from 2018 onward**, which
caps anything using institutional finances at 2017. `grad-rates-pell` does not
start until 2015. The full map lives in `src/data_pull.COVERAGE`.

## Getting started (about 10 minutes, plus the download)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python osg/pull_all_panels.py
```

That downloads every slice the three questions need into `data/` as parquet  - 
roughly 20-40 minutes, fully cached, and safe to interrupt and restart
(finished years are skipped instantly). Then:

```bash
.venv/bin/jupyter lab notebooks/
```

Start with `00_ipeds_api_tutorial.ipynb`  -  it is the five things about this API
that will otherwise cost you a day. Then run `01`, `02`, `03` in any order;
each takes seconds because everything is already cached.

## Repository layout

```
src/data_pull.py     API client: pagination, retries, parquet cache, sentinel handling
src/panels.py        the three analysis panels  -  the single source of truth
src/regression.py    CPI deflator + two-way fixed-effects panel OLS
notebooks/           00 API tutorial, 01/02/03 one per research question
osg/                 OSPool scale-out (see osg/README.md)
tests/               45 tests: unit tests run offline, integration tests use data/
data/  results/      parquet cache and outputs (both gitignored)
```

## Using the panels in Stata

Every notebook ends by writing its analysis panel three ways:

```
results/rq1_panel.parquet    results/rq1_panel.csv    results/rq1_panel.dta
```

The `.dta` is Stata 14+ (version 118), with column names truncated to Stata's
32-character limit and nullable dtypes cast to plain floats. In Stata:

```stata
use "results/rq1_panel.dta", clear
xtset unitid year
xtreg log_net_tuition_per_fte log_appr_per_fte log_fte i.year, fe vce(cluster unitid)
```

That reproduces the RQ1 specification exactly.

## Running the tests

```bash
.venv/bin/python -m pytest tests -q
```

`tests/test_pipeline.py` needs no network and no data  -  it drives the client
against a fake `requests` and the panel builders against hand-written fixtures.
`tests/test_real_data.py` checks the actual cache (no duplicate institution-years,
no `-1` sentinels surviving, rates inside [0,1], the model fits) and skips
itself if you haven't pulled yet.

## Scaling to OSPool

```bash
./launch.sh pull        # runs the download ON the access point (not a condor job)
./launch.sh regress     # condor_submit  -  one job per research question
./launch.sh status
./launch.sh pull-back
```

The download deliberately does **not** run as an HTCondor job: OSPool execute
nodes have no general outbound internet, only a proxy scoped to software
repositories. The regression *is* a real job  -  pure computation over parquet
that's already local. See [`osg/README.md`](osg/README.md), and run
`bash osg/preflight.sh` before every submit.

## Data source

U.S. Department of Education, Integrated Postsecondary Education Data System
(IPEDS), accessed through the Urban Institute Education Data Portal.

## License

Private research repository. Not for redistribution without author permission.
