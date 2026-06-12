# ZIP+4 Cluster Group Filtering

## Overview

The dashboard now supports filtering by **ZIP+4 cluster groups**, allowing you to focus analysis on specific geographic segments of your data.

## How It Works

### 1. Preparing Your Data

The `zip4_cluster_group` column is **optional** and maintains backward compatibility with existing CSVs.

#### CSV Format

Your input CSV should include the `zip4_cluster_group` column:

```csv
eps_zip,zip4,patients,zip4_cluster_group
10001,0001,150,Urban_High
10001,0002,120,Urban_High
10002,0050,80,Urban_Medium
```

#### Joining Cluster Data in Databricks

Use the provided SQL script to join cluster assignments to your patient data:

```bash
scripts/join_zip4_cluster_groups.sql
```

The script demonstrates two approaches:

1. **Split approach** (recommended): Splits the `Zipcode+4` field in the mapping table
2. **Concatenate approach**: Builds the full ZIP+4 key from your patient data

Example:

```sql
-- Recommended approach
WITH cluster_mapping AS (
  SELECT
    SUBSTRING_INDEX(`Zipcode+4`, '-', 1) AS eps_zip,
    SUBSTRING_INDEX(`Zipcode+4`, '-', -1) AS zip4,
    zip4_cluster_group
  FROM prod_marc_ia_projects.kythera_data_silver.cv_zip_4_mapping
)
SELECT
  patient_data.*,
  COALESCE(cluster_mapping.zip4_cluster_group, 'Unmapped') AS zip4_cluster_group
FROM your_patient_table AS patient_data
LEFT JOIN cluster_mapping
  ON patient_data.eps_zip = cluster_mapping.eps_zip
  AND patient_data.zip4 = cluster_mapping.zip4;
```

### 2. Using the Dashboard Filter

When you upload a CSV with the `zip4_cluster_group` column:

1. The filter appears automatically in the **Filters** section of the sidebar
2. The filter shows all unique cluster groups in your data (sorted alphabetically)
3. Select one or more groups to filter the data
4. Leave the selection empty to include all groups

#### Filter Behavior

- **Multi-select**: Choose multiple cluster groups simultaneously
- **Global filter**: Applies to ALL dashboard components:
  - Choropleth map
  - Distribution charts
  - Summary metrics
  - County tables
- **Pre-aggregation**: Filtering happens before county rollup, ensuring accurate patient counts

#### Example Use Cases

- **Urban vs. Rural**: Filter by `Urban_High`, `Urban_Medium`, `Suburban_High`
- **Specific Markets**: Focus on `Resort` or `Military_Base` clusters
- **Comparative Analysis**: Toggle between different cluster groups to compare geographic patterns

### 3. Backward Compatibility

The feature is fully backward compatible:

- CSVs **without** `zip4_cluster_group` work exactly as before
- The filter only appears when the column is present
- All existing functionality remains unchanged

### 4. Metrics and Indicators

When cluster filtering is active:

- The **Input rows** metric shows a delta indicating how many rows remain after filtering
- All downstream metrics (counties shown, patient coverage, total patients) reflect the filtered data

## Technical Details

### Data Flow

1. **Load**: CSV is loaded with optional `zip4_cluster_group` column
2. **Filter**: If cluster groups are selected, filter the input DataFrame
3. **Aggregate**: Roll up filtered data to county level
4. **Visualize**: All charts and maps use the filtered + aggregated data

### Testing

The implementation includes comprehensive test coverage:

- `tests/test_loader.py`: Optional column handling
- `tests/test_cluster_filtering.py`: Filter logic and aggregation
- 46 total tests (all passing)

Run tests with:

```bash
uv run pytest -v
```

### Code Locations

- **SQL Script**: `scripts/join_zip4_cluster_groups.sql`
- **Loader Logic**: `src/regional_viz/loader.py:29-47`
- **UI Filter**: `app/streamlit_app.py:86-99`
- **Filter Application**: `app/streamlit_app.py:145-149`
- **Tests**: `tests/test_cluster_filtering.py`, `tests/test_loader.py`

## Example Data

A sample CSV with cluster groups is available for testing:

```bash
data/test/sample_with_clusters.csv
```

This file demonstrates the expected format with various cluster group types (Urban_High, Suburban_Medium, Resort, etc.).
