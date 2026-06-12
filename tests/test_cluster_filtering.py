"""Test zip4_cluster_group filtering functionality."""
from __future__ import annotations

import pandas as pd
import pytest

from regional_viz.aggregate import aggregate_to_county
from regional_viz.synthetic import seed_dominant_county_map


def test_cluster_filter_reduces_row_count():
    """Filtering by cluster group should reduce the number of rows."""
    df = pd.DataFrame({
        "eps_zip": ["10001", "10001", "10002", "10003"],
        "zip4": ["0001", "0002", "0050", "0100"],
        "patients": [150, 120, 80, 45],
        "zip4_cluster_group": ["GroupA", "GroupA", "GroupB", "GroupC"],
    })

    # Filter to only GroupA
    df_filtered = df[df["zip4_cluster_group"].isin(["GroupA"])]

    assert len(df_filtered) == 2
    assert df_filtered["patients"].sum() == 270  # 150 + 120


def test_cluster_filter_preserves_aggregation_logic():
    """Filtering should work correctly with the aggregation pipeline."""
    df = pd.DataFrame({
        "eps_zip": ["10001", "10001", "10002", "10003"],
        "zip4": ["0001", "0002", "0050", "0100"],
        "patients": [150, 120, 80, 45],
        "zip4_cluster_group": ["Urban", "Urban", "Suburban", "Rural"],
    })

    zip2fips = {"10001": "36061", "10002": "36061", "10003": "36047"}

    # No filter - all data
    county_df_all, cov_all = aggregate_to_county(df, zip2fips)
    assert cov_all.total_count == 395  # 150 + 120 + 80 + 45

    # Filter to Urban only
    df_urban = df[df["zip4_cluster_group"] == "Urban"]
    county_df_urban, cov_urban = aggregate_to_county(df_urban, zip2fips)
    assert cov_urban.total_count == 270  # 150 + 120


def test_no_cluster_column_backward_compatibility():
    """Data without zip4_cluster_group column should still work."""
    df = pd.DataFrame({
        "eps_zip": ["10001", "10001", "10002"],
        "zip4": ["0001", "0002", "0050"],
        "patients": [150, 120, 80],
    })

    # Verify no cluster column
    assert "zip4_cluster_group" not in df.columns

    zip2fips = {"10001": "36061", "10002": "36061"}

    # Should aggregate normally
    county_df, cov = aggregate_to_county(df, zip2fips)
    assert cov.total_count == 350  # 150 + 120 + 80
    assert len(county_df) == 1  # All map to same county


def test_empty_cluster_selection_returns_no_data():
    """Selecting no clusters should return empty dataframe."""
    df = pd.DataFrame({
        "eps_zip": ["10001", "10002"],
        "zip4": ["0001", "0050"],
        "patients": [150, 80],
        "zip4_cluster_group": ["GroupA", "GroupB"],
    })

    # Simulate selecting clusters that don't exist
    df_filtered = df[df["zip4_cluster_group"].isin(["GroupC", "GroupD"])]

    assert len(df_filtered) == 0


def test_multiple_cluster_selection():
    """Selecting multiple clusters should include all matching rows."""
    df = pd.DataFrame({
        "eps_zip": ["10001", "10002", "10003", "10004"],
        "zip4": ["0001", "0050", "0100", "0200"],
        "patients": [150, 80, 45, 60],
        "zip4_cluster_group": ["GroupA", "GroupB", "GroupC", "GroupA"],
    })

    # Select GroupA and GroupC
    df_filtered = df[df["zip4_cluster_group"].isin(["GroupA", "GroupC"])]

    assert len(df_filtered) == 3  # rows 0, 2, 3
    assert df_filtered["patients"].sum() == 255  # 150 + 45 + 60
