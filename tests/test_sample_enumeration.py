"""Sample enumeration: the deterministic table path must anchor the emitted
sample rows on the most *schema-relevant* table, not on whichever table happens
to come first in file order.

Regression for the meta-analysis failure mode: a paper's supplement lists both
the study's own samples (small, high schema relevance) and a large public-repo
dump (thousands of rows, lower relevance) — both keyed by a sample id. Before the
fix the join anchored on the first key-holding table (the 9k-row dump); now it
anchors on the higher-relevance study table.
"""
import pytest
from metaextractor.extractor import MetaExtractor
from metaextractor.schema import Schema
from metaextractor.supplementary import Table


class _NoCallClient:
    """Forces the propose_plan LLM path to fail -> deterministic row-0 fallback."""
    class messages:
        @staticmethod
        def create(*args, **kwargs):
            raise RuntimeError("no LLM in this test")


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
        {"name": "body_site", "description": "body site", "type": "enum",
         "allowed_values": ["feces", "oral"]},
        {"name": "country", "description": "country of origin", "type": "string"},
    ])


def test_join_anchors_on_most_relevant_table():
    # Low-relevance, LARGE public dump: sample_id (key-like) + sex only.
    public_dump = _table(
        "public_metagenomes.tsv",
        [["sample_id", "sex"]]
        + [[f"PUB{i:04d}", "male" if i % 2 else "female"] for i in range(1, 26)],  # 25 rows
    )
    # High-relevance, SMALL study table: richer per-sample content — sample_id
    # (key-like, >=4 rows) + TWO enum matches (sex, body_site). Enum overlap is
    # the dominant relevance signal, so this outscores the bare dump.
    study_meta = _table(
        "study_samples.tsv",
        [["sample_id", "sex", "body_site"],
         ["S1", "male", "feces"],
         ["S2", "female", "feces"],
         ["S3", "male", "oral"],
         ["S4", "female", "oral"],
         ["S5", "male", "feces"]],  # 5 rows
    )

    ex = MetaExtractor(client=_NoCallClient())
    # Pass the big dump FIRST — pre-fix that made it the join primary (25 rows).
    samples, warnings, selections = ex._build_samples_from_tables(
        [public_dump, study_meta], _schema()
    )

    # Both tables are selected (neither is a matrix; both clear the gate)...
    sel = {s.name: s for s in selections}
    assert sel["study_samples.tsv"].selected
    assert sel["study_samples.tsv"].score > sel["public_metagenomes.tsv"].score

    # ...but the emitted samples come from the higher-relevance study table,
    # not the 25-row public dump that was passed first.
    assert len(samples) == 5
    assert {s["sample_id"] for s in samples} == {"S1", "S2", "S3", "S4", "S5"}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
