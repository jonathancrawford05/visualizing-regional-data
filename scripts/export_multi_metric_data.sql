-- ============================================================================
-- Export Multi-Metric Data for Regional Visualization Dashboard
-- ============================================================================
--
-- This query exports ZIP+4 level data with multiple metrics:
--   1. Patient counts (cohort population)
--   2. Cancer prevalence numerator (for calculating prevalence %)
--   3. All-cause deaths (for calculating mortality per 100k)
--   4. Cancer-attributed deaths (for calculating cancer mortality per 100k)
--
-- Source notebooks:
--   - 09_epsilon_matched_cancer_prevalence_55plus.py
--   - 10_epsilon_matched_mortality_55plus.py
--
-- Output schema:
--   eps_zip, zip4, zip4_cluster_group, patients,
--   cancer_prevalence_numerator, all_cause_deaths, cancer_deaths
--
-- ============================================================================

-- ── Configuration ───────────────────────────────────────────────────────────
-- Adjust these parameters for your analysis:
--   - COHORT_ID: Recommended value is 4 (≥4yr claim span OR valid death)
--   - CALENDAR_YEAR: Year for cross-sectional analysis (e.g., 2023)
--   - AGE_CUTOFF_YEAR: Birth year for 55+ filter (≤1960 for 55+ in study period)
--   - PROXIMITY_MONTHS: Cancer attribution window (12 months recommended)

DECLARE COHORT_ID INT DEFAULT 4;
DECLARE CALENDAR_YEAR INT DEFAULT 2023;
DECLARE AGE_55_PLUS_CUTOFF_YEAR INT DEFAULT 1960;
DECLARE PROXIMITY_WINDOW_MONTHS INT DEFAULT 12;

-- ── Base Tables ─────────────────────────────────────────────────────────────
-- Catalog and schema
SET CATALOG = 'prod_marc_ia_projects';
SET SCHEMA = 'kythera_data_silver';

-- Table references
-- ${CATALOG}.${SCHEMA}.kythera_cohorts_option_a           -- Cohort membership
-- ${CATALOG}.${SCHEMA}.kythera_epsilon_23_old_age        -- Consumer database (geographic)
-- ${CATALOG}.${SCHEMA}.cv_zip_4_mapping                  -- ZIP+4 cluster groups
-- ${CATALOG}.${SCHEMA}.cancer_analysis_per_life_year_claims_unfiltered  -- Cancer claims
-- ${CATALOG}.${SCHEMA}.kythera_veritas_april_2026        -- Death records
-- ${CATALOG}.${SCHEMA}.kythera_gender_yob                -- Demographics

-- ── Step 1: ZIP+4 Cluster Mapping ───────────────────────────────────────────
WITH cluster_mapping AS (
  SELECT
    SPLIT(`Zipcode+4`, '-')[0] AS eps_zip,
    SPLIT(`Zipcode+4`, '-')[1] AS zip4,
    glm AS zip4_cluster_group
  FROM ${CATALOG}.${SCHEMA}.cv_zip_4_mapping
),

-- ── Step 2: Patient-Level Cancer History ───────────────────────────────────
-- Identify patients with cancer history prior to or during the calendar year
cancer_patients AS (
  SELECT
    id AS patient_id,
    MIN(abs_first_cancer_date) AS patient_first_cancer_date
  FROM ${CATALOG}.${SCHEMA}.cancer_analysis_per_life_year_claims_unfiltered
  WHERE cancer_site_category IS NOT NULL
  GROUP BY id
),

cancer_history_flag AS (
  SELECT
    patient_id,
    YEAR(patient_first_cancer_date) AS patient_first_cancer_year,
    CASE
      WHEN YEAR(patient_first_cancer_date) <= CALENDAR_YEAR THEN 1
      ELSE 0
    END AS has_cancer_history
  FROM cancer_patients
),

-- ── Step 3: Patient-Level Last Cancer Date (for mortality attribution) ─────
last_cancer_claim AS (
  SELECT
    id AS patient_id,
    MAX(abs_last_cancer_date) AS last_cancer_date
  FROM ${CATALOG}.${SCHEMA}.cancer_analysis_per_life_year_claims_unfiltered
  WHERE cancer_site_category IS NOT NULL
  GROUP BY id
),

-- ── Step 4: Deaths in Calendar Year ────────────────────────────────────────
deaths_this_year AS (
  SELECT
    patient_id,
    TO_DATE(dod) AS death_date,
    death_year,
    age_at_death
  FROM ${CATALOG}.${SCHEMA}.kythera_veritas_april_2026
  WHERE death_year = CALENDAR_YEAR
),

-- ── Step 5: Cancer-Attributed Deaths ───────────────────────────────────────
-- Deaths within 12 months of last cancer claim are considered cancer-attributed
cancer_attributed_deaths AS (
  SELECT
    d.patient_id,
    d.death_date,
    lcc.last_cancer_date,
    MONTHS_BETWEEN(d.death_date, lcc.last_cancer_date) AS months_cancer_to_death,
    CASE
      WHEN lcc.last_cancer_date IS NOT NULL
        AND MONTHS_BETWEEN(d.death_date, lcc.last_cancer_date) <= PROXIMITY_WINDOW_MONTHS
        AND MONTHS_BETWEEN(d.death_date, lcc.last_cancer_date) >= 0
      THEN 1
      ELSE 0
    END AS cancer_attributed_flag
  FROM deaths_this_year d
  LEFT JOIN last_cancer_claim lcc ON d.patient_id = lcc.patient_id
),

