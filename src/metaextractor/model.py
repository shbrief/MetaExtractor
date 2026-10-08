"""The model seam: one interface every LLM call in this package goes through.

Why this exists, in order of how much it matters:

1. **One test double instead of ten.** Before this module there were ten
   hand-rolled stand-ins for the Anthropic SDK across the tests and benchmarks —
   eight nested ``messages`` classes, three ``_Stream`` context managers, four
   copies of the same ``SimpleNamespace(usage=...)`` literal. :class:`MockModel`
   replaces all of them, and unlike most of them it can be asked afterwards what
   it was called with.
2. **A model becomes a value you can pass.** ``MetaExtractor(llm=...)`` and
   ``propose_plan(llm, ...)`` take one object that knows its own model id, so a
   Sonnet-vs-Haiku comparison is a construction, not a pair of arguments that
   can disagree.
3. **A seam for the decision layer**, which needs to issue cheap bounded
   judgments through the same accounting and the same offline mock.

What it deliberately is *not*: a provider abstraction layer. Anthropic is the
only real backend, there is no registry, and no runtime dependency is added.

The cache contract
------------------

MetaExtractor's batching economics rest on two Anthropic ephemeral cache
breakpoints: the system prompt, and the large invariant paper block — with the
small per-batch schema block deliberately *past* the second breakpoint, so a
schema split into batches re-sends only the small part. A flat-string interface
would quietly destroy that, so content here is an ordered sequence of
:class:`TextBlock`, each of which may be marked ``cache=True``.

``cache: bool`` rather than Anthropic's ``cache_control`` dict, for two reasons:
a request type carrying a provider-specific key is not a seam, and a backend that
cannot cache should be able to *ignore* the marker rather than having to strip a
key it does not understand. The translation to the wire shape is
:func:`_to_blocks`, and ``tests/test_request_payload_golden.py`` pins its output.

Where the retry loop lives
--------------------------

:func:`complete_with_retry` sits **above** the model, not inside the backend, and
owns only the *mechanism*: doubling the budget on a truncated response,
accumulating usage, appending to the per-call log. Policy stays with the callers,
because the two existing loops genuinely differ — ``_extract_one`` raises
``ExtractionError`` when it exhausts its 64k ceiling, while ``propose_plan`` falls
through to a JSON parse failure at 16k — and because
``_discover_sample_ids`` swallows ``ExtractionError`` to disable discovery
silently, which only keeps working if the raise stays in its caller.

It must also stay above the model so that the budget sequence is observable
through *any* ``Model``: ``tests/test_truncation_retry.py`` asserts
``[16000, 32000, 64000]`` as seen by the backend, and if the loop were inside
``AnthropicModel`` that test would be asserting the mock's arithmetic instead.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

#: Per-batch extraction of schema fields.
STAGE_FIELDS = "fields"
#: The +1 call that enumerates sample ids before per-batch field extraction.
STAGE_SAMPLE_DISCOVERY = "sample_discovery"
#: Structural reading of one supplementary table.
STAGE_TABLE_PLAN = "table_plan"

#: Typed as ``str`` rather than a ``Literal``: the decision layer will add
#: stages, and a closed type would make every new one a type-level edit here.
Stage = str


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TextBlock:
    """One block of prompt text, optionally a cache breakpoint.

    ``cache=True`` asks the backend to mark the prefix up to and including this
    block as cacheable. A backend that cannot cache ignores it.
    """

    text: str
    cache: bool = False


#: Either a bare string (the table-plan call) or ordered, individually
#: cache-markable blocks (the extraction calls).
#: ``str`` for a bare prompt (the table-plan call), or ordered blocks for the
#: extraction calls. A plain alias rather than a ``TypeAlias``: annotations in
#: this module are strings under ``from __future__ import annotations``, and the
#: protocol takes ``Any`` so a caller is never forced to import it.
Content = str | Sequence[TextBlock]
System = Content


@dataclass(frozen=True, slots=True)
class Message:
    """One chat message."""

    role: str
    content: Any  # str | Sequence[TextBlock]

    @classmethod
    def user(cls, content: Any) -> Message:
        return cls(role="user", content=content)


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

#: The four token counters, priced at three different rates by
#: ``extractor.estimate_cost_usd`` — which reads them by subscript, so every one
#: must always be present.
TOKEN_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
#: The token counters plus the call counter: the shape of ``last_usage``, which
#: reaches run-meta JSON and from there the benchmark ledger.
USAGE_KEYS = (*TOKEN_KEYS, "n_calls")


def new_usage() -> dict[str, int]:
    """A zeroed usage tally with every key present."""
    return dict.fromkeys(USAGE_KEYS, 0)


# ---------------------------------------------------------------------------
# Responses and errors
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A completed call, normalized once at the boundary.

    Normalizing here is what removes six ``getattr(u, ..., 0) or 0`` calls from
    the callers and the "a fake omitted ``stop_reason``" hazard from the tests.
    ``usage`` stays a plain dict because usage dicts already cross a frozen wire
    boundary into run-meta and are merged by a generic accumulator; wrapping them
    would mean unwrapping at every one of those points.
    """

    text: str
    stop_reason: str | None
    model: str | None
    usage: dict[str, int]
    raw: Any = None

    def __post_init__(self) -> None:
        missing = [k for k in TOKEN_KEYS if k not in self.usage]
        if missing:
            raise ValueError(f"ModelResponse.usage is missing {missing}")


