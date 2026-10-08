"""Tests for metaextractor.table_plan — is_feature_matrix and execute_plan."""
import pytest

from metaextractor.supplementary import Table
from metaextractor.table_plan import (
    Melt,
    MeltGroup,
    PlanExecutionError,
    PlanProposalError,
    TablePlan,
    execute_plan,
    is_feature_matrix,
    needs_structure_plan,
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
        raw = ([["feature"]]
               + [[f"k__Bacteria|p__X|c__Y|o__Z|f__W|g__G|t__sp{i}"] for i in range(10)])
        assert not is_feature_matrix(_table("single_col", raw))


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------

class TestExecutePlan:
    def test_flat_plan_keeps_every_column_under_its_header(self):
        raw = [
            ["Sample ID", "Age (years)", "Gender"],
            ["s1", "30", "male"],
            ["s2", "25", "female"],
        ]
        result = execute_plan(_table("t", raw), TablePlan(header_rows=[0], data_starts_at=1))
        assert result.columns == ["Sample ID", "Age (years)", "Gender"]
        assert [r["Gender"] for r in result.rows] == ["male", "female"]

    def test_title_row_and_stacked_header(self):
        raw = [
            ["Table S1A. Donors / Patients", "", ""],
            ["Patient", "Metagenomics", ""],
            ["ID", "Day 0", "Day 30"],
            ["347", "Yes", "Yes"],
        ]
        plan = TablePlan(header_rows=[1, 2], data_starts_at=3)
        result = execute_plan(_table("t", raw), plan)
        # super-header forward-filled over its span; the leaf row is not filled
        assert result.columns == ["Patient | ID", "Metagenomics | Day 0", "Metagenomics | Day 30"]
        assert result.rows == [{"Patient | ID": "347", "Metagenomics | Day 0": "Yes",
                                "Metagenomics | Day 30": "Yes"}]

    def test_blank_and_duplicate_leaf_labels_get_unique_names(self):
        raw = [["id", "", "id"], ["a", "b", "c"]]
        result = execute_plan(_table("t", raw), TablePlan(header_rows=[0], data_starts_at=1))
        assert result.columns == ["id", "col_1", "id_1"]

    def test_drop_rows(self):
        raw = [
            ["sample_id", "age"],
            ["s1", "30"],
            ["NOTE: summary row", ""],  # row index 2
            ["s2", "25"],
        ]
        plan = TablePlan(header_rows=[0], data_starts_at=1, drop_rows=[2])
        result = execute_plan(_table("t", raw), plan)
        assert [r["sample_id"] for r in result.rows] == ["s1", "s2"]

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
            melt=Melt(category_label="sample type",
                      groups=[MeltGroup(value_label="body site",
                                        sources={"Mother": 1, "Infant": 2})]),
        )
        result = execute_plan(_table("t", raw), plan)
        assert result.columns == ["pair_id", "sample type", "body site"]
        assert len(result.rows) == 4
        assert {r["sample type"] for r in result.rows} == {"Mother", "Infant"}
        assert {r["body site"] for r in result.rows} == {"stool", "feces", "oral"}

    def test_skip_empty_category_rows(self):
        raw = [
            ["pair_id", "val_Mother", "val_Infant"],
            ["p1", "30", ""],   # Infant has no value
        ]
        plan = TablePlan(
            header_rows=[0],
            data_starts_at=1,
            melt=Melt(category_label="sample type",
                      groups=[MeltGroup(value_label="val", sources={"Mother": 1, "Infant": 2})],
                      skip_missing_categories=True),
        )
        result = execute_plan(_table("t", raw), plan)
        assert len(result.rows) == 1
        assert result.rows[0]["sample type"] == "Mother"

    def test_invalid_header_row_raises(self):
        raw = [["a", "b"], ["1", "2"]]
        with pytest.raises(PlanExecutionError):
            execute_plan(_table("t", raw), TablePlan(header_rows=[5], data_starts_at=1))

    def test_invalid_melt_column_raises(self):
        raw = [["a", "b"], ["1", "2"]]
        plan = TablePlan(header_rows=[0], data_starts_at=1,
                         melt=Melt(category_label="c",
                                   groups=[MeltGroup(value_label="v", sources={"x": 99})]))
        with pytest.raises(PlanExecutionError):
            execute_plan(_table("t", raw), plan)

    def test_short_row_padded(self):
        raw = [["a", "b", "c"], ["1"]]
        result = execute_plan(_table("t", raw), TablePlan(header_rows=[0], data_starts_at=1))
        assert result.rows[0] == {"a": "1", "b": "", "c": ""}

    def test_plan_names_and_legacy_id_columns_are_ignored(self):
        # A response in the old format (with id_columns naming schema fields) does not
        # rename anything: the structural fields are used and extra keys are ignored.
        plan = TablePlan.model_validate({"header_rows": [0], "data_starts_at": 1,
                                         "id_columns": [{"col": 1, "name": "body_site"}]})
        raw = [["run", "country"], ["R1", "Sweden"]]
        assert execute_plan(_table("t", raw), plan).columns == ["run", "country"]


