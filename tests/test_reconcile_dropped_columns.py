"""The plan path drops any raw column the LLM doesn't keep as an id_column.

For an SRA/ENA run manifest, the sequencing model lives in ``instrument_model``
(alias → ``sequencing_platform``). If the plan omits it, ``execute_plan`` strips
it before ``map_columns`` can alias it. ``_reconcile_dropped_schema_columns``
re-attaches such columns for the safe flat-table case; these tests prove the
column survives end to end on the deterministic tables path.
"""
import json

import pytest
from metaextractor.extractor import (
    MetaExtractor,
    _reconcile_dropped_schema_columns,
)
from metaextractor.schema import Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import IdColumn, TablePlan, execute_plan


def _sra_table() -> Table:
    raw = [
        ["Run", "instrument_platform", "instrument_model", "LibrarySource"],
        ["ERR001", "ILLUMINA", "Illumina HiSeq 2000", "METAGENOMIC"],
        ["ERR002", "ILLUMINA", "Illumina HiSeq 2000", "METAGENOMIC"],
        ["ERR003", "ILLUMINA", "Illumina HiSeq 2500", "METAGENOMIC"],
    ]
    header = raw[0]
    rows = [{header[i]: r[i] for i in range(len(header))} for r in raw[1:]]
    return Table(name="sra_meta.tsv", source="test", columns=list(header),
                 rows=rows, raw_rows=raw)


def _schema() -> Schema:
    return Schema.from_dict([
        {"name": "ncbi_accession", "description": "SRA/ENA run accession", "type": "string"},
        {"name": "sequencing_platform", "description": "sequencing instrument model", "type": "string"},
    ])


# Plan the LLM would emit if it kept only the run id and dropped the instrument
# columns — the failure mode the reconciliation exists to repair.
def _plan_drops_instrument() -> TablePlan:
    return TablePlan(
        header_rows=[0],
        data_starts_at=1,
        id_columns=[IdColumn(col=0, name="ncbi_accession")],
        melt=None,
        drop_columns=[1, 2, 3],
        notes="run id only",
    )


class _StubPlanClient:
    """Returns a fixed TablePlan JSON from messages.create."""

    def __init__(self, plan: TablePlan):
        self._payload = plan.model_dump()
        self.messages = self

    def create(self, *args, **kwargs):
        payload = self._payload

        class _Block:
            type = "text"
            text = json.dumps(payload)

        class _Usage:
            input_tokens = 10
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0
            output_tokens = 5

        class _Msg:
            content = [_Block()]
            usage = _Usage()

        return _Msg()


def test_helper_reattaches_dropped_alias_column():
    t = _sra_table()
    plan = _plan_drops_instrument()
    transformed = execute_plan(t, plan)
    # Plan stripped instrument_model.
    assert transformed.columns == ["ncbi_accession"]

    warnings: list[str] = []
    _reconcile_dropped_schema_columns(
        t, plan, transformed, ["ncbi_accession", "sequencing_platform"], warnings
    )

    # Re-attached under its original header, values aligned by position.
    assert "instrument_model" in transformed.columns
    assert [r["instrument_model"] for r in transformed.rows] == [
        "Illumina HiSeq 2000", "Illumina HiSeq 2000", "Illumina HiSeq 2500",
    ]
    # instrument_platform (deliberately un-aliased) is NOT re-attached.
    assert "instrument_platform" not in transformed.columns
    assert any("re-attached" in w for w in warnings)


def test_helper_noop_when_field_already_present():
    t = _sra_table()
    plan = TablePlan(
        header_rows=[0], data_starts_at=1,
        id_columns=[IdColumn(col=0, name="ncbi_accession"),
                    IdColumn(col=2, name="sequencing_platform")],
        melt=None,
    )
    transformed = execute_plan(t, plan)
    before = list(transformed.columns)
    warnings: list[str] = []
    _reconcile_dropped_schema_columns(
        t, plan, transformed, ["ncbi_accession", "sequencing_platform"], warnings
    )
    assert transformed.columns == before
    assert warnings == []


def test_helper_skips_melted_plan():
    t = _sra_table()
    plan = _plan_drops_instrument()
    transformed = execute_plan(t, plan)
    # Pretend the plan melted — reconciliation must not touch row-aligned data.
    plan.melt = object.__new__(type("M", (), {}))  # non-None sentinel
    warnings: list[str] = []
    _reconcile_dropped_schema_columns(
        t, plan, transformed, ["ncbi_accession", "sequencing_platform"], warnings
    )
    assert "instrument_model" not in transformed.columns


def test_end_to_end_sequencing_platform_recovered_on_tables_path():
    ex = MetaExtractor(client=_StubPlanClient(_plan_drops_instrument()),
                       min_table_relevance=0.0)
    samples, warnings, selections = ex._build_samples_from_tables(
        [_sra_table()], _schema()
    )
    assert len(samples) == 3
    # Alias fired *after* reconciliation re-attached the dropped column.
    assert all(s.get("sequencing_platform") for s in samples)
    assert samples[0]["sequencing_platform"] == "Illumina HiSeq 2000"
    assert samples[0]["ncbi_accession"] == "ERR001"
