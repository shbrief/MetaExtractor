"""Responses that stop at max_tokens are re-requested with a larger budget and logged.

The budget sequence is asserted as the *backend* saw it, which is why
``complete_with_retry`` lives above the model rather than inside it: if the
doubling happened inside ``AnthropicModel``, these assertions would be checking
the mock's own arithmetic instead of production code.
"""
import json

import pytest

from metaextractor.extractor import ExtractionError, MetaExtractor
from metaextractor.model import (
    STAGE_FIELDS,
    STAGE_SAMPLE_DISCOVERY,
    STAGE_TABLE_PLAN,
    MockModel,
    MockReply,
)
from metaextractor.schema import Field, Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import propose_plan

PAYLOAD = {"granularity": "study_level", "fields": {
    "disease": {"value": "Healthy", "extraction_type": "directly_stated", "confidence": "high",
                "evidence_quote": "q", "section": "Methods"}}}
SCHEMA = Schema(fields=[Field(name="disease", description="d", type="string")])

_FULL = json.dumps(PAYLOAD)
_PLAN = {"header_rows": [0], "data_starts_at": 1}

#: Three output tokens per call, so a three-attempt run totals 21 and the
#: truncated attempts are visibly counted rather than only the final one.
_USAGE = {"input_tokens": 3, "output_tokens": 7,
          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def _truncate_below(needs, full, truncated):
    """Reply truncated while the requested budget is below ``needs``, then fully."""
    def respond(call):
        if call.max_tokens < needs:
            return MockReply(truncated, stop_reason="max_tokens")
        return MockReply(full)
    return respond


def _llm(needs):
    """A model that needs ``needs`` output tokens before it can answer."""
    fields = _truncate_below(needs, _FULL, _FULL[: len(_FULL) // 2])
    return MockModel(
        responses={
            STAGE_FIELDS: fields,
            STAGE_SAMPLE_DISCOVERY: fields,
            STAGE_TABLE_PLAN: _truncate_below(needs, _PLAN, '{"header_rows": [0'),
        },
        model_id="m", response_model="claude-test", usage=_USAGE,
    )


def test_truncated_response_is_rerequested_with_doubled_budget():
    llm = _llm(needs=64000)
    ex = MetaExtractor(llm=llm, max_tokens=16000, max_tokens_ceiling=64000)
    result = ex.extract("Methods text.", SCHEMA)
    assert result.fields["disease"].value == "Healthy"
    assert llm.budgets() == [16000, 32000, 64000]
    assert [c["stop_reason"] for c in ex.last_calls] == ["max_tokens", "max_tokens", "end_turn"]
    # usage of the truncated calls is counted, not only the final one
    assert ex.last_usage["n_calls"] == 3 and ex.last_usage["output_tokens"] == 21


def test_truncation_at_ceiling_raises_explicit_error():
    llm = _llm(needs=10**9)
    ex = MetaExtractor(llm=llm, max_tokens=1000, max_tokens_ceiling=4000)
    with pytest.raises(ExtractionError, match="truncated at max_tokens=4000"):
        ex.extract("Methods text.", SCHEMA)
    assert llm.budgets() == [1000, 2000, 4000]
    assert ex.last_usage["n_calls"] == 3


def test_table_plan_rerequested_on_truncation():
    llm = _llm(needs=8192)
    calls = []
    t = Table(name="t.xlsx", source="local", columns=["a"], rows=[{"a": "1"}],
              raw_rows=[["a"], ["1"]])
    plan, usage = propose_plan(llm, t, calls=calls)
    assert plan.header_rows == [0]
    assert llm.budgets(STAGE_TABLE_PLAN) == [2048, 4096, 8192]
    assert usage["n_calls"] == 3
    assert [c["purpose"] for c in calls] == ["table_plan"] * 3
    assert calls[-1]["plan"] == _PLAN   # plan is logged
    assert calls[-1]["table"] == "t.xlsx"


def test_extractor_model_is_the_backends_model_not_an_argument():
    """``MetaExtractor(llm=...)`` can no longer disagree with what is called.

    Before the seam, ``MetaExtractor(client=X, model="claude-sonnet-5")`` reported
    and *priced* as Sonnet whatever X actually called.
    """
    llm = _llm(needs=0)
    ex = MetaExtractor(llm=llm)
    assert ex.model == "m"
    ex.extract("Methods text.", SCHEMA)
    assert ex.last_response_models == {"claude-test"}
