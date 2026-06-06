"""Shared fixtures. All fixtures are offline — tests must never hit network."""
from __future__ import annotations

import pandas as pd
import pytest

from regional_viz.synthetic import generate_synthetic_zip4, seed_dominant_county_map


@pytest.fixture
def tiny_zip4_frame() -> pd.DataFrame:
    """Minimal hand-crafted frame for crisp assertions.

    Includes a leading-zero ZIP (06103 Hartford CT) — anything that drops
    leading zeros will fail loudly.
    """
    return pd.DataFrame(
        {
            "eps_zip": ["06103", "06103", "10001", "10001", "33101", "99999"],
            "zip4": ["0001", "0002", "1000", "2000", "5500", "0000"],
            "patients": [3, 5, 7, 1, 10, 4],
        }
    )


@pytest.fixture
def tiny_zip2fips() -> dict[str, str]:
    return {"06103": "09003", "10001": "36061", "33101": "12086"}


@pytest.fixture
def tiny_hud_allocation() -> pd.DataFrame:
    """ZIP 10001 split 70/30 across two counties, 06103 single, 33101 single."""
    return pd.DataFrame(
        {
            "zip": ["06103", "10001", "10001", "33101"],
            "fips": ["09003", "36061", "36005", "12086"],
            "res_ratio": [1.0, 0.7, 0.3, 1.0],
        }
    )


@pytest.fixture
def synthetic_frame() -> pd.DataFrame:
    return generate_synthetic_zip4(n_rows=2000, seed=1234)


@pytest.fixture
def synthetic_zip2fips() -> dict[str, str]:
    return seed_dominant_county_map()
