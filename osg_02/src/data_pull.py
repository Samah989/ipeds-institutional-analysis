"""Lightweight IPEDS data client  -  workshop edition.

Pulls directory + grad-rates from the Urban Institute Education Data Portal.
Only 3 years to keep the download under 2 minutes.

API docs: https://educationdata.urban.org/documentation/
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
DATA_DIR = Path(os.environ.get("IPEDS_DATA")
                or Path(__file__).resolve().parents[1] / "data")
TIMEOUT = 300
RETRIES = 5
MISSING = (-1, -2, -3)

# Only 3 years  -  keeps the pull under 2 minutes
COVERAGE = {
    "directory": range(2020, 2023),
    "grad-rates": range(2020, 2023),
}


def _cache_path(topic, year, nested, filters):
    key = json.dumps([topic, year, nested or "", sorted(filters.items())])
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    stem = f"{topic}-{nested}" if nested else topic
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    return DATA_DIR / f"{stem}__{year}__{slug}__{digest}.parquet"


def _get(url):
    import requests
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


def to_na(df, cols=None):
    """Replace IPEDS missing sentinels (-1, -2, -3) with NaN."""
    import numpy as np
    target = cols or df.select_dtypes("number").columns
    for c in target:
        if c in df.columns:
            df[c] = df[c].replace(list(MISSING), np.nan)
    return df


def fetch(topic, year, nested=None, use_cache=True, **filters):
    cache = _cache_path(topic, year, nested, filters)
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    url = f"{BASE}/{topic}/{year}/" + (f"{nested}/" if nested else "")
    url += "?" + urlencode(filters) if filters else ""
    rows = []
    while url:
        page = _get(url)
        rows += page["results"]
        url = page.get("next")
        log.info("%s %s: %d rows so far", topic, year, len(rows))

    df = pd.DataFrame(rows)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def fetch_years(topic, years, nested=None, **filters):
    frames = []
    for y in years:
        try:
            frames.append(fetch(topic, y, nested, **filters))
        except Exception as e:
            log.warning("skip %s %s: %s", topic, y, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_cached(prefix, **filters):
    slug = "_".join(f"{k}-{v}" for k, v in sorted(filters.items())) or "all"
    files = sorted(DATA_DIR.glob(f"{prefix}__*__{slug}__*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"no cached {prefix} in {DATA_DIR}; run `bash pull_data.sh` first")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def fetch_all():
    """Download directory + grad-rates for 2020-2022."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for topic, years in COVERAGE.items():
        log.info("==> Fetching %s (%d-%d)", topic, years.start, years.stop - 1)
        if topic == "grad-rates":
            fetch_years(topic, years, race=99, sex=99)
        else:
            fetch_years(topic, years)
    log.info("==> All panels cached in %s", DATA_DIR)
