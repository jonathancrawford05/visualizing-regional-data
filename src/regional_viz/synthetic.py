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
    zipf_a: float = 1.6,
    plus4_per_zip: tuple[int, int] = (3, 12),
) -> pd.DataFrame:
    """Build a dummy ZIP+4 patient-count frame.

    Parameters
    ----------
    n_rows:
        Number of ZIP+4 rows to produce. Defaults to ~10k like the sample.
    seed:
        RNG seed for reproducibility — the demo notebook / Streamlit app
        should be deterministic.
    zipf_a:
        Shape parameter for the Zipf distribution used to draw patient
        counts. Higher = heavier tail. 1.6 produces a realistic spread:
        most ZIPs see 1-5 patients, a few see thousands.
    plus4_per_zip:
        (min, max) inclusive number of distinct +4 suffixes generated per
        ZIP5. The real data shows most ZIPs split across several +4 rows.
    """
    rng = np.random.default_rng(seed)
    zip5_pool = np.array([z for z, _, _ in SEED_ZIPS])

    # Per-ZIP hotness: a small set of ZIPs is dramatically over-represented.
    weights = rng.zipf(zipf_a, size=len(zip5_pool)).astype(float)
    weights /= weights.sum()

    zips = rng.choice(zip5_pool, size=n_rows, p=weights)
    plus4 = rng.integers(0, 9999, size=n_rows)
    patients = rng.zipf(zipf_a, size=n_rows).clip(max=50)

    return pd.DataFrame(
        {
            "eps_zip": zips.astype(str),
            "zip4": [f"{x:04d}" for x in plus4],
            "patients": patients.astype(int),
        }
    )


def seed_dominant_county_map() -> dict[str, str]:
    """Return a ZIP -> dominant-FIPS dict covering the seeded ZIPs.

    Lets the demo and the test suite run fully offline. Real runs replace
    this with :func:`crosswalk.load_zip2fips_dominant`.
    """
    return {z: f for z, f, _ in SEED_ZIPS}
