from __future__ import annotations

import math

import pandas as pd

from regional_viz.aggregate import aggregate_to_county, allocate_hud, aggregate_metrics_to_county


class TestAggregateToCounty:
    def test_sum_preserving_for_mapped_zips(self, tiny_zip4_frame, tiny_zip2fips):
        cty, _ = aggregate_to_county(tiny_zip4_frame, tiny_zip2fips)
        # 06103 -> 09003: 3+5 = 8
        # 10001 -> 36061: 7+1 = 8
        # 33101 -> 12086: 10
        # 99999 -> unmapped, dropped from output
        as_dict = dict(zip(cty["fips"], cty["patients"]))
        assert as_dict == {"09003": 8, "36061": 8, "12086": 10}

    def test_coverage_report_counts_unmapped(self, tiny_zip4_frame, tiny_zip2fips):
        _, coverage = aggregate_to_county(tiny_zip4_frame, tiny_zip2fips)
        # total = 3+5+7+1+10+4 = 30; mapped = 26; unmapped ZIPs = 1 (99999)
        assert coverage.total_count == 30
        assert coverage.mapped_count == 26
        assert coverage.unmapped_zip_count == 1
        assert math.isclose(coverage.coverage_ratio, 26 / 30)

    def test_output_sorted_descending(self, tiny_zip4_frame, tiny_zip2fips):
        cty, _ = aggregate_to_county(tiny_zip4_frame, tiny_zip2fips)
        assert cty["patients"].is_monotonic_decreasing

    def test_zero_input_doesnt_crash(self, tiny_zip2fips):
        empty = pd.DataFrame({"eps_zip": [], "patients": []})
        cty, cov = aggregate_to_county(empty, tiny_zip2fips)
        assert cty.empty
        assert cov.total_count == 0
        assert cov.coverage_ratio == 0.0

    def test_collapses_zip4_rows_to_zip5(self, tiny_zip4_frame, tiny_zip2fips):
        """Several +4 rows per ZIP5 should roll up cleanly."""
        cty, _ = aggregate_to_county(tiny_zip4_frame, tiny_zip2fips)
        # Two +4 rows for 06103 should produce exactly one county row.
        assert (cty["fips"] == "09003").sum() == 1


class TestAllocateHud:
    def test_split_zip_distributes_proportionally(
        self, tiny_zip4_frame, tiny_hud_allocation
    ):
        """ZIP 10001 has 8 patients (7+1); split 70/30 -> 5.6 to 36061, 2.4 to 36005."""
        cty, _ = allocate_hud(tiny_zip4_frame, tiny_hud_allocation)
        d = dict(zip(cty["fips"], cty["patients"]))
        assert math.isclose(d["36061"], 5.6)
        assert math.isclose(d["36005"], 2.4)
        assert math.isclose(d["09003"], 8.0)  # 06103 single county
        assert math.isclose(d["12086"], 10.0)

    def test_totals_preserved_for_mapped_zips(self, tiny_zip4_frame, tiny_hud_allocation):
        cty, coverage = allocate_hud(tiny_zip4_frame, tiny_hud_allocation)
        # All ZIPs except 99999 are in the HUD frame, so mapped total = 26.
        assert math.isclose(cty["patients"].sum(), 26.0)
        assert coverage.mapped_count == 26

    def test_unmapped_zip_reported(self, tiny_zip4_frame, tiny_hud_allocation):
        _, coverage = allocate_hud(tiny_zip4_frame, tiny_hud_allocation)
        assert coverage.unmapped_zip_count == 1