class ModelCallError(RuntimeError):
    """The backend failed to complete a call.

    A ``RuntimeError`` subclass on purpose: ``cli.main`` catches only
    ``ExtractionError``, so a transport failure escapes as a traceback today and
    must keep doing so. Making the CLI write run-meta for a failed transport call
    would be an improvement, and a behaviour change.
    """


class CredentialError(ModelCallError):
    """The API rejected the credentials (401)."""


class UnexpectedCall(ModelCallError):
    """A :class:`MockModel` was called for a stage it has no response for.

    Subclasses :class:`ModelCallError` deliberately, so callers that treat a
    model failure as recoverable still do. That means raising this is *damage
    control*, not enforcement: a test that requires a stage not to be called must
    assert :meth:`MockModel.assert_not_called` afterwards.
    """


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Model(Protocol):
    """What every LLM call in this package goes through.

    Two members, because two are needed. No ``temperature``, ``tools``,
    ``thinking`` or ``stop_sequences``: nothing sets them, and a parameter no
    caller sets is how a seam drifts out of sync with what the code does.
    """

    @property
    def model_id(self) -> str:
        """The model this backend calls, e.g. ``claude-sonnet-5``."""
        ...

    def complete(
        self,
        *,
        stage: Stage,
        system: Any,
        messages: Sequence[Message],
        max_tokens: int,
        label: str | None = None,
    ) -> ModelResponse:
        """One completion. No retry, no accumulation — see module docstring."""
        ...


# ---------------------------------------------------------------------------
# The Anthropic backend
# ---------------------------------------------------------------------------

def _to_blocks(value: Any) -> Any:
    """Translate :class:`TextBlock` sequences to the Anthropic wire shape.

    A bare string passes through untouched, which is what keeps the table-plan
    call byte-identical (it sends bare strings and no cache control at all).

    **Key order is load-bearing.** The SDK serializes dicts in insertion order,
    so ``type``, ``text``, ``cache_control`` is part of the request bytes;
    ``tests/test_request_payload_golden.py`` asserts it.
    """
    if value is None or isinstance(value, str):
        return value
    out = []
    for b in value:
        if isinstance(b, TextBlock):
            block: dict[str, Any] = {"type": "text", "text": b.text}
            if b.cache:
                block["cache_control"] = {"type": "ephemeral"}
            out.append(block)
        else:
            out.append(b)  # already a wire-shaped dict
    return out


