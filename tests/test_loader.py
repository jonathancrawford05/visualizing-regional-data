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


def test_load_zip_counts_accepts_optional_zip4_cluster_group(tmp_path):
    """The zip4_cluster_group column is optional for backward compatibility."""
    p = tmp_path / "with_cluster.csv"
    p.write_text("eps_zip,zip4,patients,zip4_cluster_group\n06103,1234,7,GroupA\n10001,5555,3,GroupB\n")
    df = load_zip_counts(p)
    assert "zip4_cluster_group" in df.columns
    assert df["zip4_cluster_group"].tolist() == ["GroupA", "GroupB"]


def test_load_zip_counts_works_without_zip4_cluster_group(tmp_path):
    """CSVs without zip4_cluster_group column should still load (backward compatibility)."""
    p = tmp_path / "no_cluster.csv"
    p.write_text("eps_zip,zip4,patients\n06103,1234,7\n10001,5555,3\n")
    df = load_zip_counts(p)
    assert "zip4_cluster_group" not in df.columns
    assert len(df) == 2


def test_load_zip_counts_accepts_metric_columns(tmp_path):
    """New metric columns (prevalence, mortality) are optional and preserved."""
    p = tmp_path / "with_metrics.csv"
    p.write_text(
        "eps_zip,zip4,patients,cancer_prevalence_numerator,all_cause_deaths,cancer_deaths\n"
        "06103,1234,100,15,2,1\n"
        "10001,5555,50,8,1,0\n"
    )
    df = load_zip_counts(p)
    assert "cancer_prevalence_numerator" in df.columns
    assert "all_cause_deaths" in df.columns
    assert "cancer_deaths" in df.columns
    assert df["cancer_prevalence_numerator"].tolist() == [15, 8]
    assert df["all_cause_deaths"].tolist() == [2, 1]
    assert df["cancer_deaths"].tolist() == [1, 0]


def test_load_zip_counts_metric_columns_are_numeric(tmp_path):
    """Metric columns must be coerced to appropriate numeric types."""
    p = tmp_path / "with_metrics.csv"
    p.write_text(
        "eps_zip,zip4,patients,cancer_prevalence_numerator,all_cause_deaths,cancer_deaths\n"
        "06103,1234,100,15,2,1\n"
    )
    df = load_zip_counts(p)
    assert df["cancer_prevalence_numerator"].dtype in ["int64", "Int64"]
    assert df["all_cause_deaths"].dtype in ["int64", "Int64"]
    assert df["cancer_deaths"].dtype in ["int64", "Int64"]


def test_load_zip_counts_works_without_metric_columns(tmp_path):
    """CSVs without new metric columns still work (backward compatibility)."""
    p = tmp_path / "old_format.csv"
    p.write_text("eps_zip,zip4,patients\n06103,1234,7\n")
    df = load_zip_counts(p)
    assert "cancer_prevalence_numerator" not in df.columns
    assert "all_cause_deaths" not in df.columns
    assert "cancer_deaths" not in df.columns
    assert len(df) == 1
