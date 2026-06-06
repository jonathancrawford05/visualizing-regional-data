# Design decisions

These are the choices baked into the PoC, with the *why* so we can revisit
them deliberately rather than by inertia. Each one is the answer to a
question that came up in the original conversation.

## 1. Roll up to **county**, not ZIP+4

**Decision.** Collapse ZIP+4 rows to 5-digit ZIP, then map to county FIPS.

**Why.** The +4 suffix only disambiguates the handful of ZIPs that
straddle a county line. There is **no clean open crosswalk from ZIP+4 →
county**, and free geocoders return ZIP-centroid coordinates regardless
of the +4. For a county map, the +4 is dead weight. We keep the column in
the schema for future block-group or carrier-route work, but downstream
code never reads it.

## 2. Default crosswalk: dominant-county, with **HUD as the upgrade path**

**Decision.** Default to a public ZIP→single-FIPS dictionary
(`bgruber/zip2fips`). Provide a second strategy
(`aggregate.allocate_hud`) that consumes the HUD `ZIP_COUNTY` Excel file
and uses its residential allocation ratios to split a ZIP's count across
overlapping counties.

**Why two strategies, not one.**

- **Dominant.** Zero registration, ~95% patient coverage on the sample,
  good enough for a "does this look right?" demo.
- **HUD allocation.** Free but registration-walled. Splits ZIPs that
  straddle a county line proportionally. This is the variant we'd ship
  if the map were going into an actuarial deliverable.

Both strategies expose the same input/output contract (`DataFrame` in,
`(county_df, CoverageReport)` out), so swapping is a one-line change.

## 3. **Coverage is a first-class output**, not a print statement

**Decision.** Every aggregation function returns a `CoverageReport`
(total, mapped, unmapped-ZIP count, ratio). The Streamlit app surfaces
this prominently.

**Why.** In a claims pipeline, *silently* losing 5% of patients is a
defect, not a rounding error. The original script printed coverage and
moved on; we want the caller (notebook, dashboard, batch job) to be able
to *act* on it — warn, fail the job, or trigger a re-fetch.

## 4. **Albers equal-area** projection for the static map

**Decision.** EPSG:5070 (USA Contiguous Albers Equal Area) for the
static PNG. Drop AK/HI/territories from the static view; Plotly's
`scope="usa"` handles them on the interactive map.

**Why.** Choropleths read area as importance. Web Mercator inflates the
sparse west and shrinks the dense northeast — exactly backwards for a
patient-count map. Equal-area projection keeps the comparison honest.

## 5. **Quantile bins**, color-range **clipped at the 97th percentile**

**Decision.** Static map uses 6 quantile bins. Interactive map uses a
continuous Viridis scale clipped at `quantile(0.97)`.

**Why.** Patient-per-region distributions are heavily right-skewed —
Ocean County NJ has 7,100 patients; the median county has under 100. A
linear color scale washes out everything except a handful of hotspots.
Quantile bins (static) and a clipped continuous scale (interactive)
preserve the within-cluster contrast we actually want to see.

## 6. **Static + interactive**, not pick one

**Decision.** Two renderers, same input contract. Plotly HTML for
exploration; matplotlib + GeoPandas PNG for reports.

**Why.** Different consumers want different things. Stakeholders want
hover-to-inspect. Reports and Slack screenshots want a PNG. The cost of
maintaining both is one extra ~40-line module.

## 7. **Synthetic data ships with the repo**, with structural fidelity

**Decision.** A deterministic generator (`synthetic.generate_synthetic_zip4`)
produces a ZIP+4 frame that matches the real schema and mimics the real
distribution: Zipf-skewed counts, multiple +4 rows per ZIP, all 50 states
plus DC, leading-zero ZIPs included.

**Why.** Three reasons:

1. The real Epsilon × Kythera data is PII-adjacent — we don't want it
   sitting in git history or CI logs.
2. Demos and tests must work offline.
3. We need the synthetic data to *exercise the same code paths* as
   production, especially the leading-zero ZIP path (the single most
   common silent bug in ZIP-code pipelines).

The curated seed list in `_seed_zips.py` is hand-checked against the
public crosswalk so the dominant-county map gives 100% coverage on
synthetic data — that property is enforced as a test.

## 8. **TDD-first** module layout

**Decision.** One module per concern, each with a focused test file.
Aggregation tests pin the behavioral contract (sum preservation,
coverage accounting, sort order). Visualization is deliberately *not*
unit-tested beyond what's needed; rendering correctness is best judged
by eye via the Streamlit demo.

**Why.** The fragile pieces in this kind of pipeline are the data
transforms (ZIP parsing, mapping, aggregation). Pinning those with tests
lets us refactor freely. Tests for the renderers would be expensive to
maintain and would catch fewer real defects than just *looking* at the
map.

## 9. **Streamlit over Jupyter** for the demo

**Decision.** The primary demo artifact is `app/streamlit_app.py`, not a
notebook.

**Why.** The user said the goal is iteration toward a final solution.
Stakeholders argue more productively over a UI with sliders and a file
uploader than over a notebook; non-engineers can run a Streamlit app
without `pip install jupyter`. A notebook is welcome later for narrative
write-ups, but it's not the iteration tool.

## What we deliberately deferred

- **ZCTA-level choropleth.** Faithful to the ZIP granularity but
  conceptually messy (ZCTAs ≠ ZIPs) and the national shapefile is
  large. Easy to add later — same input shape, different `merge` key.
- **`pygris` / TIGER cartographic boundaries.** Higher-quality
  geometry than the Plotly mirror, at the cost of a heavier dependency
  and a one-time download. Worth pulling in if we ship a print-quality
  map.
- **Time slicing.** The current pipeline is a snapshot. Adding a `date`
  column to the aggregator is a one-line change; surfacing it through
  the dashboard is a slider. Out of scope for the PoC.
- **State / metro rollups.** Same pipeline, different `groupby` key.
  Add when the question demands it.