class AnthropicModel:
    """The one real backend.

    Streaming is a transport detail, not a semantic one: the extraction path
    opens a stream and immediately calls ``get_final_message()``, which is the
    SDK's idiom for a long non-streaming call without the short timeout. So the
    choice lives here, as a named class attribute rather than an inline branch,
    because switching a stage between ``stream`` and ``create`` changes the wire
    body (``"stream": true`` appears) and should be directly assertable.
    """

    #: Stages issued with ``messages.stream``; everything else uses
    #: ``messages.create``.
    STREAMING_STAGES = frozenset({STAGE_FIELDS, STAGE_SAMPLE_DISCOVERY})

    def __init__(self, model: str, *, api_key: str | None = None,
                 client: Any = None):
        """Args:
            model: the model id to call.
            api_key: resolved key; see :mod:`metaextractor.keys`.
            client: a pre-built SDK client, for tests that need to see the exact
                request. Follows the injection style of
                :mod:`metaextractor.sra_manifest`'s ``http_get``.
        """
        self._model = model
        if client is not None:
            self._client = client
        else:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=api_key)

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        *,
        stage: Stage,
        system: Any,
        messages: Sequence[Message],
        max_tokens: int,
        label: str | None = None,
    ) -> ModelResponse:
        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": _to_blocks(system),
            "messages": [{"role": m.role, "content": _to_blocks(m.content)}
                         for m in messages],
        }
        try:
            if stage in self.STREAMING_STAGES:
                with self._client.messages.stream(**kwargs) as stream:
                    raw = stream.get_final_message()
            else:
                raw = self._client.messages.create(**kwargs)
        except Exception as e:
            # Composed so the message matches what propose_plan produced before
            # the seam: "LLM call failed: {type(e).__name__}: {e}".
            raise ModelCallError(f"{type(e).__name__}: {e}") from e
        return self._from_anthropic(raw)

    @staticmethod
    def _from_anthropic(raw: Any) -> ModelResponse:
        u = getattr(raw, "usage", None)
        usage = {k: (getattr(u, k, 0) or 0) if u is not None else 0 for k in TOKEN_KEYS}
        text = "".join(
            b.text for b in (getattr(raw, "content", None) or [])
            if getattr(b, "type", None) == "text"
        ).strip()
        model = getattr(raw, "model", None)
        return ModelResponse(
            text=text,
            stop_reason=getattr(raw, "stop_reason", None),
            model=str(model) if model else None,
            usage=usage,
            raw=raw,
        )

    @classmethod
    def check_credentials(cls, api_key: str) -> None:
        """Raise :class:`CredentialError` if the API rejects ``api_key``.

        Not on the :class:`Model` protocol: there is no cross-provider guarantee
        that listing models is free and 401s on a bad key, it is not part of the
        completion contract, and putting it on the protocol would force
        :class:`MockModel` and every future backend to carry a no-op.
        """
        from anthropic import Anthropic, AuthenticationError
        try:
            Anthropic(api_key=api_key).models.list(limit=1)
        except AuthenticationError as e:
            raise CredentialError(str(e)) from e

    @staticmethod
    def sdk_version() -> str | None:
        """Version of the installed Anthropic SDK, for run-meta provenance."""
        try:
            import anthropic
            return getattr(anthropic, "__version__", None)
        except ImportError:
            return None


# ---------------------------------------------------------------------------
# Retry mechanism
# ---------------------------------------------------------------------------

@dataclass
class CompletionRun:
    """Every attempt of one logical completion, and the budget it ended on."""

    attempts: list[ModelResponse]
    budget: int

    @property
    def final(self) -> ModelResponse:
        return self.attempts[-1]


