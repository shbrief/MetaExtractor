"""Table path: ENA manifests use a fixed column map (no plan); feature and figure
source-data tables are not used as sample tables.

Offline: the client raises if any table plan is requested where none should be.
"""
import pytest

from metaextractor.extractor import MetaExtractor
from metaextractor.model import MockModel
from metaextractor.schema import Schema
from metaextractor.supplementary import Table
from metaextractor.table_select import per_sample_identifier_check

ENA_COLUMNS = ["run_accession", "sample_accession", "experiment_accession", "study_accession",
               "instrument_platform", "instrument_model", "library_source", "library_strategy",
               "library_layout", "scientific_name", "tax_id", "sample_title", "sample_alias",
               "host", "host_sex", "host_body_site", "country", "collection_date", "first_public"]


def _table(name, columns, rows, source="test"):
    raw = [columns] + [[r.get(c, "") for c in columns] for r in rows]
    return Table(name=name, source=source, columns=list(columns), rows=rows, raw_rows=raw)


def _schema():
    return Schema.from_dict([
        {"name": n, "description": d, "type": "string"} for n, d in [
            ("sample_id", "unique sample identifier"), ("ncbi_accession", "run accession"),
            ("country", "country of sampling"), ("body_site", "anatomical body site"),
            ("sex", "biological sex"), ("sequencing_platform", "sequencer model"),
            ("host_species", "host organism"), ("disease", "disease state")]
    ])


def _ena_row(i):
    # Out_v3 Bengtsson-PalmeJ_2015 shape: empty host_body_site, a filled country.
    return {"run_accession": f"ERR63635{i}", "sample_accession": f"SAMEA278445{i}",
            "instrument_platform": "ILLUMINA", "instrument_model": "Illumina HiSeq 2000",
            "scientific_name": "human gut metagenome", "sample_title": "Student fecal sample",
            "sample_alias": f"TRAVELRES{i}", "host": "Homo sapiens", "host_sex": "",
            "host_body_site": "", "country": "Sweden", "collection_date": "2013-05-23"}


def test_ena_manifest_uses_fixed_map_without_plan():
    manifest = _table("PRJEB7369_ena_manifest.tsv", ENA_COLUMNS,
                      [_ena_row(i) for i in range(1, 6)], source="ena")
    llm = MockModel()
    ex = MetaExtractor(llm=llm)
    samples, warnings, _ = ex._build_samples_from_tables([manifest], _schema())
    assert len(samples) == 5
    s = samples[0]
    assert s["ncbi_accession"] == "ERR636351" and s["sample_id"] == "TRAVELRES1"
    assert s["country"] == "Sweden" and s["sequencing_platform"] == "Illumina HiSeq 2000"
    assert s["host_species"] == "Homo sapiens"
    assert s["body_site"] == ""          # from the empty host_body_site; never from country
    assert ex.last_table_sources["country"] == "manifest:PRJEB7369_ena_manifest.tsv:country"
    assert (ex.last_table_sources["body_site"]
            == "manifest:PRJEB7369_ena_manifest.tsv:host_body_site")
    assert any("ENA run manifest read as is" in w for w in warnings)
    # The manifest path must bypass the plan call entirely. Asserted after the
    # fact rather than by raising inside the call: propose_plan catches model
    # errors and falls back, so a raising double could not enforce this.
    llm.assert_not_called()


def test_figure_source_data_is_skipped_before_any_plan():
    t = _table("41564_2023_1355_MOESM4_ESM.xlsx::Source_data_for_Suppl_Figure_2b",
               ["sample_id", "country"],
               [{"sample_id": f"S{i}", "country": "China"} for i in range(9)])
    llm = MockModel()
    ex = MetaExtractor(llm=llm)
    samples, _, selections = ex._build_samples_from_tables([t], _schema())
    assert samples == []
    assert not selections[0].selected
    assert selections[0].reasons == ["figure source data (table name)"]
    llm.assert_not_called()


@pytest.mark.parametrize("rows, ok", [
    # LiJ_2017 Table S10 shape: gene-group ids under a sample-like column, 70% distinct
    ([{"sample_id": f"CAG-{i % 7}"} for i in range(10)], False),
    # FanY_2023 figure panel: six donors repeated over 510 rows
    ([{"sample_id": f"D{i % 6}"} for i in range(60)], False),
    # per-sample table
    ([{"sample_id": f"S{i}"} for i in range(10)], True),
    # sample names repeat across runs, but run accessions are unique (manifest)
    ([{"sample_id": f"S{i % 5}", "ncbi_accession": f"SRR{i}"} for i in range(10)], True),
    # no per-sample key at all: left to the join
    ([{"subject_id": "P1"} for _ in range(10)], True),
])
def test_per_sample_identifier_check(rows, ok):
    assert per_sample_identifier_check(rows)[0] is ok


def test_feature_table_is_not_used_as_sample_table(monkeypatch):
    feature = _table("Table S10", ["sample_id", "disease"],
                     [{"sample_id": f"CAG-{i % 7}", "disease": "Hypertension"} for i in range(20)])
    llm = MockModel()
    ex = MetaExtractor(llm=llm)
    monkeypatch.setattr(ex, "_apply_table_plan", lambda t, reason, warnings: t)
    samples, warnings, selections = ex._build_samples_from_tables([feature], _schema())
    assert samples == []
    assert not selections[0].selected
    assert "identifier not per-sample" in selections[0].reasons[-1]
    llm.assert_not_called()


def test_unmapped_columns_keep_header_text_and_source():
    # A column the lexical mapping does not recognise stays in the record under its header
    # text, and its source table and column are recorded, so the saved table can be mapped
    # downstream (e.g. by MetaHarmonizer SchemaMapper).
    t = _table("S2.xlsx::Table S2", ["Sample ID", "Treatment status", "Insert size (bp)"],
               [{"Sample ID": f"S{i}", "Treatment status": "MTX" if i % 2 else "naive",
                 "Insert size (bp)": "300"} for i in range(6)])
    llm = MockModel()
    ex = MetaExtractor(llm=llm)
    samples, _, _ = ex._build_samples_from_tables([t], _schema())
    assert samples[1] == {"sample_id": "S1", "Treatment status": "MTX", "Insert size (bp)": "300"}
    assert ex.last_table_sources == {
        "sample_id": "table:S2.xlsx::Table S2:Sample ID",
        "Treatment status": "table:S2.xlsx::Table S2:Treatment status",
        "Insert size (bp)": "table:S2.xlsx::Table S2:Insert size (bp)"}
