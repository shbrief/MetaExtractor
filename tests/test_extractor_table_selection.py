"""Offline test: deterministic table-selection provenance on ExtractionResult.

Both input tables fail the relevance gate (one matrix, one irrelevant), so
the LLM ``propose_plan`` path is never reached — the client asserts if called.
"""
import pytest
from metaextractor.extractor import MetaExtractor
from metaextractor.schema import Schema
from metaextractor.supplementary import Table


class _NoCallClient:
    class messages:
        @staticmethod
        def create(*args, **kwargs):
            raise AssertionError("LLM must not be called when no table passes the gate")


def _table(name: str, raw_rows: list[list[str]]) -> Table:
    header = raw_rows[0]
    columns = list(header)
    rows = [{columns[i]: (row[i] if i < len(row) else "") for i in range(len(columns))}
            for row in raw_rows[1:]]
    return Table(name=name, source="test", columns=columns, rows=rows, raw_rows=raw_rows)


def _schema() -> Schema:
    return Schema.from_dict([
        {"name": "sample_id", "description": "unique sample identifier", "type": "string"},
        {"name": "sex", "description": "biological sex", "type": "enum",
         "allowed_values": ["male", "female"]},
    ])


def test_selection_provenance_recorded_offline():
    matrix = _table("taxa.tsv", [["feature", "s1", "s2", "s3"]] + [
        [f"k__Bacteria|p__F|c__c|o__o|f__f|g__g|t__sp{i}",
         str(0.1 * i), str(0.2 * i), str(0.05 * i)]
        for i in range(1, 12)
    ])
    junk = _table("summary.csv", [
        ["statistic", "value"],
        ["total subjects", "42"],
        ["mean read depth", "3.1e7"],
    ])

    ex = MetaExtractor(client=_NoCallClient())
    samples, warnings, selections = ex._build_samples_from_tables([matrix, junk], _schema())

    assert samples == []
    by_name = {s.name: s for s in selections}
    assert set(by_name) == {"taxa.tsv", "summary.csv"}
    assert all(not s.selected for s in selections)

    assert by_name["taxa.tsv"].is_matrix
    assert by_name["taxa.tsv"].score == 0.0
    assert not by_name["summary.csv"].is_matrix        # low-relevance, not a matrix
    assert by_name["summary.csv"].score < 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
