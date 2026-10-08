"""Cheap bounded judgments, behind a seam, with an audit trail.

Several decisions in this pipeline are *bounded*: is this table a per-sample
metadata table, does this string describe a cohort or one sample, should this
table be re-read with a structure plan. Each is currently made by a hand-tuned
threshold or regex, and each one's accuracy is unknown because nothing recorded
whether it was right.

This module is the seam such judgments go through. It exists so that:

* a judgment can be *measured* offline before anything is wired to it;
* a judgment can be swapped from a heuristic to a model without the call site
  changing;
* every call is archived, so a run can be audited after the fact;
* a failed judgment falls back to today's heuristic rather than aborting.

**Nothing in the extraction path calls this yet, by design.** The sequence is:
build the seam, probe each candidate offline against the committed runs, publish
a GO/NO-GO per candidate, then wire only the GOs behind a flag that defaults off.
Wiring first and measuring later is how a pipeline acquires a layer nobody can
account for.

Three question shapes
---------------------

:meth:`DecisionModel.yes_no`, :meth:`~DecisionModel.choose` and
:meth:`~DecisionModel.score`. All three return a :class:`Verdict` carrying the
answer, a confidence, and the raw text, so a caller can threshold on confidence
and abstain.

On calibration, honestly
------------------------

:class:`HaikuDecisionModel` asks a small generative model for a verdict and a
self-reported confidence. A self-reported number is **not** a calibrated
probability: it cannot be relied on to mean that 70% of its 0.7 answers are
right. For a yes/no or pick-one-of-N judgment that is usually good enough,
because the answer carries the decision and the confidence only gates abstention.
For a *ranking* -- "which of these twenty tables most likely holds the metadata"
-- it is the weak case, and the probe should say so rather than treating the
number as a probability. A properly calibrated classifier would be better there;
that is a later decision, and this seam is what would let it be swapped in
without touching a call site.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from metaextractor.model import (
    Message,
    Model,
    ModelCallError,
    TextBlock,
    new_usage,
)

#: Stage name used for decision calls, so they are distinguishable in a model's
#: call log and in :class:`~metaextractor.model.MockModel` routing.
STAGE_DECISION = "decision"

#: Default judge. The cheapest model in the pricing table; a bounded judgment
#: does not need a frontier model, and the point of the layer is that it is cheap
#: enough to ask often.
DEFAULT_DECISION_MODEL = "claude-haiku-4-5"

#: Confidence below which a caller should abstain and use its heuristic instead.
#: Deliberately exposed rather than hidden: it is a policy knob, and the probe
#: is what should set it per judgment.
DEFAULT_MIN_CONFIDENCE = 0.6


class DecisionError(RuntimeError):
    """A judgment could not be obtained. Callers fall back; they never abort."""


@dataclass(frozen=True)
class Verdict:
    """One judgment.

    Attributes:
        answer: ``True``/``False`` for yes/no, the chosen option for a choice, a
            float in [0, 1] for a score, or ``None`` when the judge abstained.
        confidence: the judge's self-reported confidence in [0, 1]. **Not** a
            calibrated probability -- see the module docstring.
        reason: a short justification, when the judge gave one.
        raw: the judge's unparsed reply, for auditing.
        fell_back: ``True`` when this verdict came from the caller's heuristic
            because the judge failed or abstained.
    """

    answer: Any
    confidence: float = 0.0
    reason: str | None = None
    raw: str | None = None
    fell_back: bool = False

    @property
    def usable(self) -> bool:
        return self.answer is not None and not self.fell_back

    def at_least(self, min_confidence: float) -> bool:
        """Whether this verdict is confident enough to act on."""
        return self.usable and self.confidence >= min_confidence


@runtime_checkable
class DecisionModel(Protocol):
    """What a bounded judgment goes through."""

    def yes_no(self, question: str, context: str, *,
               label: str | None = None) -> Verdict: ...

    def choose(self, question: str, options: Sequence[str], context: str, *,
               label: str | None = None) -> Verdict: ...

    def score(self, question: str, context: str, *,
              label: str | None = None) -> Verdict: ...


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

@dataclass
class DecisionArchive:
    """Append-only JSONL record of every judgment made in a run.

    The point is auditability: a run that routed differently because of a
    judgment should be explainable afterwards without re-running it. Writes are
    best-effort -- an unwritable archive must never fail an extraction.
    """

    path: Path | None = None
    entries: list[dict] = field(default_factory=list)

    def record(self, **entry: Any) -> None:
        entry["utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.entries.append(entry)
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # auditing must not be able to break a run

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            key = e.get("kind", "?") + (":fallback" if e.get("fell_back") else "")
            out[key] = out.get(key, 0) + 1
        return out


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

_SYSTEM = """You answer one bounded question about a scientific paper's data.

