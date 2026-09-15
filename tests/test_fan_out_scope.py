"""fan_out_fields_to_samples propagates only values known to apply to a sample."""
from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.sample_rules import fan_out_fields_to_samples, is_aggregate, is_multi_valued
from metaextractor.schema import Field, Schema


def _fr(value, by_subgroup=None):
    return FieldResult(value=value, by_subgroup=by_subgroup, extraction_type="directly_stated",
                       confidence="high", evidence_quote="q", section="s")


def _schema(**scopes):
    return Schema(fields=[Field(name=n, description=n, type="string", scope=sc)
                          for n, sc in scopes.items()])


def _result(fields, samples, subgroups=None):
    return ExtractionResult(granularity="sample_level", fields=fields, samples=samples,
                            subgroups=subgroups or [])


def test_cohort_disease_list_is_not_copied_to_samples():
    r = _result({"disease": _fr("Healthy; Hypertension; Pre-hypertension")},
                [{"sample_id": "s1"}, {"sample_id": "s2"}])
    counts = fan_out_fields_to_samples(r, _schema(disease="sample"))
    assert all("disease" not in s for s in r.samples)
    assert counts["blocked_multi_valued"] == 2


def test_aggregate_age_is_not_copied():
    r = _result({"age": _fr("52.3 ± 8.1")}, [{"sample_id": "s1"}])
    counts = fan_out_fields_to_samples(r, _schema(age="sample"))
    assert "age" not in r.samples[0] and counts["blocked_aggregate"] == 1


def test_study_scoped_value_is_propagated_with_provenance():
    r = _result({"sequencing_platform": _fr("Illumina HiSeq 2000; Illumina HiSeq 2500")},
                [{"sample_id": "s1"}])
    fan_out_fields_to_samples(r, _schema(sequencing_platform="study"))
    assert r.samples[0]["sequencing_platform"] == "Illumina HiSeq 2000; Illumina HiSeq 2500"
    assert r.sample_provenance[0]["sequencing_platform"] == "study_fanout"


def _propagating(**scopes):
    return Schema(fields=[Field(name=n, description=n, type="string", scope=sc,
                                propagate_study_value=True) for n, sc in scopes.items()])


def test_annotated_sample_scoped_value_needs_homogeneous_cohort():
    homogeneous = _result({"body_site": _fr("feces")}, [{"sample_id": "s1"}])
    fan_out_fields_to_samples(homogeneous, _propagating(body_site="sample"))
    assert homogeneous.samples[0]["body_site"] == "feces"
    assert homogeneous.sample_provenance[0]["body_site"] == "study_fanout"
    mixed = _result({"body_site": _fr("feces")}, [{"sample_id": "s1"}],
                    subgroups=["cases", "controls"])
    counts = fan_out_fields_to_samples(mixed, _propagating(body_site="sample"))
    assert "body_site" not in mixed.samples[0] and counts["blocked_sample_scope"] == 1


def test_sample_scoped_study_value_without_annotation_is_not_propagated():
    # out_v3 NayakRR_2021: a study-level "Methotrexate" with no subgroups was copied to
    # all 434 manifest records, although half the curated samples were untreated.
    r = _result({"treatment": _fr(["Methotrexate"]), "age_min": _fr("23"), "age_max": _fr("34")},
                [{"sample_id": "s1"}, {"sample_id": "s2"}])
    counts = fan_out_fields_to_samples(
        r, _schema(treatment="sample", age_min="sample", age_max="sample"))
    assert all(k not in s for s in r.samples for k in ("treatment", "age_min", "age_max"))
    assert counts["blocked_sample_scope_no_propagation"] == 6 and counts["study_fanout"] == 0


def test_unique_subgroup_match_propagates_subgroup_value():
    r = _result({"disease": _fr("RA; Healthy", by_subgroup={"cases": "RA", "controls": "Healthy"})},
                [{"sample_id": "s1", "group": "Controls"}, {"sample_id": "s2", "group": "case"}],
                subgroups=["cases", "controls"])
    fan_out_fields_to_samples(r, _schema(disease="sample"))
    assert [s.get("disease") for s in r.samples] == ["Healthy", "RA"]
    assert r.sample_provenance[0]["disease"] == "subgroup_fanout:controls"


def test_ambiguous_subgroup_gets_no_subgroup_value():
    r = _result({"disease": _fr("RA; Healthy", by_subgroup={"cases": "RA", "controls": "Healthy"})},
                [{"sample_id": "s1", "a": "cases", "b": "controls"}],
                subgroups=["cases", "controls"])
    counts = fan_out_fields_to_samples(r, _schema(disease="sample"))
    assert "disease" not in r.samples[0]
    assert counts["ambiguous_subgroup_samples"] == 1


def test_existing_sample_values_are_never_overwritten():
    r = _result({"country": _fr("Italy")}, [{"sample_id": "s1", "country": "Spain"}])
    fan_out_fields_to_samples(r, _schema(country=None))
    assert r.samples[0]["country"] == "Spain"


def test_value_classifiers():
    assert is_multi_valued(["a", "b"]) and is_multi_valued("a; b") and not is_multi_valued("a")
    assert not is_multi_valued("Diabetes Mellitus, Type 2")
    assert is_aggregate("mean 45") and is_aggregate("23-34") and is_aggregate("n = 40")
    assert not is_aggregate("COVID-19") and not is_aggregate("Type 2 Diabetes Mellitus")
