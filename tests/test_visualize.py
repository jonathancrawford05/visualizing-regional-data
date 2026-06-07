from __future__ import annotations

import pandas as pd
import pytest

from regional_viz.visualize import (
    distribution_data,
    distribution_figure,
    distribution_histogram,
    distribution_quantiles,
    filter_county_df_by_percentile,
    fips_to_county_name,
)


def test_distribution_data_sorts_and_limits():
    df = pd.DataFrame(
        {
            "fips": ["00001", "00002", "00001", "00003"],
            "patients": [10, 5, 7, 3],
        }
    )
    out = distribution_data(df)
    # totals: 00001 -> 17, 00002 -> 5, 00003 -> 3
    assert list(out["fips"]) == ["00001", "00002", "00003"]
    assert list(out["patients"]) == [17, 5, 3]

    top2 = distribution_data(df, top_n=2)
    assert len(top2) == 2
    assert list(top2["fips"]) == ["00001", "00002"]


def test_distribution_data_filters_by_min_patients():
    df = pd.DataFrame(
        {
            "fips": ["00001", "00002", "00001", "00003"],
            "patients": [10, 5, 7, 3],
        }
    )
    out = distribution_data(df, min_patients=6)
    assert list(out["fips"]) == ["00001"]
    assert list(out["patients"]) == [17]


def test_distribution_data_includes_county_names():
    df = pd.DataFrame(
        {
            "fips": ["36061", "09003", "12086"],
            "patients": [100, 50, 20],
        }
    )
    county_names = {
        "36061": ("New York", "NY"),
        "09003": ("Hartford", "CT"),
        "12086": ("Miami-Dade", "FL"),
    }
    out = distribution_data(df, county_names=county_names)
    assert "county" in out.columns
    assert "state" in out.columns
    assert list(out["county"]) == ["New York", "Hartford", "Miami-Dade"]
    assert list(out["state"]) == ["NY", "CT", "FL"]


def test_distribution_data_county_names_partial_coverage():
    """Unknown FIPS codes get empty strings, not errors."""
    df = pd.DataFrame({"fips": ["36061", "99999"], "patients": [100, 50]})
    county_names = {"36061": ("New York", "NY")}
    out = distribution_data(df, county_names=county_names)
    assert out.loc[out["fips"] == "99999", "county"].iloc[0] == ""
    assert out.loc[out["fips"] == "99999", "state"].iloc[0] == ""


def test_distribution_figure_returns_plotly_figure():
    df = pd.DataFrame(
        {
            "fips": ["00001", "00002", "00001", "00003"],
            "patients": [10, 5, 7, 3],
        }
    )
    fig = distribution_figure(df, top_n=2)
    assert len(fig.data[0].x) == 2
    assert list(fig.data[0].x) == ["00001", "00002"]

    fig = distribution_figure(df, min_patients=6)
    assert len(fig.data[0].x) == 1
    assert list(fig.data[0].x) == ["00001"]


def test_distribution_figure_uses_county_name_labels():
    """When county_names are provided, x-axis shows 'County, ST' not raw FIPS."""
    df = pd.DataFrame({"fips": ["36061", "09003"], "patients": [100, 50]})
    county_names = {"36061": ("New York", "NY"), "09003": ("Hartford", "CT")}
    fig = distribution_figure(df, county_names=county_names)
    x_labels = list(fig.data[0].x)
    assert x_labels == ["New York, NY", "Hartford, CT"]


def test_distribution_histogram_and_quantiles():
    df = pd.DataFrame(
        {
            "fips": ["00001", "00002", "00001", "00003", "00004"],
            "patients": [10, 5, 7, 3, 20],
        }
    )
    fig = distribution_histogram(df, bins=5, min_patients=8)
    assert fig.data[0].type == "bar"
    assert fig.layout.title.text == "Patient count distribution across counties"
    assert fig.layout.xaxis.title.text == "Patients per county (log buckets)"

    quantiles = distribution_quantiles(df, quantiles=(0.5, 0.9))
    assert list(quantiles["quantile"]) == [50, 90]
    assert list(quantiles["patients"]) == [7.0, 16.0]


# ---------------------------------------------------------------------------
# filter_county_df_by_percentile
# ---------------------------------------------------------------------------

def _make_county_df(patients: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {"fips": [f"{i:05d}" for i in range(len(patients))], "patients": patients}
    )


def test_filter_county_df_by_percentile_zero_returns_all():
    df = _make_county_df([10, 20, 30, 40, 50])
    out = filter_county_df_by_percentile(df, 0.0)
    assert len(out) == 5


def test_filter_county_df_by_percentile_excludes_low_counties():
    df = _make_county_df([10, 20, 30, 40, 50])
    # 80th percentile of [10,20,30,40,50] is 42, so only 50 survives
    out = filter_county_df_by_percentile(df, 0.80)
    assert all(out["patients"] >= out["patients"].min())
    assert len(out) < 5


def test_filter_county_df_by_percentile_one_hundred():
    """1.0 returns at least the maximum county."""
    df = _make_county_df([10, 20, 30, 40, 50])
    out = filter_county_df_by_percentile(df, 1.0)
    assert 50 in list(out["patients"])


def test_filter_county_df_by_percentile_preserves_columns():
    df = pd.DataFrame({"fips": ["36061", "09003"], "patients": [100, 5]})
    out = filter_county_df_by_percentile(df, 0.5)
    assert list(out.columns) == ["fips", "patients"]


# ---------------------------------------------------------------------------
# fips_to_county_name
# ---------------------------------------------------------------------------

def _make_mock_geojson(entries: list[tuple[str, str, str]]) -> dict:
    """Build a minimal GeoJSON dict: list of (fips, county_name, state_fips)."""
    return {
        "features": [
            {
                "id": fips,
                "properties": {"NAME": name, "STATE": state_fips},
            }
            for fips, name, state_fips in entries
        ]
    }


def test_fips_to_county_name_basic():
    geo = _make_mock_geojson([
        ("36061", "New York", "36"),
        ("09003", "Hartford", "09"),
        ("12086", "Miami-Dade", "12"),
    ])
    mapping = fips_to_county_name(geo)
    assert mapping["36061"] == ("New York", "NY")
    assert mapping["09003"] == ("Hartford", "CT")
    assert mapping["12086"] == ("Miami-Dade", "FL")


def test_fips_to_county_name_unknown_state_returns_fips_prefix():
    """A state FIPS not in the lookup falls back to the raw 2-digit prefix."""
    geo = _make_mock_geojson([("99001", "TestCounty", "99")])
    mapping = fips_to_county_name(geo)
    assert mapping["99001"] == ("TestCounty", "99")


def test_fips_to_county_name_empty_geojson():
    assert fips_to_county_name({"features": []}) == {}
    assert fips_to_county_name({}) == {}
