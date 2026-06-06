from __future__ import annotations

import pandas as pd
import pytest

from regional_viz.loader import SchemaError, load_zip_counts, validate_schema


def test_validate_schema_accepts_required_columns():
    df = pd.DataFrame({"eps_zip": ["10001"], "patients": [1]})
    validate_schema(df)  # no raise


def test_validate_schema_rejects_missing_columns():
    df = pd.DataFrame({"zip": ["10001"], "patients": [1]})
    with pytest.raises(SchemaError, match="eps_zip"):
        validate_schema(df)


def test_load_zip_counts_preserves_leading_zero(tmp_path):
    """Hartford, CT is 06103. If pandas reads it as int we get 6103 and the
    county lookup silently misses every New England ZIP."""
    p = tmp_path / "raw.csv"
    p.write_text("eps_zip,zip4,patients\n06103,1234,7\n10001,5555,3\n")
    df = load_zip_counts(p)
    assert df["eps_zip"].tolist() == ["06103", "10001"]
    # Must be string-like (object or StringDtype, depending on pandas version),
    # never a numeric dtype that would strip the leading zero.
    assert df["eps_zip"].map(type).eq(str).all()


def test_load_zip_counts_zfills_short_zips(tmp_path):
    """Even if upstream strips the leading zero, we restore it."""
    p = tmp_path / "raw.csv"
    p.write_text("eps_zip,patients\n6103,7\n")
    df = load_zip_counts(p)
    assert df["eps_zip"].iloc[0] == "06103"


def test_load_zip_counts_raises_on_bad_schema(tmp_path):
    p = tmp_path / "raw.csv"
    p.write_text("postal_code,count\n10001,1\n")
    with pytest.raises(SchemaError):
        load_zip_counts(p)
