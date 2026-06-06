# Quick start

## Install

Recommended path uses [uv](https://docs.astral.sh/uv/) — one tool for
both the virtualenv and the installer, and `uv.lock` reproduces the
exact dependency tree:

```bash
# install uv once, then:
uv sync --extra viz --extra app --extra dev
```

Pip alternative (no lockfile but otherwise equivalent):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[viz,app,dev]"
```

Optional extras:
- `viz` — geopandas, mapclassify, plotly, matplotlib (for the renderers)
- `app` — streamlit + plotly (for the dashboard)
- `dev` — pytest + coverage

## Run the tests

```bash
uv run pytest        # or just `pytest` inside an activated venv
```

All 24 tests should pass in under a second. None of them touch the network.

## Generate demo data

```bash
uv run python scripts/generate_demo_data.py --rows 10000 --seed 42
# wrote 10,000 rows -> data/raw/synthetic.csv
```

The CSV has the same schema as the real Epsilon × Kythera extract:
`eps_zip, zip4, patients`. ZIPs are 5-digit strings (leading zeros
preserved); patient counts follow a Zipf-style heavy tail and span ZIPs
from every U.S. state plus DC.

## Run the Streamlit dashboard

```bash
uv run streamlit run app/streamlit_app.py
```

The sidebar lets you:

- Pick **Synthetic** (offline) or **Upload CSV** (uses the public
  ZIP→FIPS crosswalk fetched from GitHub).
- Tune the **color-range clip quantile** — heavy-tail counts otherwise
  collapse the rest of the country into the same dark color.

The dashboard surfaces coverage metrics up top: total input, counties
hit, and percentage of patients that made it into a county bucket. If
that last number is anything but 100% on a real-data run, the
diagnostics panel will tell you how many ZIPs were missed.

## Render the static + interactive maps from Python

```python
from regional_viz import (
    generate_synthetic_zip4,
    aggregate_to_county,
    seed_dominant_county_map,
)
from regional_viz.visualize import render_interactive, render_static

df = generate_synthetic_zip4(n_rows=10_000, seed=42)
cty, coverage = aggregate_to_county(df, seed_dominant_county_map())
print(f"coverage: {coverage.coverage_ratio:.1%}")

render_interactive(cty, "outputs/map.html")
render_static(cty, "outputs/map.png")
```

## Switching to real data

```python
from regional_viz.loader import load_zip_counts
from regional_viz.crosswalk import load_zip2fips_dominant
from regional_viz.aggregate import aggregate_to_county

df = load_zip_counts("data/raw/real_extract.csv")
mapping = load_zip2fips_dominant()                 # public dominant-county crosswalk
cty, coverage = aggregate_to_county(df, mapping)
```

For an actuarial-grade run, swap in the HUD allocation table:

```python
from regional_viz.crosswalk import load_hud_allocation
from regional_viz.aggregate import allocate_hud

hud = load_hud_allocation("data/raw/ZIP_COUNTY_Q4_2024.xlsx")
cty, coverage = allocate_hud(df, hud)
```

The HUD file is free but requires a one-time registration at
<https://www.huduser.gov/portal/datasets/usps_crosswalk.html>.
