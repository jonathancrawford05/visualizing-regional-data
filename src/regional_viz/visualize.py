"""Choropleth rendering — interactive (Plotly) and static equal-area (GeoPandas).

Both renderers share the same input contract: a county-level frame with
columns ``fips`` (5-digit FIPS string) and a count column. The county
GeoJSON used by the interactive renderer is Plotly's mirror of the Census
TIGER cartographic-boundary file; it's small enough to fetch on demand and
keyed by 5-digit FIPS exactly the way we need.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

PLOTLY_COUNTIES_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/"
    "geojson-counties-fips.json"
)
NON_CONUS_STATE_PREFIXES = frozenset({"02", "15", "60", "66", "69", "72", "78"})


def _load_geojson(source: str | Path) -> dict:
    """Load a GeoJSON from a URL or local file."""
    src = str(source)
    if src.startswith(("http://", "https://")):
        with urlopen(src) as r:
            return json.load(r)
    return json.loads(Path(src).read_text())


def render_interactive(
    county_df: pd.DataFrame,
    out_html: str | Path,
    *,
    count_col: str = "patients",
    geojson_source: str | Path = PLOTLY_COUNTIES_URL,
    title: str = "Individuals per U.S. county",
    quantile_clip: float = 0.97,
) -> Path:
    """Write a Plotly HTML choropleth. Returns the output path."""
    import plotly.express as px  # local import: optional dep

    geojson = _load_geojson(geojson_source)
    range_max = float(county_df[count_col].quantile(quantile_clip))

    fig = px.choropleth(
        county_df,
        geojson=geojson,
        locations="fips",
        color=count_col,
        color_continuous_scale="Viridis",
        range_color=(0, range_max),
        scope="usa",
        hover_data={"fips": True, count_col: ":,"},
        labels={count_col: "Individuals"},
    )
    fig.update_layout(title_text=title, margin=dict(l=0, r=0, t=40, b=0))
    out = Path(out_html)
    fig.write_html(out, include_plotlyjs="cdn")
    return out


def render_static(
    county_df: pd.DataFrame,
    out_png: str | Path,
    *,
    count_col: str = "patients",
    geojson_source: str | Path = PLOTLY_COUNTIES_URL,
    title: str = "Individuals per U.S. county (contiguous 48)",
    k_bins: int = 6,
) -> Path:
    """Render an Albers equal-area PNG choropleth of the contiguous 48.

    Equal-area projection (EPSG:5070) is the right call for a population
    choropleth — without it, the visually large but sparse western states
    look more important than they are. Quantile binning is used because
    patient counts are heavily right-skewed; linear bins would wash out
    everything but a handful of hotspots.
    """
    import geopandas as gpd  # optional deps
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gdf = gpd.read_file(geojson_source).merge(
        county_df, left_on="id", right_on="fips", how="left"
    )
    gdf["state"] = gdf["id"].str[:2]
    conus = gdf[~gdf["state"].isin(NON_CONUS_STATE_PREFIXES)].to_crs(5070)

    fig, ax = plt.subplots(figsize=(15, 9))
    conus.plot(
        column=count_col,
        scheme="quantiles",
        k=k_bins,
        cmap="viridis",
        linewidth=0.05,
        edgecolor="white",
        legend=True,
        legend_kwds={
            "title": "Individuals (quantile bins)",
            "loc": "lower right",
        },
        missing_kwds={
            "color": "#e8e8e8",
            "edgecolor": "white",
            "linewidth": 0.05,
            "label": "no data",
        },
        ax=ax,
    )
    ax.set_axis_off()
    ax.set_title(title, fontsize=15)
    plt.tight_layout()
    out = Path(out_png)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def distribution_data(county_df: pd.DataFrame, *, top_n: int | None = None) -> pd.DataFrame:
    """Return a DataFrame summarizing patient counts by FIPS, sorted desc.

    If `top_n` is provided, return only the top N rows by `patients`.
    This is a small helper that unit tests can exercise without requiring
    an optional plotting dependency.
    """
    df = county_df[["fips", "patients"]].groupby("fips", as_index=False).sum()
    df = df.sort_values("patients", ascending=False).reset_index(drop=True)
    if top_n is not None:
        return df.head(top_n)
    return df


def distribution_figure(county_df: pd.DataFrame, *, top_n: int = 100):
    """Create a Plotly bar figure showing patients by FIPS (top_n).

    Requires `plotly` (optional). Returns a Plotly `Figure`.
    """
    import plotly.express as px

    df = distribution_data(county_df, top_n=top_n)
    fig = px.bar(df, x="fips", y="patients", labels={"patients": "Individuals"})
    fig.update_layout(title_text=f"Top {len(df)} counties by patients", xaxis_title="FIPS")
    return fig
