"""The exact request this library puts on the wire, pinned.

Written **before** the Model-seam refactor and survived it with no assertion
changed. The seam moved four lines in this file, all of them constructing the
model under test — ``client=rec`` became ``llm=AnthropicModel("m", client=rec)``,
and ``propose_plan(rec, "m", table)`` lost its model-name positional. Every
assertion below held byte for byte across that change. That is the point: a
refactor validated by a test adjusted to fit it has been validated by nothing,
so if a future change here touches an assertion rather than a construction, the
wire moved and that needs explaining rather than accommodating.

Four layers, strongest first:

1. **The exact keyword set.** Nothing but ``model``, ``max_tokens``, ``system``
   and ``messages`` may reach the SDK. This is what backs the run-meta claim
   ``"sampling_and_thinking": "not set (API defaults: ...)"`` -- it fails the
   moment anyone adds ``temperature``, ``tools``, ``thinking`` or ``metadata``.
2. **Which SDK method.** ``messages.stream`` for the field and sample-discovery
   stages, ``messages.create`` for the table plan. Streaming is a transport
   choice (a long call without the short timeout), not a semantic one, but
   changing it changes the wire body, so it is pinned.
3. **Structural equality** against an inline literal, with each prompt text
   replaced by its SHA-256. Inline rather than a golden file so both cache
   breakpoints are visible to a reviewer in the diff; hashed so that "the
   request structure changed" and "a prompt changed" are two distinct failures.
4. **Cache-breakpoint invariants** asserted independently of the literal, so the
   intent survives a future prompt edit.

The prompt digests themselves are pinned separately. ``SYSTEM_PROMPT`` is kept
stable *specifically* so the prefix cache hits, so a test that makes an
accidental whitespace change loud is enforcing an invariant the codebase already
relies on -- not inventing one. A legitimate prompt change requires updating
``SYSTEM_PROMPT_SHA256`` here, deliberately.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from metaextractor.extractor import MetaExtractor
from metaextractor.model import AnthropicModel
from metaextractor.prompts import SYSTEM_PROMPT
from metaextractor.schema import Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import propose_plan

#: Digest of the system prompt. Update only when the prompt is changed on purpose;
#: it is held stable so the Anthropic prefix cache hits across batches.
SYSTEM_PROMPT_SHA256 = "1f73f3b9d9fc4e664e45991c02bbeccff36392016dfb6727bc8df79cab31ad2a"

#: Digests of the two user-content blocks for the fixture inputs below. Pinned
#: rather than recomputed from the request, so the comparison is against a
#: recorded value and not against itself.
PAPER_BLOCK_SHA256 = "ef40001d7c1d7ac35c3b23803194b781b7961122effa23a07245f77981a2ead9"
SCHEMA_BLOCK_SHA256 = "08127372ab1658e4131e46591a34fb22fc2ffa76a7262e4637457cd35308276f"

PAPER = "Methods. We enrolled 42 adults. Stool DNA was extracted with a kit."
SCHEMA = Schema.from_dict({"fields": [
    {"name": "n_participants", "description": "Total enrolled.", "type": "number"},
    {"name": "body_site", "description": "Specimen site.", "type": "string"},
]})

_RESULT_JSON = json.dumps({
    "granularity": "study_level",
    "fields": {
        "n_participants": {"value": 42, "extraction_type": "directly_stated",
                           "confidence": "high", "evidence_quote": "We enrolled 42 adults.",
                           "section": "Methods"},
        "body_site": {"value": "stool", "extraction_type": "directly_stated",
                      "confidence": "high", "evidence_quote": "Stool DNA",
                      "section": "Methods"},
    },
})
_PLAN_JSON = json.dumps({"header_rows": [0], "data_starts_at": 1})


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _digest_texts(value):
    """``value`` with each content block's ``text`` replaced by its SHA-256.

    Only the ``text`` key of a block is hashed. Everything else -- the model name,
    ``role``, ``type``, ``cache_control``, ``max_tokens`` -- is compared literally,
    because those are exactly the parts a refactor must not change.
    """
    if isinstance(value, list):
        return [_digest_texts(v) for v in value]
    if isinstance(value, dict):
        return {k: (_sha(v) if k == "text" and isinstance(v, str) else _digest_texts(v))
                for k, v in value.items()}
    return value


class _Recorder:
    """Stands in for ``anthropic.Anthropic``, capturing what would be sent.

    The one copy of this shape in the test suite. Everywhere else the model is
    faked at a higher level; here the coupling to the SDK call signature *is*
    the thing under test.
    """

    def __init__(self, text: str):
        self.calls: list[tuple[str, dict]] = []
        outer = self

        def _message():
            return SimpleNamespace(
                model="recorded-model",
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(input_tokens=11, output_tokens=7,
                                      cache_creation_input_tokens=3,
                                      cache_read_input_tokens=5),
            )

        class _Stream:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def get_final_message(self_inner):
                return _message()

        class messages:
            @staticmethod
            def stream(**kw):
                outer.calls.append(("stream", kw))
                return _Stream()

            @staticmethod
            def create(**kw):
                outer.calls.append(("create", kw))
                return _message()

        self.messages = messages

    def only(self, method: str) -> dict:
        matching = [kw for m, kw in self.calls if m == method]
        assert len(matching) == 1, (
            f"expected exactly one {method} call, got {[m for m, _ in self.calls]}")
        return matching[0]


@pytest.fixture
def extract_request() -> dict:
    """The kwargs a single field extraction puts on the wire."""
    rec = _Recorder(_RESULT_JSON)
    MetaExtractor(llm=AnthropicModel("m", client=rec), max_tokens=16384,
                  sample_discovery=False).extract(PAPER, SCHEMA, paper_id="PMID:1")
    return rec.only("stream")


@pytest.fixture
def plan_request() -> dict:
    """The kwargs a single table-plan proposal puts on the wire."""
    rec = _Recorder(_PLAN_JSON)
    raw = [["Table S1. Donors", "", ""], ["ID", "Age", "Site"], ["s1", "30", "stool"]]
    table = Table(name="t.xlsx", source="local", columns=[], rows=[], raw_rows=raw)
    propose_plan(AnthropicModel("m", client=rec), table)
    return rec.only("create")


# ---------------------------------------------------------------------------
# 1. The exact keyword set
# ---------------------------------------------------------------------------

def test_extract_sends_only_four_keywords(extract_request):
    """No sampling, tool, thinking or metadata parameter may appear.

    run-meta records "sampling_and_thinking: not set (API defaults ...)". This is
    the assertion that keeps that record true.
    """
    assert set(extract_request) == {"model", "max_tokens", "system", "messages"}


def test_plan_sends_only_four_keywords(plan_request):
    assert set(plan_request) == {"model", "max_tokens", "system", "messages"}


# ---------------------------------------------------------------------------
# 2. Which SDK method
# ---------------------------------------------------------------------------

def test_field_extraction_uses_streaming():
    rec = _Recorder(_RESULT_JSON)
    MetaExtractor(llm=AnthropicModel("m", client=rec),
                  sample_discovery=False).extract(PAPER, SCHEMA)
    assert [m for m, _ in rec.calls] == ["stream"]


def test_table_plan_uses_create_not_streaming():
    rec = _Recorder(_PLAN_JSON)
    raw = [["Title", ""], ["ID", "Age"], ["s1", "30"]]
    propose_plan(AnthropicModel("m", client=rec),
                 Table(name="t.xlsx", source="local", columns=[], rows=[], raw_rows=raw))
    assert [m for m, _ in rec.calls] == ["create"]


# ---------------------------------------------------------------------------
# 3. Structural equality
# ---------------------------------------------------------------------------

def test_extract_request_structure(extract_request):
    """Two ephemeral cache breakpoints: the system prompt and the paper block.

    The schema block deliberately sits *past* the second breakpoint, so a
    schema split into batches re-sends only the small part. That shape is the
    entire economic basis of field batching.
    """
    assert _digest_texts(extract_request) == {
        "model": "m",
        "max_tokens": 16384,
        "system": [
            {"type": "text", "text": SYSTEM_PROMPT_SHA256,
             "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": PAPER_BLOCK_SHA256,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": SCHEMA_BLOCK_SHA256},
            ]},
        ],
    }


def test_plan_request_structure(plan_request):
    """The plan call sends bare strings and no cache control at all."""
    assert isinstance(plan_request["system"], str)
    assert isinstance(plan_request["messages"][0]["content"], str)
    assert plan_request["messages"][0]["role"] == "user"
    assert plan_request["max_tokens"] == 2048
    assert "cache_control" not in json.dumps(plan_request)


# ---------------------------------------------------------------------------
# 4. Cache-breakpoint invariants, independent of the literal above
# ---------------------------------------------------------------------------

def test_exactly_two_cache_breakpoints(extract_request):
    blocks = list(extract_request["system"]) + list(
        extract_request["messages"][0]["content"])
    assert sum(1 for b in blocks if "cache_control" in b) == 2


def test_paper_is_cached_and_schema_is_not(extract_request):
    content = extract_request["messages"][0]["content"]
    assert [("cache_control" in b) for b in content] == [True, False], (
        "the paper block must carry the breakpoint and the schema block must sit "
        "past it; reversing them would re-send the paper on every batch"
    )
    assert "<paper>" in content[0]["text"]
    assert "<schema>" in content[1]["text"]


def test_cache_block_key_order_is_stable(extract_request):
    """The SDK serialises dicts in insertion order, so key order is wire-visible."""
    for block in list(extract_request["system"]) + [
            extract_request["messages"][0]["content"][0]]:
        assert list(block) == ["type", "text", "cache_control"]


def test_system_block_is_the_whole_system_prompt(extract_request):
    assert extract_request["system"][0]["text"] == SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# The prompt digests themselves
# ---------------------------------------------------------------------------

def test_system_prompt_digest_is_pinned():
    """Held stable so the prefix cache hits. Update deliberately, never to pass.

    If this fails after an intentional prompt edit, replace the expected digest
    and say so in the commit message -- a changed system prompt invalidates every
    cached prefix and is a cost change, not a cosmetic one.
    """
    assert _sha(SYSTEM_PROMPT) == SYSTEM_PROMPT_SHA256, (
        f"SYSTEM_PROMPT digest is now {_sha(SYSTEM_PROMPT)}")
