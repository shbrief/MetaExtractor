"""Presence vs value-aware precision/recall on FieldMetrics."""
import pytest

from metaextractor.evaluation import FieldMetrics, evaluate


def test_wrong_value_counts_as_presence_hit_but_not_value_hit():
    fm = FieldMetrics(label="x", tp_correct=6, tp_wrong=4, fn=5, fp=2)
    assert fm.presence_precision == pytest.approx(10 / 12)
    assert fm.presence_recall == pytest.approx(10 / 15)
    assert fm.value_precision == pytest.approx(6 / 12)
    assert fm.value_recall == pytest.approx(6 / 15)
    assert fm.value_f1 == pytest.approx(2 * 0.5 * 0.4 / 0.9)
    assert fm.value_accuracy == pytest.approx(0.6)
    # Backward-compatible aliases keep presence semantics.
    assert fm.precision == fm.presence_precision and fm.recall == fm.presence_recall


def test_empty_metrics_are_none():
    fm = FieldMetrics(label="x")
    assert fm.value_precision is None and fm.value_recall is None and fm.value_f1 is None


def test_scorer_does_not_inherit_study_values_by_default():
    extraction = {
        "granularity": "sample_level",
        "fields": {"country": {"value": "Italy", "extraction_type": "directly_stated",
                               "confidence": "high", "evidence_quote": "Italy", "section": "m"}},
        "samples": [{"sample_id": "s1"}],
    }
    gold = [{"country": "Italy"}]
    fm = evaluate(extraction, gold, {"country": "country"}).per_field["country"]
    assert fm.fn == 1
    fm = evaluate(extraction, gold, {"country": "country"},
                  inherit_study_fields=True).per_field["country"]
    assert fm.tp_correct == 1


def test_none_sample_is_a_phantom_row():
    extraction = {"granularity": "sample_level", "fields": {}, "samples": [None, {"a": "1"}]}
    fm = evaluate(extraction, [{"a": "2"}, {"a": "1"}], {"a": "a"}).per_field["a"]
    assert (fm.fn, fm.tp_correct) == (1, 1)
