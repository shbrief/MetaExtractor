"""normalize_age_bounds: opt-in, schema-gated, unit-aware per-subject age bounds."""
from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.sample_rules import AgeBoundRules, normalize_age_bounds
from metaextractor.schema import Field, Schema

RULES = AgeBoundRules(
    age_fields={"age": "age_unit", "age_years": None},
    group_bounds={"Adult": (18, 65), "Elderly": (65, None), "Infant": (0, 2)},
)
SCHEMA = Schema(fields=[Field(name=n, description=n, type="string")
                        for n in ("age", "age_unit", "age_years", "age_group",
                                  "age_min", "age_max")])


def _fr(value):
    return FieldResult(value=value, extraction_type="directly_stated", confidence="high",
                       evidence_quote="", section="")


def _result(samples=None, fields=None, prov=None):
    return ExtractionResult(granularity="sample_level", fields=fields or {},
                            samples=samples or [], sample_provenance=prov or [])


def test_off_unless_configured():
    r = _result(samples=[{"age": "41"}])
    assert normalize_age_bounds(r, None, SCHEMA) == 0
    assert "age_min" not in r.samples[0]


def test_schema_gate_never_adds_undeclared_fields():
    schema = Schema(fields=[Field(name="age", description="age", type="string")])
    r = _result(samples=[{"age": "41"}])
    assert normalize_age_bounds(r, RULES, schema) == 0
    assert set(r.samples[0]) == {"age"}


def test_specific_age_sets_both_bounds_even_over_existing_values():
    r = _result(samples=[{"age": "41", "age_min": "18", "age_max": "65"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 2
    assert (r.samples[0]["age_min"], r.samples[0]["age_max"]) == ("41", "41")
    assert r.sample_provenance[0]["age_min"] == "age_rule:specific_age"


def test_consistent_bounds_are_a_noop():
    r = _result(samples=[{"age": "41", "age_min": "41", "age_max": "41.0"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 0


def test_months_are_converted_to_years():
    r = _result(samples=[{"age": "18", "age_unit": "months"}])
    normalize_age_bounds(r, RULES, SCHEMA)
    assert (r.samples[0]["age_min"], r.samples[0]["age_max"]) == ("1.5", "1.5")


def test_unknown_unit_leaves_row_untouched():
    r = _result(samples=[{"age": "18", "age_unit": "fortnights", "age_group": "Adult"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 0
    assert "age_min" not in r.samples[0]


def test_propagated_study_age_is_not_an_individual_age():
    r = _result(samples=[{"age": "45", "age_group": "Adult"}],
                prov=[{"age": "study_fanout", "age_group": "llm_sample"}])
    normalize_age_bounds(r, RULES, SCHEMA)
    assert (r.samples[0]["age_min"], r.samples[0]["age_max"]) == ("18", "65")
    assert r.sample_provenance[0]["age_max"] == "age_rule:age_group:Adult"


def test_reported_range_is_kept_over_group_definition():
    r = _result(samples=[{"age_group": "Adult", "age_min": "23"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 0
    assert r.samples[0]["age_min"] == "23" and "age_max" not in r.samples[0]


def test_group_with_open_upper_bound_leaves_max_unset():
    r = _result(samples=[{"age_group": "Elderly"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 1
    assert r.samples[0]["age_min"] == "65" and "age_max" not in r.samples[0]


def test_unconfigured_group_is_left_alone():
    r = _result(samples=[{"age_group": "Newborn"}])
    assert normalize_age_bounds(r, RULES, SCHEMA) == 0


def test_study_level_age_is_never_turned_into_bounds():
    r = _result(fields={"age": _fr("45"), "age_min": _fr("not_reported"),
                        "age_max": _fr("not_reported")})
    assert normalize_age_bounds(r, RULES, SCHEMA) == 0
    assert r.fields["age_min"].value == "not_reported"


def test_study_level_group_rule_only_fills_emitted_fields():
    r = _result(fields={"age_group": _fr("Adult"), "age_min": _fr("not_reported"),
                        "age_max": _fr("not_reported")})
    assert normalize_age_bounds(r, RULES, SCHEMA) == 2
    assert r.fields["age_min"].value == "18" and r.fields["age_min"].extraction_type == "derived"
    r2 = _result(fields={"age_group": _fr("Adult")})
    assert normalize_age_bounds(r2, RULES, SCHEMA) == 0
    assert "age_min" not in r2.fields


def test_cmd_benchmark_config_loads():
    from pathlib import Path
    rules = AgeBoundRules.from_json(
        Path(__file__).resolve().parents[1] / "benchmarks/cmd_sonnet5/age_rules_cmd.json")
    assert rules.group_bounds["Adult"] == (18, 65)
    assert rules.age_fields == {"age": "age_unit", "age_years": None}
    assert "curation convention" in rules.justification
