# visualizing-regional-data

PoC for mapping **individuals per U.S. county** from an Epsilon consumer
database (ZIP+4 geography) joined to Kythera medical claims (patient
population).

The goal of this repo is *not* the final pipeline — it's a tight feedback
loop so we can iterate on three open questions before locking the design:

1. **How faithful to the ZIP geography do we want to be?** (Dominant-county
   vs. HUD allocation-ratio vs. ZCTA-level choropleth.)
2. **How do we want the map to read?** (Binning scheme, color scale, clip
   on the heavy tail, projection.)
3. **What's our coverage budget?** (Acceptable share of patients that
   land in "unmapped" buckets when a ZIP isn't in the crosswalk.)

## What's in the box

| Path                              | Purpose                                                          |
|-----------------------------------|------------------------------------------------------------------|
| `src/regional_viz/loader.py`      | Schema-validating CSV loader. Preserves leading-zero ZIPs.       |
| `src/regional_viz/crosswalk.py`   | Public ZIP→dominant-FIPS map + HUD allocation-ratio loader.      |
| `src/regional_viz/aggregate.py`   | Sum-preserving rollup with coverage reporting + multi-metric aggregation. |
| `src/regional_viz/cluster.py`     | Cluster-comparison transforms: per-cluster units, credibility weighting, IQR censoring. |
| `src/regional_viz/synthetic.py`   | Deterministic dummy data with all-50-states geographic coverage. |
| `src/regional_viz/visualize.py`   | Plotly (interactive HTML) and GeoPandas (Albers PNG) renderers.  |
| `tests/`                          | 84 pytest cases — all offline, all <2s.                          |
| `app/streamlit_app.py`            | Interactive demo dashboard (County map + Cluster comparison tabs). |
| `scripts/generate_demo_data.py`   | CLI to write a synthetic ZIP+4 CSV.                              |
| `scripts/export_multi_metric_data.sql` | Databricks SQL to export multi-metric data.                |
| `docs/quickstart.md`              | 60-second run guide.                                             |
| `docs/design-decisions.md`        | Why this stack, this crosswalk, this projection.                 |
| `docs/multi-metric-feature-plan.md` | Implementation plan for multi-metric support.                 |
| `docs/cluster-comparison-feature.md` | Cluster tab: credibility weighting + IQR censoring.          |
| `docs/performance-enhancements-plan.md` | Planned A+B+C work for large inputs (caching, scalable plots, ingest). |

## Quick start

```bash
uv sync --extra viz --extra app --extra dev       # installs from uv.lock
uv run pytest                                     # 57 tests, all offline
uv run python scripts/generate_demo_data.py       # data/raw/synthetic.csv
uv run streamlit run app/streamlit_app.py         # interactive choropleth
```

> Note: If `uv sync --extra app` fails while downloading `pyarrow` with an
> `invalid peer certificate: UnknownIssuer` error, try setting a trusted CA
> bundle first:
>
> ```bash
> export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
> uv sync --extra viz --extra app --extra dev
> ```

`uv.lock` pins the full transitive tree so the environment reproduces
exactly. This app also raises Streamlit's default 200 MB upload cap to 512 MB
via `.streamlit/config.toml`.

If you'd rather use plain pip + venv, the project is a standard
PEP 621 package: `pip install -e ".[viz,app,dev]"` from inside a venv
also works (no lockfile, but otherwise equivalent).

See [`docs/quickstart.md`](docs/quickstart.md) for the longer version and
[`docs/design-decisions.md`](docs/design-decisions.md) for the *why*.

## How this differs from the original script

The seed for this repo was a single-file script
(`zip_to_county_choropleth.py`) that produced a county-level choropleth from
the sample data. That script remains a clear summary of the pipeline; this
repo lifts it into a structured codebase so we can iterate confidently:

- **Testable units.** Loader / crosswalk / aggregation / synth / viz are
  independent modules with focused tests. The original mixed I/O,
  network, and rendering in one file.
