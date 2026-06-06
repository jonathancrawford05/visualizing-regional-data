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
| `src/regional_viz/aggregate.py`   | Sum-preserving rollup with coverage reporting.                   |
| `src/regional_viz/synthetic.py`   | Deterministic dummy data with all-50-states geographic coverage. |
| `src/regional_viz/visualize.py`   | Plotly (interactive HTML) and GeoPandas (Albers PNG) renderers.  |
| `tests/`                          | 24 pytest cases — all offline, all <1s.                          |
| `app/streamlit_app.py`            | Interactive demo dashboard for stakeholder iteration.            |
| `scripts/generate_demo_data.py`   | CLI to write a synthetic ZIP+4 CSV.                              |
| `docs/quickstart.md`              | 60-second run guide.                                             |
| `docs/design-decisions.md`        | Why this stack, this crosswalk, this projection.                 |

## Quick start

```bash
uv sync --extra viz --extra app --extra dev       # installs from uv.lock
uv run pytest                                     # 24 tests, all offline
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
exactly. If you'd rather use plain pip + venv, the project is a standard
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

## TDD posture

Every module has tests that assert the *behavioral contract* a caller
relies on, not the implementation:

- Loader tests pin the leading-zero invariant (the bug that silently
  vaporizes New England in any naïve pandas read).
- Aggregation tests pin sum-preservation, descending sort, and the
  coverage report's accounting.
- HUD allocation tests pin proportional split and total preservation.
- Synthetic tests pin schema parity, reproducibility, geographic spread,
  and the heavy-tail count distribution — so the demo can't silently
  degenerate into a single-state map.

The intended development loop is to add a failing test for any new
behavior (a new crosswalk, a new binning scheme, a new diagnostic), make
it pass, then wire it through the Streamlit app.
