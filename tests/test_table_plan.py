"""Tests for metaextractor.table_plan — is_feature_matrix and execute_plan."""
import pytest
from metaextractor.supplementary import Table
from metaextractor.table_plan import (
    IdColumn,
    Melt,
    MeltGroup,
    PlanExecutionError,
    PlanProposalError,
    TablePlan,
    execute_plan,
    is_feature_matrix,
)


def _table(name: str, raw_rows: list[list[str]]) -> Table:
    if len(raw_rows) < 2:
        return Table(name=name, source="test", columns=[], rows=[], raw_rows=raw_rows)
    header = raw_rows[0]
    columns = list(header)
    rows = [{columns[i]: (row[i] if i < len(row) else "") for i in range(len(columns))}
            for row in raw_rows[1:]]
    return Table(name=name, source="test", columns=columns, rows=rows, raw_rows=raw_rows)


# ---------------------------------------------------------------------------
# is_feature_matrix
# ---------------------------------------------------------------------------

class TestIsFeatureMatrix:
    def test_normal_metadata_table_not_feature_matrix(self):
        raw = [
            ["sample_id", "body_site", "age", "sex"],
            ["s1", "stool", "30", "male"],
            ["s2", "oral", "25", "female"],
            ["s3", "stool", "45", "male"],
        ]
        assert not is_feature_matrix(_table("meta", raw))

    def test_metaphlan_taxonomy_detected(self):
        # Column 0 has MetaPhlAn-style feature IDs; rest are numeric
        raw = [
            ["feature", "s1", "s2", "s3"],
        ] + [
            [f"k__Bacteria|p__Firmicutes|c__cls|o__ord|f__fam|g__gen|t__sp{i}",
             str(0.1 * i), str(0.2 * i), str(0.05 * i)]
            for i in range(1, 12)
        ]
        assert is_feature_matrix(_table("taxa", raw))

    def test_genome_accessions_detected(self):
        raw = [
            ["genome", "s1", "s2", "s3"],
        ] + [
            [f"GCF_00000{i:04d}.1", str(i * 0.01), str(i * 0.02), str(i * 0.03)]
            for i in range(1, 12)
        ]
        assert is_feature_matrix(_table("genomes", raw))

    def test_sample_ids_as_columns_detected(self):
        # Most non-first headers look like sample IDs (alphanum + separator(s))
        # The regex requires at least one _ or - in the ID.
        sample_ids = [f"SRS-{100000 + i:06d}" for i in range(10)]
        raw = [["field"] + sample_ids]
        raw += [["age"] + [str(20 + i) for i in range(10)]]
        raw += [["sex"] + ["male"] * 5 + ["female"] * 5]
        raw += [["body_site"] + ["stool"] * 10]
        assert is_feature_matrix(_table("transposed", raw))

    def test_too_few_rows_returns_false(self):
        raw = [["a", "b"], ["1", "2"]]
        assert not is_feature_matrix(_table("small", raw))

    def test_single_column_returns_false(self):
        raw = [["feature"]] + [[f"k__Bacteria|p__X|c__Y|o__Z|f__W|g__G|t__sp{i}"] for i in range(10)]
        assert not is_feature_matrix(_table("single_col", raw))


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------