def complete_with_retry(
    llm: Model,
    *,
    stage: Stage,
    system: Any,
    messages: Sequence[Message],
    max_tokens: int,
    max_tokens_ceiling: int,
    usage: dict[str, int] | None = None,
    calls: list[dict] | None = None,
    call_record: Callable[[ModelResponse, int], dict] | None = None,
    label: str | None = None,
) -> CompletionRun:
    """Complete, doubling the budget while the response is cut off at it.

    Returns with ``stop_reason == "max_tokens"`` still set when the ceiling is
    exhausted, and raises nothing — deciding what that means is the caller's,
    because the two callers decide differently.

    Args:
        usage: mutated in place, so the caller's running tally is updated
            whether or not this returns normally.
        calls: appended to via ``call_record``, which builds the stage-specific
            record. The two existing key sets differ, and ``cli._print_calls``
            discriminates on which optional key is present, so they stay owned
            by their callers.
    """
    budget = max_tokens
    attempts: list[ModelResponse] = []
    while True:
        resp = llm.complete(stage=stage, system=system, messages=messages,
                            max_tokens=budget, label=label)
        attempts.append(resp)
        if usage is not None:
            for k in TOKEN_KEYS:
                usage[k] = usage.get(k, 0) + resp.usage[k]
            usage["n_calls"] = usage.get("n_calls", 0) + 1
        if calls is not None and call_record is not None:
            calls.append(call_record(resp, budget))
        if resp.stop_reason == "max_tokens" and budget < max_tokens_ceiling:
            budget = min(budget * 2, max_tokens_ceiling)
            continue
        return CompletionRun(attempts=attempts, budget=budget)


# ---------------------------------------------------------------------------
# The mock
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MockCall:
    """One recorded call, with helpers for the parts a test usually checks."""

    stage: str
    system: Any
    messages: tuple[Message, ...]
    max_tokens: int
    label: str | None
    index: int

    @staticmethod
    def _text(content: Any) -> str:
        if content is None or isinstance(content, str):
            return content or ""
        return "".join(b.text if isinstance(b, TextBlock) else str(b.get("text", ""))
                       for b in content)

    @property
    def system_text(self) -> str:
        return self._text(self.system)

    @property
    def user_text(self) -> str:
        users = [m for m in self.messages if m.role == "user"]
        return self._text(users[-1].content) if users else ""

    @property
    def cache_markers(self) -> tuple[str, ...]:
        """Texts of every block marked cacheable, system first."""
        out = []
        for content in (self.system, *(m.content for m in self.messages)):
            if content is None or isinstance(content, str):
                continue
            out.extend(b.text for b in content
                       if isinstance(b, TextBlock) and b.cache)
        return tuple(out)


@dataclass(frozen=True, slots=True)
class MockReply:
    """An explicit canned reply, when the defaults are not enough."""

    text: Any  # str, or a Mapping/Sequence to be JSON-encoded
    stop_reason: str = "end_turn"
    model: str | None = None
    usage: Any = None


#: What a response can be specified as: a payload (string, or an object to be
#: JSON-encoded), a :class:`MockReply`, a ready :class:`ModelResponse`, or a
#: callable taking the :class:`MockCall` — which is how a reply varies with the
#: requested budget.
Spec = Any

_DEFAULT_USAGE = {"input_tokens": 1, "cache_creation_input_tokens": 0,
                  "cache_read_input_tokens": 0, "output_tokens": 1}


