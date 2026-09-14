"""Responses that stop at max_tokens are re-requested with a larger budget and logged."""
import json
from types import SimpleNamespace

import pytest

from metaextractor.extractor import ExtractionError, MetaExtractor
from metaextractor.schema import Field, Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import propose_plan

PAYLOAD = {"granularity": "study_level", "fields": {
    "disease": {"value": "Healthy", "extraction_type": "directly_stated", "confidence": "high",
                "evidence_quote": "q", "section": "Methods"}}}
SCHEMA = Schema(fields=[Field(name="disease", description="d", type="string")])


def _msg(text, stop_reason):
    return SimpleNamespace(
        model="claude-test", stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=3, output_tokens=7,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class _Client:
    """Returns a truncated response while max_tokens < ``needs``, then the full one."""

    def __init__(self, needs):
        self.needs, self.budgets = needs, []
        outer = self

        class messages:
            @staticmethod
            def stream(**kw):
                outer.budgets.append(kw["max_tokens"])
                full = json.dumps(PAYLOAD)
                if kw["max_tokens"] < outer.needs:
                    return _Stream(_msg(full[: len(full) // 2], "max_tokens"))
                return _Stream(_msg(full, "end_turn"))

            @staticmethod
            def create(**kw):
                outer.budgets.append(kw["max_tokens"])
                if kw["max_tokens"] < outer.needs:
                    return _msg('{"header_rows": [0', "max_tokens")
                return _msg(json.dumps({"header_rows": [0], "data_starts_at": 1,
                                        "id_columns": [{"col": 0, "name": "a"}]}), "end_turn")
        self.messages = messages


def test_truncated_response_is_rerequested_with_doubled_budget():
    client = _Client(needs=64000)
    ex = MetaExtractor(client=client, model="m", max_tokens=16000, max_tokens_ceiling=64000)
    result = ex.extract("Methods text.", SCHEMA)
    assert result.fields["disease"].value == "Healthy"
    assert client.budgets == [16000, 32000, 64000]
    assert [c["stop_reason"] for c in ex.last_calls] == ["max_tokens", "max_tokens", "end_turn"]
    # usage of the truncated calls is counted, not only the final one
    assert ex.last_usage["n_calls"] == 3 and ex.last_usage["output_tokens"] == 21


def test_truncation_at_ceiling_raises_explicit_error():
    client = _Client(needs=10**9)
    ex = MetaExtractor(client=client, model="m", max_tokens=1000, max_tokens_ceiling=4000)
    with pytest.raises(ExtractionError, match="truncated at max_tokens=4000"):
        ex.extract("Methods text.", SCHEMA)
    assert client.budgets == [1000, 2000, 4000]
    assert ex.last_usage["n_calls"] == 3


def test_table_plan_rerequested_on_truncation():
    client = _Client(needs=8192)
    calls = []
    t = Table(name="t.xlsx", source="local", columns=["a"], rows=[{"a": "1"}],
              raw_rows=[["a"], ["1"]])
    plan, usage = propose_plan(client, "m", t, ["sample_id"], calls=calls)
    assert plan.header_rows == [0]
    assert client.budgets == [2048, 4096, 8192]
    assert usage["n_calls"] == 3
    assert [c["purpose"] for c in calls] == ["table_plan"] * 3
