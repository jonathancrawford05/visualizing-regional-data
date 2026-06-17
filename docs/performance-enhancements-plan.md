# Performance Enhancements for Large Inputs — Implementation Plan

> **Status:** In progress — being delivered one component at a time so the
> UX can be validated between steps.
>
> | Component | Status | Notes |
> |-----------|--------|-------|
> | **A. Cache the heavy steps** | ✅ Done | Shipped in branch `claude/ecstatic-pascal-fzji5x`. See **Progress log** below. |
> | **B. Size-independent plotting** | ⬜ Not started | Next up. Fixes the ZIP+4 crash. |
> | **C. Leaner ingest** | ⬜ Not started | pyarrow engine + compact dtypes. |
>
> Each component is its own session + review cycle. Mirror the existing
> module/test conventions, TDD-first.

## Progress log

### Component A — Cache the heavy steps ✅ (2026-06-17)

Implemented in `app/streamlit_app.py` (caching is Streamlit-specific, so the
wrappers live in the app layer; the pure functions in `src/regional_viz/`
are unchanged and still the single source of aggregation truth).

- **A1 — cached upload parse:** `parse_upload(file_id, _raw)`. `file_id` is
  Streamlit's stable `UploadedFile.file_id`; the bytes are passed as `_raw`
  (hash-excluded). Synthetic generation is likewise cached via
  `get_synthetic_df(n_rows, seed, n_clusters, with_metrics)` with a derived
  `file_id = f"synthetic:{n_rows}:{seed}:{n_clusters}:metrics"`.
- **A2 — cached county rollup:** `cached_aggregate_to_county(file_id,
  cluster_groups_key, use_multi_metric, _df, _zip2fips)`. The global
  **percentile filter is applied *after* this call**, so moving that slider
  no longer re-aggregates.
- **A3 — cached cluster rollup:** `cached_aggregate_to_cluster_units(file_id,
  level, metric_key, _df)`. **Restructure:** aggregate over *all* clusters
  once, then filter `units` to the selected clusters; credibility, capping
  and cluster selection are cheap post-processing. Per-cluster `expected` is
  computed independently per cluster, so filter-after ≡ filter-before
  (covered by a test).
