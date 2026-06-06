from __future__ import annotations

import numpy as np
import pandas as pd

from regional_viz._seed_zips import SEED_ZIPS
from regional_viz.synthetic import generate_synthetic_zip4, seed_dominant_county_map


def test_schema_matches_real_input():
    df = generate_synthetic_zip4(n_rows=500, seed=0)
    assert list(df.columns) == ["eps_zip", "zip4", "patients"]
    assert df["eps_zip"].map(type).eq(str).all()
    assert df["zip4"].map(type).eq(str).all()
    assert np.issubdtype(df["patients"].dtype, np.integer)


def test_reproducible_with_seed():
    a = generate_synthetic_zip4(n_rows=300, seed=7)
    b = generate_synthetic_zip4(n_rows=300, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_zips_are_five_digit_strings():
    df = generate_synthetic_zip4(n_rows=500, seed=0)
    assert df["eps_zip"].str.len().eq(5).all()


def test_includes_leading_zero_zips():
    """The seed includes Hartford CT (06103) — anything stripping leading
    zeros would lose every New England ZIP in the real pipeline too."""
    df = generate_synthetic_zip4(n_rows=5000, seed=0)
    assert df["eps_zip"].str.startswith("0").any()


def test_geographic_coverage_includes_many_states():
    df = generate_synthetic_zip4(n_rows=5000, seed=0)
    state_prefixes = df["eps_zip"].str[:2].nunique()
    # Heuristic: ZIP prefix groups roughly map to state regions
    assert state_prefixes >= 30


def test_most_seeded_zips_are_lit_in_a_typical_run():
    """A 10k-row draw should exercise most of the seed pool, not collapse
    onto a handful of hotspots. Catches future regressions in the
    weighting distribution (the per-ZIP Zipf shape is sharp enough that a
    careless tweak silently flattens the choropleth)."""
    df = generate_synthetic_zip4(n_rows=10_000, seed=0)
    share_lit = df["eps_zip"].nunique() / len(SEED_ZIPS)
    assert share_lit >= 0.80, f"only {share_lit:.0%} of seeded ZIPs received any rows"


def test_count_distribution_is_skewed():
    """Real data has a Florida/NY/NJ skew. Generator should mimic that —
    the top decile of rows should carry the majority of patients."""
    df = generate_synthetic_zip4(n_rows=10_000, seed=0)
    top10pct = int(len(df) * 0.10)
    share = df.nlargest(top10pct, "patients")["patients"].sum() / df["patients"].sum()
    assert share > 0.4


def test_seed_dominant_county_map_round_trips():
    mapping = seed_dominant_county_map()
    assert len(mapping) == len(SEED_ZIPS)
    for z, f, _ in SEED_ZIPS:
        assert mapping[z] == f
