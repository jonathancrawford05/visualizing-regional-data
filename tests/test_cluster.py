"""Tests for the cluster-comparison feature.

Covers the four pure transforms that back the new dashboard tab:

  * aggregate_to_cluster_units — raw ZIP+4 rows -> per-unit rows within a
    cluster, at ZIP or ZIP+4 granularity.
  * credibility_factor — the three Z formulas (sqrt / linear / Bühlmann).
  * apply_credibility — shrink each unit toward its cluster's expected value.
  * iqr_upper_fence / apply_cap — IQR-based censoring of the long tail.

All assertions use hand-computed numbers so the math is pinned, not just
the shape of the output.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from regional_viz.cluster import (
    CLUSTER_METRIC_SPECS,
    aggregate_to_cluster_units,
    apply_cap,
    apply_credibility,
    credibility_factor,
    iqr_upper_fence,
)


@pytest.fixture
def raw_cluster_frame() -> pd.DataFrame:
    """Two clusters, an all-cause-mortality numerator, ZIP+4 granularity.

    Cluster A:
      10001-0001  patients=100  deaths=2
      10001-0002  patients=100  deaths=4
      10002-0050  patients=50   deaths=1
    Cluster B:
      10003-0100  patients=40   deaths=8
    """
    return pd.DataFrame(
        {
            "eps_zip": ["10001", "10001", "10002", "10003"],
            "zip4": ["0001", "0002", "0050", "0100"],
            "zip4_cluster_group": ["A", "A", "A", "B"],
            "patients": [100, 100, 50, 40],
            "all_cause_deaths": [2, 4, 1, 8],
        }
    )


# ---------------------------------------------------------------------------
# aggregate_to_cluster_units
# ---------------------------------------------------------------------------

def test_aggregate_units_zip4_level(raw_cluster_frame):
    units = aggregate_to_cluster_units(
        raw_cluster_frame,
        level="zip4",
        numerator_col="all_cause_deaths",
        multiplier=100_000.0,
    )
    assert set(units.columns) == {"cluster", "unit", "numerator", "denominator", "value"}
    # ZIP+4 keeps every +4 distinct: 4 units total.
    assert len(units) == 4
    row = units[units["unit"] == "10001-0001"].iloc[0]
    assert row["cluster"] == "A"
    assert row["numerator"] == 2
    assert row["denominator"] == 100
    assert row["value"] == pytest.approx(2_000.0)  # 1e5 * 2 / 100


def test_aggregate_units_zip_level_collapses_plus4(raw_cluster_frame):
    units = aggregate_to_cluster_units(
        raw_cluster_frame,
        level="zip",
        numerator_col="all_cause_deaths",
        multiplier=100_000.0,
    )
    # ZIP level collapses 10001's two +4 rows into one unit: 3 units total.
    assert len(units) == 3
    z10001 = units[units["unit"] == "10001"].iloc[0]
    assert z10001["numerator"] == 6  # 2 + 4
    assert z10001["denominator"] == 200  # 100 + 100
    assert z10001["value"] == pytest.approx(3_000.0)  # 1e5 * 6 / 200


def test_aggregate_units_zero_denominator_is_zero_not_nan():
    df = pd.DataFrame(
        {
            "eps_zip": ["10001"],
            "zip4": ["0001"],
            "zip4_cluster_group": ["A"],
            "patients": [0],
            "all_cause_deaths": [0],
        }
    )
    units = aggregate_to_cluster_units(
        df, level="zip4", numerator_col="all_cause_deaths", multiplier=100_000.0
    )
    assert units["value"].iloc[0] == 0.0
    assert not units["value"].isna().any()


def test_aggregate_units_rejects_bad_level(raw_cluster_frame):
    with pytest.raises(ValueError):
        aggregate_to_cluster_units(
            raw_cluster_frame,
            level="county",
            numerator_col="all_cause_deaths",
            multiplier=100_000.0,
        )


# ---------------------------------------------------------------------------
# credibility_factor
# ---------------------------------------------------------------------------

def test_credibility_sqrt():
    # Z = min(1, sqrt(n / threshold))
    assert credibility_factor(100, 100, "sqrt") == pytest.approx(1.0)
    assert credibility_factor(25, 100, "sqrt") == pytest.approx(0.5)
    assert credibility_factor(400, 100, "sqrt") == pytest.approx(1.0)  # capped
    assert credibility_factor(0, 100, "sqrt") == pytest.approx(0.0)


def test_credibility_linear():
    assert credibility_factor(50, 100, "linear") == pytest.approx(0.5)
    assert credibility_factor(100, 100, "linear") == pytest.approx(1.0)
    assert credibility_factor(250, 100, "linear") == pytest.approx(1.0)  # capped


def test_credibility_buhlmann():
    # Z = n / (n + k); threshold plays the role of k.
    assert credibility_factor(100, 100, "buhlmann") == pytest.approx(0.5)
    assert credibility_factor(300, 100, "buhlmann") == pytest.approx(0.75)
    assert credibility_factor(0, 100, "buhlmann") == pytest.approx(0.0)


def test_credibility_factor_vectorized():
    z = credibility_factor(np.array([0, 25, 100, 400]), 100, "sqrt")
    assert isinstance(z, np.ndarray)
    np.testing.assert_allclose(z, [0.0, 0.5, 1.0, 1.0])


def test_credibility_factor_rejects_bad_method():
    with pytest.raises(ValueError):
        credibility_factor(10, 100, "bogus")


def test_credibility_factor_rejects_nonpositive_threshold():
    with pytest.raises(ValueError):
        credibility_factor(10, 0, "sqrt")


# ---------------------------------------------------------------------------
# apply_credibility
# ---------------------------------------------------------------------------

def _units(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["cluster", "unit", "numerator", "denominator", "value"]
    )


def test_apply_credibility_full_and_zero_credibility():
    # Cluster A expected = denominator-weighted mean of value
    #   = (500*100 + 100*100) / 200 = 300
    units = _units(
        [
            ("A", "u1", 100, 100, 500.0),  # n == threshold -> Z = 1 -> keeps 500
            ("A", "u2", 0, 100, 100.0),    # n == 0 -> Z = 0 -> snaps to expected 300
        ]
    )
    out = apply_credibility(units, threshold=100, method="sqrt")
    a = out.set_index("unit")
    assert a.loc["u1", "expected"] == pytest.approx(300.0)
    assert a.loc["u1", "z"] == pytest.approx(1.0)
    assert a.loc["u1", "cred_value"] == pytest.approx(500.0)
    assert a.loc["u2", "z"] == pytest.approx(0.0)
    assert a.loc["u2", "cred_value"] == pytest.approx(300.0)


def test_apply_credibility_partial_blend():
    # Cluster B expected = (900*50 + 100*50) / 100 = 500
    # u3: Z = sqrt(25/100) = 0.5 -> 0.5*900 + 0.5*500 = 700
    units = _units(
        [
            ("B", "u3", 25, 50, 900.0),
            ("B", "u4", 0, 50, 100.0),
        ]
    )
    out = apply_credibility(units, threshold=100, method="sqrt")
    b = out.set_index("unit")
    assert b.loc["u3", "expected"] == pytest.approx(500.0)
    assert b.loc["u3", "z"] == pytest.approx(0.5)
    assert b.loc["u3", "cred_value"] == pytest.approx(700.0)
    assert b.loc["u4", "cred_value"] == pytest.approx(500.0)


def test_apply_credibility_expected_is_per_cluster():
    units = _units(
        [
            ("A", "u1", 10, 100, 1000.0),
            ("B", "u2", 10, 100, 0.0),
        ]
    )
    out = apply_credibility(units, threshold=100, method="sqrt")
    exp = out.set_index("unit")["expected"]
    # Single-unit clusters: expected equals that unit's own value.
    assert exp.loc["u1"] == pytest.approx(1000.0)
    assert exp.loc["u2"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# iqr_upper_fence / apply_cap
# ---------------------------------------------------------------------------

def test_iqr_upper_fence_default_k():
    # [1..8, 100]: Q1=3, Q3=7, IQR=4 -> 7 + 3.5*4 = 21
    values = [1, 2, 3, 4, 5, 6, 7, 8, 100]
    assert iqr_upper_fence(values) == pytest.approx(21.0)


def test_iqr_upper_fence_custom_k():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 100]
    assert iqr_upper_fence(values, k=1.5) == pytest.approx(13.0)


def test_apply_cap_censors_above_fence():
    units = pd.DataFrame({"cred_value": [1, 2, 3, 4, 5, 6, 7, 8, 100]})
    capped, cap = apply_cap(units, value_col="cred_value", k=1.5)
    assert cap == pytest.approx(13.0)
    # Only the 100 is above the fence.
    assert capped["is_censored"].sum() == 1
    assert capped.loc[capped["cred_value"] == 100, "capped_value"].iloc[0] == pytest.approx(13.0)
    # Everything else is unchanged.
    assert capped.loc[capped["cred_value"] == 8, "capped_value"].iloc[0] == pytest.approx(8.0)


def test_apply_cap_explicit_cap_overrides_iqr():
    units = pd.DataFrame({"cred_value": [1, 2, 3, 4, 5, 100]})
    capped, cap = apply_cap(units, value_col="cred_value", cap=5.0)
    assert cap == pytest.approx(5.0)
    assert capped["is_censored"].sum() == 1  # only 100 > 5
    assert capped["capped_value"].max() == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# metric specs
# ---------------------------------------------------------------------------

def test_cluster_metric_specs_cover_three_rate_metrics():
    keys = set(CLUSTER_METRIC_SPECS)
    assert keys == {
        "cancer_prevalence_pct",
        "all_cause_mortality_per_100k",
        "cancer_mortality_per_100k",
    }
    prev = CLUSTER_METRIC_SPECS["cancer_prevalence_pct"]
    assert prev.numerator_col == "cancer_prevalence_numerator"
    assert prev.multiplier == pytest.approx(100.0)
    mort = CLUSTER_METRIC_SPECS["all_cause_mortality_per_100k"]
    assert mort.numerator_col == "all_cause_deaths"
    assert mort.multiplier == pytest.approx(100_000.0)
