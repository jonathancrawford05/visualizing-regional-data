"""Streamlit demo: load a ZIP+4 CSV, aggregate to county, show the choropleth.

Run with::

    streamlit run app/streamlit_app.py

The sidebar lets stakeholders toggle between dummy data and a real upload,
swap binning schemes, and inspect the coverage report — the iteration knobs
we expect to argue about before locking the final pipeline.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import streamlit as st

from regional_viz.aggregate import aggregate_to_county
from regional_viz.loader import load_zip_counts
from regional_viz.synthetic import generate_synthetic_zip4, seed_dominant_county_map
from regional_viz.visualize import PLOTLY_COUNTIES_URL


@st.cache_data(show_spinner="Fetching county GeoJSON…")
def load_counties_geojson() -> dict:
    with urlopen(PLOTLY_COUNTIES_URL) as r:
        return json.load(r)


@st.cache_data
def load_public_zip2fips() -> dict[str, str]:
    from regional_viz.crosswalk import load_zip2fips_dominant
    return load_zip2fips_dominant()


def main() -> None:
    st.set_page_config(page_title="Individuals per U.S. county", layout="wide")
    st.title("Individuals per U.S. county")
    st.caption(
        "PoC: Epsilon ZIP+4 ⨯ Kythera patient counts → dominant-county FIPS → choropleth."
    )

    with st.sidebar:
        st.header("Inputs")
        source = st.radio(
            "Data source",
            ["Synthetic (dummy)", "Upload CSV"],
            help="Synthetic data covers all 50 states with a Zipf-skewed count distribution.",
        )

        if source == "Synthetic (dummy)":
            n_rows = st.slider("rows", 1_000, 50_000, 10_000, step=1_000)
            seed = st.number_input("seed", 0, 10_000, 42)
            df = generate_synthetic_zip4(n_rows=n_rows, seed=int(seed))
            zip2fips = seed_dominant_county_map()
            st.success(f"Generated {len(df):,} synthetic ZIP+4 rows.")
        else:
            up = st.file_uploader(
                "CSV with columns eps_zip, zip4, patients",
                type="csv",
                help="Streamlit default limit is 200 MB per file; this app raises it to 512 MB via .streamlit/config.toml.",
            )
            if up is None:
                st.stop()
            # Same logic as loader.load_zip_counts but from a buffer.
            raw = pd.read_csv(io.BytesIO(up.getvalue()), dtype={"eps_zip": str})
            raw["eps_zip"] = raw["eps_zip"].str.zfill(5)
            raw["patients"] = raw["patients"].astype(int)
            df = raw
            with st.spinner("Loading public ZIP→FIPS crosswalk…"):
                zip2fips = load_public_zip2fips()

        st.header("Display")
        clip_q = st.slider(
            "color-range clip quantile", 0.80, 1.00, 0.97, step=0.01,
            help="Hot counties otherwise wash out the rest of the map.",
        )

        st.header("Distribution")
        distribution_mode = st.radio(
            "Distribution mode",
            ["Top N counties", "At or above percentile"],
            index=0,
            help="Choose whether to show the top N counties by patient count or all counties above a percentile threshold.",
        )
        if distribution_mode == "Top N counties":
            distribution_top_n = st.slider(
                "Top N counties",
                10,
                500,
                200,
                step=10,
                help="Show the top N counties by patient count.",
            )
            distribution_percentile = None
        else:
            distribution_top_n = None
            percentile_value = st.slider(
                "Minimum patient percentile",
                50,
                99,
                90,
                step=1,
                format="%d%%",
                help="Show all counties whose patient count is at or above the selected percentile.",
            )
            distribution_percentile = percentile_value / 100

    # ---- aggregate ----------------------------------------------------------
    county_df, coverage = aggregate_to_county(df, zip2fips)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("input rows", f"{len(df):,}")
    c2.metric("counties covered", f"{len(county_df):,}")
    c3.metric(
        "patient coverage",
        f"{coverage.coverage_ratio:.1%}",
        delta=f"{coverage.unmapped_zip_count} unmapped ZIPs",
        delta_color="inverse",
    )
    # New metric: total patients in the input (sum of patients across ZIP+4 rows)
    c4.metric("total patients", f"{coverage.total_count:,}")

    # ---- map ----------------------------------------------------------------
    import plotly.express as px
    geo = load_counties_geojson()
    range_max = float(county_df["patients"].quantile(clip_q)) or 1.0
    fig = px.choropleth(
        county_df,
        geojson=geo,
        locations="fips",
        color="patients",
        color_continuous_scale="Viridis",
        range_color=(0, range_max),
        scope="usa",
        labels={"patients": "Individuals"},
        hover_data={"fips": True, "patients": ":,"},
    )
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=600)
    st.plotly_chart(fig, use_container_width=True)

    # ---- supporting detail --------------------------------------------------
    with st.expander("Top 25 counties"):
        st.dataframe(county_df.head(25), use_container_width=True)

    dist_kwargs: dict[str, int | float | None]
    if distribution_percentile is not None:
        min_patients = float(county_df["patients"].quantile(distribution_percentile))
        dist_kwargs = {"top_n": None, "min_patients": min_patients}
    else:
        dist_kwargs = {"top_n": distribution_top_n, "min_patients": None}

    try:
        from regional_viz.visualize import (
            distribution_figure,
            distribution_histogram,
            distribution_quantiles,
        )

        with st.expander("Patient distribution by county"):
            fig = distribution_figure(county_df, **dist_kwargs)
            st.plotly_chart(fig, use_container_width=True)
            histogram = distribution_histogram(county_df, min_patients=dist_kwargs["min_patients"])
            st.plotly_chart(histogram, use_container_width=True)
            st.write(
                "**Distribution quantiles**: showing the patient-count quantiles for all counties."
            )
            st.dataframe(distribution_quantiles(county_df), use_container_width=True)
    except Exception:
        # Optional dependency (plotly) may be missing in some test environments;
        # fall back to a simple dataframe view of the distribution data.
        from regional_viz.visualize import distribution_data

        with st.expander("Patient distribution by county"):
            st.dataframe(
                distribution_data(county_df, **dist_kwargs).head(200),
                use_container_width=True,
            )
    with st.expander("Coverage diagnostics"):
        st.write(
            f"**Total patients in input:** {coverage.total_count:,}\n\n"
            f"**Patients mapped to a county:** {coverage.mapped_count:,}\n\n"
            f"**ZIPs missing from crosswalk:** {coverage.unmapped_zip_count}\n\n"
            "Production-grade option: replace the dominant-county crosswalk with "
            "the HUD `ZIP_COUNTY` allocation table (see `aggregate.allocate_hud`)."
        )


if __name__ == "__main__":
    main()
