"""Verbatim extraction scoring + the harmonization canonicalizer hook.

MetaExtractor now emits enum values verbatim (surface form), leaving
vocabulary mapping to a downstream stage. So a surface-form mismatch is an
*expected* TP_wrong under raw scoring, and a supplied ``canonicalize`` maps it
back to TP_correct. ``evaluate_both`` reports both and names the recoverable
cells. Sample cells may also carry a ``{value, normalized_value}`` split that
``prefer_normalized`` reads.
"""
from metaextractor.evaluation import evaluate, evaluate_both

FIELD_MAP = {"sex": "sex"}
GOLD = [{"sample_id": "S1", "sex": "female"}]


def _extraction(sex_cell):
    return {
        "granularity": "sample_level",
        "fields": {},
        "samples": [{"sample_id": "S1", "sex": sex_cell}],
    }


def _canon(value, field):
    # Trivial crosswalk standing in for MetaHarmonizer.
    return {"f": "female", "m": "male"}.get(str(value).strip().lower(), value)


def test_verbatim_mismatch_is_tp_wrong_raw():
    res = evaluate(_extraction("F"), GOLD, FIELD_MAP)
    assert res.per_field["sex"].tp_wrong == 1
    assert res.per_field["sex"].tp_correct == 0


def test_canonicalize_recovers_to_tp_correct():
    res = evaluate(_extraction("F"), GOLD, FIELD_MAP, canonicalize=_canon)
    assert res.per_field["sex"].tp_correct == 1
    assert res.per_field["sex"].tp_wrong == 0
    # Raw verbatim value is preserved in the cell, not the canonical form.
    assert res.per_cell[0].extracted == "F"


def test_evaluate_both_reports_recoverable():
    comp = evaluate_both(_extraction("F"), GOLD, FIELD_MAP, canonicalize=_canon)
    assert comp.raw.per_field["sex"].tp_wrong == 1
    assert comp.harmonized.per_field["sex"].tp_correct == 1
    assert comp.recoverable_count == 1
    assert comp.recoverable[0].field == "sex"
    assert comp.recoverable[0].extracted == "F"  # raw, not canonicalized


def test_prefer_normalized_reads_split_cell():
    ext = _extraction({"value": "F", "normalized_value": "female"})
    # Default reads verbatim -> mismatch.
    assert evaluate(ext, GOLD, FIELD_MAP).per_field["sex"].tp_wrong == 1
    # prefer_normalized reads the canonical form written back into the data.
    res = evaluate(ext, GOLD, FIELD_MAP, prefer_normalized=True)
    assert res.per_field["sex"].tp_correct == 1
