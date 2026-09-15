"""Run manifests are joined with each run's BioSample attributes (EBI BioSamples).

Offline: HTTP is a fake keyed by URL. Shapes follow out_v3 NayakRR_2021, whose curated
per-sample treatment ("MTX" at day 30 / "no" at day 0) is in the BioSample attributes
(treatment MTX / naive, day, patient id) but not in any ENA read_run field.
"""
import json

from metaextractor.extractor import MetaExtractor
from metaextractor.schema import Schema
from metaextractor.sra_manifest import (
    EBI_BIOSAMPLE,
    add_biosample_attributes,
    fetch_biosample_attributes,
    manifest_for_paper,
)

COLS = ["run_accession", "sample_accession", "instrument_model", "host", "host_sex",
        "host_body_site", "country", "collection_date"]
TSV = "\t".join(COLS) + "\n" + "\n".join([
    "SRR12455507\tSAMN15823301\tIllumina NovaSeq 6000\tHomo sapiens\t\t\tUSA\t2014-01",
    "SRR12455508\tSAMN15823301\tIllumina NovaSeq 6000\tHomo sapiens\t\t\tUSA\t2014-01",
    "SRR12455516\tSAMN15823264\tIllumina NovaSeq 6000\tHomo sapiens\t\t\tUSA\t2013-11",
    "SRR99999999\tSAMEA0000001\tIllumina NovaSeq 6000\tHomo sapiens\t\t\tUSA\t2013-11",
]) + "\n"


def _sample(acc, **chars):
    base = {"INSDC status": "live", "SRA accession": "SRS1", "External Id": acc,
            "NCBI submission package": "MIMARKS.survey.human-gut.5.0"}
    return {"accession": acc, "characteristics": {
        k: [{"text": v}] for k, v in {**base, **chars}.items()}}


RECORDS = {
    "SAMN15823301": _sample("SAMN15823301", treatment="MTX", day="30", **{
        "patient id": "347", "geo loc name": "USA", "host": "Homo sapiens",
        "mouse_id": "not applicable", "sex": "female"}),
    "SAMN15823264": _sample("SAMN15823264", treatment="naive", day="0", **{
        "patient id": "088", "geo loc name": "USA", "mouse_id": "missing: control sample",
        "sex": "male"}),
    # A service answering with another record must not be attached to this sample.
    "SAMEA0000001": _sample("SAMN00000001", treatment="MTX"),
}


def fake_get(url):
    for acc, rec in RECORDS.items():
        if url == EBI_BIOSAMPLE.format(acc=acc):
            return json.dumps(rec).encode()
    if "filereport" in url:
        return TSV.encode()
    raise AssertionError(f"unexpected URL {url}")


def test_attributes_filtered_and_accession_checked():
    attrs, warnings = fetch_biosample_attributes(list(RECORDS), fake_get)
    assert set(attrs) == {"SAMN15823301", "SAMN15823264"}
    a = attrs["SAMN15823301"]
    assert a["treatment"] == "MTX" and a["patient_id"] == "347" and a["geo_loc_name"] == "USA"
    assert a["mouse_id"] == "" and attrs["SAMN15823264"]["mouse_id"] == ""   # INSDC missing terms
    assert not any(k.startswith(("insdc", "sra_accession", "external_id", "ncbi_submission"))
                   for k in a)
    assert warnings == ["BioSample attributes not retrieved for 1 sample(s): accession mismatch."]


def test_manifest_gets_per_run_attribute_columns():
    res = manifest_for_paper("x", explicit_project="PRJNA656577", http_get=fake_get)
    t = res.table
    assert res.source == "ena:PRJNA656577 (4 runs) + BioSample attributes"
    assert "host_sex" not in t.columns and "host_body_site" not in t.columns  # empty everywhere
    assert "host" in t.columns and t.columns.count("host") == 1               # manifest's kept
    by_run = {r["run_accession"]: r for r in t.rows}
    assert by_run["SRR12455507"]["treatment"] == "MTX" and by_run["SRR12455508"]["day"] == "30"
    assert by_run["SRR12455516"]["treatment"] == "naive"
    assert by_run["SRR99999999"]["treatment"] == ""
    assert t.raw_rows[0] == t.columns and len(t.raw_rows) == 5


def test_attributes_disabled_leaves_manifest_unchanged():
    res = manifest_for_paper("x", explicit_project="PRJNA656577", http_get=fake_get,
                             biosample_attributes=False)
    assert res.table.columns == COLS and res.source == "ena:PRJNA656577 (4 runs)"


def test_table_path_fills_sample_level_fields_from_attributes():
    res = manifest_for_paper("x", explicit_project="PRJNA656577", http_get=fake_get)

    class NoCall:
        class messages:
            def create(*a, **k):
                raise AssertionError("no model call")

    schema = Schema.from_dict([{"name": n, "description": n, "type": "string"} for n in
                               ("ncbi_accession", "treatment", "sex", "country", "subject_id")])
    ex = MetaExtractor(client=NoCall())
    samples, _, _ = ex._build_samples_from_tables([res.table], schema)
    by_run = {s["ncbi_accession"]: s for s in samples}
    assert by_run["SRR12455507"]["treatment"] == "MTX" and by_run["SRR12455516"]["treatment"] == "naive"
    assert by_run["SRR12455507"]["sex"] == "female"          # filled BioSample sex, not empty host_sex
    assert ex.last_table_sources["treatment"].endswith(":treatment")


def test_no_sample_accession_column_is_a_no_op():
    from metaextractor.supplementary import Table
    t = Table(name="m", source="ena", columns=["run_accession"], rows=[{"run_accession": "R1"}],
              raw_rows=[["run_accession"], ["R1"]])
    assert add_biosample_attributes(t, fake_get) == (t, [])
