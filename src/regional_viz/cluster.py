"""Cluster-comparison transforms for the dashboard's zip-cluster tab.

The county rollup in :mod:`regional_viz.aggregate` collapses everything to
FIPS. This module works one level up the chain instead: it keeps the
``zip4_cluster_group`` and rolls raw ZIP+4 rows up to *units within a
cluster* — either ZIP5 (less granular, less noisy) or ZIP+4 (granular,
noisier). Those per-unit rows are what the box / violin distributions plot.

Two ideas keep the ZIP+4 noise in check:

  * **Credibility weighting.** A ZIP+4 with a single death reads as a wild
    rate. We shrink each unit's observed value toward its cluster's expected
    value, with weight ``Z`` driven by the unit's *numerator* (deaths or
    cancer claimants). Three standard Z formulas are offered; the slider in
    the UI sets the threshold for whichever is selected.

  * **IQR censoring.** Even after shrinkage a few units sit far out. Rather
    than let them stretch the axis, we cap at ``Q3 + k*IQR`` and mark the
    censored points so density at/above the cap is still visible.

Everything here is pure pandas/numpy — no plotting, no Streamlit — so the
math is unit-testable in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

CREDIBILITY_METHODS: tuple[str, ...] = ("sqrt", "linear", "buhlmann")


@dataclass(frozen=True)
class MetricSpec:
    """How to compute one rate metric from a numerator/denominator pair."""

    key: str
    label: str
    numerator_col: str
    denominator_col: str
    multiplier: float


# The three rate metrics that carry a numerator and so benefit from
# credibility weighting. Keys match the derived-column names produced by
# ``aggregate.aggregate_metrics_to_county`` and the app's metric selector.
CLUSTER_METRIC_SPECS: dict[str, MetricSpec] = {
    "cancer_prevalence_pct": MetricSpec(
        key="cancer_prevalence_pct",
        label="Cancer prevalence (%)",
        numerator_col="cancer_prevalence_numerator",
        denominator_col="patients",
        multiplier=100.0,
    ),
    "all_cause_mortality_per_100k": MetricSpec(
        key="all_cause_mortality_per_100k",
        label="All-cause mortality (per 100k)",
        numerator_col="all_cause_deaths",
        denominator_col="patients",
        multiplier=100_000.0,
    ),
    "cancer_mortality_per_100k": MetricSpec(
        key="cancer_mortality_per_100k",
        label="Cancer-attributed mortality (per 100k)",
        numerator_col="cancer_deaths",
        denominator_col="patients",
        multiplier=100_000.0,
    ),
}


def aggregate_to_cluster_units(
    df: pd.DataFrame,
    *,
    level: str = "zip4",
    numerator_col: str,
    denominator_col: str = "patients",
    multiplier: float,
    cluster_col: str = "zip4_cluster_group",
    zip_col: str = "eps_zip",
    zip4_col: str = "zip4",
) -> pd.DataFrame:
    """Roll raw ZIP+4 rows up to per-unit rows within each cluster.

    *level* selects the unit granularity:
      * ``"zip"``  — one unit per ZIP5 (the +4 rows are summed together).
      * ``"zip4"`` — one unit per ZIP+4 combination.

    Returns a long frame with columns ``cluster, unit, numerator,
    denominator, value`` where ``value = multiplier * numerator /
    denominator`` (and ``0.0`` for zero-denominator units, never NaN).
    """
    if level not in ("zip", "zip4"):
        raise ValueError(f"level must be 'zip' or 'zip4', got {level!r}")

    work = df.copy()
    if level == "zip":
        work["unit"] = work[zip_col].astype(str)
    else:
        work["unit"] = work[zip_col].astype(str) + "-" + work[zip4_col].astype(str)

    units = work.groupby([cluster_col, "unit"], as_index=False).agg(
        numerator=(numerator_col, "sum"),
        denominator=(denominator_col, "sum"),
    )
    units = units.rename(columns={cluster_col: "cluster"})
    units["value"] = np.where(
        units["denominator"] > 0,
        multiplier * units["numerator"] / units["denominator"],
        0.0,
    )
    return units


def credibility_factor(
    n,
    threshold: float,
    method: str = "sqrt",
):
    """Credibility weight ``Z`` in [0, 1] from a numerator count ``n``.

    *method*:
      * ``"sqrt"``     — ``min(1, sqrt(n / threshold))`` (limited
        fluctuation / square-root rule). ``threshold`` is the numerator
        count at which a unit becomes fully credible.
      * ``"linear"``   — ``min(1, n / threshold)``.
      * ``"buhlmann"`` — ``n / (n + threshold)``; here ``threshold`` plays
        the role of the Bühlmann ``k``.

    Accepts a scalar or an array-like ``n`` and returns the matching shape.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")

    arr = np.asarray(n, dtype=float)
    if method == "sqrt":
        z = np.sqrt(arr / threshold)
    elif method == "linear":
        z = arr / threshold
    elif method == "buhlmann":
        z = arr / (arr + threshold)
    else:
        raise ValueError(
            f"method must be one of {CREDIBILITY_METHODS}, got {method!r}"
        )

    z = np.clip(z, 0.0, 1.0)
    return float(z) if z.ndim == 0 else z