-- ── Step 6: Demographics (55+ Filter) ──────────────────────────────────────
demographics_55plus AS (
  SELECT
    patient_id,
    patient_gender AS gender,
    patient_birth_year AS yob
  FROM ${CATALOG}.${SCHEMA}.kythera_gender_yob
  WHERE patient_birth_year <= AGE_55_PLUS_CUTOFF_YEAR
),

-- ── Step 7: Main Query - Cohort × Epsilon × Metrics ────────────────────────
cohort_epsilon_metrics AS (
  SELECT
    eps.eps_zip,
    eps.zip4,
    cm.zip4_cluster_group,
    cohort.patient_id,
    COALESCE(cancer.has_cancer_history, 0) AS has_cancer_history,
    CASE WHEN deaths.patient_id IS NOT NULL THEN 1 ELSE 0 END AS died_this_year,
    COALESCE(ca_deaths.cancer_attributed_flag, 0) AS cancer_attributed
  FROM ${CATALOG}.${SCHEMA}.kythera_cohorts_option_a cohort
  -- Join Epsilon (geographic data) - INNER join = Epsilon-matched only
  INNER JOIN ${CATALOG}.${SCHEMA}.kythera_epsilon_23_old_age eps
    ON cohort.patient_id = eps.patient_id
  -- Join demographics (55+ filter)
  INNER JOIN demographics_55plus demog
    ON cohort.patient_id = demog.patient_id
  -- Join cluster mapping (optional, for filtering by cluster group)
  LEFT JOIN cluster_mapping cm
    ON eps.eps_zip = cm.eps_zip
    AND eps.zip4 = cm.zip4
  -- Join cancer history
  LEFT JOIN cancer_history_flag cancer
    ON cohort.patient_id = cancer.patient_id
  -- Join deaths this year
  LEFT JOIN deaths_this_year deaths
    ON cohort.patient_id = deaths.patient_id
  -- Join cancer-attributed deaths
  LEFT JOIN cancer_attributed_deaths ca_deaths
    ON cohort.patient_id = ca_deaths.patient_id
  WHERE cohort.cohort_id = COHORT_ID
    AND cohort.calendar_year = CALENDAR_YEAR
    AND cohort.alive_flag = 1  -- Alive at start of year (denominator)
    AND eps.state IS NOT NULL  -- Complete geographic data
    AND eps.eps_zip IS NOT NULL
)

-- ── Final Output: Aggregate to ZIP+4 Level ─────────────────────────────────
SELECT
  eps_zip,
  zip4,
  zip4_cluster_group,
  COUNT(DISTINCT patient_id) AS patients,
  SUM(has_cancer_history) AS cancer_prevalence_numerator,
  SUM(died_this_year) AS all_cause_deaths,
  SUM(cancer_attributed) AS cancer_deaths
FROM cohort_epsilon_metrics
GROUP BY eps_zip, zip4, zip4_cluster_group
ORDER BY patients DESC;

-- ============================================================================
-- Expected Output Format
-- ============================================================================
--
-- eps_zip | zip4 | zip4_cluster_group | patients | cancer_prevalence_numerator | all_cause_deaths | cancer_deaths
-- --------|------|--------------------|---------:|---------------------------:|-----------------:|--------------:
-- 01001   | 1345 | G-9-7              |      100 |                         15 |                2 |             1
-- 01001   | 2209 | G-9-7              |       50 |                          8 |                1 |             0
-- ...
--
-- Column Definitions:
--   - patients: Count of distinct patients alive at start of calendar year
--   - cancer_prevalence_numerator: Count with cancer history (diagnosis ≤ calendar year)
--   - all_cause_deaths: Count of deaths (any cause) during calendar year
--   - cancer_deaths: Count of cancer-attributed deaths (within 12-month window)
--
-- Derived Metrics (calculated in dashboard at county level):
--   - cancer_prevalence_pct = (sum(cancer_prevalence_numerator) / sum(patients)) × 100
--   - all_cause_mortality_per_100k = (sum(all_cause_deaths) / sum(patients)) × 100,000
--   - cancer_mortality_per_100k = (sum(cancer_deaths) / sum(patients)) × 100,000
--
-- ============================================================================
-- Usage Notes
-- ============================================================================
--
-- 1. Export to CSV for dashboard upload:
--    - Use Databricks SQL export or Python export via dbutils
--    - Ensure leading zeros in ZIP codes are preserved
--
-- 2. Cohort selection:
--    - Cohort 4 (≥4yr span) is recommended for mortality analysis
--    - Cohort 5 (≥5yr span) can be used for sensitivity analysis
--
-- 3. Calendar year selection:
--    - Avoid 2024-2025 due to claims lag and incomplete data
--    - 2023 is recommended for most recent complete data
--
-- 4. Geographic filtering:
--    - Only Epsilon-matched patients with complete geographic data
--    - Coverage rate: ~45% of Option A 55+ population
--
-- 5. Cancer attribution:
--    - 12-month proximity window is aligned with NB10 methodology
--    - Not death certificate cause of death (proxy only)
--
-- ============================================================================