Rules:
- Answer ONLY from the provided context. Do not use outside knowledge.
- If the context does not settle the question, abstain: set "answer" to null.
- Abstaining is correct and expected when the evidence is absent. A guess is worse
  than an abstention, because the caller has a deterministic fallback.
- Reply with a single JSON object and nothing else.

Reply shape:
{"answer": <answer>, "confidence": <0.0-1.0>, "reason": "<= 20 words"}

"answer" is true/false for a yes-no question, one of the listed options verbatim
for a choice, a number in [0,1] for a score, or null to abstain.
"confidence" is how sure you are, where 1.0 means the context states it outright."""


def _parse(raw: str) -> tuple[Any, float, str | None]:
    """Pull ``(answer, confidence, reason)`` out of a judge's reply."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    text = text[start:i + 1]
                    break
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise DecisionError(f"judge reply was not JSON: {e}") from e
    if not isinstance(payload, dict):
        raise DecisionError("judge reply was not a JSON object")
    try:
        conf = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = payload.get("reason")
    return payload.get("answer"), max(0.0, min(1.0, conf)), (
        str(reason) if reason is not None else None)


class HaikuDecisionModel:
    """A :class:`DecisionModel` backed by a cheap generative model.

    Goes through :class:`~metaextractor.model.Model`, so it shares the usage
    accounting, the retry mechanism and the offline
    :class:`~metaextractor.model.MockModel` with everything else.
    """

    def __init__(self, llm: Model, *, archive: DecisionArchive | None = None,
                 max_tokens: int = 256):
        self.llm = llm
        self.archive = archive or DecisionArchive()
        self.max_tokens = max_tokens
        self.usage = new_usage()

    def _ask(self, kind: str, question: str, context: str,
             options: Sequence[str] | None, label: str | None) -> Verdict:
        prompt = [f"Question: {question}"]
        if options:
            prompt.append("Options (answer with one, verbatim):\n"
                          + "\n".join(f"- {o}" for o in options))
        prompt.append(f"Context:\n{context}")
        try:
            resp = self.llm.complete(
                stage=STAGE_DECISION,
                system=[TextBlock(_SYSTEM, cache=True)],
                messages=[Message.user("\n\n".join(prompt))],
                max_tokens=self.max_tokens,
                label=label,
            )
        except ModelCallError as e:
            self.archive.record(kind=kind, question=question, label=label,
                                error=f"{type(e).__name__}: {e}", fell_back=True)
            raise DecisionError(str(e)) from e

        for k in ("input_tokens", "cache_creation_input_tokens",
                  "cache_read_input_tokens", "output_tokens"):
            self.usage[k] += resp.usage[k]
        self.usage["n_calls"] += 1

        answer, conf, reason = _parse(resp.text)
        if options and answer is not None and answer not in options:
            # A judge that invents an option has not answered the question.
            self.archive.record(kind=kind, question=question, label=label,
                                answer=answer, invalid_option=True, fell_back=True)
            raise DecisionError(f"judge chose {answer!r}, not one of {list(options)}")
        if kind == "yes_no" and answer is not None and not isinstance(answer, bool):
            raise DecisionError(f"judge gave {answer!r} for a yes/no question")
        if kind == "score" and answer is not None:
            try:
                answer = max(0.0, min(1.0, float(answer)))
            except (TypeError, ValueError) as e:
                raise DecisionError(f"judge gave {answer!r} for a score") from e

        self.archive.record(kind=kind, question=question, label=label,
                            answer=answer, confidence=conf, reason=reason,
                            model=resp.model, fell_back=False)
        return Verdict(answer=answer, confidence=conf, reason=reason, raw=resp.text)

    def yes_no(self, question: str, context: str, *,
               label: str | None = None) -> Verdict:
        return self._ask("yes_no", question, context, None, label)

    def choose(self, question: str, options: Sequence[str], context: str, *,
               label: str | None = None) -> Verdict:
        if not options:
            raise ValueError("choose() needs at least one option")
        return self._ask("choose", question, context, list(options), label)

    def score(self, question: str, context: str, *,
              label: str | None = None) -> Verdict:
        return self._ask("score", question, context, None, label)