class TestAggregateMetricsToCounty:
    """Tests for multi-metric aggregation with derived calculations."""

    def test_cancer_prevalence_calculated_correctly(self, tiny_zip2fips):
        """Cancer prevalence should be (sum(numerator) / sum(patients)) * 100."""
        df = pd.DataFrame({
            "eps_zip": ["06103", "06103", "10001"],
            "patients": [100, 50, 200],
            "cancer_prevalence_numerator": [15, 8, 30],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        # 06103 -> 09003: (15+8)/(100+50) = 23/150 = 15.33%
        # 10001 -> 36061: 30/200 = 15.0%
        row_09003 = cty[cty["fips"] == "09003"].iloc[0]
        row_36061 = cty[cty["fips"] == "36061"].iloc[0]
        assert math.isclose(row_09003["cancer_prevalence_pct"], 15.33333, abs_tol=0.01)
        assert math.isclose(row_36061["cancer_prevalence_pct"], 15.0)

    def test_all_cause_mortality_rate_calculated_correctly(self, tiny_zip2fips):
        """All-cause mortality should be (sum(deaths) / sum(patients)) * 100000."""
        df = pd.DataFrame({
            "eps_zip": ["06103", "06103", "10001"],
            "patients": [100, 50, 200],
            "all_cause_deaths": [2, 1, 4],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        # 06103 -> 09003: (2+1)/(100+50) * 100000 = 3/150 * 100000 = 2000
        # 10001 -> 36061: 4/200 * 100000 = 2000
        row_09003 = cty[cty["fips"] == "09003"].iloc[0]
        row_36061 = cty[cty["fips"] == "36061"].iloc[0]
        assert math.isclose(row_09003["all_cause_mortality_per_100k"], 2000.0)
        assert math.isclose(row_36061["all_cause_mortality_per_100k"], 2000.0)

    def test_cancer_mortality_rate_calculated_correctly(self, tiny_zip2fips):
        """Cancer mortality should be (sum(cancer_deaths) / sum(patients)) * 100000."""
        df = pd.DataFrame({
            "eps_zip": ["06103", "10001"],
            "patients": [150, 200],
            "cancer_deaths": [1, 2],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        # 06103 -> 09003: 1/150 * 100000 = 666.67
        # 10001 -> 36061: 2/200 * 100000 = 1000.0
        row_09003 = cty[cty["fips"] == "09003"].iloc[0]
        row_36061 = cty[cty["fips"] == "36061"].iloc[0]
        assert math.isclose(row_09003["cancer_mortality_per_100k"], 666.67, abs_tol=0.01)
        assert math.isclose(row_36061["cancer_mortality_per_100k"], 1000.0)

    def test_zero_denominator_produces_zero_metrics(self, tiny_zip2fips):
        """Counties with zero patients should have zero-valued metrics, not NaN."""
        df = pd.DataFrame({
            "eps_zip": ["06103"],
            "patients": [0],
            "cancer_prevalence_numerator": [0],
            "all_cause_deaths": [0],
            "cancer_deaths": [0],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        row = cty.iloc[0]
        assert row["cancer_prevalence_pct"] == 0.0
        assert row["all_cause_mortality_per_100k"] == 0.0
        assert row["cancer_mortality_per_100k"] == 0.0
        assert not pd.isna(row["cancer_prevalence_pct"])

    def test_missing_metric_columns_produce_na(self, tiny_zip2fips):
        """If metric columns are absent, derived columns should be NaN."""
        df = pd.DataFrame({
            "eps_zip": ["06103"],
            "patients": [100],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        row = cty.iloc[0]
        assert pd.isna(row["cancer_prevalence_pct"])
        assert pd.isna(row["all_cause_mortality_per_100k"])
        assert pd.isna(row["cancer_mortality_per_100k"])

    def test_partial_metric_columns_calculate_what_exists(self, tiny_zip2fips):
        """Only metrics with complete data should be calculated."""
        df = pd.DataFrame({
            "eps_zip": ["06103"],
            "patients": [100],
            "cancer_prevalence_numerator": [15],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        row = cty.iloc[0]
        assert math.isclose(row["cancer_prevalence_pct"], 15.0)
        assert pd.isna(row["all_cause_mortality_per_100k"])
        assert pd.isna(row["cancer_mortality_per_100k"])

    def test_sum_preservation_for_metric_numerators(self, tiny_zip2fips):
        """Numerator columns should sum-preserve like patient counts."""
        df = pd.DataFrame({
            "eps_zip": ["06103", "06103", "10001", "99999"],
            "patients": [100, 50, 200, 10],
            "cancer_prevalence_numerator": [15, 8, 30, 5],
            "all_cause_deaths": [2, 1, 4, 1],
            "cancer_deaths": [1, 0, 2, 0],
        })
        cty, coverage = aggregate_metrics_to_county(df, tiny_zip2fips)
        # 99999 is unmapped, so totals exclude it
        assert cty["patients"].sum() == 350  # 100+50+200
        assert cty["cancer_prevalence_numerator"].sum() == 53  # 15+8+30
        assert cty["all_cause_deaths"].sum() == 7  # 2+1+4
        assert cty["cancer_deaths"].sum() == 3  # 1+0+2

    def test_output_includes_all_columns(self, tiny_zip2fips):
        """Output should include patients, numerators, and derived metrics."""
        df = pd.DataFrame({
            "eps_zip": ["06103"],
            "patients": [100],
            "cancer_prevalence_numerator": [15],
            "all_cause_deaths": [2],
            "cancer_deaths": [1],
        })
        cty, _ = aggregate_metrics_to_county(df, tiny_zip2fips)
        expected_cols = {
            "fips", "patients",
            "cancer_prevalence_numerator", "cancer_prevalence_pct",
            "all_cause_deaths", "all_cause_mortality_per_100k",
            "cancer_deaths", "cancer_mortality_per_100k",
        }
        assert set(cty.columns) == expected_cols


class TestEndToEndOnSynthetic:
    def test_synthetic_data_aggregates_with_full_coverage(
        self, synthetic_frame, synthetic_zip2fips
    ):
        """Synthetic ZIPs are all drawn from the seed table, so the seed
        crosswalk should give 100% coverage. If this fails, the seed data
        and the crosswalk have drifted apart."""
        _, coverage = aggregate_to_county(synthetic_frame, synthetic_zip2fips)
        assert coverage.coverage_ratio == 1.0
        assert coverage.unmapped_zip_count == 0

    def test_synthetic_aggregation_has_geographic_spread(
        self, synthetic_frame, synthetic_zip2fips
    ):
        """A demo that pins to one state isn't a demo. Expect coverage in
        many states from the rolled-up FIPS."""
        cty, _ = aggregate_to_county(synthetic_frame, synthetic_zip2fips)
        states = cty["fips"].str[:2].unique()
        assert len(states) >= 20, f"only {len(states)} states represented"