class TestExecutePlan:
    def test_simple_flat_plan(self):
        raw = [
            ["sample_id", "age", "sex"],
            ["s1", "30", "male"],
            ["s2", "25", "female"],
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[
                IdColumn(col=0, name="sample_id"),
                IdColumn(col=1, name="age"),
                IdColumn(col=2, name="sex"),
            ],
        )
        result = execute_plan(_table("t", raw), plan)
        assert result.columns == ["sample_id", "age", "sex"]
        assert len(result.rows) == 2
        assert result.rows[0]["sample_id"] == "s1"
        assert result.rows[1]["sex"] == "female"

    def test_drop_rows(self):
        raw = [
            ["sample_id", "age"],
            ["s1", "30"],
            ["NOTE: summary row", ""],  # row index 2
            ["s2", "25"],
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[IdColumn(col=0, name="sample_id"), IdColumn(col=1, name="age")],
            drop_rows=[2],
        )
        result = execute_plan(_table("t", raw), plan)
        assert len(result.rows) == 2
        ids = [r["sample_id"] for r in result.rows]
        assert "NOTE: summary row" not in ids

    def test_melt_wide_to_long(self):
        # Wide: one row per pair with Mother/Infant body-site columns
        raw = [
            ["pair_id", "body_site_Mother", "body_site_Infant"],
            ["p1", "stool", "feces"],
            ["p2", "oral", "feces"],
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[IdColumn(col=0, name="subject_id")],
            melt=Melt(
                category_column="sample_type",
                groups=[
                    MeltGroup(value_column="body_site", sources={"Mother": 1, "Infant": 2}),
                ],
            ),
        )
        result = execute_plan(_table("t", raw), plan)
        # 2 pairs × 2 categories = 4 rows
        assert len(result.rows) == 4
        types = {r["sample_type"] for r in result.rows}
        assert types == {"Mother", "Infant"}
        sites = {r["body_site"] for r in result.rows}
        assert sites == {"stool", "feces", "oral"}

    def test_skip_empty_category_rows(self):
        raw = [
            ["pair_id", "val_Mother", "val_Infant"],
            ["p1", "30", ""],   # Infant has no value
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[IdColumn(col=0, name="subject_id")],
            melt=Melt(
                category_column="sample_type",
                groups=[MeltGroup(value_column="value", sources={"Mother": 1, "Infant": 2})],
                skip_missing_categories=True,
            ),
        )
        result = execute_plan(_table("t", raw), plan)
        # Infant row skipped because value is ""
        assert len(result.rows) == 1
        assert result.rows[0]["sample_type"] == "Mother"

    def test_invalid_header_row_raises(self):
        raw = [["a", "b"], ["1", "2"]]
        plan = TablePlan(
            header_rows=[5],  # out of bounds
            data_starts_at=1,
            id_columns=[IdColumn(col=0, name="a")],
        )
        with pytest.raises(PlanExecutionError):
            execute_plan(_table("t", raw), plan)

    def test_invalid_column_index_raises(self):
        raw = [["a", "b"], ["1", "2"]]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[IdColumn(col=99, name="a")],  # out of range
        )
        with pytest.raises(PlanExecutionError):
            execute_plan(_table("t", raw), plan)

    def test_short_row_padded(self):
        # Data rows shorter than header are padded with ""
        raw = [
            ["a", "b", "c"],
            ["1"],  # missing b and c
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            id_columns=[
                IdColumn(col=0, name="a"),
                IdColumn(col=1, name="b"),
                IdColumn(col=2, name="c"),
            ],
        )
        result = execute_plan(_table("t", raw), plan)
        assert result.rows[0]["a"] == "1"
        assert result.rows[0]["b"] == ""
        assert result.rows[0]["c"] == ""


# ---------------------------------------------------------------------------
# propose_plan fallback — no LLM needed
# ---------------------------------------------------------------------------

class TestProposePlanFallback:
    """Verify the exception-handling contract: any failure in propose_plan
    raises PlanProposalError so _build_samples_from_tables can fall back."""

    def test_missing_api_key_raises_plan_proposal_error(self):
        from metaextractor.table_plan import propose_plan
        from anthropic import Anthropic

        # Build a client with a deliberately invalid API key so auth fails.
        client = Anthropic(api_key="sk-invalid-key-for-testing")
        raw = [["sample_id", "age"], ["s1", "30"], ["s2", "25"]]
        table = _table("t", raw)

        with pytest.raises(PlanProposalError):
            propose_plan(client, "claude-sonnet-4-6", table, ["sample_id", "age"])