def apply_credibility(
    units: pd.DataFrame,
    *,
    threshold: float,
    method: str = "sqrt",
    value_col: str = "value",
    numerator_col: str = "numerator",
    denominator_col: str = "denominator",
    cluster_col: str = "cluster",
) -> pd.DataFrame:
    """Shrink each unit's value toward its cluster's expected value.

    The cluster *expected* is the denominator-weighted mean of the unit
    values — algebraically the cluster's own aggregate rate, and so the
    natural complement-of-credibility target. Each unit's credibility-
    weighted value is ``Z * observed + (1 - Z) * expected`` with ``Z`` from
    :func:`credibility_factor` applied to the unit's numerator.

    Returns a copy of *units* with three columns added: ``expected``, ``z``
    and ``cred_value``.
    """
    out = units.copy()

    weighted = out[value_col] * out[denominator_col]
    den_sum = out.groupby(cluster_col)[denominator_col].transform("sum")
    weighted_sum = weighted.groupby(out[cluster_col]).transform("sum")
    out["expected"] = np.where(den_sum > 0, weighted_sum / den_sum, 0.0)

    out["z"] = credibility_factor(out[numerator_col].to_numpy(), threshold, method)
    out["cred_value"] = out["z"] * out[value_col] + (1.0 - out["z"]) * out["expected"]
    return out


def iqr_upper_fence(values: Iterable[float], k: float = 3.5) -> float:
    """Return the Tukey-style upper fence ``Q3 + k * (Q3 - Q1)``.

    ``k`` defaults to 3.5 — wider than Tukey's 1.5 "outlier" /3.0 "far out"
    fences, chosen so only genuinely extreme units get censored. NaNs are
    dropped; an all-NaN/empty input returns NaN.
    """
    v = np.asarray(list(values), dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return float("nan")
    q1, q3 = np.quantile(v, [0.25, 0.75])
    return float(q3 + k * (q3 - q1))


def apply_cap(
    units: pd.DataFrame,
    *,
    value_col: str = "cred_value",
    k: float = 3.5,
    cap: float | None = None,
) -> tuple[pd.DataFrame, float]:
    """Censor *value_col* at an upper cap, preserving density above it.

    When *cap* is ``None`` it is derived globally as :func:`iqr_upper_fence`
    of *value_col* (one shared fence so the axis is comparable across
    clusters). Values above the cap are clipped to it and flagged, so the
    censored points pile up at the cap rather than vanishing.

    Returns ``(frame, cap)`` where *frame* has ``capped_value`` and
    ``is_censored`` columns added.
    """
    out = units.copy()
    if cap is None:
        cap = iqr_upper_fence(out[value_col], k)
    out["is_censored"] = out[value_col] > cap
    out["capped_value"] = out[value_col].clip(upper=cap)
    return out, float(cap)
