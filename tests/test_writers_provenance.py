"""Sample-level CSV honours include_provenance with per-cell sources."""
import csv

from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.writers import to_csv


def _result():
    return ExtractionResult(
        paper_id="123", granularity="sample_level",
        fields={"country": FieldResult(value="Italy", extraction_type="directly_stated",
                                       confidence="high", evidence_quote="in Italy",
                                       section="Methods")},
        samples=[{"sample_id": "S1", "country": "Italy"}],
        sample_provenance=[{"sample_id": "table:t.tsv:ID", "country": "study_fanout"}],
    )


def test_sample_level_csv_includes_sources_and_study_evidence(tmp_path):
    out = tmp_path / "r.csv"
    to_csv(_result(), out, include_provenance=True)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["country__source"] == "study_fanout"
    assert rows[0]["country__evidence"] == "in Italy"
    assert rows[0]["sample_id__source"] == "table:t.tsv:ID"
    assert "sample_id__evidence" not in rows[0]


def test_sample_level_csv_without_provenance_is_unchanged(tmp_path):
    out = tmp_path / "r.csv"
    to_csv(_result(), out)
    header = next(csv.reader(out.open()))
    assert header == ["paper_id", "country", "sample_id"]
