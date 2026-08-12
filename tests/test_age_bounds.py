"""age_min/age_max are per-subject bounds, filled deterministically after
extraction by precedence: a specific per-subject age wins; else a reported
numeric range is kept as-is (e.g. "Subjects were 23 to 34 years old" -> 23/34);
else the age_group definition (Adult -> 18/65) is the last-resort fallback.

``_normalize_age_bounds`` implements this. These tests pin the precedence and
the canonical group bounds.
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


def test_reported_range_is_kept_over_group_definition():
    """A reported cohort range (23-34) with age not_reported and age_group
    Adult is kept as-is — at the study level and (post fan-out) every sample —
    not overwritten with the group definition (18/65)."""
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
    assert n == 0
    assert (r.fields["age_min"].value, r.fields["age_max"].value) == ("23", "34")
    assert all((s["age_min"], s["age_max"]) == ("23", "34") for s in r.samples)


def test_partial_reported_range_blocks_group_fallback():
    """One numeric bound present marks a reported range; the group definition
    fallback does not fire and does not fill the other bound."""
    r = _result(fields={}, samples=[{"age_group": "Adult", "age_min": "23"}])
    assert _normalize_age_bounds(r) == 0
    assert r.samples[0]["age_min"] == "23"
    assert "age_max" not in r.samples[0]


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
