from __future__ import annotations

import pandas as pd

from regional_viz.crosswalk import dominant_county_map


def test_dominant_county_map_basic(tiny_zip2fips):
    s = pd.Series(["06103", "10001", "33101"])
    out = dominant_county_map(s, tiny_zip2fips)
    assert out.tolist() == ["09003", "36061", "12086"]


def test_dominant_county_map_unknown_zips_become_nan(tiny_zip2fips):
    s = pd.Series(["99999", "10001"])
    out = dominant_county_map(s, tiny_zip2fips)
    assert pd.isna(out.iloc[0])
    assert out.iloc[1] == "36061"
