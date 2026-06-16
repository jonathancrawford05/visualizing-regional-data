-- Join zip4_cluster_group to patient data in Databricks
-- This script demonstrates two approaches for joining the cluster mapping

-- Approach 1: Split the Zipcode+4 column in the mapping table
-- Use this if your patient data has separate eps_zip and zip4 columns
WITH cluster_mapping AS (
  SELECT
    SPLIT(REPLACE(`Zipcode+4`, '-', ''), '')[0] AS eps_zip,
    SPLIT(REPLACE(`Zipcode+4`, '-', ''), '')[1] AS zip4,
    zip4_cluster_group
  FROM prod_marc_ia_projects.kythera_data_silver.cv_zip_4_mapping
)
SELECT
  patient_data.*,
  cluster_mapping.zip4_cluster_group
FROM your_patient_table AS patient_data
LEFT JOIN cluster_mapping
  ON patient_data.eps_zip = cluster_mapping.eps_zip
  AND patient_data.zip4 = cluster_mapping.zip4;


-- Approach 2: Concatenate eps_zip and zip4 in patient data
-- Alternative if you prefer to construct the full Zipcode+4 key
SELECT
  patient_data.*,
  mapping.zip4_cluster_group
FROM your_patient_table AS patient_data
LEFT JOIN prod_marc_ia_projects.kythera_data_silver.cv_zip_4_mapping AS mapping
  ON CONCAT(patient_data.eps_zip, '-', patient_data.zip4) = mapping.`Zipcode+4`;


-- Recommended: Approach 1 with proper handling of NULL cluster groups
-- This version provides a default value for unmapped ZIP+4 combinations
WITH cluster_mapping AS (
  SELECT
    SUBSTRING_INDEX(`Zipcode+4`, '-', 1) AS eps_zip,
    SUBSTRING_INDEX(`Zipcode+4`, '-', -1) AS zip4,
    zip4_cluster_group
  FROM prod_marc_ia_projects.kythera_data_silver.cv_zip_4_mapping
)
SELECT
  patient_data.eps_zip,
  patient_data.zip4,
  patient_data.patients,
  COALESCE(cluster_mapping.zip4_cluster_group, 'Unmapped') AS zip4_cluster_group
FROM your_patient_table AS patient_data
LEFT JOIN cluster_mapping
  ON patient_data.eps_zip = cluster_mapping.eps_zip
  AND patient_data.zip4 = cluster_mapping.zip4;