class MockModel:
    """A deterministic offline :class:`Model`.

    Every call is recorded **first, unconditionally**, before any raise. That is
    what lets "this must not be called" be asserted after the fact — which
    matters, because ``propose_plan`` catches model errors and falls back, so a
    double that raises from inside the call cannot enforce anything. See
    :class:`UnexpectedCall`.

    Args:
        responses: spec per stage.
        by_label: spec per ``label`` (a table name, say), checked before
            ``responses``. This replaces the older benchmark double that routed
            per-table by regex-scraping the table name out of the prompt.
        raises: an exception to raise for every call, or one per stage. This is
            how "fail *this* path into its fallback" is expressed, as distinct
            from "forbid *that* one" — an intent the previous doubles conflated.
        model_id: what the backend reports as its own model.
        response_model: what the *response* reports, so requested-vs-returned
            stays distinguishable the way run-meta's ``model_requested`` /
            ``models_returned`` pair compares them.
    """

    def __init__(
        self,
        responses: dict[str, Spec] | None = None,
        *,
        by_label: dict[str, Spec] | None = None,
        raises: BaseException | dict[str, BaseException] | None = None,
        model_id: str = "mock-model",
        response_model: str | None = None,
        stop_reason: str = "end_turn",
        usage: dict[str, int] | None = None,
    ):
        self._responses = dict(responses or {})
        self._by_label = dict(by_label or {})
        self._raises = raises
        self._model_id = model_id
        self._response_model = response_model
        self._stop_reason = stop_reason
        self._usage = dict(usage) if usage else dict(_DEFAULT_USAGE)
        self.calls: list[MockCall] = []

    # -- Model -------------------------------------------------------------

    @property
    def model_id(self) -> str:
        return self._model_id

    def complete(
        self,
        *,
        stage: Stage,
        system: Any,
        messages: Sequence[Message],
        max_tokens: int,
        label: str | None = None,
    ) -> ModelResponse:
        call = MockCall(stage=stage, system=system, messages=tuple(messages),
                        max_tokens=max_tokens, label=label, index=len(self.calls))
        self.calls.append(call)  # first, always, before any raise

        if self._raises is not None:
            if isinstance(self._raises, dict):
                exc = self._raises.get(stage)
                if exc is not None:
                    raise exc
            else:
                raise self._raises

        spec = None
        if label is not None and label in self._by_label:
            spec = self._by_label[label]
        elif stage in self._responses:
            spec = self._responses[stage]
        else:
            raise UnexpectedCall(
                f"MockModel has no response for stage {stage!r}"
                + (f" / label {label!r}" if label else "")
                + f". Stages configured: {sorted(self._responses)}."
            )
        return self._resolve(spec, call)

    # -- resolution --------------------------------------------------------

    def _resolve(self, spec: Spec, call: MockCall) -> ModelResponse:
        while callable(spec) and not isinstance(spec, (str, bytes)):
            spec = spec(call)
        if isinstance(spec, ModelResponse):
            return spec
        if isinstance(spec, MockReply):
            return ModelResponse(
                text=self._encode(spec.text),
                stop_reason=spec.stop_reason,
                model=spec.model or self._response_model or self._model_id,
                usage=dict(spec.usage) if spec.usage else dict(self._usage),
            )
        return ModelResponse(
            text=self._encode(spec),
            stop_reason=self._stop_reason,
            model=self._response_model or self._model_id,
            usage=dict(self._usage),
        )

    @staticmethod
    def _encode(value: Any) -> str:
        if isinstance(value, str):
            return value
        import json
        return json.dumps(value)

    # -- introspection -----------------------------------------------------

    def requests(self, stage: str | None = None) -> list[MockCall]:
        return [c for c in self.calls if stage is None or c.stage == stage]

    def stages_called(self) -> list[str]:
        return [c.stage for c in self.calls]

    def budgets(self, stage: str | None = None) -> list[int]:
        """Requested ``max_tokens`` per call — the retry sequence, as observed."""
        return [c.max_tokens for c in self.requests(stage)]

    def assert_not_called(self, stage: str | None = None) -> None:
        got = self.requests(stage)
        assert not got, (
            f"expected no {stage or 'model'} call, got "
            f"{[(c.stage, c.label) for c in got]}"
        )

    def assert_called(self, stage: str | None = None,
                      times: int | None = None) -> None:
        got = self.requests(stage)
        assert got, f"expected a {stage or 'model'} call, got none"
        if times is not None:
            assert len(got) == times, (
                f"expected {times} {stage or 'model'} call(s), got {len(got)}")
