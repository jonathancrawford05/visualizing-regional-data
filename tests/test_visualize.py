from __future__ import annotations

import pandas as pd

from regional_viz.visualize import (
    distribution_data,
    distribution_figure,
    distribution_histogram,
    distribution_quantiles,
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