- **Coverage reporting is first-class.** Unmapped ZIPs are surfaced
  through a `CoverageReport` rather than printed and discarded. Silent
  drops are a defect in a claims pipeline.
- **Two crosswalk strategies, one interface.** `aggregate_to_county`
  (dominant) and `allocate_hud` (boundary-splitting) take the same input
  frame and return the same output shape, so we can A/B them without
  rewriting downstream code.
- **Synthetic data ships with the repo.** No need to pass around the real
  CSV during development. The synthetic generator deliberately mimics
  the heavy-tail patient distribution and includes leading-zero New
  England ZIPs so the pipeline is exercised the way production will.
- **Hermetic tests.** Nothing in the test suite touches the network;
  fixtures inject the crosswalk. CI stays fast and offline.

## Multi-Metric Support

The dashboard now supports multiple metrics beyond patient counts:

**Supported metrics:**
1. **Patient counts** (default) — Count of individuals per county
2. **Cancer prevalence (%)** — Percentage with cancer history
3. **All-cause mortality (per 100k)** — Total death rate
4. **Cancer-attributed mortality (per 100k)** — Cancer death rate

**Input schema:**
```csv
eps_zip,zip4,zip4_cluster_group,patients,cancer_prevalence_numerator,all_cause_deaths,cancer_deaths
01001,1345,G-9-7,100,15,2,1
```

**Backward compatibility:** All new columns are optional. CSVs with only `eps_zip` and `patients` still work.

**How metrics are calculated:**
- Input data is at ZIP+4 level with raw counts
- Dashboard aggregates to county level and calculates rates:
  - `cancer_prevalence_pct = (sum(numerator) / sum(patients)) × 100`
  - `mortality_per_100k = (sum(deaths) / sum(patients)) × 100,000`

See [`docs/multi-metric-feature-plan.md`](docs/multi-metric-feature-plan.md) for implementation details and [`scripts/export_multi_metric_data.sql`](scripts/export_multi_metric_data.sql) for the Databricks SQL query to generate input data.

## Cluster Comparison

The **Cluster comparison** tab compares a metric's distribution across the
ZIP+4 cluster groups (15 in production). Each cluster is a box or violin; the
points are its ZIP or ZIP+4 units.

- **Aggregation level:** ZIP (smoother) or ZIP+4 (granular).
- **Credibility weighting:** each unit is shrunk toward its cluster's expected
  value — `Z·observed + (1−Z)·expected` — with `Z` driven by the unit's
  numerator (deaths / cancer claimants). Three methods: square-root (limited
  fluctuation, default), linear, and Bühlmann `n/(n+k)`. A slider sets the
  threshold. This tames noisy small ZIP+4 cells.
- **IQR censoring:** an optional cap at `Q3 + k·IQR` (k defaults to 3.5)
  clips the long tail while keeping censored points visible at the cap.

See [`docs/cluster-comparison-feature.md`](docs/cluster-comparison-feature.md) for the full design.

## TDD posture

Every module has tests that assert the *behavioral contract* a caller
relies on, not the implementation:

- Loader tests pin the leading-zero invariant (the bug that silently
  vaporizes New England in any naïve pandas read) and validate optional metric columns.
- Aggregation tests pin sum-preservation, descending sort, coverage reporting,
  and multi-metric calculations (prevalence %, mortality rates).
- HUD allocation tests pin proportional split and total preservation.
- Synthetic tests pin schema parity, reproducibility, geographic spread,
  and the heavy-tail count distribution — so the demo can't silently
  degenerate into a single-state map.
- Cluster tests pin the credibility blend (`Z·observed + (1−Z)·expected`
  with hand-computed Z), the three Z formulas, per-cluster expected values,
  and the `Q3 + k·IQR` censoring fence.

The intended development loop is to add a failing test for any new
behavior (a new crosswalk, a new binning scheme, a new diagnostic), make
it pass, then wire it through the Streamlit app.
