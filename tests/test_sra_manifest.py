"""Tests for metaextractor.sra_manifest — authoritative SRA/ENA manifest fetch.

The resolver must pick the study's *own* project (the one in a data-availability
context) and must NOT latch onto a merely-referenced project — the failure mode
that produced wrong `_sra_meta.tsv` files in the R curation pipeline.
"""
from metaextractor.column_mapper import apply_mapping, map_columns
from metaextractor.sra_manifest import (
    _parse_manifest_tsv,
    extract_dataset_accessions,
    fetch_run_manifest,
    manifest_for_paper,
    resolve_projects,
)

_PAD = " filler text. " * 40  # >250 chars to isolate accession context windows


def _availability(acc: str) -> str:
    return (
        f"Data availability. Raw sequencing reads have been deposited in the "
        f"European Nucleotide Archive under accession {acc}."
    )


# --------------------------------------------------------------------------- #
# Accession extraction + context scoring
# --------------------------------------------------------------------------- #

class TestExtraction:
    def test_finds_bioproject_and_run(self):
        text = f"Methods.{_PAD}{_availability('PRJEB7369')} Runs ERR636354–ERR636400."
        accs = {a.value: a for a in extract_dataset_accessions(text)}
        assert "PRJEB7369" in accs and accs["PRJEB7369"].kind == "bioproject"
        assert "ERR636354" in accs and accs["ERR636354"].kind == "run"
        assert accs["PRJEB7369"].context_score > 0  # deposit/ENA/accession nearby

    def test_referenced_project_has_no_context(self):
        text = (
            f"We compared our cohort against a previously published cohort "
            f"(PRJNA000001).{_PAD}{_availability('PRJEB7369')}"
        )
        accs = {a.value: a for a in extract_dataset_accessions(text)}
        assert accs["PRJNA000001"].context_score == 0
        assert accs["PRJEB7369"].context_score > 0


# --------------------------------------------------------------------------- #
# Project resolution — the anti-wrong-project logic
# --------------------------------------------------------------------------- #

class TestResolveProjects:
    def test_prefers_availability_context_over_referenced(self):
        text = (
            f"We compared against a public dataset (PRJNA000001).{_PAD}"
            f"{_availability('PRJEB7369')}"
        )
        projects, warns = resolve_projects(
            extract_dataset_accessions(text), http_get=lambda u: b""
        )
        assert projects == ["PRJEB7369"]  # referenced PRJNA000001 excluded

    def test_single_unambiguous_project_used_without_context(self):
        text = f"Sequences are under PRJEB7369.{_PAD}"
        # Strip the availability terms so context_score is 0 but it's the only one.
        text = text.replace("under", "labeled")
        projects, warns = resolve_projects(
            extract_dataset_accessions(text), http_get=lambda u: b""
        )
        assert projects == ["PRJEB7369"]

    def test_multiple_projects_no_context_refuses_to_guess(self):
        text = f"Compared PRJNA000001 and PRJNA000002.{_PAD} both public."
        projects, warns = resolve_projects(
            extract_dataset_accessions(text), http_get=lambda u: b""
        )
        assert projects == []
        assert warns and "not guessing" in warns[0]

    def test_resolves_run_accession_to_project_when_no_bioproject(self):
        text = _availability("ERR636354")  # a run in data-availability context

        def fake_get(url: str) -> bytes:
            assert "ERR636354" in url and "study_accession" in url
            return b"study_accession\nPRJEB7369\n"

        projects, warns = resolve_projects(
            extract_dataset_accessions(text), http_get=fake_get
        )
        assert projects == ["PRJEB7369"]


# --------------------------------------------------------------------------- #
# Manifest TSV parsing + field fallback
# --------------------------------------------------------------------------- #

_GOOD_TSV = (
    "run_accession\tinstrument_platform\tinstrument_model\tlibrary_source\n"
    "ERR636354\tILLUMINA\tIllumina HiSeq 2000\tMETAGENOMIC\n"
    "ERR636359\tILLUMINA\tIllumina HiSeq 2000\tMETAGENOMIC\n"
)


class TestFetchManifest:
    def test_parse_manifest_tsv(self):
        t = _parse_manifest_tsv("PRJEB7369", _GOOD_TSV)
        assert t is not None
        assert t.source == "ena"
        assert t.columns[0] == "run_accession"
        assert len(t.rows) == 2
        assert t.rows[0]["instrument_model"] == "Illumina HiSeq 2000"

    def test_falls_back_to_minimal_fields_on_ena_error(self):
        # First request (full fields) returns an ENA error page; retry with the
        # minimal field set returns a valid manifest.
        calls: list[str] = []

        def fake_get(url: str) -> bytes:
            calls.append(url)
            if "host_body_site" in url:  # only the full field list has this
                return b"Invalid value for field: host_body_site"
            return _GOOD_TSV.encode()

        t = fetch_run_manifest("PRJEB7369", http_get=fake_get)
        assert t is not None and len(t.rows) == 2
        assert len(calls) == 2  # full attempt, then minimal


# --------------------------------------------------------------------------- #
# End-to-end orchestration + downstream column mapping
# --------------------------------------------------------------------------- #

class TestManifestForPaper:
    def test_explicit_project_bypasses_resolution(self):
        def fake_get(url: str) -> bytes:
            assert "PRJEB7369" in url
            return _GOOD_TSV.encode()

        res = manifest_for_paper("no accessions here", explicit_project="PRJEB7369",
                                 http_get=fake_get)
        assert res.table is not None
        assert res.projects == ["PRJEB7369"]
        assert res.n_runs == 2
        assert res.source.startswith("ena:PRJEB7369")

    def test_returns_empty_when_nothing_resolvable(self):
        res = manifest_for_paper("a paper with no data accessions", http_get=lambda u: b"")
        assert res.table is None and res.projects == []

    def test_manifest_columns_map_to_schema_fields(self):
        # The whole point: the fetched manifest feeds the deterministic path and
        # its columns alias onto schema fields.
        res = manifest_for_paper("x", explicit_project="PRJEB7369",
                                 http_get=lambda u: _GOOD_TSV.encode())
        m = map_columns(res.table.columns, ["ncbi_accession", "sequencing_platform"])
        renamed = apply_mapping(res.table.rows, m)
        assert renamed[0]["ncbi_accession"] == "ERR636354"
        assert renamed[0]["sequencing_platform"] == "Illumina HiSeq 2000"