class MockDecisionModel:
    """A deterministic, offline :class:`DecisionModel`.

    Answers are looked up by ``label`` first, then by question substring, then
    fall back to ``default``. Every call is recorded, so a test can assert what
    was asked as well as what was answered.
    """

    def __init__(self, answers: dict[str, Any] | None = None, *,
                 by_question: dict[str, Any] | None = None,
                 default: Any = None,
                 confidence: float = 1.0,
                 raises: BaseException | None = None,
                 archive: DecisionArchive | None = None):
        self._answers = dict(answers or {})
        self._by_question = dict(by_question or {})
        self._default = default
        self._confidence = confidence
        self._raises = raises
        self.archive = archive or DecisionArchive()
        self.calls: list[dict] = []

    def _resolve(self, kind: str, question: str, context: str,
                 options: Sequence[str] | None, label: str | None) -> Verdict:
        self.calls.append({"kind": kind, "question": question, "label": label,
                           "options": list(options) if options else None,
                           "context": context})
        if self._raises is not None:
            raise self._raises
        if label is not None and label in self._answers:
            answer = self._answers[label]
        else:
            answer = self._default
            for needle, value in self._by_question.items():
                if needle in question:
                    answer = value
                    break
        if callable(answer):
            answer = answer(self.calls[-1])
        conf = 0.0 if answer is None else self._confidence
        self.archive.record(kind=kind, question=question, label=label,
                            answer=answer, confidence=conf, fell_back=False)
        return Verdict(answer=answer, confidence=conf, raw=json.dumps(
            {"answer": answer, "confidence": conf}))

    def yes_no(self, question: str, context: str, *,
               label: str | None = None) -> Verdict:
        return self._resolve("yes_no", question, context, None, label)

    def choose(self, question: str, options: Sequence[str], context: str, *,
               label: str | None = None) -> Verdict:
        return self._resolve("choose", question, context, list(options), label)

    def score(self, question: str, context: str, *,
              label: str | None = None) -> Verdict:
        return self._resolve("score", question, context, None, label)

    # -- introspection -----------------------------------------------------

    def asked(self, kind: str | None = None) -> list[dict]:
        return [c for c in self.calls if kind is None or c["kind"] == kind]

    def assert_not_called(self) -> None:
        assert not self.calls, f"expected no judgment, got {len(self.calls)}"


def judge_or_fallback(
    judge: DecisionModel | None,
    heuristic: Any,
    ask,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    archive: DecisionArchive | None = None,
    label: str | None = None,
) -> Verdict:
    """Ask ``judge``, falling back to ``heuristic`` on any failure or abstention.

    This is the shape every wired judgment must take: the pipeline behaves
    exactly as it does today when no judge is configured, when the judge errors,
    when it abstains, and when it answers below ``min_confidence``. A decision
    layer that can change an outcome by failing is worse than no decision layer.

    Args:
        judge: the decision model, or ``None`` to use the heuristic outright.
        heuristic: today's answer, used whenever the judge does not supply one.
        ask: ``callable(judge) -> Verdict``, the judgment to make.
        min_confidence: below this the judge's answer is discarded.
    """
    if judge is None:
        return Verdict(answer=heuristic, confidence=1.0, fell_back=True)
    try:
        verdict = ask(judge)
    except (DecisionError, ModelCallError) as e:
        if archive is not None:
            archive.record(kind="fallback", label=label, error=str(e), fell_back=True)
        return Verdict(answer=heuristic, confidence=1.0, fell_back=True)
    if not verdict.at_least(min_confidence):
        if archive is not None:
            archive.record(kind="fallback", label=label, fell_back=True,
                           answer=verdict.answer, confidence=verdict.confidence,
                           below_threshold=True)
        return Verdict(answer=heuristic, confidence=verdict.confidence,
                       reason=verdict.reason, raw=verdict.raw, fell_back=True)
    return verdict
