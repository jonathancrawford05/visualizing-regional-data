from __future__ import annotations

import math

import pandas as pd

from regional_viz.aggregate import aggregate_to_county, allocate_hud


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
