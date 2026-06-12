"""Load and validate the upstream Epsilon x Kythera ZIP+4 patient-count table.

The critical correctness concerns at this stage:
  * ZIP codes MUST be strings — pandas silently strips leading zeros from
    numeric ZIPs, which corrupts every New England / Puerto Rico ZIP.
  * The schema is enforced explicitly so a renamed column upstream fails
    loudly rather than silently producing an empty map.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = ("eps_zip", "patients")


class SchemaError(ValueError):
    """Raised when the input frame is missing required columns."""


def validate_schema(df: pd.DataFrame, required: Iterable[str] = REQUIRED_COLUMNS) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"Input is missing required columns: {missing}")


def load_zip_counts(
    path: str | Path,
    zip_col: str = "eps_zip",
    count_col: str = "patients",
) -> pd.DataFrame:
    """Read a ZIP+4 patient-count CSV.

    Returns a frame with `zip_col` zero-padded to 5 digits and `count_col`
    coerced to integer. The `zip4` suffix column (if present) is preserved
    but unused downstream — it does not help county rollup.

    Optional columns:
      * `zip4_cluster_group` — cluster assignment for ZIP+4 combinations.
        If present, can be used for filtering in the dashboard.
    """
    df = pd.read_csv(path, dtype={zip_col: str})
    validate_schema(df, required=(zip_col, count_col))
    df[zip_col] = df[zip_col].str.zfill(5)
    df[count_col] = df[count_col].astype(int)
    return df