# ---------------------------------------------------------------------------
# needs_structure_plan
# ---------------------------------------------------------------------------

class TestNeedsStructurePlan:
    @pytest.mark.parametrize("raw", [
        [["sample_id", "age", "sex"], ["s1", "30", "male"], ["s2", "25", "female"],
         ["s3", "41", "male"]],
        [["Run", "Treatment", "Day"], ["SRR1", "MTX", "30"], ["SRR2", "naive", "0"]],
    ])
    def test_single_clean_header_needs_no_plan(self, raw):
        assert needs_structure_plan(_table("t", raw)) == (False, "single header row")

    @pytest.mark.parametrize("raw, reason", [
        ([["Table S1A. Donors", "", ""], ["ID", "Age", "Sex"], ["1", "30", "M"]],
         "row 0 has fewer than two labels"),
        ([["Patient", "Metagenomics", ""], ["ID", "Day 0", "Day 30"], ["347", "Yes", "No"],
          ["348", "No", "Yes"]], "blank cells inside the header span (stacked or merged header)"),
        ([["id", "value", "value"], ["a", "1", "2"]], "duplicate header labels"),
        ([["s1", "30", "2.5"], ["s2", "25", "1.0"]], "numeric header labels"),
        ([["Group", "Weight", "Height"], ["", "kg", "cm"], ["A", "70", "180"], ["B", "65", "170"]],
         "row 1 looks like a second header row"),
        ([["pair", "age_mother", "age_infant", "bmi_mother", "bmi_infant"],
          ["p1", "30", "1", "22", "15"]], "repeated column groups ('mother'/'infant')"),
    ])
    def test_layouts_that_need_a_plan(self, raw, reason):
        assert needs_structure_plan(_table("t", raw)) == (True, reason)


# ---------------------------------------------------------------------------
# propose_plan fallback — no LLM needed
# ---------------------------------------------------------------------------

class TestProposePlanFallback:
    """Verify the exception-handling contract: any failure in propose_plan
    raises PlanProposalError so _build_samples_from_tables can fall back."""

    @pytest.mark.network
    def test_missing_api_key_raises_plan_proposal_error(self):
        """Marked ``network``: this issues a real POST to api.anthropic.com.

        It passes with or without connectivity, because a 401 and a transport
        failure both become PlanProposalError — which is exactly why it is a weak
        test, and why it is deselected by default rather than silently adding
        latency to every run. Phase B replaces it with an injected model double.
        """
        from anthropic import Anthropic

        from metaextractor.table_plan import propose_plan

        # Build a client with a deliberately invalid API key so auth fails.
        client = Anthropic(api_key="sk-invalid-key-for-testing")
        raw = [["sample_id", "age"], ["s1", "30"], ["s2", "25"]]
        table = _table("t", raw)

        with pytest.raises(PlanProposalError):
            propose_plan(client, "claude-sonnet-4-6", table)
