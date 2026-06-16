# Multi-Metric Dashboard Feature Plan

## Overview
Extend the dashboard to support multiple metrics beyond patient counts:
1. Patient counts (existing, default)
2. Cancer prevalence (new)
3. All-cause mortality rate (new)
4. Cancer-attributed mortality rate (new)

## Data Schema Extension

### Current Schema
```csv
eps_zip,zip4,zip4_cluster_group,patients
01001,1345,G-9-7,1
01001,2209,G-9-7,1
```

### Extended Schema
```csv
eps_zip,zip4,zip4_cluster_group,patients,cancer_prevalence_numerator,all_cause_deaths,cancer_deaths
01001,1345,G-9-7,100,15,2,1
01001,2209,G-9-7,50,8,1,0
```

**New columns:**
- `cancer_prevalence_numerator`: Number of patients with cancer history (denominator is `patients`)
- `all_cause_deaths`: Total deaths (Veritas) in the time period
- `cancer_deaths`: Cancer-attributed deaths (12-month proximity window)

**Derived metrics (calculated at county level):**
- `cancer_prevalence_pct`: `(sum(cancer_prevalence_numerator) / sum(patients)) * 100`
- `all_cause_mortality_per_100k`: `(sum(all_cause_deaths) / sum(patients)) * 100000`
- `cancer_mortality_per_100k`: `(sum(cancer_deaths) / sum(patients)) * 100000`

## Implementation Phases

### Phase 1: Data Layer (TDD Foundation)
**Files to modify:**
- `src/regional_viz/loader.py` - Add optional columns to schema validation
- `tests/test_loader.py` - Test backward compatibility and new columns

**Test cases:**
- [ ] Loading CSV with new columns preserves all data
- [ ] Loading CSV without new columns still works (backward compatibility)
- [ ] New columns are validated as numeric types

### Phase 2: Aggregation Layer
**Files to modify:**
- `src/regional_viz/aggregate.py` - Add multi-metric aggregation function
- `tests/test_aggregate.py` - Test metric calculations and sum preservation

**Test cases:**
- [ ] Cancer prevalence calculated correctly at county level
- [ ] Mortality rates calculated correctly at county level
- [ ] Handles zero-denominator cases (counties with zero patients)
- [ ] Sum preservation for numerator columns
- [ ] Metrics filtered correctly when percentile filter applied

### Phase 3: Visualization Layer
**Files to modify:**
- `src/regional_viz/visualize.py` - Add metric-specific formatting helpers
- `tests/test_visualize.py` - Test metric formatting

**Test cases:**
- [ ] Metric labels formatted correctly (%, per 100k)
- [ ] Color ranges appropriate for each metric type
- [ ] Hover data shows correct metric

### Phase 4: Dashboard Integration
**Files to modify:**
- `app/streamlit_app.py` - Add metric selector and conditional rendering

**Changes:**
1. Add metric selector radio button in sidebar
2. Conditionally aggregate based on selected metric
3. Update map labels and hover text
4. Update distribution charts for selected metric
5. Consider: add distribution histogram for metric values

**UI Flow:**
```
Sidebar:
  [Metric Selection]
    ○ Patient counts (default)
    ○ Cancer prevalence (%)
    ○ All-cause mortality (per 100k)
    ○ Cancer-attributed mortality (per 100k)
    
Main Panel:
  - Map shows selected metric by county
  - Top 25 counties table shows selected metric
  - Distribution bar chart shows selected metric
```

### Phase 5: SQL Documentation
**Files to create:**
- `scripts/export_multi_metric_data.sql` - Databricks SQL to generate CSV

**Content:**
- Base query structure from user's demo script
- Add prevalence numerator from notebook 09
- Add death counts from notebook 10
- Document column definitions

## Decision Points

### Should other dashboard elements update with metric selection?

**Analysis:**
- **Map**: YES - Primary visualization, must show selected metric
- **Top 25 counties table**: YES - Show counties ranked by selected metric
- **Distribution bar chart**: YES - Show distribution of selected metric
- **Distribution histogram**: MAYBE - Useful to see value distribution across counties
- **Distribution quantiles table**: YES - Show percentiles for selected metric
- **Coverage metrics**: NO - These are about data quality, not the metric

**Recommendation:** Update all distribution elements to reflect selected metric. This provides consistent insight into geographic variation for each metric.

### Metric-specific considerations:

**Patient counts:**
- Current behavior (no change)
- Integer values
- Color scale: 0 to 97th percentile

**Cancer prevalence:**
- Percentage values (0-100%)
- Format: `15.3%`
- Color scale: 0% to 97th percentile of observed values
- Hover: Show both numerator and denominator

**Mortality rates:**
- Per 100,000 population
- Format: `450 per 100k`
- Color scale: 0 to 97th percentile
- Hover: Show both death count and population

## Backward Compatibility

**Critical:** The feature must not break existing workflows.

**Strategy:**
1. All new columns are optional
2. If new columns are absent, only "Patient counts" metric is selectable
3. Dashboard auto-selects "Patient counts" by default
4. Tests verify old CSV format still works

## Testing Strategy

**Unit tests:**
- Loader handles optional columns
- Aggregation calculates metrics correctly
- Metric formatting is correct

**Integration test:**
- Generate synthetic data with all columns
- Load and aggregate
- Verify metrics match expected values

**Manual testing:**
- Upload old CSV → should work unchanged
- Upload new CSV → should show all metric options
- Switch metrics → map and charts update correctly

## SQL Query Template

See `scripts/export_multi_metric_data.sql` for the full query. Key additions to the demo script:

```sql
-- Add cancer prevalence numerator (from notebook 09)
LEFT JOIN (
  SELECT patient_id, 
         CASE WHEN patient_first_cancer_year <= 2023 THEN 1 ELSE 0 END as has_cancer
  FROM cancer_prevalence_by_patient
) cancer ON cohort.patient_id = cancer.patient_id

-- Add death counts (from notebook 10)
LEFT JOIN (
  SELECT patient_id,
         death_year,
         cancer_attributed_flag
  FROM mortality_analysis
) deaths ON cohort.patient_id = deaths.patient_id 
          AND deaths.death_year = 2023

GROUP BY zip4_cluster_group, eps.eps_zip, eps.zip4
```

## Success Criteria

- [ ] All existing tests pass
- [ ] New tests cover all new functionality
- [ ] Old CSV format works unchanged
- [ ] New CSV format enables all 4 metrics
- [ ] Metric selection updates all relevant UI elements
- [ ] SQL query documented for data export
- [ ] README updated with new schema documentation

## Future Enhancements (Out of Scope)

These are deferred to future iterations:
- Multiple tabs for different metric categories
- Time series analysis (multiple years)
- Demographic stratification (age, gender)
- Statistical significance indicators
- Export filtered data to CSV
- Custom metric definitions
