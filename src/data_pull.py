"""Client for the Urban Institute Education Data Portal (IPEDS).

Free, no API key needed.  Three things the docs don't make obvious, all
verified against the live API:

1. A page holds at most 10,000 rows.  Follow the `next` link -- asking for
   `?page=N` past the end returns HTTP 404, not an empty list.
2. Missing values come back as -1 / -2 / -3, not null.  Never regress on a
   raw column; run it through `to_na()` first.
3. Coverage is uneven.  `finance` stops after 2017, `grad-rates-pell` starts
   in 2015, `sfa-all-undergraduates` is empty in 2003 and after 2021.
   See COVERAGE below.

Docs: https://educationdata.urban.org/documentation/
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

log = logging.getLogger(__name__)

BASE = "https://educationdata.urban.org/api/v1/college-university/ipeds"
# Repo-root/data by default.  Inside an HTCondor job the inputs land flat
# (src/ and data/ side by side), and this resolves to the job's scratch dir,
# which is what we want.  Override with IPEDS_DATA=/some/path.
DATA_DIR = Path(os.environ.get("IPEDS_DATA")
                or Path(__file__).resolve().parents[1] / "data")
TIMEOUT = 300          # an unfiltered grad-rates page can take 20s+
RETRIES = 5
MISSING = (-1, -2, -3)  # the portal's missing-value sentinels

# Years each topic actually returns rows for (probed year by year, 2026-08).
COVERAGE = {
    "directory": range(2003, 2024),
    "finance": range(2003, 2018),            # hard stop: 2018+ returns count=0
    "sfa-all-undergraduates": range(2004, 2022),
    "grad-rates": range(2003, 2024),
    "grad-rates-pell": range(2015, 2024),
}


def _cache_path(topic: str, year: int, nested: str | None, filters: dict) -> Path:
    """One file per (topic, year, nested, filters).  `nested` and `filters`
    MUST be in the key: two calls with different filters hit different URLs
    and return different rows, so sharing a filename silently serves one
    call the other's data."""
    key = json.dumps([topic, year, nested or "", sorted(filters.items())])
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    stem = f"{topic}-{nested}" if nested else topic
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    return DATA_DIR / f"{stem}__{year}__{slug}__{digest}.parquet"


def _get(url: str) -> dict:
    """GET with exponential backoff.  The portal is free and shared, so we
    retry rather than hammer."""
    import requests  # imported lazily so `import src.data_pull` works anywhere

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == RETRIES:
                raise
            wait = 2**attempt
            log.warning("%s (try %d/%d), sleeping %ds", e, attempt, RETRIES, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch(topic: str, year: int, nested: str | None = None,
          use_cache: bool = True, **filters) -> pd.DataFrame:
    """Pull one (topic, year) slice, following pagination, and cache it.

    >>> fetch("directory", 2016, fips=53)      # Washington, 129 rows
    >>> fetch("grad-rates", 2016, race=99, sex=99)   # totals only, 9k not 224k
    """
    cache = _cache_path(topic, year, nested, filters)
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    url = f"{BASE}/{topic}/{year}/" + (f"{nested}/" if nested else "")
    url += "?" + urlencode(filters) if filters else ""
    rows: list[dict] = []
    while url:
        page = _get(url)
        rows += page["results"]
        url = page.get("next")          # never build ?page=N by hand: 404s
        log.info("%s %s: %d rows so far", topic, year, len(rows))

    df = pd.DataFrame(rows)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_parquet(cache, index=False)   # cache empties too, so we don't re-ask
    return df


def fetch_years(topic: str, years, nested: str | None = None, **filters) -> pd.DataFrame:
    """Stack many years of one topic.  Years the portal has no data for are
    skipped with a warning instead of killing a multi-hour pull."""
    frames = []
    for y in years:
        try:
            df = fetch(topic, y, nested=nested, **filters)
        except Exception as e:  # noqa: BLE001
            log.warning("skipping %s %s: %s", topic, y, e)
            continue
        if df.empty:
            log.warning("%s %s returned 0 rows (outside coverage?)", topic, y)
        else:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def to_na(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Replace the portal's -1/-2/-3 sentinels with NaN in `cols` only.

    Scoped deliberately: -2 is a *legitimate* category value in `subcohort`
    and `fed_aid_type`, so a blanket replace would corrupt those columns.
    """
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").mask(
            lambda s: s.isin(MISSING))
    return out


def load_cached(prefix: str, **filters) -> pd.DataFrame:
    """Re-read every cached slice for one topic, from disk, no network.

    `prefix` must be the *full* cache stem (e.g. "finance"), and the filter
    slug must match, so a `sector=1` pull and a `fips=53` pull of the same
    topic are never silently concatenated into a double-counted panel.
    """
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    files = sorted(DATA_DIR.glob(f"{prefix}__*__{slug}__*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"no cached {prefix} (filters={filters or 'none'}) in {DATA_DIR}; "
            f"run `python osg/pull_all_panels.py` first")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
