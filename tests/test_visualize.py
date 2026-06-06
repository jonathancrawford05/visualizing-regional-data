from __future__ import annotations

import pandas as pd

from regional_viz.visualize import distribution_data


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
