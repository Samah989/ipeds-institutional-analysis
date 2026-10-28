"""Download every IPEDS slice the three research questions need.

Run this on the OSG *access point* (or your laptop), never as a submitted
HTCondor job: OSPool execute nodes have no general outbound internet, only a
proxy scoped to software repos.  See osg/README.md.

Everything lands in data/ as parquet and is cached, so re-running is free and
a interrupted pull picks up where it stopped.

    python osg/pull_all_panels.py
"""

import logging
import sys
from pathlib import Path

# Works both from the repo root (src/ is one level up from this file) and
# inside an HTCondor job, where inputs land flat next to the script.
sys.path[:0] = [str(Path(__file__).resolve().parent),
                str(Path(__file__).resolve().parents[1])]

from src.data_pull import COVERAGE, fetch_years

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# (topic, years, extra query filters).  Filtering server-side is the single
# biggest speed-up available: grad-rates is 224,501 rows/year unfiltered but
# 9,118 rows -- one page, no pagination -- once we ask for race/sex totals.
PULLS = [
    ("directory", COVERAGE["directory"], {}),
    ("finance", COVERAGE["finance"], {}),
    ("sfa-all-undergraduates", COVERAGE["sfa-all-undergraduates"], {}),
    ("grad-rates", COVERAGE["grad-rates"], {"race": 99, "sex": 99}),
    ("grad-rates-pell", COVERAGE["grad-rates-pell"], {}),
]

if __name__ == "__main__":
    for topic, years, filters in PULLS:
        df = fetch_years(topic, years, **filters)
        print(f"{topic}: {len(df):,} rows, {min(years)}-{max(years)}", flush=True)
    print("All panels pulled.")
