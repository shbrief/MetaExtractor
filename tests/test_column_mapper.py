"""Tests for metaextractor.column_mapper."""
import pytest
from metaextractor.column_mapper import (
    ColumnMapping,
    apply_mapping,
    join_tables,
    map_columns,
)

SCHEMA = [
    "sample_id",
    "subject_id",
    "body_site",
    "sex",
    "age",
    "disease",
    "study_name",
    "ncbi_accession",
]


# ---------------------------------------------------------------------------
# map_columns
# ---------------------------------------------------------------------------

class TestMapColumns:
    def test_exact_match(self):
        m = map_columns(["sample_id", "body_site"], SCHEMA)
        assert m.mapped == {"sample_id": "sample_id", "body_site": "body_site"}
        assert m.unmapped == []

    def test_case_insensitive_exact(self):
        m = map_columns(["Sample_ID", "Body_Site"], SCHEMA)
        assert m.mapped["Sample_ID"] == "sample_id"
        assert m.mapped["Body_Site"] == "body_site"

    def test_normalized_exact(self):
        # "sample-id" normalizes to "sampleid" → matches "sample_id"
        m = map_columns(["sample-id"], SCHEMA)
        assert m.mapped.get("sample-id") == "sample_id"

    def test_alias_gender_to_sex(self):
        m = map_columns(["Gender"], SCHEMA)
        assert m.mapped.get("Gender") == "sex"
        assert m.tier_used.get("Gender") == "alias"

    def test_unmapped_column_passes_through(self):
        m = map_columns(["completely_unknown_col"], SCHEMA)
        assert "completely_unknown_col" in m.unmapped
        assert "completely_unknown_col" not in m.mapped

    def test_no_collision_same_target(self):
        # "gender" and "sex" both map to "sex" — first wins, second collides
        m = map_columns(["Gender", "sex"], SCHEMA)
        assert m.mapped.get("Gender") == "sex" or m.mapped.get("sex") == "sex"
        assert len([v for v in m.mapped.values() if v == "sex"]) == 1
        assert len(m.collisions) == 1

    def test_empty_headers(self):
        m = map_columns([], SCHEMA)
        assert m.mapped == {}
        assert m.unmapped == []

    def test_empty_schema(self):
        m = map_columns(["sample_id", "body_site"], [])
        assert m.mapped == {}
        assert set(m.unmapped) == {"sample_id", "body_site"}


# ---------------------------------------------------------------------------
# apply_mapping
# ---------------------------------------------------------------------------

class TestApplyMapping:
    def test_renames_mapped_keys(self):
        mapping = ColumnMapping(mapped={"SampleID": "sample_id", "Site": "body_site"})
        rows = [{"SampleID": "s1", "Site": "stool", "extra": "x"}]
        out = apply_mapping(rows, mapping)
        assert out[0]["sample_id"] == "s1"
        assert out[0]["body_site"] == "stool"
        # Unmapped column kept as-is
        assert out[0]["extra"] == "x"

    def test_values_pass_through_verbatim(self):
        mapping = ColumnMapping(mapped={"col": "sample_id"})
        rows = [{"col": "  has spaces  "}]
        out = apply_mapping(rows, mapping)
        assert out[0]["sample_id"] == "  has spaces  "

    def test_empty_rows(self):
        mapping = ColumnMapping(mapped={"a": "sample_id"})
        assert apply_mapping([], mapping) == []


# ---------------------------------------------------------------------------
# join_tables
# ---------------------------------------------------------------------------

class TestJoinTables:
    def _make_rows(self, data: list[dict]) -> list[dict[str, str]]:
        return [{k: str(v) for k, v in row.items()} for row in data]

    def test_single_table_returned_unchanged(self):
        rows = self._make_rows([{"sample_id": "s1", "age": "30"}])
        merged, plan = join_tables([("t1", rows)])
        assert merged == rows
        assert plan.primary == "t1"
        assert plan.joins == []

    def test_two_tables_joined_on_sample_id(self):
        left = self._make_rows([
            {"sample_id": "s1", "age": "30"},
            {"sample_id": "s2", "age": "25"},
        ])
        right = self._make_rows([
            {"sample_id": "s1", "body_site": "stool"},
            {"sample_id": "s2", "body_site": "oral"},
        ])
        merged, plan = join_tables([("left", left), ("right", right)])
        assert len(merged) == 2
        by_id = {r["sample_id"]: r for r in merged}
        assert by_id["s1"]["body_site"] == "stool"
        assert by_id["s1"]["age"] == "30"
        assert plan.joins[0]["key"] == "sample_id"

    def test_no_shared_key_skips_table(self):
        left = self._make_rows([{"sample_id": "s1", "age": "30"}])
        right = self._make_rows([{"unrelated_col": "val"}])
        merged, plan = join_tables([("left", left), ("right", right)])
        assert len(plan.skipped) == 1
        assert plan.skipped[0]["right"] == "right"
        assert len(merged) == 1

    def test_low_overlap_skips_table(self):
        left = self._make_rows([{"sample_id": f"s{i}"} for i in range(10)])
        right = self._make_rows([{"sample_id": "s0", "extra": "val"}])
        # Only 1/10 overlap → below default 0.9 threshold
        merged, plan = join_tables([("left", left), ("right", right)])
        assert any(s["right"] == "right" for s in plan.skipped)

    def test_conflict_kept_from_primary(self):
        left = self._make_rows([{"sample_id": "s1", "age": "30"}])
        right = self._make_rows([{"sample_id": "s1", "age": "99"}])
        merged, plan = join_tables([("left", left), ("right", right)])
        # Primary value wins; conflict stored
        assert merged[0]["age"] == "30"
        assert "age" in merged[0].get("__conflicts__", {})

    def test_empty_input(self):
        merged, plan = join_tables([])
        assert merged == []
        assert plan.primary == ""
