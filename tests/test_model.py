"""Tests for metaextractor.model — the seam, the backend adapter, the mock.

Nothing here touches the network: ``AnthropicModel`` is constructed with an
injected client, which is the only thing the real backend needs from the SDK.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from metaextractor.model import (
    STAGE_FIELDS,
    STAGE_SAMPLE_DISCOVERY,
    STAGE_TABLE_PLAN,
    TOKEN_KEYS,
    USAGE_KEYS,
    AnthropicModel,
    CompletionRun,
    Message,
    MockCall,
    MockModel,
    MockReply,
    Model,
    ModelCallError,
    ModelResponse,
    TextBlock,
    UnexpectedCall,
    _to_blocks,
    complete_with_retry,
    new_usage,
)


def _msg(text="{}", stop="end_turn", model="srv-model", **usage):
    u = {"input_tokens": 11, "output_tokens": 7,
         "cache_creation_input_tokens": 3, "cache_read_input_tokens": 5}
    u.update(usage)
    return SimpleNamespace(
        model=model, stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(**u),
    )


class _Client:
    """Minimal SDK stand-in that records kwargs and which method was used."""

    def __init__(self, reply=None, raises=None):
        self.calls: list[tuple[str, dict]] = []
        outer = self
        reply = reply if reply is not None else _msg()

        class _Stream:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def get_final_message(s):
                return reply

        class messages:
            @staticmethod
            def stream(**kw):
                outer.calls.append(("stream", kw))
                if raises:
                    raise raises
                return _Stream()

            @staticmethod
            def create(**kw):
                outer.calls.append(("create", kw))
                if raises:
                    raise raises
                return reply

        self.messages = messages


# ---------------------------------------------------------------------------
# _to_blocks
# ---------------------------------------------------------------------------

class TestToBlocks:
    def test_bare_string_passes_through(self):
        assert _to_blocks("a system prompt") == "a system prompt"

    def test_none_passes_through(self):
        assert _to_blocks(None) is None

    def test_uncached_block_has_no_cache_control(self):
        assert _to_blocks([TextBlock("x")]) == [{"type": "text", "text": "x"}]

    def test_cached_block_gets_ephemeral_cache_control(self):
        assert _to_blocks([TextBlock("x", cache=True)]) == [
            {"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}]

    def test_key_order_is_type_text_cache_control(self):
        """Wire-visible: the SDK serialises dicts in insertion order."""
        block = _to_blocks([TextBlock("x", cache=True)])[0]
        assert list(block) == ["type", "text", "cache_control"]

    def test_already_wire_shaped_dicts_pass_through(self):
        raw = [{"type": "text", "text": "x"}]
        assert _to_blocks(raw) == raw

    def test_block_order_is_preserved(self):
        out = _to_blocks([TextBlock("first", cache=True), TextBlock("second")])
        assert [b["text"] for b in out] == ["first", "second"]
        assert "cache_control" in out[0] and "cache_control" not in out[1]


# ---------------------------------------------------------------------------
# AnthropicModel
# ---------------------------------------------------------------------------

class TestAnthropicModel:
    def test_streaming_stages_use_stream(self):
        for stage in (STAGE_FIELDS, STAGE_SAMPLE_DISCOVERY):
            c = _Client()
            AnthropicModel("m", client=c).complete(
                stage=stage, system="s", messages=[Message.user("u")], max_tokens=10)
            assert [m for m, _ in c.calls] == ["stream"], stage

    def test_other_stages_use_create(self):
        c = _Client()
        AnthropicModel("m", client=c).complete(
            stage=STAGE_TABLE_PLAN, system="s", messages=[Message.user("u")],
            max_tokens=10)
        assert [m for m, _ in c.calls] == ["create"]

    def test_streaming_stages_is_assertable(self):
        assert AnthropicModel.STREAMING_STAGES == {STAGE_FIELDS, STAGE_SAMPLE_DISCOVERY}
        assert STAGE_TABLE_PLAN not in AnthropicModel.STREAMING_STAGES

    def test_sends_exactly_four_keywords(self):
        c = _Client()
        AnthropicModel("m", client=c).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert set(c.calls[0][1]) == {"model", "max_tokens", "system", "messages"}

    def test_model_id_reaches_the_wire(self):
        c = _Client()
        AnthropicModel("claude-haiku-4-5", client=c).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert c.calls[0][1]["model"] == "claude-haiku-4-5"

    def test_messages_are_translated_to_dicts(self):
        c = _Client()
        AnthropicModel("m", client=c).complete(
            stage=STAGE_FIELDS, system=[TextBlock("sys", cache=True)],
            messages=[Message.user([TextBlock("paper", cache=True), TextBlock("schema")])],
            max_tokens=10)
        kw = c.calls[0][1]
        assert kw["messages"] == [{"role": "user", "content": [
            {"type": "text", "text": "paper", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "schema"},
        ]}]

    def test_normalises_the_response(self):
        r = AnthropicModel("m", client=_Client(_msg(text="  hello  "))).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert r.text == "hello"
        assert r.stop_reason == "end_turn"
        assert r.model == "srv-model"
        assert r.usage == {"input_tokens": 11, "output_tokens": 7,
                           "cache_creation_input_tokens": 3,
                           "cache_read_input_tokens": 5}

    def test_joins_multiple_text_blocks_and_skips_non_text(self):
        reply = SimpleNamespace(
            model="m", stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="a"),
                     SimpleNamespace(type="thinking", text="IGNORED"),
                     SimpleNamespace(type="text", text="b")],
            usage=SimpleNamespace(**dict.fromkeys(TOKEN_KEYS, 1)))
        r = AnthropicModel("m", client=_Client(reply)).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert r.text == "ab"

    def test_missing_usage_attributes_become_zero(self):
        reply = SimpleNamespace(model="m", stop_reason="end_turn",
                                content=[SimpleNamespace(type="text", text="{}")],
                                usage=SimpleNamespace(input_tokens=None))
        r = AnthropicModel("m", client=_Client(reply)).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert r.usage == dict.fromkeys(TOKEN_KEYS, 0)

    def test_absent_stop_reason_is_none_not_an_error(self):
        reply = SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")],
                                usage=SimpleNamespace(**dict.fromkeys(TOKEN_KEYS, 0)))
        r = AnthropicModel("m", client=_Client(reply)).complete(
            stage=STAGE_FIELDS, system="s", messages=[Message.user("u")], max_tokens=10)
        assert r.stop_reason is None and r.model is None

    def test_backend_exceptions_become_model_call_error(self):
        c = _Client(raises=ValueError("boom"))
        with pytest.raises(ModelCallError, match="ValueError: boom"):
            AnthropicModel("m", client=c).complete(
                stage=STAGE_FIELDS, system="s", messages=[Message.user("u")],
                max_tokens=10)

    def test_error_message_matches_the_pre_seam_format(self):
        """propose_plan composed 'LLM call failed: {type}: {msg}'; keep the tail."""
        c = _Client(raises=KeyError("k"))
        with pytest.raises(ModelCallError) as ei:
            AnthropicModel("m", client=c).complete(
                stage=STAGE_TABLE_PLAN, system="s", messages=[Message.user("u")],
                max_tokens=10)
        assert str(ei.value) == "KeyError: 'k'"

    def test_satisfies_the_protocol(self):
        assert isinstance(AnthropicModel("m", client=_Client()), Model)

    def test_sdk_version_is_a_string_or_none(self):
        assert AnthropicModel.sdk_version() is None or isinstance(
            AnthropicModel.sdk_version(), str)


# ---------------------------------------------------------------------------
# usage helpers
# ---------------------------------------------------------------------------

class TestUsage:
    def test_new_usage_has_every_key_zeroed(self):
        assert new_usage() == dict.fromkeys(USAGE_KEYS, 0)

    def test_usage_keys_are_tokens_plus_n_calls(self):
        assert USAGE_KEYS == (*TOKEN_KEYS, "n_calls")

    def test_response_rejects_incomplete_usage(self):
        with pytest.raises(ValueError, match="missing"):
            ModelResponse(text="", stop_reason=None, model=None,
                          usage={"input_tokens": 1})


# ---------------------------------------------------------------------------
# complete_with_retry
# ---------------------------------------------------------------------------

class TestCompleteWithRetry:
    def _llm(self, needs):
        def respond(call: MockCall):
            if call.max_tokens < needs:
                return MockReply("truncated", stop_reason="max_tokens")
            return MockReply("full")
        return MockModel(responses={STAGE_FIELDS: respond, STAGE_TABLE_PLAN: respond})

    def _run(self, llm, **over):
        kw = dict(stage=STAGE_FIELDS, system="s", messages=[Message.user("u")],
                  max_tokens=16000, max_tokens_ceiling=64000)
        kw.update(over)
        return complete_with_retry(llm, **kw)

    def test_doubles_the_budget_until_the_response_fits(self):
        llm = self._llm(needs=64000)
        run = self._run(llm)
        assert llm.budgets() == [16000, 32000, 64000]
        assert run.budget == 64000
        assert run.final.text == "full"
        assert len(run.attempts) == 3

    def test_stops_at_the_ceiling_and_leaves_stop_reason_set(self):
        """Policy is the caller's: this returns truncated rather than raising."""
        llm = self._llm(needs=10**9)
        run = self._run(llm, max_tokens=1000, max_tokens_ceiling=4000)
        assert llm.budgets() == [1000, 2000, 4000]
        assert run.budget == 4000
        assert run.final.stop_reason == "max_tokens"

    def test_does_not_retry_a_complete_response(self):
        llm = MockModel(responses={STAGE_FIELDS: "done"})
        run = self._run(llm)
        assert llm.budgets() == [16000]
        assert run.budget == 16000

    def test_plan_ceiling_sequence(self):
        llm = self._llm(needs=8192)
        complete_with_retry(llm, stage=STAGE_TABLE_PLAN, system="s",
                            messages=[Message.user("u")], max_tokens=2048,
                            max_tokens_ceiling=16384)
        assert llm.budgets(STAGE_TABLE_PLAN) == [2048, 4096, 8192]

    def test_accumulates_usage_in_place_across_attempts(self):
        llm = self._llm(needs=64000)
        usage = new_usage()
        self._run(llm, usage=usage)
        assert usage["n_calls"] == 3
        assert usage["output_tokens"] == 3  # default mock usage is 1 per call
        assert set(usage) == set(USAGE_KEYS)

    def test_usage_is_accumulated_even_when_the_ceiling_is_hit(self):
        usage = new_usage()
        self._run(self._llm(needs=10**9), max_tokens=1000,
                  max_tokens_ceiling=4000, usage=usage)
        assert usage["n_calls"] == 3

    def test_call_record_appends_one_entry_per_attempt(self):
        llm = self._llm(needs=64000)
        calls: list[dict] = []
        self._run(llm, calls=calls,
                  call_record=lambda resp, budget: {
                      "purpose": "fields", "max_tokens": budget,
                      "stop_reason": resp.stop_reason})
        assert [c["max_tokens"] for c in calls] == [16000, 32000, 64000]
        assert [c["stop_reason"] for c in calls] == [
            "max_tokens", "max_tokens", "end_turn"]

    def test_no_calls_list_means_no_record(self):
        self._run(self._llm(needs=16000))  # must not raise

    def test_label_is_forwarded(self):
        llm = MockModel(responses={STAGE_TABLE_PLAN: "{}"})
        complete_with_retry(llm, stage=STAGE_TABLE_PLAN, system="s",
                            messages=[Message.user("u")], max_tokens=10,
                            max_tokens_ceiling=10, label="t.xlsx")
        assert llm.calls[0].label == "t.xlsx"

    def test_completion_run_final_is_the_last_attempt(self):
        run = CompletionRun(attempts=[
            ModelResponse(text="a", stop_reason=None, model=None,
                          usage=dict.fromkeys(TOKEN_KEYS, 0)),
            ModelResponse(text="b", stop_reason=None, model=None,
                          usage=dict.fromkeys(TOKEN_KEYS, 0)),
        ], budget=1)
        assert run.final.text == "b"


