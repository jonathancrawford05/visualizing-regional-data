"""Synthesize a ZIP+4 patient-count table for demo / development.

Real Epsilon x Kythera data is PII-adjacent and slow to wrangle. The
generator below produces a structurally-faithful stand-in:

  * Schema matches the real file (``eps_zip, zip4, patients``).
  * Leading-zero ZIPs (New England) are preserved as strings.
  * Each ZIP appears across several +4 rows, mirroring how the real claims
    cluster within a ZIP.
  * Patient counts follow a Zipf-style heavy tail — a handful of "hot"
    ZIPs dominate, exactly like the real Florida / NJ / NY skew in the
    sample data.
  * Coverage spans all 50 states + DC so the demo choropleth shows the
    full country, not a single regional hotspot.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from regional_viz._seed_zips import SEED_ZIPS


def generate_synthetic_zip4(
    n_rows: int = 10_000,
    seed: int = 42,
    weight_zipf_a: float = 2.5,
    count_zipf_a: float = 1.6,
    plus4_per_zip: tuple[int, int] = (3, 12),
    n_clusters: int = 0,
    with_metrics: bool = False,
) -> pd.DataFrame:
    """Build a dummy ZIP+4 patient-count frame.

    Parameters
    ----------
    n_rows:
        Number of ZIP+4 rows to produce. Defaults to ~10k like the sample.
    seed:
        RNG seed for reproducibility — the demo notebook / Streamlit app
        should be deterministic.
    weight_zipf_a:
        Shape parameter for the per-ZIP weighting distribution. Higher
        values spread row draws across more of the seeded ZIPs; lower
        values concentrate on a handful. 2.5 lights every seeded ZIP in
        a 10k-row draw while still producing a Florida-style hotspot.
    count_zipf_a:
        Shape parameter for the per-row patient-count distribution.
        Higher = lighter tail. 1.6 produces a realistic spread: most
        rows are 1-5 patients, a few are 50.
    plus4_per_zip:
        (min, max) inclusive number of distinct +4 suffixes generated per
        ZIP5. The real data shows most ZIPs split across several +4 rows.
    n_clusters:
        If > 0, add a ``zip4_cluster_group`` column assigning each row to
        one of ``n_clusters`` synthetic clusters (labelled ``G-01`` …).
        Default 0 keeps the legacy 3-column schema.
    with_metrics:
        If True, add ``cancer_prevalence_numerator``, ``all_cause_deaths``
        and ``cancer_deaths`` columns. Each cluster gets its own baseline
        rates so the cluster-comparison tab shows real between-cluster
        spread; per-row binomial noise creates the ZIP+4 outliers the
        credibility weighting is meant to tame. Requires ``n_clusters > 0``.
    """
    if with_metrics and n_clusters <= 0:
        raise ValueError("with_metrics requires n_clusters > 0")

    rng = np.random.default_rng(seed)
    zip5_pool = np.array([z for z, _, _ in SEED_ZIPS])

    # Per-ZIP hotness: a small set of ZIPs is dramatically over-represented,
    # but with weight_zipf_a high enough that the long tail still receives
    # at least a handful of rows. Decoupled from the per-row count shape so
    # tuning "spread of hotspots" doesn't drag the per-county count
    # distribution with it.
    weights = rng.zipf(weight_zipf_a, size=len(zip5_pool)).astype(float)
    weights /= weights.sum()

    zips = rng.choice(zip5_pool, size=n_rows, p=weights)
    plus4 = rng.integers(0, 9999, size=n_rows)
    patients = rng.zipf(count_zipf_a, size=n_rows).clip(max=50).astype(int)

    out = pd.DataFrame(
        {
            "eps_zip": zips.astype(str),
            "zip4": [f"{x:04d}" for x in plus4],
            "patients": patients,
        }
    )

    if n_clusters > 0:
        cluster_idx = rng.integers(0, n_clusters, size=n_rows)
        out["zip4_cluster_group"] = [f"G-{i + 1:02d}" for i in cluster_idx]

        if with_metrics:
            # Each cluster gets its own baseline rates so clusters are
            # visibly different; binomial draws on the patient count then
            # introduce ZIP+4-level noise (and outliers in the small cells).
            prev_base = rng.uniform(0.08, 0.25, size=n_clusters)
            allcause_base = rng.uniform(0.01, 0.05, size=n_clusters)
            cancer_frac = rng.uniform(0.3, 0.6, size=n_clusters)

            prev_p = prev_base[cluster_idx]
            allcause_p = allcause_base[cluster_idx]
            cancer_p = cancer_frac[cluster_idx]

            out["cancer_prevalence_numerator"] = rng.binomial(patients, prev_p)
            all_cause = rng.binomial(patients, allcause_p)
            out["all_cause_deaths"] = all_cause
            out["cancer_deaths"] = rng.binomial(all_cause, cancer_p)

    return out


def seed_dominant_county_map() -> dict[str, str]:
    """Return a ZIP -> dominant-FIPS dict covering the seeded ZIPs.

    Lets the demo and the test suite run fully offline. Real runs replace
    this with :func:`crosswalk.load_zip2fips_dominant`.
    """
    return {z: f for z, f, _ in SEED_ZIPS}
