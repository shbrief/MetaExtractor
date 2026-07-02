"""Tests for metaextractor.table_select — deterministic schema-relevance scoring."""
from metaextractor.schema import Schema
from metaextractor.supplementary import Table
from metaextractor.table_select import (
    is_measurement_matrix,
    rank_tables,
    score_table,
)


def _table(name: str, raw_rows: list[list[str]]) -> Table:
    if len(raw_rows) < 2:
        return Table(name=name, source="test", columns=[], rows=[], raw_rows=raw_rows)
    header = raw_rows[0]
    columns = list(header)
    rows = [{columns[i]: (row[i] if i < len(row) else "") for i in range(len(columns))}
            for row in raw_rows[1:]]
    return Table(name=name, source="test", columns=columns, rows=rows, raw_rows=raw_rows)


def _schema() -> Schema:
    return Schema.from_dict([
        {"name": "sample_id", "description": "unique sample identifier", "type": "string"},
        {"name": "age", "description": "subject age in years", "type": "number"},
        {"name": "sex", "description": "biological sex", "type": "enum",
         "allowed_values": ["male", "female"]},
        {"name": "body_site", "description": "anatomical sampling site", "type": "enum",
         "allowed_values": ["stool", "oral", "skin"]},
    ])


_SAMPLE_META = [
    ["sample_id", "age", "sex", "body_site"],
    ["S001", "30", "male", "stool"],
    ["S002", "25", "female", "oral"],
    ["S003", "45", "male", "skin"],
    ["S004", "51", "female", "stool"],
    ["S005", "38", "male", "oral"],
]


# ---------------------------------------------------------------------------
# score_table
# ---------------------------------------------------------------------------

class TestScoreTable:
    def test_sample_metadata_scores_high(self):
        rel = score_table(_table("st8", _SAMPLE_META), _schema())
        # A fully-matched per-sample table caps ~0.625 under the current
        # weights (shape saturates slowly; matched fields split name/enum) —
        # what matters is it clears the default 0.15 gate with wide margin.
        assert rel.score >= 0.6
        # every schema field is accounted for by a column
        assert set(rel.matched_fields) == {"sample_id", "age", "sex", "body_site"}

    def test_feature_matrix_scores_zero(self):
        raw = [["feature", "s1", "s2", "s3"]] + [
            [f"k__Bacteria|p__Firmicutes|c__c|o__o|f__f|g__g|t__sp{i}",
             str(0.1 * i), str(0.2 * i), str(0.05 * i)]
            for i in range(1, 12)
        ]
        rel = score_table(_table("taxa", raw), _schema())
        assert rel.score == 0.0
        assert rel.is_matrix

    def test_general_numeric_matrix_without_microbiome_signature(self):
        # A gene × samples matrix: non-taxonomy feature column, and sample
        # headers ("CtrlA"/"TreatD") are NOT ID-shaped, so the microbiome
        # fast-path (is_feature_matrix) misses it. The general numeric +
        # no-schema-match path must still reject it.
        raw = [["gene", "CtrlA", "CtrlB", "CtrlC", "TreatD", "TreatE"]] + [
            [f"BRCA{i}", str(i * 1.1), str(i * 0.9), str(i * 1.3), str(i * 2.0), str(i * 0.4)]
            for i in range(1, 9)
        ]
        rel = score_table(_table("expr", raw), _schema())
        assert rel.is_matrix
        assert rel.score == 0.0

    def test_numeric_sample_table_is_not_flagged_as_matrix(self):
        # Wide, fully-numeric, but a per-sample table: headers match schema
        # fields, so the "matches nothing" guard spares it.
        schema = Schema.from_dict([
            {"name": "sample_id", "description": "unique sample identifier", "type": "string"},
            {"name": "age", "description": "subject age in years", "type": "number"},
            {"name": "bmi", "description": "body mass index", "type": "number"},
            {"name": "glucose", "description": "fasting glucose", "type": "number"},
            {"name": "cholesterol", "description": "total cholesterol", "type": "number"},
        ])
        raw = [["sample_id", "age", "bmi", "glucose", "cholesterol", "insulin"]] + [
            [f"S{i:03d}", str(30 + i), str(22 + i), str(90 + i), str(180 + i), str(5 + i)]
            for i in range(1, 7)
        ]
        rel = score_table(_table("labs", raw), schema)
        assert not rel.is_matrix
        assert rel.score >= 0.15
        assert not is_measurement_matrix(_table("labs", raw), schema)

    def test_irrelevant_summary_table_scores_low(self):
        # A study-level summary block: no per-sample key, no schema columns.
        raw = [
            ["statistic", "value"],
            ["total subjects", "42"],
            ["mean read depth", "3.1e7"],
        ]
        rel = score_table(_table("summary", raw), _schema())
        assert rel.score < 0.15

    def test_enum_values_match_despite_mismatched_header(self):
        # Header says "Gender", not "sex" — content-based enum_match must catch it.
        raw = [
            ["subject", "Gender", "Age"],
            ["A1", "male", "30"],
            ["A2", "female", "25"],
            ["A3", "male", "45"],
            ["A4", "female", "39"],
        ]
        rel = score_table(_table("g", raw), _schema())
        assert rel.matched_fields.get("sex") == "Gender"
        assert rel.enum_match > 0.0

    def test_id_column_signal_rewards_unique_key(self):
        with_id = score_table(_table("with_id", _SAMPLE_META), _schema())
        # No column is near-unique → no key-like column at all.
        no_key = [
            ["sex", "body_site"],
            ["male", "stool"],
            ["female", "stool"],
            ["male", "oral"],
            ["female", "oral"],
            ["male", "stool"],
        ]
        without_id = score_table(_table("no_key", no_key), _schema())
        assert with_id.id_column == 1.0
        assert without_id.id_column == 0.0


# ---------------------------------------------------------------------------
# rank_tables
# ---------------------------------------------------------------------------

class TestRankTables:
    def test_orders_relevant_table_first(self):
        summary = _table("summary", [
            ["statistic", "value"],
            ["n", "42"],
            ["depth", "3.1e7"],
        ])
        meta = _table("st8", _SAMPLE_META)
        ranked = rank_tables([summary, meta], _schema())
        assert [r.name for r in ranked] == ["st8", "summary"]
        assert ranked[0].score > ranked[1].score
