"""Streamlit demo: load a ZIP+4 CSV, aggregate to county, show the choropleth.

Run with::

    streamlit run app/streamlit_app.py

The sidebar lets stakeholders toggle between dummy data and a real upload,
apply a global patient-percentile filter (affects map and all charts),
adjust colour-range clipping, and control the distribution bar chart.

Two tabs:
  * **County map** — the choropleth + county distributions (the original view).
  * **Cluster comparison** — distribution of a selected metric across ZIP+4
    cluster groups, with credibility weighting and IQR censoring to tame
    ZIP+4-level outliers.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import streamlit as st

from regional_viz.aggregate import aggregate_to_county, aggregate_metrics_to_county
from regional_viz.cluster import (
    CLUSTER_METRIC_SPECS,
    aggregate_to_cluster_units,
    apply_cap,
    apply_credibility,
)
from regional_viz.loader import load_zip_counts
from regional_viz.synthetic import generate_synthetic_zip4, seed_dominant_county_map
from regional_viz.visualize import (
    PLOTLY_COUNTIES_URL,
    cluster_distribution_figure,
    filter_county_df_by_percentile,
    fips_to_county_name,
)

# Human-facing labels -> internal credibility method keys.
CREDIBILITY_METHOD_LABELS: dict[str, str] = {
    "Square-root (limited fluctuation)": "sqrt",
    "Linear": "linear",
    "Bühlmann (n / (n + k))": "buhlmann",
}


@st.cache_data(show_spinner="Fetching county GeoJSON…")
def load_counties_geojson() -> dict:
    with urlopen(PLOTLY_COUNTIES_URL) as r:
        return json.load(r)


@st.cache_data
def load_public_zip2fips() -> dict[str, str]:
    from regional_viz.crosswalk import load_zip2fips_dominant
    return load_zip2fips_dominant()


# ---------------------------------------------------------------------------
# Cached data path (perf plan, component A)
#
# Streamlit reruns the whole script on every widget interaction. Without
# caching, each slider nudge re-parses the upload *and* re-runs aggregation.
# These wrappers pay the ingest + groupby cost once, keyed on the data's
# identity (a stable ``file_id``) plus the few inputs the heavy step actually
# depends on. Big payloads are passed as ``_``-prefixed args so Streamlit does
# not hash them; the cheap, stable key lives in the non-underscore args.
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner="Generating synthetic data…")
def get_synthetic_df(
    n_rows: int, seed: int, n_clusters: int, with_metrics: bool
) -> pd.DataFrame:
    """Cache synthetic generation so re-runs don't regenerate the frame."""
    return generate_synthetic_zip4(
        n_rows=n_rows, seed=seed, n_clusters=n_clusters, with_metrics=with_metrics
    )


@st.cache_data(show_spinner="Parsing upload…")
def parse_upload(file_id: str, _raw: bytes) -> pd.DataFrame:
    """Parse an uploaded CSV once per upload identity.

    ``_raw`` is underscore-prefixed so Streamlit does not hash the (up to
    512 MB) payload; the cache key is the upload's stable ``file_id``.
    Leaner, dtype-tuned ingest is deferred to component C of the perf plan.
    """
    raw = pd.read_csv(io.BytesIO(_raw), dtype={"eps_zip": str})
    raw["eps_zip"] = raw["eps_zip"].str.zfill(5)
    raw["patients"] = raw["patients"].astype(int)
    return raw


@st.cache_data(show_spinner="Aggregating to county…")
def cached_aggregate_to_county(
    file_id: str,
    cluster_groups_key: tuple,
    use_multi_metric: bool,
    _df: pd.DataFrame,
    _zip2fips,
):
    """Cache the county rollup keyed on data identity + cluster filter + mode.

    The heavy groupby depends only on the (cluster-filtered) input and which
    rollup is used; the global percentile filter is applied cheaply *after*
    this call, so moving that slider does not re-aggregate.
    """
    if use_multi_metric:
        return aggregate_metrics_to_county(_df, _zip2fips)
    return aggregate_to_county(_df, _zip2fips)


@st.cache_data(show_spinner="Aggregating cluster units…")
def cached_aggregate_to_cluster_units(
    file_id: str, level: str, metric_key: str, _df: pd.DataFrame
) -> pd.DataFrame:
    """Cache the per-unit cluster rollup keyed on data + level + metric.

    Aggregates over *all* clusters; credibility weighting, IQR capping and
    cluster selection are cheap post-processing applied after this cached
    result, so nudging those widgets does not trigger the heavy groupby.
    """
    spec = CLUSTER_METRIC_SPECS[metric_key]
    return aggregate_to_cluster_units(
        _df,
        level=level,
        numerator_col=spec.numerator_col,
        denominator_col=spec.denominator_col,
        multiplier=spec.multiplier,
    )


