"""Streamlit demo: load a ZIP+4 CSV, aggregate to county, show the choropleth.

Run with::

    streamlit run app/streamlit_app.py

The sidebar lets stakeholders toggle between dummy data and a real upload,
apply a global patient-percentile filter (affects map and all charts),
adjust colour-range clipping, and control the distribution bar chart.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import streamlit as st

from regional_viz.aggregate import aggregate_to_county, aggregate_metrics_to_county
from regional_viz.loader import load_zip_counts
from regional_viz.synthetic import generate_synthetic_zip4, seed_dominant_county_map
from regional_viz.visualize import (
    PLOTLY_COUNTIES_URL,
    filter_county_df_by_percentile,
    fips_to_county_name,
)


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
        # ---- Data source ---------------------------------------------------
        st.header("Data")
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
            raw = pd.read_csv(io.BytesIO(up.getvalue()), dtype={"eps_zip": str})
            raw["eps_zip"] = raw["eps_zip"].str.zfill(5)
            raw["patients"] = raw["patients"].astype(int)
            df = raw
            with st.spinner("Loading public ZIP→FIPS crosswalk…"):
                zip2fips = load_public_zip2fips()

        # ---- Global filters ------------------------------------------------
        st.header("Filters")
        st.info(
            "These filters apply to **all** dashboard components — the map, "
            "distribution charts, and summary metrics.",
            icon="ℹ️",
        )

        # Metric selection (if multi-metric data is available)
        metric_options = {"Patient counts": "patients"}
        has_prevalence = "cancer_prevalence_numerator" in df.columns
        has_all_cause = "all_cause_deaths" in df.columns
        has_cancer_mort = "cancer_deaths" in df.columns

        if has_prevalence:
            metric_options["Cancer prevalence (%)"] = "cancer_prevalence_pct"
        if has_all_cause:
            metric_options["All-cause mortality (per 100k)"] = "all_cause_mortality_per_100k"
        if has_cancer_mort:
            metric_options["Cancer-attributed mortality (per 100k)"] = "cancer_mortality_per_100k"

        selected_metric_label = st.radio(
            "Metric to display",
            options=list(metric_options.keys()),
            index=0,
            help=(
                "Select which metric to visualize on the map and charts. "
                "Only metrics with data in the uploaded CSV are available."
            ),
        )
        selected_metric = metric_options[selected_metric_label]

        # ZIP+4 cluster group filter (optional column)
        selected_cluster_groups = None
        if "zip4_cluster_group" in df.columns:
            unique_groups = sorted(df["zip4_cluster_group"].dropna().unique())
            if len(unique_groups) > 0:
                selected_cluster_groups = st.multiselect(
                    "ZIP+4 cluster groups",
                    options=unique_groups,
                    default=None,
                    help=(
                        "Filter data to specific ZIP+4 cluster groups. "
                        "Leave empty to include all groups. "
                        "Select one or more groups to filter the data."
                    ),
                )

        min_percentile_pct = st.slider(
            "Minimum patient percentile",
            min_value=0,
            max_value=100,
            value=0,
            step=1,
            format="%d%%",
            help=(
                "Exclude counties whose patient count falls below this percentile. "
                "**0% = include all data** (default). "
                "50% = top half of counties by patient count. "
                "99% = only the very highest-count counties."
            ),
        )
        min_percentile = min_percentile_pct / 100.0

        # ---- Map display ---------------------------------------------------
        st.header("Map display")
        clip_q = st.slider(
            "Colour-range clip quantile",
            0.80,
            1.00,
            0.97,
            step=0.01,
            help=(
                "Clips the top of the colour scale at this quantile of the "
                "filtered data, preventing a few very high-count counties from "
                "washing out the rest of the map."
            ),
        )

        # ---- Distribution display ------------------------------------------
        st.header("Distribution chart")
        distribution_mode = st.radio(
            "Show in bar chart",
            ["Top N counties", "All filtered counties"],
            index=0,
            help=(
                "**Top N counties** limits the bar chart to the N highest-count "
                "counties in the filtered data. "
                "**All filtered counties** shows every county that passes the "
                "percentile filter above."
            ),
        )
        if distribution_mode == "Top N counties":
            distribution_top_n = st.slider(
                "Top N",
                10,
                500,
                200,
                step=10,
                help="Number of counties to display in the bar chart.",
            )
        else:
            distribution_top_n = None

    # ---- Apply global filters at input level -------------------------------
    # Filter by zip4_cluster_group before aggregation (if column exists and selections made)
    df_filtered = df.copy()
    if selected_cluster_groups and len(selected_cluster_groups) > 0:
        df_filtered = df_filtered[df_filtered["zip4_cluster_group"].isin(selected_cluster_groups)]

    # ---- Aggregate ---------------------------------------------------------
    # Use multi-metric aggregation if any metric columns are present
    use_multi_metric = has_prevalence or has_all_cause or has_cancer_mort
    if use_multi_metric:
        county_df_full, coverage = aggregate_metrics_to_county(df_filtered, zip2fips)
    else:
        county_df_full, coverage = aggregate_to_county(df_filtered, zip2fips)

    # Apply global percentile filter to all downstream components
    # Filter on patient counts regardless of selected metric (population-based filter)
    county_df = filter_county_df_by_percentile(county_df_full, min_percentile, metric_col="patients")

    # ---- Metrics -----------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)

    # Show input rows with indicator if cluster filter is active
    input_rows_label = "Input rows"
    input_rows_delta = None
    if selected_cluster_groups and len(selected_cluster_groups) > 0:
        input_rows_delta = f"{len(df_filtered):,} after cluster filter"

    c1.metric(input_rows_label, f"{len(df):,}", delta=input_rows_delta)
    c2.metric(
        "Counties shown",
        f"{len(county_df):,}",
        delta=f"of {len(county_df_full):,} total" if min_percentile > 0 else None,
    )
    c3.metric(
        "Patient coverage",
        f"{coverage.coverage_ratio:.1%}",
        delta=f"{coverage.unmapped_zip_count} unmapped ZIPs",
        delta_color="inverse",
    )
    c4.metric("Total patients", f"{coverage.total_count:,}")

    # ---- Map ---------------------------------------------------------------
    import plotly.express as px

    geo = load_counties_geojson()
    county_names = fips_to_county_name(geo)

    if county_df.empty:
        st.warning("No counties remain after applying the current filter. Lower the percentile to see data.")
    else:
        # Determine metric-specific formatting
        if selected_metric == "patients":
            metric_label = "Individuals"
            hover_format = ":,"
        elif selected_metric == "cancer_prevalence_pct":
            metric_label = "Cancer Prevalence (%)"
            hover_format = ":.2f"
        elif selected_metric in ["all_cause_mortality_per_100k", "cancer_mortality_per_100k"]:
            metric_label = selected_metric_label
            hover_format = ":.1f"
        else:
            metric_label = selected_metric_label
            hover_format = ":,"

        range_max = float(county_df[selected_metric].quantile(clip_q)) or 1.0
        map_fig = px.choropleth(
            county_df,
            geojson=geo,
            locations="fips",
            color=selected_metric,
            color_continuous_scale="Viridis",
            range_color=(0, range_max),
            scope="usa",
            labels={selected_metric: metric_label},
            hover_data={"fips": True, selected_metric: hover_format},
        )
        map_fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=600)
        st.plotly_chart(map_fig, use_container_width=True)

    # ---- Supporting detail -------------------------------------------------
    with st.expander("Top 25 counties"):
        top25 = county_df.head(25).copy()
        top25.insert(1, "county", top25["fips"].map(lambda f: county_names.get(f, ("", ""))[0]))
        top25.insert(2, "state", top25["fips"].map(lambda f: county_names.get(f, ("", ""))[1]))
        st.dataframe(top25, use_container_width=True)

    try:
        from regional_viz.visualize import (
            distribution_figure,
            distribution_histogram,
            distribution_quantiles,
        )

        with st.expander(f"{selected_metric_label} distribution by county"):
            bar_fig = distribution_figure(
                county_df,
                metric_col=selected_metric,
                metric_label=metric_label,
                top_n=distribution_top_n,
                county_names=county_names,
            )
            st.plotly_chart(bar_fig, use_container_width=True)

            histogram = distribution_histogram(
                county_df,
                metric_col=selected_metric,
                metric_label=metric_label,
            )
            st.plotly_chart(histogram, use_container_width=True)

            st.write(
                f"**Distribution quantiles** — {metric_label.lower()} percentiles across filtered counties."
            )
            st.dataframe(
                distribution_quantiles(county_df, metric_col=selected_metric),
                use_container_width=True
            )

    except Exception:
        from regional_viz.visualize import distribution_data

        with st.expander(f"{selected_metric_label} distribution by county"):
            st.dataframe(
                distribution_data(
                    county_df,
                    metric_col=selected_metric,
                    top_n=distribution_top_n,
                    county_names=county_names,
                ).head(200),
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
