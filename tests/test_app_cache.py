"""Component A (perf plan): the cached data-path wrappers in the app.

Streamlit's cache behaviour itself is hard to unit-test (it needs a script
run context), but the wrappers are deliberately thin: they construct a cache
key from documented inputs and delegate to the already-tested pure functions.
These tests load the app module and assert the delegation is faithful — i.e.
caching does not change results — including the ``_``-prefixed payload
threading and the "aggregate all clusters, then filter" restructure.

Run outside a Streamlit runtime, ``@st.cache_data`` functions execute and
return their value (caching is simply a no-op), so we can call them directly.
"""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

from regional_viz.aggregate import aggregate_metrics_to_county, aggregate_to_county
from regional_viz.cluster import CLUSTER_METRIC_SPECS, aggregate_to_cluster_units
from regional_viz.synthetic import generate_synthetic_zip4


def _load_app_module():
    """Import ``app/streamlit_app.py`` by path (the app dir is not a package)."""
    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    spec = importlib.util.spec_from_file_location("streamlit_app", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = _load_app_module()


def test_parse_upload_roundtrips_and_preserves_leading_zero_zip():
    csv = "eps_zip,zip4,patients\n6103,0001,3\n10001,2000,7\n"
    raw = csv.encode()

    df = app.parse_upload("upload-1", raw)

    # Leading-zero ZIP invariant is load-bearing (zfill to 5).
    assert df["eps_zip"].tolist() == ["06103", "10001"]
    assert df["patients"].tolist() == [3, 7]
    assert df["patients"].dtype == int


def test_get_synthetic_df_matches_direct_generation():
    cached = app.get_synthetic_df(n_rows=500, seed=7, n_clusters=4, with_metrics=True)
    direct = generate_synthetic_zip4(
        n_rows=500, seed=7, n_clusters=4, with_metrics=True
    )
    pd.testing.assert_frame_equal(cached, direct)


def test_cached_aggregate_to_county_delegates(tiny_zip4_frame, tiny_zip2fips):
    cached_df, cached_cov = app.cached_aggregate_to_county(
        "fid", (), False, tiny_zip4_frame, tiny_zip2fips
    )
    direct_df, direct_cov = aggregate_to_county(tiny_zip4_frame, tiny_zip2fips)

    pd.testing.assert_frame_equal(cached_df, direct_df)
    assert cached_cov == direct_cov


def test_cached_aggregate_to_county_multi_metric_delegates():
    df = generate_synthetic_zip4(n_rows=800, seed=3, n_clusters=5, with_metrics=True)
    zip2fips = {z: "00001" for z in df["eps_zip"].unique()}

    cached_df, cached_cov = app.cached_aggregate_to_county(
        "fid", (), True, df, zip2fips
    )
    direct_df, direct_cov = aggregate_metrics_to_county(df, zip2fips)

    pd.testing.assert_frame_equal(cached_df, direct_df)
    assert cached_cov == direct_cov


def test_cached_cluster_units_aggregates_all_clusters_then_filter_is_equivalent():
    """The restructure: aggregate all clusters, then filter ⇒ same as filter-first."""
    df = generate_synthetic_zip4(n_rows=1500, seed=11, n_clusters=6, with_metrics=True)
    metric_key = "cancer_prevalence_pct"
    spec = CLUSTER_METRIC_SPECS[metric_key]

    units_full = app.cached_aggregate_to_cluster_units(
        "fid", "zip4", metric_key, df
    )

    # Full aggregation covers every cluster present in the input.
    assert set(units_full["cluster"]) == set(df["zip4_cluster_group"].dropna())

    # Filtering the cached full result to a subset must equal aggregating only
    # that subset up front (the old code path).
    selected = sorted(df["zip4_cluster_group"].dropna().unique())[:2]
    filtered_after = (
        units_full[units_full["cluster"].isin(selected)]
        .sort_values(["cluster", "unit"], ignore_index=True)
    )

    sub = df[df["zip4_cluster_group"].isin(selected)]
    filtered_before = aggregate_to_cluster_units(
        sub,
        level="zip4",
        numerator_col=spec.numerator_col,
        denominator_col=spec.denominator_col,
        multiplier=spec.multiplier,
    ).sort_values(["cluster", "unit"], ignore_index=True)

    pd.testing.assert_frame_equal(filtered_after, filtered_before)
