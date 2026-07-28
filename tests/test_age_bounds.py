"""The cMD schema defines age_min/age_max as *per-subject* bounds, never a
cohort range: when a specific age is known they equal that age; when only
age_group is known they are the definition of that group (Adult -> 18/65).

``_normalize_age_bounds`` enforces this deterministically after extraction,
repairing the common LLM error of dropping a prose cohort range (e.g.
"Subjects were 23 to 34 years old") into age_min/age_max. These tests pin the
rule and the canonical group bounds.
"""
from metaextractor.extractor import AGE_GROUP_BOUNDS, _normalize_age_bounds
from metaextractor.output import ExtractionResult, FieldResult


def _fr(value, extraction_type="directly_stated"):
    return FieldResult(
        value=value,
        extraction_type=extraction_type,
        confidence="high",
        evidence_quote="",
        section="",
    )


def _result(fields, samples=None, granularity="sample_level"):
    return ExtractionResult(
        granularity=granularity,
        fields=fields,
        samples=samples or [],
    )


def test_group_only_range_is_replaced_by_group_definition():
    """The Bengtsson-PalmeJ_2015 failure mode: age not_reported, age_group
    Adult, but a cohort range (23-34) parked in age_min/age_max — at both the
    study level and (post fan-out) every sample."""
    r = _result(
        fields={
            "age": _fr("not_reported"),
            "age_group": _fr("Adult"),
            "age_min": _fr("23"),
            "age_max": _fr("34"),
        },
        samples=[{"age_group": "Adult", "age_min": "23", "age_max": "34"} for _ in range(3)],
    )
    n = _normalize_age_bounds(r)
    assert n == 2 + 2 * 3  # study-level pair + one pair per sample
    assert (r.fields["age_min"].value, r.fields["age_max"].value) == ("18", "65")
    assert r.fields["age_min"].extraction_type == "derived"
    assert all((s["age_min"], s["age_max"]) == ("18", "65") for s in r.samples)


def test_specific_age_fills_missing_bounds_only():
    """A per-subject age with no bounds -> age_min == age_max == age."""
    r = _result(fields={}, samples=[{"age": "41", "age_group": "Adult"}])
    n = _normalize_age_bounds(r)
    assert n == 2
    assert (r.samples[0]["age_min"], r.samples[0]["age_max"]) == ("41", "41")


def test_specific_age_does_not_clobber_present_bounds():
    r = _result(fields={}, samples=[{"age": "41", "age_min": "41", "age_max": "41"}])
    assert _normalize_age_bounds(r) == 0


def test_no_age_information_is_left_alone():
    r = _result(
        fields={"age": _fr("not_reported"), "age_group": _fr("not_reported")},
        samples=[],
        granularity="study_level",
    )
    assert _normalize_age_bounds(r) == 0


def test_already_correct_bounds_are_a_noop():
    r = _result(
        fields={
            "age": _fr("not_reported"),
            "age_group": _fr("Adult"),
            "age_min": _fr("18"),
            "age_max": _fr("65"),
        },
        samples=[],
        granularity="study_level",
    )
    assert _normalize_age_bounds(r) == 0


def test_all_known_groups_map_to_canonical_bounds():
    """Bounds match the dominant curated-gold group-definition values."""
    expected = {
        "Infant": ("0", "2"),
        "Child": ("2", "11"),
        "Adolescent": ("11", "18"),
        "Adult": ("18", "65"),
        "Elderly": ("65", "130"),
    }
    assert set(AGE_GROUP_BOUNDS) == set(expected)
    for group, (lo, hi) in expected.items():
        r = _result(
            fields={"age": _fr("not_reported"), "age_group": _fr(group)},
            samples=[{"age_group": group}],
            granularity="sample_level",
        )
        _normalize_age_bounds(r)
        assert (r.samples[0]["age_min"], r.samples[0]["age_max"]) == (lo, hi)


def test_newborn_is_left_untouched():
    """Newborn is defined in sub-year units and excluded from auto-fill."""
    r = _result(
        fields={"age": _fr("not_reported"), "age_group": _fr("Newborn")},
        samples=[{"age_group": "Newborn"}],
    )
    assert _normalize_age_bounds(r) == 0
    assert "age_min" not in r.samples[0]
