"""ZIP5 -> county FIPS crosswalks.

Two strategies are exposed; both share the same Mapping return shape so the
aggregator doesn't care which one was used:

  * `dominant_county_map`: ZIP -> single county FIPS. Pulled from a public
    convenience crosswalk (the GitHub `bgruber/zip2fips` mirror, same one
    the original PoC script used). Easy, no registration, ~95% patient
    coverage on the sample data.

  * `load_hud_allocation`: full HUD USPS ZIP_COUNTY crosswalk with
    residential allocation ratios — the production-grade option. Splits a
    ZIP straddling a county line proportionally rather than dumping all
    rows into one. Requires the HUD xlsx download.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from urllib.request import urlopen

import pandas as pd

DEFAULT_ZIP2FIPS_URL = (
    "https://raw.githubusercontent.com/bgruber/zip2fips/master/zip2fips.json"
)


def load_zip2fips_dominant(url: str = DEFAULT_ZIP2FIPS_URL) -> dict[str, str]:
    """Fetch the public ZIP->dominant-county-FIPS JSON mapping."""
    with urlopen(url) as r:
        raw = json.load(r)
    # Defensive: normalize to 5-digit zero-padded ZIPs and 5-digit FIPS.
    return {str(z).zfill(5): str(f).zfill(5) for z, f in raw.items()}


def dominant_county_map(
    zip_codes: pd.Series,
    mapping: Mapping[str, str],
) -> pd.Series:
    """Look up dominant-county FIPS for each ZIP. Unknown ZIPs become NaN."""
    return zip_codes.map(mapping)


def load_hud_allocation(path: str | Path) -> pd.DataFrame:
    """Load a HUD USPS ZIP_COUNTY xlsx into a tidy allocation frame.

    Returns columns: ``zip, fips, res_ratio`` (residential addresses share).
    Residential ratio is the right choice for a patient/individual map; HUD
    also provides business/other/total ratios for different use-cases.
    """
    df = pd.read_excel(path, dtype={"ZIP": str, "COUNTY": str})
    df = df.rename(columns=str.lower)
    out = df[["zip", "county", "res_ratio"]].copy()
    out["zip"] = out["zip"].str.zfill(5)
    out["county"] = out["county"].str.zfill(5)
    return out.rename(columns={"county": "fips"})