# ---------------------------------------------------------------------------
# MockModel
# ---------------------------------------------------------------------------

class TestMockModel:
    def _call(self, llm, **over):
        kw = dict(stage=STAGE_FIELDS, system="s", messages=[Message.user("u")],
                  max_tokens=100)
        kw.update(over)
        return llm.complete(**kw)

    def test_satisfies_the_protocol(self):
        assert isinstance(MockModel(), Model)

    def test_string_spec_is_returned_verbatim(self):
        assert self._call(MockModel(responses={STAGE_FIELDS: "raw text"})).text == "raw text"

    def test_mapping_spec_is_json_encoded(self):
        text = self._call(MockModel(responses={STAGE_FIELDS: {"a": 1}})).text
        assert json.loads(text) == {"a": 1}

    def test_mock_reply_controls_stop_reason_and_usage(self):
        r = self._call(MockModel(responses={STAGE_FIELDS: MockReply(
            "x", stop_reason="refusal", usage=dict.fromkeys(TOKEN_KEYS, 9))}))
        assert r.stop_reason == "refusal"
        assert r.usage["output_tokens"] == 9

    def test_callable_spec_sees_the_request(self):
        llm = MockModel(responses={
            STAGE_FIELDS: lambda call: f"budget={call.max_tokens}"})
        assert self._call(llm, max_tokens=4242).text == "budget=4242"

    def test_by_label_routes_per_table(self):
        llm = MockModel(by_label={"a.xlsx": {"header_rows": [0]},
                                  "b.xlsx": {"header_rows": [1]}})
        r1 = self._call(llm, stage=STAGE_TABLE_PLAN, label="a.xlsx")
        r2 = self._call(llm, stage=STAGE_TABLE_PLAN, label="b.xlsx")
        assert json.loads(r1.text)["header_rows"] == [0]
        assert json.loads(r2.text)["header_rows"] == [1]

    def test_by_label_takes_precedence_over_stage(self):
        llm = MockModel(responses={STAGE_TABLE_PLAN: "stage"},
                        by_label={"t": "label"})
        assert self._call(llm, stage=STAGE_TABLE_PLAN, label="t").text == "label"
        assert self._call(llm, stage=STAGE_TABLE_PLAN, label="other").text == "stage"

    def test_unstubbed_stage_raises_unexpected_call(self):
        with pytest.raises(UnexpectedCall, match="no response for stage"):
            self._call(MockModel())

    def test_unexpected_call_is_a_model_call_error(self):
        """So callers that treat a model failure as recoverable still do."""
        assert issubclass(UnexpectedCall, ModelCallError)

    def test_raises_applies_to_every_stage(self):
        llm = MockModel(raises=ModelCallError("down"))
        with pytest.raises(ModelCallError, match="down"):
            self._call(llm)

    def test_raises_can_be_per_stage(self):
        llm = MockModel(responses={STAGE_FIELDS: "ok"},
                        raises={STAGE_TABLE_PLAN: ModelCallError("no plans")})
        assert self._call(llm).text == "ok"
        with pytest.raises(ModelCallError, match="no plans"):
            self._call(llm, stage=STAGE_TABLE_PLAN)

    def test_a_raising_call_is_still_recorded(self):
        """The property that makes assert_not_called meaningful."""
        llm = MockModel(raises=ModelCallError("down"))
        with pytest.raises(ModelCallError):
            self._call(llm)
        assert llm.stages_called() == [STAGE_FIELDS]

    def test_an_unexpected_call_is_still_recorded(self):
        llm = MockModel()
        with pytest.raises(UnexpectedCall):
            self._call(llm)
        assert len(llm.calls) == 1

    def test_assert_not_called_passes_when_untouched(self):
        MockModel().assert_not_called()

    def test_assert_not_called_fails_after_a_call(self):
        llm = MockModel(responses={STAGE_FIELDS: "x"})
        self._call(llm)
        with pytest.raises(AssertionError, match="expected no"):
            llm.assert_not_called()

    def test_assert_not_called_can_be_scoped_to_a_stage(self):
        llm = MockModel(responses={STAGE_FIELDS: "x"})
        self._call(llm)
        llm.assert_not_called(STAGE_TABLE_PLAN)
        with pytest.raises(AssertionError):
            llm.assert_not_called(STAGE_FIELDS)

    def test_assert_called_checks_the_count(self):
        llm = MockModel(responses={STAGE_FIELDS: "x"})
        self._call(llm)
        self._call(llm)
        llm.assert_called(STAGE_FIELDS, times=2)
        with pytest.raises(AssertionError):
            llm.assert_called(STAGE_FIELDS, times=1)

    def test_model_id_and_response_model_are_separate(self):
        """Requested vs returned, the way run-meta compares them."""
        llm = MockModel(responses={STAGE_FIELDS: "x"}, model_id="requested",
                        response_model="returned")
        assert llm.model_id == "requested"
        assert self._call(llm).model == "returned"

    def test_response_model_defaults_to_model_id(self):
        llm = MockModel(responses={STAGE_FIELDS: "x"}, model_id="only")
        assert self._call(llm).model == "only"

    def test_records_carry_the_request(self):
        llm = MockModel(responses={STAGE_FIELDS: "x"})
        self._call(llm, system=[TextBlock("sys", cache=True)],
                   messages=[Message.user([TextBlock("paper", cache=True),
                                           TextBlock("schema")])])
        call = llm.calls[0]
        assert call.stage == STAGE_FIELDS
        assert call.index == 0
        assert call.system_text == "sys"
        assert call.user_text == "paperschema"
        assert call.cache_markers == ("sys", "paper")

    def test_cache_markers_empty_for_bare_strings(self):
        llm = MockModel(responses={STAGE_TABLE_PLAN: "x"})
        self._call(llm, stage=STAGE_TABLE_PLAN, system="s",
                   messages=[Message.user("u")])
        assert llm.calls[0].cache_markers == ()

    def test_default_usage_matches_the_literal_the_old_doubles_used(self):
        r = self._call(MockModel(responses={STAGE_FIELDS: "x"}))
        assert r.usage == {"input_tokens": 1, "output_tokens": 1,
                           "cache_creation_input_tokens": 0,
                           "cache_read_input_tokens": 0}
