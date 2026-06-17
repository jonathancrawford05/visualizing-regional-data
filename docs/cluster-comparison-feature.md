# Cluster Comparison Tab

## Overview

The dashboard has a second tab, **Cluster comparison**, for comparing the
distribution of a selected metric across the ZIP+4 **cluster groups** (15 in
the production data). Each cluster is drawn as one box or violin; the points
within it are that cluster's ZIP or ZIP+4 units.

The tab is built around two ideas that keep ZIP+4-level noise from dominating:
**credibility weighting** (shrink noisy small cells toward the cluster mean)
and **IQR censoring** (cap the long tail without hiding it).

## Controls

| Control | What it does |
| --- | --- |
| **Metric** | One of the three rate metrics: cancer prevalence (%), all-cause mortality (per 100k), cancer-attributed mortality (per 100k). Only metrics whose numerator column is present appear. |
| **Aggregation level** | `ZIP+4 (granular)` keeps every +4 as its own unit (noisier). `ZIP (smoother)` sums the +4 rows per ZIP5 (less granular, less noisy). |
| **Credibility method** | `Square-root (limited fluctuation)` (default), `Linear`, or `Bühlmann (n/(n+k))`. |
| **Credibility threshold** | Numerator count for full credibility (sqrt/linear), or the `k` in Bühlmann. |
| **Plot type** | `Box` or `Violin`. Both draw outlier points explicitly. |
| **Cap outliers (IQR)** | Toggle censoring on/off. |
| **IQR k** | Cap = `Q3 + k·IQR`. Defaults to **3.5**. |
| **Clusters to compare** | Multi-select; defaults to **all** clusters. |

The tab uses its own cluster multi-select and operates on the full loaded
data — it is independent of the County map tab's sidebar cluster filter.

## Credibility weighting

For each unit *i* (a ZIP or ZIP+4) in cluster *c*, the raw observed rate is
shrunk toward the cluster's expected rate:

```
estimate_i = Z_i · observed_i + (1 − Z_i) · expected_c
```

- **`observed_i`** — the unit's own metric value (`multiplier · numerator_i / denominator_i`).
- **`expected_c`** — the cluster's aggregate metric value, computed as the
  denominator-weighted mean of the unit values (algebraically the cluster's
  own pooled rate). This is the *complement of credibility* target.
- **`Z_i` ∈ [0, 1]`** — the credibility factor, driven by the unit's
  **numerator** *n_i* (deaths or cancer claimants) and the threshold:

  | Method | Formula | Threshold meaning |
  | --- | --- | --- |
  | `sqrt` (default) | `min(1, √(n/threshold))` | numerator count for full credibility (Z=1) |
  | `linear` | `min(1, n/threshold)` | numerator count for full credibility |
  | `buhlmann` | `n / (n + threshold)` | the Bühlmann `k` |

A ZIP+4 with a single death therefore has a tiny `Z` and is pulled almost
entirely to its cluster mean, instead of reading as a wild rate. A unit that
clears the threshold stands on its own data.

## IQR censoring

Even after shrinkage a few units sit far out. Rather than let them stretch
the y-axis, values above a single global fence

```
cap = Q3 + k · (Q3 − Q1)        # k defaults to 3.5
```

are clipped to the cap and flagged. The censored points pile up *at* the cap,
so you still see how much density sits at or above it. A dashed reference line
marks the cap on the chart, and the per-cluster summary reports how many units
each cluster had censored.

## Code locations

- **Pure transforms:** `src/regional_viz/cluster.py`
  - `aggregate_to_cluster_units` — raw ZIP+4 → per-unit rows within a cluster
  - `credibility_factor`, `apply_credibility`
  - `iqr_upper_fence`, `apply_cap`
  - `CLUSTER_METRIC_SPECS` — the three rate-metric definitions
- **Figure:** `cluster_distribution_figure` in `src/regional_viz/visualize.py`
- **Synthetic data:** `generate_synthetic_zip4(..., n_clusters=15, with_metrics=True)` in `src/regional_viz/synthetic.py`
- **UI:** `render_cluster_tab` in `app/streamlit_app.py`
- **Tests:** `tests/test_cluster.py`, plus additions in `tests/test_visualize.py` and `tests/test_synthetic.py`

## Testing

```bash
uv run pytest -v
```

All transforms are pure pandas/numpy and are tested with hand-computed
expected values (credibility blends, IQR fences, aggregation totals).
