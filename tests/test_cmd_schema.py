"""The committed cMD benchmark schema carries the fan-out annotations the benchmark relies on.

Guards against an accidental regeneration of ``cmd.clean.linkml.yaml`` (e.g. from a changed
registry source or an edited ``make_clean_schema.py``) silently changing propagation.
"""
from collections import Counter
from pathlib import Path

from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.sample_rules import fan_out_fields_to_samples
from metaextractor.schema_loader import load_schema_file

SCHEMA = Path(__file__).resolve().parents[1] / "benchmarks" / "cmd_sonnet5" / "cmd.clean.linkml.yaml"


def test_scope_and_propagation_annotations():
    fields = load_schema_file(SCHEMA).fields
    assert len(fields) == 71
    assert Counter(f.scope for f in fields) == {"sample": 55, "study": 9, None: 7}
    by_name = {f.name: f for f in fields}
    assert by_name["uncurated_metadata"].scope == "sample"
    assert sorted(f.name for f in fields if f.propagate_study_value) == [
        "antibiotics_current_use", "body_site", "disease"]
    assert {f.name: f.unit_of for f in fields if f.unit_of} == {"age_unit": "age"}
    assert sorted(f.name for f in fields if f.scope is None) == [
        "age_unit", "ancestry", "ancestry_details", "country", "lifestyle", "location", "westernized"]


def test_study_level_uncurated_metadata_is_not_propagated():
    schema = load_schema_file(SCHEMA)
    fr = FieldResult(value="Student cohort; travel to India", extraction_type="directly_stated",
                     confidence="high", evidence_quote="q", section="Methods")
    r = ExtractionResult(granularity="sample_level", fields={"uncurated_metadata": fr},
                         samples=[{"sample_id": "s1"}, {"sample_id": "s2"}])
    counts = fan_out_fields_to_samples(r, schema)
    assert all("uncurated_metadata" not in s for s in r.samples)
    assert counts["study_fanout"] == 0