def render_county_tab(
    *,
    file_id: str,
    df: pd.DataFrame,
    df_filtered: pd.DataFrame,
    zip2fips: dict[str, str],
    selected_metric: str,
    selected_metric_label: str,
    selected_cluster_groups,
    min_percentile: float,
    clip_q: float,
    distribution_top_n,
    use_multi_metric: bool,
) -> None:
    """The original choropleth view: aggregate to county, map, distributions."""
    cluster_groups_key = (
        tuple(sorted(selected_cluster_groups)) if selected_cluster_groups else ()
    )
    county_df_full, coverage = cached_aggregate_to_county(
        file_id,
        cluster_groups_key,
        use_multi_metric,
        df_filtered,
        zip2fips,
    )

    # Global percentile filter is population-based: always on patient counts.
    county_df = filter_county_df_by_percentile(
        county_df_full, min_percentile, metric_col="patients"
    )

    # ---- Metrics -----------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    input_rows_delta = None
    if selected_cluster_groups and len(selected_cluster_groups) > 0:
        input_rows_delta = f"{len(df_filtered):,} after cluster filter"

    c1.metric("Input rows", f"{len(df):,}", delta=input_rows_delta)
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
        st.warning(
            "No counties remain after applying the current filter. "
            "Lower the percentile to see data."
        )
    else:
        if selected_metric == "patients":
            metric_label = "Individuals"
            hover_format = ":,"
        elif selected_metric == "cancer_prevalence_pct":
            metric_label = "Cancer Prevalence (%)"
            hover_format = ":.2f"
        elif selected_metric in (
            "all_cause_mortality_per_100k",
            "cancer_mortality_per_100k",
        ):
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
            metric_label = selected_metric_label
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
                f"**Distribution quantiles** — {metric_label.lower()} "
                "percentiles across filtered counties."
            )
            st.dataframe(
                distribution_quantiles(county_df, metric_col=selected_metric),
                use_container_width=True,
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


def render_cluster_tab(df: pd.DataFrame, *, file_id: str) -> None:
    """Compare a metric's distribution across ZIP+4 cluster groups.

    Each cluster is one box/violin; the points within it are its ZIP or
    ZIP+4 units. Credibility weighting shrinks small-numerator units toward
    their cluster's expected value, and an optional IQR cap censors the long
    tail so the axis stays readable while density above the cap is preserved.
    """
    st.subheader("Cluster comparison")

    if "zip4_cluster_group" not in df.columns:
        st.info(
            "This tab needs a `zip4_cluster_group` column. Use the synthetic "
            "source, or upload a CSV with cluster assignments."
        )
        return

    available = {
        key: spec
        for key, spec in CLUSTER_METRIC_SPECS.items()
        if spec.numerator_col in df.columns
    }
    if not available:
        st.info(
            "This tab needs at least one metric numerator column "
            "(`cancer_prevalence_numerator`, `all_cause_deaths`, or "
            "`cancer_deaths`)."
        )
        return

    clusters = sorted(df["zip4_cluster_group"].dropna().unique())

    st.caption(
        "Points are **credibility-weighted** unit values: each ZIP/ZIP+4 is "
        "blended toward its cluster's expected value with weight Z driven by "
        "its numerator (deaths or cancer claimants). This tames the noise of "
        "small ZIP+4 cells."
    )

    ctrl1, ctrl2, ctrl3 = st.columns(3)

    with ctrl1:
        metric_label = st.selectbox(
            "Metric", [spec.label for spec in available.values()]
        )
        spec = next(s for s in available.values() if s.label == metric_label)
        level_label = st.radio(
            "Aggregation level",
            ["ZIP+4 (granular)", "ZIP (smoother)"],
            index=0,
            help=(
                "ZIP+4 is the most granular but noisiest unit. ZIP collapses "
                "the +4 rows together — less granular, less noisy."
            ),
        )
        level = "zip4" if level_label.startswith("ZIP+4") else "zip"

    with ctrl2:
        method_label = st.selectbox(
            "Credibility method", list(CREDIBILITY_METHOD_LABELS), index=0
        )
        method = CREDIBILITY_METHOD_LABELS[method_label]
        threshold_help = (
            "Bühlmann k — larger k shrinks harder."
            if method == "buhlmann"
            else "Numerator count at which a unit becomes fully credible (Z=1)."
        )
        threshold = st.slider(
            "Credibility threshold",
            min_value=1,
            max_value=200,
            value=30,
            help=threshold_help,
        )

    with ctrl3:
        plot_type = st.radio("Plot type", ["Box", "Violin"], index=0).lower()
        cap_on = st.checkbox(
            "Cap outliers (IQR)",
            value=True,
            help="Censor values above Q3 + k·IQR; censored points pile at the cap.",
        )
        iqr_k = st.slider(
            "IQR k (cap = Q3 + k·IQR)",
            min_value=0.5,
            max_value=6.0,
            value=3.5,
            step=0.5,
            disabled=not cap_on,
        )

    selected = st.multiselect("Clusters to compare", clusters, default=clusters)
    if not selected:
        st.warning("Select at least one cluster to compare.")
        return

    # Aggregate over *all* clusters once (cached on data + level + metric),
    # then filter to the selected clusters. Per-cluster ``expected`` is
    # computed independently per cluster, so filtering after aggregation is
    # equivalent to filtering before — but lets the heavy groupby be reused
    # when the cluster selection changes.
    units_full = cached_aggregate_to_cluster_units(file_id, level, spec.key, df)
    units = units_full[units_full["cluster"].isin(selected)]
    units = apply_credibility(units, threshold=threshold, method=method)

    cap = None
    value_col = "cred_value"
    if cap_on:
        units, cap = apply_cap(units, value_col="cred_value", k=iqr_k)
        value_col = "capped_value"

    fig = cluster_distribution_figure(
        units,
        value_col=value_col,
        plot_type=plot_type,
        metric_label=spec.label,
        cap=cap,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Per-cluster summary ----------------------------------------------
    agg = {"units": ("unit", "size"), "expected": ("expected", "first")}
    if cap_on:
        agg["censored"] = ("is_censored", "sum")
    summary = units.groupby("cluster", as_index=False).agg(**agg)
    summary = summary.rename(
        columns={
            "cluster": "Cluster",
            "units": "Units",
            "expected": f"Cluster expected ({spec.label})",
            "censored": "Censored (above cap)",
        }
    )
    with st.expander("Per-cluster summary"):
        st.dataframe(summary, use_container_width=True)
        if cap_on and cap is not None:
            st.caption(f"Global IQR cap applied at {cap:,.2f} (k = {iqr_k}).")


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
            n_clusters = 15
            df = get_synthetic_df(
                n_rows=n_rows, seed=int(seed), n_clusters=n_clusters, with_metrics=True
            )
            # Stable identity for the cache: same params ⇒ same frame.
            file_id = f"synthetic:{n_rows}:{int(seed)}:{n_clusters}:metrics"
            zip2fips = seed_dominant_county_map()
            st.success(f"Generated {len(df):,} synthetic ZIP+4 rows (15 clusters).")
        else:
            up = st.file_uploader(
                "CSV with columns eps_zip, zip4, patients",
                type="csv",
                help="Streamlit default limit is 200 MB per file; this app raises it to 512 MB via .streamlit/config.toml.",
            )
            if up is None:
                st.stop()
            # ``file_id`` is Streamlit's stable per-upload identity, so the
            # parse (and downstream aggregation) is cached across reruns.
            file_id = up.file_id
            df = parse_upload(file_id, up.getvalue())
            with st.spinner("Loading public ZIP→FIPS crosswalk…"):
                zip2fips = load_public_zip2fips()

        # ---- Global filters ------------------------------------------------
        st.header("Filters")
        st.info(
            "These filters apply to the **County map** tab — the map, "
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

        # ZIP+4 cluster group filter (optional column) — County tab only.
        selected_cluster_groups = None
        if "zip4_cluster_group" in df.columns:
            unique_groups = sorted(df["zip4_cluster_group"].dropna().unique())
            if len(unique_groups) > 0:
                selected_cluster_groups = st.multiselect(
                    "ZIP+4 cluster groups",
                    options=unique_groups,
                    default=None,
                    help=(
                        "Filter the County map tab to specific ZIP+4 cluster "
                        "groups. Leave empty to include all groups."
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

    # ---- County-tab cluster filter (pre-aggregation) -----------------------
    df_filtered = df.copy()
    if selected_cluster_groups and len(selected_cluster_groups) > 0:
        df_filtered = df_filtered[
            df_filtered["zip4_cluster_group"].isin(selected_cluster_groups)
        ]

    use_multi_metric = has_prevalence or has_all_cause or has_cancer_mort

    # ---- Tabs --------------------------------------------------------------
    tab_map, tab_cluster = st.tabs(["County map", "Cluster comparison"])

    with tab_map:
        render_county_tab(
            file_id=file_id,
            df=df,
            df_filtered=df_filtered,
            zip2fips=zip2fips,
            selected_metric=selected_metric,
            selected_metric_label=selected_metric_label,
            selected_cluster_groups=selected_cluster_groups,
            min_percentile=min_percentile,
            clip_q=clip_q,
            distribution_top_n=distribution_top_n,
            use_multi_metric=use_multi_metric,
        )

    with tab_cluster:
        # Operates on the full loaded data with its own cluster multiselect,
        # independent of the County tab's sidebar cluster filter.
        render_cluster_tab(df, file_id=file_id)


if __name__ == "__main__":
    main()
