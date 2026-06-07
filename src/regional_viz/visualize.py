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

import numpy as np
import pandas as pd

PLOTLY_COUNTIES_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/"
    "geojson-counties-fips.json"
)
NON_CONUS_STATE_PREFIXES = frozenset({"02", "15", "60", "66", "69", "72", "78"})

STATE_FIPS_TO_ABBR: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR",
    "78": "VI",
}


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


def fips_to_county_name(geojson: dict) -> dict[str, tuple[str, str]]:
    """Extract ``{fips: (county_name, state_abbr)}`` from a counties GeoJSON dict.

    Expects the Plotly / Census TIGER GeoJSON where each feature has an ``id``
    equal to the 5-digit FIPS and ``properties.NAME`` / ``properties.STATE``.
    Unknown state FIPS fall back to the raw 2-digit prefix string.
    """
    result: dict[str, tuple[str, str]] = {}
    for feature in geojson.get("features", []):
        fips = feature.get("id", "")
        props = feature.get("properties", {})
        name = props.get("NAME", "")
        state_fips = props.get("STATE", fips[:2] if len(fips) >= 2 else "")
        abbr = STATE_FIPS_TO_ABBR.get(state_fips, state_fips)
        result[fips] = (name, abbr)
    return result


def filter_county_df_by_percentile(
    county_df: pd.DataFrame,
    min_percentile: float,
) -> pd.DataFrame:
    """Return counties whose patient count is at or above *min_percentile*.

    *min_percentile* is a fraction in [0.0, 1.0].  0.0 returns all rows
    unchanged; 1.0 returns only counties at or above the maximum value.
    """
    if min_percentile <= 0.0:
        return county_df
    threshold = float(county_df["patients"].quantile(min_percentile))
    return county_df[county_df["patients"] >= threshold].reset_index(drop=True)


def distribution_data(
    county_df: pd.DataFrame,
    *,
    top_n: int | None = None,
    min_patients: float | None = None,
    county_names: dict[str, tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Return a DataFrame summarizing patient counts by FIPS, sorted desc.

    If *min_patients* is provided, filter out counties below that threshold.
    If *top_n* is provided, return only the top N rows by ``patients``.
    If *county_names* is provided (mapping FIPS → (name, state_abbr)),
    ``county`` and ``state`` columns are added to the output.
    """
    df = county_df[["fips", "patients"]].groupby("fips", as_index=False).sum()
    df = df.sort_values("patients", ascending=False).reset_index(drop=True)
    if min_patients is not None:
        df = df[df["patients"] >= min_patients].reset_index(drop=True)
    if county_names is not None:
        df["county"] = df["fips"].map(lambda f: county_names.get(f, ("", ""))[0])
        df["state"] = df["fips"].map(lambda f: county_names.get(f, ("", ""))[1])
    if top_n is not None:
        return df.head(top_n)
    return df


def distribution_figure(
    county_df: pd.DataFrame,
    *,
    top_n: int | None = 100,
    min_patients: float | None = None,
    county_names: dict[str, tuple[str, str]] | None = None,
):
    """Create a Plotly bar figure showing patients by FIPS.

    Requires ``plotly`` (optional). Returns a Plotly ``Figure``.
    When *county_names* is provided, x-axis labels show "County, ST" instead
    of raw FIPS codes.
    """
    import plotly.express as px

    df = distribution_data(
        county_df, top_n=top_n, min_patients=min_patients, county_names=county_names
    )
    if county_names is not None and "county" in df.columns:
        df = df.copy()
        df["label"] = df["county"] + ", " + df["state"]
        x_col = "label"
        xaxis_title = "County"
    else:
        x_col = "fips"
        xaxis_title = "FIPS"

    fig = px.bar(df, x=x_col, y="patients", labels={"patients": "Individuals"})
    subtitle = "Top counties by patients"
    if min_patients is not None:
        subtitle = f"Counties with ≥ {min_patients:.0f} patients"
    fig.update_layout(title_text=subtitle, xaxis_title=xaxis_title)
    return fig


def distribution_histogram(
    county_df: pd.DataFrame,
    *,
    bins: int = 40,
    min_patients: float | None = None,
) -> "plotly.graph_objs._figure.Figure":
    """Create a Plotly histogram of county patient counts.

    This uses explicit log-space binning so skewed patient distributions
    remain visible as bars even when counts span many orders of magnitude.
    If `min_patients` is provided, counties below the threshold are omitted.
    """
    import plotly.express as px

    values = county_df["patients"].astype(float)
    if min_patients is not None:
        values = values[values >= min_patients]
    values = values[values > 0]
    if values.empty:
        empty_df = pd.DataFrame({"bin": [], "counties": []})
        fig = px.bar(empty_df, x="bin", y="counties")
        fig.update_layout(
            title_text="Patient count distribution across counties",
            xaxis_title="Patients per county",
            yaxis_title="Number of counties",
        )
        return fig

    min_val = max(values.min(), 1.0)
    max_val = values.max()
    bin_edges = np.logspace(np.log10(min_val), np.log10(max_val), bins + 1)
    counts, edges = np.histogram(values, bins=bin_edges)
    labels = [
        f"{int(edges[i]):,}–{int(edges[i + 1] - 1):,}"
        for i in range(len(counts))
    ]
    hist_df = pd.DataFrame({"bin": labels, "counties": counts})
    fig = px.bar(
        hist_df,
        x="bin",
        y="counties",
        labels={"bin": "Patients per county", "counties": "Number of counties"},
    )
    fig.update_layout(
        title_text="Patient count distribution across counties",
        xaxis_title="Patients per county (log buckets)",
        yaxis_title="Number of counties",
    )
    return fig


def distribution_quantiles(
    county_df: pd.DataFrame,
    *,
    quantiles: list[float] | tuple[float, ...] = (0.25, 0.50, 0.75, 0.90, 0.99),
) -> pd.DataFrame:
    """Return a DataFrame with selected patient-count quantiles.

    This is useful for showing actual percentiles a user selected.
    """
    values = county_df["patients"].quantile(quantiles).reset_index()
    values.columns = ["quantile", "patients"]
    values["quantile"] = (values["quantile"] * 100).astype(int)
    return values
