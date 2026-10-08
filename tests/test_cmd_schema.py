"""The committed cMD benchmark schema carries the fan-out annotations the benchmark relies on.

Guards against an accidental regeneration of ``cmd.clean.linkml.yaml`` (e.g. from a changed
registry source or an edited ``make_clean_schema.py``) silently changing propagation.

The annotations now originate in the registry's ``cmd_schema.csv`` (``scope``,
``propagate.study.value``, ``unit.of``) rather than in ``make_clean_schema.py``, so this
file pins the values that survive that round trip.
"""
from collections import Counter
from pathlib import Path

from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.sample_rules import fan_out_fields_to_samples
from metaextractor.schema_loader import load_schema_file

SCHEMA = (Path(__file__).resolve().parents[1]
          / "benchmarks" / "cmd_sonnet5" / "cmd.clean.linkml.yaml")


def test_scope_and_propagation_annotations():
    fields = load_schema_file(SCHEMA).fields
    assert len(fields) == 71
    assert Counter(f.scope for f in fields) == {"sample": 62, "study": 9}
    by_name = {f.name: f for f in fields}
    assert by_name["uncurated_metadata"].scope == "sample"
    # The four cohort attributes joined the allowlist once the heterogeneity sentinel
    # could block a "Mixed" / "Multiple countries" cohort value on its own.
    assert sorted(f.name for f in fields if f.propagate_study_value) == [
        "ancestry", "antibiotics_current_use", "body_site", "country", "disease",
        "lifestyle", "location", "westernized"]
    assert {f.name: f.unit_of for f in fields if f.unit_of} == {
        "age_unit": "age",
        "antibiotics_exclusion_period_unit": "antibiotics_exclusion_period",
        "biomarker_unit": "biomarker_value",
        "disease_response_os_unit": "disease_response_os"}
    # Every slot is scoped by the schema table; none is left for the loader to infer.
    assert [f.name for f in fields if f.scope is None] == []


def test_homogeneous_cohort_value_reaches_every_sample():
    """A single cohort-wide value on an allowlisted slot propagates (the common case)."""
    schema = load_schema_file(SCHEMA)
    fr = FieldResult(value="No", extraction_type="directly_stated", confidence="high",
                     evidence_quote="semi-isolated Yanomami from Brazil", section="Methods")
    r = ExtractionResult(granularity="sample_level", fields={"westernized": fr},
                         samples=[{"sample_id": "s1"}, {"sample_id": "s2"}])
    counts = fan_out_fields_to_samples(r, schema)
    assert [s["westernized"] for s in r.samples] == ["No", "No"]
    assert counts["study_fanout"] == 2


def test_heterogeneous_cohort_value_is_not_propagated():
    """A cohort-variety value describes the study, not its samples, so it is blocked.

    ``"Multiple countries"`` is a single, non-aggregate, non-multi-valued string, so the
    older gates let it through; only the heterogeneity sentinel stops it.
    """
    schema = load_schema_file(SCHEMA)
    for value in ("Mixed", "Multiple countries"):
        fr = FieldResult(value=value, extraction_type="directly_stated", confidence="high",
                         evidence_quote="the samples cover 31 countries", section="Results")
        r = ExtractionResult(granularity="sample_level", fields={"country": fr},
                             samples=[{"sample_id": "s1"}, {"sample_id": "s2"}])
        counts = fan_out_fields_to_samples(r, schema)
        assert all("country" not in s for s in r.samples), value
        assert counts["study_fanout"] == 0
        assert counts["blocked_heterogeneous"] == 2


def test_study_level_uncurated_metadata_is_not_propagated():
    schema = load_schema_file(SCHEMA)
    fr = FieldResult(value="Student cohort; travel to India", extraction_type="directly_stated",
                     confidence="high", evidence_quote="q", section="Methods")
    r = ExtractionResult(granularity="sample_level", fields={"uncurated_metadata": fr},
                         samples=[{"sample_id": "s1"}, {"sample_id": "s2"}])
    counts = fan_out_fields_to_samples(r, schema)
    assert all("uncurated_metadata" not in s for s in r.samples)
    assert counts["study_fanout"] == 0
