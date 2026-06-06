"""Roll ZIP+4 patient counts up to county FIPS.

Two public functions, mirroring the two crosswalk strategies:

  * `aggregate_to_county`  — uses a ZIP -> dominant-FIPS dict. Patient totals
    are exactly preserved for ZIPs found in the mapping; unmapped ZIPs are
    reported in the returned coverage dict so the caller can decide what to
    do (warn, drop, fall back to a state-level rollup, etc.).

  * `allocate_hud` — uses the HUD residential-ratio table to split each
    ZIP's count across the counties it overlaps. Totals are preserved up to
    floating-point error.

Both functions deliberately do NOT silently drop unmapped ZIPs — coverage is
returned to the caller. Silent loss in a claims pipeline is a defect.
"""
from __future__ import annotations

from typing import Mapping, NamedTuple

import pandas as pd


class CoverageReport(NamedTuple):
    total_count: int
    mapped_count: int
    unmapped_zip_count: int

    @property
    def coverage_ratio(self) -> float:
        return self.mapped_count / self.total_count if self.total_count else 0.0


def aggregate_to_county(
    df: pd.DataFrame,
    zip2fips: Mapping[str, str],
    zip_col: str = "eps_zip",
    count_col: str = "patients",
) -> tuple[pd.DataFrame, CoverageReport]:
    """Collapse ZIP+4 rows to county FIPS via the dominant-county mapping.

    Returns ``(county_df, coverage)``:
      * county_df: columns ``fips, <count_col>`` sorted descending by count.
      * coverage: how much of the input total made it into the rollup.
    """
    zip5 = df.groupby(zip_col, as_index=False)[count_col].sum()
    zip5["fips"] = zip5[zip_col].map(zip2fips)

    total = int(df[count_col].sum())
    mapped_rows = zip5.dropna(subset=["fips"])
    mapped = int(mapped_rows[count_col].sum())
    unmapped_zips = int(zip5["fips"].isna().sum())

    cty = (
        mapped_rows.groupby("fips", as_index=False)[count_col]
        .sum()
        .sort_values(count_col, ascending=False, ignore_index=True)
    )
    return cty, CoverageReport(total, mapped, unmapped_zips)


def allocate_hud(
    df: pd.DataFrame,
    hud: pd.DataFrame,
    zip_col: str = "eps_zip",
    count_col: str = "patients",
) -> tuple[pd.DataFrame, CoverageReport]:
    """Distribute each ZIP's count across counties by HUD residential ratio.

    ``hud`` must have columns ``zip, fips, res_ratio`` (use
    :func:`crosswalk.load_hud_allocation`). Sum of ratios per ZIP is ~1.0.
    Output count column is a float because allocation produces fractions.
    """
    zip5 = df.groupby(zip_col, as_index=False)[count_col].sum()
    merged = zip5.merge(hud, left_on=zip_col, right_on="zip", how="left")
    merged["alloc"] = merged[count_col] * merged["res_ratio"]

    total = int(df[count_col].sum())
    mapped_rows = merged.dropna(subset=["fips"])
    mapped = float(mapped_rows["alloc"].sum())
    unmapped_zips = int(merged.loc[merged["fips"].isna(), zip_col].nunique())

    cty = (
        mapped_rows.groupby("fips", as_index=False)["alloc"]
        .sum()
        .rename(columns={"alloc": count_col})
        .sort_values(count_col, ascending=False, ignore_index=True)
    )
    return cty, CoverageReport(total, int(round(mapped)), unmapped_zips)
