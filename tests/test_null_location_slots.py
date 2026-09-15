"""A field reported as absent may carry null location slots (``section``, ``evidence_quote``).

The fixture is the complete Haiku 4.5 response of out_v3 haiku_r1/Bengtsson-PalmeJ_2015
attempt 1, which failed validation with ``"section": null`` on five fields whose value is
``not_reported`` (the cause of all five failed Haiku 4.5 attempts in out_v3).
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from metaextractor.extractor import MetaExtractor
from metaextractor.output import ExtractionResult, FieldResult
from metaextractor.schema import Field, Schema

FIXTURE = Path(__file__).parent / "fixtures" / "haiku45_null_section_response.json"
NULL_SECTION_FIELDS = {"disease_response_os", "disease_response_os_unit",
                       "ecog_performance_status", "tumor_size_measurement",
                       "tumor_size_residual_measurement"}


def _field(**kw):
    base = {"value": "not_reported", "extraction_type": "not_reported", "confidence": "high",
            "evidence_quote": "", "section": None}
    return {**base, **kw}


def test_out_v3_failing_response_now_validates():
    payload = json.loads(FIXTURE.read_text())
    assert {k for k, v in payload["fields"].items() if v["section"] is None} == NULL_SECTION_FIELDS
    result = ExtractionResult.model_validate(payload)
    for name in NULL_SECTION_FIELDS:
        assert result.fields[name].section is None
        assert result.fields[name].value == "not_reported"


@pytest.mark.parametrize("value", ["not_reported", "Not Reported", "", None, []])
def test_absent_value_allows_null_location(value):
    fr = FieldResult.model_validate(_field(value=value, evidence_quote=None, section=None))
    assert fr.section is None and fr.evidence_quote is None


@pytest.mark.parametrize("slot", ["section", "evidence_quote"])
def test_reported_value_still_requires_location(slot):
    with pytest.raises(ValidationError, match=slot):
        kw = {"value": "Healthy", "extraction_type": "directly_stated",
              "evidence_quote": "q", "section": "Methods", slot: None}
        FieldResult.model_validate(_field(**kw))


def test_extractor_accepts_failing_response_end_to_end():
    text = FIXTURE.read_text()
    msg = SimpleNamespace(
        model="claude-haiku-4-5", stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return msg

    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: _Stream()))
    schema = Schema(fields=[Field(name=n, description="d", type="string")
                            for n in json.loads(text)["fields"]])
    result = MetaExtractor(client=client, model="m").extract("Methods text.", schema,
                                                             paper_id="26259788")
    assert NULL_SECTION_FIELDS <= set(result.fields)