- **Tests:** `tests/test_app_cache.py` loads the app module and asserts each
  wrapper delegates faithfully (caching doesn't change results), the leading-
  zero ZIP invariant survives `parse_upload`, and filter-after ≡ filter-before
  for the cluster restructure. Verified end-to-end with Streamlit `AppTest`
  (both tabs render, percentile change reruns clean, no exceptions). Full
  suite: 90 passed.
- **Deferred (still optional, see A3 note below):** caching
  `apply_credibility` on `(file_id, level, metric_key, threshold, method)`.
  Left out for now — the post-processing is cheap at current scale; revisit
  if threshold/method changes feel sluggish on a real ≥5M-row file. The
  bigger remaining win is **B** (the crash), which should come next.

## Motivation

The dashboard works on synthetic data but struggles on production-scale
input. A representative real file is **~260 MB / ~10.5M ZIP+4 rows /
~17.6M patients / ~3,100 counties**. Two distinct problems were observed
and measured (5M-row synthetic stand-in):

1. **No caching on the data path.** Streamlit reruns the whole script on
   every widget interaction, so each slider nudge re-parses the 260 MB CSV
   **and** re-runs aggregation. Measured at 5M rows: cluster aggregation
   **6.6 s (ZIP+4) + 2.2 s** credibility/cap, *per interaction*, on top of
   the county rollup. This is the sluggish UX.

2. **The cluster plot ships every unit to the browser — the fall-over.**
   `px.box` / `px.violin` serialise *every* unit value into the figure. At
   ZIP+4 granularity the data has **millions of units** (5M rows →
   **4.27M units → ~34 MB of raw floats, >100 MB as JSON**, millions of
   points for plotly.js client-side). This exceeds Streamlit's WebSocket
   message limit and/or kills the browser tab. ZIP granularity collapses to
   a few thousand units (tiny payload), which is why "ZIP (smoother)"
   worked while "ZIP+4 (granular)" crashed.

## Scope (agreed)

Implement **A + B + C**. Box-plot outliers at scale: **exact server-side
box statistics over all units, plus a bounded sample of outlier dots**
(default ≤ 500 per cluster), provided this does not change the
interpretation of results (it should not — the box/whiskers/fences are
computed from the full population; only the rendering of individual outlier
*dots* is sampled).

---

## A. Cache the heavy steps

**Goal:** pay ingest + aggregation cost once, not on every rerun.

### A1. Cache the upload parse
- New cached loader, keyed on the upload's *identity* not its bytes:
  ```python
  @st.cache_data(show_spinner="Parsing upload…")
  def parse_upload(file_id: str, _raw: bytes, columns: tuple[str, ...]) -> pd.DataFrame:
      ...
  ```
  - `_raw` is prefixed with `_` so Streamlit does **not** hash the 260 MB
    payload; the cache key is `file_id` (+ `columns`). Use
    `uploaded_file.file_id` (stable per upload) and
    `uploaded_file.getvalue()`.
- Inside, read with compact dtypes and only needed columns (see **C**).

### A2. Cache the county aggregation
- Wrap `aggregate_metrics_to_county` / `aggregate_to_county` in a cached
  helper keyed on `(file_id, tuple(selected_cluster_groups), use_multi_metric)`.
  Pass the DataFrame as a `_df` (hash-excluded) arg.
- Return value (`county_df_full`, coverage) is small (~3k rows) — cheap to
  cache.

### A3. Cache the cluster aggregation
- Wrap `aggregate_to_cluster_units` in a cached helper keyed on
  `(file_id, level, metric_key)` — **not** on the credibility/cap params.
  - Rationale: the heavy groupby depends only on data + level + metric.
    Credibility (`threshold`, `method`) and capping (`k`) and cluster
    selection are cheap post-processing applied *after* the cached result.
- Optionally also cache `apply_credibility` keyed on
  `(file_id, level, metric_key, threshold, method)` if the ~2 s recompute
  per threshold/method change is still noticeable.

### Caching notes / gotchas
- `@st.cache_data` hashes every non-`_`-prefixed arg. Always pass big
  DataFrames / bytes as `_`-prefixed params and put a cheap, stable key
  (e.g. `file_id`, `level`, `metric_key`) in the hashable args.
- Synthetic source: derive a stable `file_id` from `(n_rows, seed)` so the
  synthetic path also benefits and the cache key is well-defined.
- Return cached frames are stored in memory; at this scale the ZIP+4 units
  frame (~4M rows) is ~100 MB — acceptable, but keep an eye on total memory
  if multiple (level, metric) combinations get cached. Consider
  `max_entries` on the cluster-units cache.

---

## B. Size-independent plotting (fixes the crash)

**Goal:** make the cluster figure payload independent of input size.

All new logic goes into **pure functions in `src/regional_viz/cluster.py`**
with hand-checked tests in `tests/test_cluster.py`; the figure builder stays
in `visualize.py`.

### B1. Server-side box statistics
- New pure function:
  ```python
  def cluster_box_stats(
      units: pd.DataFrame,
      *,
      value_col: str = "capped_value",
      cluster_col: str = "cluster",
  ) -> pd.DataFrame:
      """Per-cluster five-number summary + Tukey fences + count.

      Returns one row per cluster with columns:
        cluster, n, q1, median, q3, lowerfence, upperfence, mean, min, max
      Fences use the standard 1.5*IQR Tukey rule (whisker extent), computed
      over ALL units in the cluster — independent of how many outlier dots
      are later drawn.
      """
  ```
- Tests: hand-computed quartiles/fences on a small fixture (reuse the
  `[1..8,100]` style vectors already used for `iqr_upper_fence`).

### B2. Bounded outlier sampling
- New pure function:
  ```python
  def sample_outlier_points(
      units: pd.DataFrame,
      stats: pd.DataFrame,
      *,
      value_col: str = "capped_value",
      cluster_col: str = "cluster",
      max_per_cluster: int = 500,
      seed: int = 0,
  ) -> pd.DataFrame:
      """Return the points beyond each cluster's whisker fences, down-sampled
      to at most max_per_cluster per cluster (deterministic via seed)."""
  ```
- Tests: a cluster with > `max_per_cluster` outliers returns exactly
  `max_per_cluster`; a cluster with few returns all; determinism under a
  fixed seed.

### B3. Figure builder using precomputed stats
- New figure function in `visualize.py`:
  ```python
  def cluster_box_figure_from_stats(
      stats: pd.DataFrame,
      outliers: pd.DataFrame | None = None,
      *,
      metric_label: str = "Value",
      cap: float | None = None,
      height: int = 520,
  ):
      """go.Box per cluster from precomputed q1/median/q3/fences (no raw
      data), plus an optional go.Scatter of sampled outlier dots."""
  ```
  - Use `plotly.graph_objects.Box(q1=[...], median=[...], q3=[...],
    lowerfence=[...], upperfence=[...], mean=[...])` — this ships ~6
    numbers per cluster, *not* the underlying points.
  - Keep the existing dashed `cap` reference line and `height` (the
    st.tabs height fix — keep it).
- Tests: figure has one box trace; box trace carries `q1`/`median`/`q3`
  arrays of length = #clusters; payload contains no multi-million-length
  array (assert the largest array in `fig.data` is bounded by
  `#clusters + max_per_cluster*#clusters`).

### B4. Violin at scale (downsample)
- Violin's KDE needs the points, so add a pure helper:
  ```python
  def downsample_per_cluster(
      units: pd.DataFrame,
      *,
      value_col: str = "capped_value",
      cluster_col: str = "cluster",
      max_per_cluster: int = 5_000,
      seed: int = 0,
  ) -> pd.DataFrame: ...
  ```
- Feed the downsampled frame to the existing `cluster_distribution_figure`
  (violin path). Tests: bounded size per cluster; determinism.

### App wiring (`render_cluster_tab`)
- After `apply_credibility` + `apply_cap`:
  - **Box:** `stats = cluster_box_stats(units)`,
    `outliers = sample_outlier_points(units, stats)`,
    `cluster_box_figure_from_stats(stats, outliers, ...)`.
  - **Violin:** `cluster_distribution_figure(downsample_per_cluster(units), plot_type="violin", ...)`.
- Per-cluster summary table already exists; extend it with `n` units and the
  exact (un-sampled) censored counts so nothing is lost by sampling.

---

## C. Leaner ingest

**Goal:** cut read time and memory.

- Read with the **pyarrow CSV engine** (already available — `pyarrow` 24 is
  a Streamlit dependency):
  ```python
  pd.read_csv(buf, engine="pyarrow",
              dtype_backend="pyarrow",  # or numpy; validate downstream
              usecols=needed_columns,
              dtype={"eps_zip": "string", "zip4": "string"})
  ```
  - `usecols`: read only `eps_zip, zip4, patients, zip4_cluster_group` and
    whichever numerator columns are present — skip everything else.
  - Compact dtypes: `patients` and numerators as **int32**;
    `zip4_cluster_group` as **category**; `eps_zip`/`zip4` as string.
  - Validate that the pyarrow backend plays well with existing groupby /
    arithmetic in `aggregate*`; if friction, keep numpy dtypes but still use
    `engine="pyarrow"` for the parse and `.astype(...)` to compact dtypes.
- Keep `loader.load_zip_counts` as the schema-validating path for the
  programmatic/CLI flow; the Streamlit upload path can call a thin wrapper
  that adds `usecols` + dtype tuning. Preserve the **leading-zero ZIP**
  invariant (strings, `zfill(5)`) — this is load-bearing and already tested.

---

## Test & acceptance plan

- **Unit (pure, offline, <2s):** `cluster_box_stats`, `sample_outlier_points`,
  `downsample_per_cluster`, `cluster_box_figure_from_stats` — all with
  hand-computed expectations, in the existing `tests/test_cluster.py` /
  `tests/test_visualize.py` style.
- **Payload bound (regression):** a test asserting the box figure's largest
  data array length is `<= #clusters + max_per_cluster*#clusters` even when
  fed a frame of, say, 1M synthetic units — this is the guard against the
  crash regressing.
- **Caching:** verify the cached loaders are keyed correctly (changing
  `level`/`metric` invalidates; moving an unrelated slider does not).
  (Streamlit cache behaviour is hard to unit-test directly — assert the
  helper functions are pure and keys are constructed from the documented
  inputs; manual verification via the headless-Chromium drive used
  previously.)
- **Manual at scale:** drive the running app with the pre-installed
  Chromium (`/opt/pw-browsers`) on a multi-million-row synthetic frame;
  confirm ZIP+4 box/violin render and that toggling widgets is responsive
  (cached) and does not crash.

## Acceptance criteria

1. ZIP+4 cluster box **and** violin render on a ≥5M-row input without the
   app/browser falling over.
2. After first load, changing metric / method / threshold / k / plot type /
   cluster selection updates in well under a second (no full re-parse,
   no full re-aggregate).
3. Box statistics reflect **all** units exactly; only outlier *dots* are
   sampled (≤ 500/cluster). The per-cluster summary reports true counts.
4. Existing tests stay green; new pure functions are covered.

## Out of scope (note for future)

- Switching ingest to a columnar store / DuckDB for out-of-core
  aggregation (would remove the in-memory ceiling entirely). Revisit if
  inputs grow beyond comfortable RAM.
- Server-side rendering of the county choropleth (3k rows — not a problem
  today).
