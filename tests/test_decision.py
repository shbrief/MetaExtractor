"""Tests for metaextractor.decision — the bounded-judgment seam.

Nothing in the extraction path calls this yet; these tests pin the contract the
probe will measure against, and in particular the fallback property, which is
what makes the layer safe to enable at all.
"""
from __future__ import annotations

import json

import pytest

from metaextractor.decision import (
    DEFAULT_MIN_CONFIDENCE,
    STAGE_DECISION,
    DecisionArchive,
    DecisionError,
    DecisionModel,
    HaikuDecisionModel,
    MockDecisionModel,
    Verdict,
    judge_or_fallback,
)
from metaextractor.model import MockModel, ModelCallError


def _llm(payload, **kw):
    """A MockModel answering the decision stage with ``payload``."""
    return MockModel(responses={STAGE_DECISION: payload}, **kw)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_usable_requires_an_answer_and_no_fallback(self):
        assert Verdict(answer=True, confidence=0.9).usable
        assert not Verdict(answer=None, confidence=0.9).usable
        assert not Verdict(answer=True, confidence=0.9, fell_back=True).usable

    def test_at_least_thresholds_on_confidence(self):
        v = Verdict(answer=True, confidence=0.5)
        assert v.at_least(0.5)
        assert not v.at_least(0.51)

    def test_an_abstention_is_never_at_least_anything(self):
        assert not Verdict(answer=None, confidence=1.0).at_least(0.0)


# ---------------------------------------------------------------------------
# HaikuDecisionModel
# ---------------------------------------------------------------------------

class TestHaikuDecisionModel:
    def test_satisfies_the_protocol(self):
        assert isinstance(HaikuDecisionModel(_llm("{}")), DecisionModel)

    def test_yes_no_parses_a_boolean(self):
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 0.8,
                                     "reason": "stated in Methods"}))
        v = j.yes_no("Is this a per-sample table?", "ctx")
        assert v.answer is True and v.confidence == 0.8
        assert v.reason == "stated in Methods"

    def test_choose_requires_one_of_the_options(self):
        j = HaikuDecisionModel(_llm({"answer": "stool", "confidence": 0.9}))
        assert j.choose("Which site?", ["stool", "oral"], "ctx").answer == "stool"

    def test_choose_rejects_an_invented_option(self):
        """A judge that invents an option has not answered the question."""
        j = HaikuDecisionModel(_llm({"answer": "spleen", "confidence": 0.99}))
        with pytest.raises(DecisionError, match="not one of"):
            j.choose("Which site?", ["stool", "oral"], "ctx")

    def test_choose_with_no_options_is_a_programming_error(self):
        with pytest.raises(ValueError):
            HaikuDecisionModel(_llm("{}")).choose("q", [], "ctx")

    def test_score_is_clamped_to_the_unit_interval(self):
        j = HaikuDecisionModel(_llm({"answer": 1.7, "confidence": 0.5}))
        assert j.score("How likely?", "ctx").answer == 1.0
        j = HaikuDecisionModel(_llm({"answer": -3, "confidence": 0.5}))
        assert j.score("How likely?", "ctx").answer == 0.0

    def test_confidence_is_clamped(self):
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 42}))
        assert j.yes_no("q", "ctx").confidence == 1.0

    def test_missing_confidence_is_zero(self):
        j = HaikuDecisionModel(_llm({"answer": True}))
        assert j.yes_no("q", "ctx").confidence == 0.0

    def test_abstention_is_a_null_answer(self):
        j = HaikuDecisionModel(_llm({"answer": None, "confidence": 0.0,
                                     "reason": "not stated"}))
        v = j.yes_no("q", "ctx")
        assert v.answer is None and not v.usable

    def test_non_boolean_answer_to_a_yes_no_is_an_error(self):
        j = HaikuDecisionModel(_llm({"answer": "probably", "confidence": 0.9}))
        with pytest.raises(DecisionError, match="yes/no"):
            j.yes_no("q", "ctx")

    def test_a_fenced_reply_is_parsed(self):
        j = HaikuDecisionModel(_llm('```json\n{"answer": true, "confidence": 1}\n```'))
        assert j.yes_no("q", "ctx").answer is True

    def test_prose_around_the_object_is_tolerated(self):
        j = HaikuDecisionModel(_llm('Sure! {"answer": false, "confidence": 0.7} Hope that helps.'))
        assert j.yes_no("q", "ctx").answer is False

    def test_non_json_reply_raises(self):
        j = HaikuDecisionModel(_llm("I think probably yes"))
        with pytest.raises(DecisionError, match="not JSON"):
            j.yes_no("q", "ctx")

    def test_a_model_failure_becomes_a_decision_error(self):
        j = HaikuDecisionModel(MockModel(raises=ModelCallError("down")))
        with pytest.raises(DecisionError):
            j.yes_no("q", "ctx")

    def test_usage_is_accumulated(self):
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 1}))
        j.yes_no("q", "ctx")
        j.yes_no("q", "ctx")
        assert j.usage["n_calls"] == 2
        assert j.usage["output_tokens"] == 2

    def test_the_system_prompt_is_cached(self):
        """The judge's system prompt is invariant, so it should hit the cache."""
        llm = _llm({"answer": True, "confidence": 1})
        HaikuDecisionModel(llm).yes_no("q", "ctx")
        assert len(llm.calls[0].cache_markers) == 1

    def test_options_reach_the_prompt(self):
        llm = _llm({"answer": "a", "confidence": 1})
        HaikuDecisionModel(llm).choose("Which?", ["a", "b"], "ctx")
        assert "- a" in llm.calls[0].user_text and "- b" in llm.calls[0].user_text

    def test_label_is_forwarded_to_the_model(self):
        llm = _llm({"answer": True, "confidence": 1})
        HaikuDecisionModel(llm).yes_no("q", "ctx", label="t.xlsx")
        assert llm.calls[0].label == "t.xlsx"


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

class TestArchive:
    def test_records_every_call(self):
        arc = DecisionArchive()
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 0.9}), archive=arc)
        j.yes_no("q1", "ctx")
        j.yes_no("q2", "ctx")
        assert len(arc.entries) == 2
        assert [e["question"] for e in arc.entries] == ["q1", "q2"]
        assert all("utc" in e for e in arc.entries)

    def test_records_a_failure(self):
        arc = DecisionArchive()
        j = HaikuDecisionModel(MockModel(raises=ModelCallError("down")), archive=arc)
        with pytest.raises(DecisionError):
            j.yes_no("q", "ctx")
        assert arc.entries[0]["fell_back"] is True
        assert "error" in arc.entries[0]

    def test_writes_jsonl_to_disk(self, tmp_path):
        path = tmp_path / "sub" / "decisions.jsonl"
        arc = DecisionArchive(path=path)
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 1}), archive=arc)
        j.yes_no("q", "ctx")
        j.yes_no("q", "ctx")
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["answer"] is True

    def test_an_unwritable_archive_never_breaks_a_run(self, tmp_path):
        """Auditing must not be able to fail an extraction."""
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        arc = DecisionArchive(path=blocker / "nested" / "a.jsonl")
        j = HaikuDecisionModel(_llm({"answer": True, "confidence": 1}), archive=arc)
        assert j.yes_no("q", "ctx").answer is True   # no raise
        assert len(arc.entries) == 1                 # still recorded in memory

    def test_summary_counts_by_kind(self):
        arc = DecisionArchive()
        arc.record(kind="yes_no", fell_back=False)
        arc.record(kind="yes_no", fell_back=True)
        arc.record(kind="choose", fell_back=False)
        assert arc.summary() == {"yes_no": 1, "yes_no:fallback": 1, "choose": 1}


# ---------------------------------------------------------------------------
# MockDecisionModel
# ---------------------------------------------------------------------------

class TestMockDecisionModel:
    def test_satisfies_the_protocol(self):
        assert isinstance(MockDecisionModel(), DecisionModel)

    def test_answers_by_label(self):
        j = MockDecisionModel(answers={"t1.xlsx": True, "t2.xlsx": False})
        assert j.yes_no("q", "c", label="t1.xlsx").answer is True
        assert j.yes_no("q", "c", label="t2.xlsx").answer is False

    def test_answers_by_question_substring(self):
        j = MockDecisionModel(by_question={"per-sample": True, "matrix": False})
        assert j.yes_no("Is this per-sample?", "c").answer is True
        assert j.yes_no("Is this a matrix?", "c").answer is False

    def test_default_is_used_when_nothing_matches(self):
        assert MockDecisionModel(default=True).yes_no("q", "c").answer is True

    def test_default_none_means_abstain(self):
        v = MockDecisionModel().yes_no("q", "c")
        assert v.answer is None and v.confidence == 0.0 and not v.usable

    def test_callable_answer_sees_the_call(self):
        j = MockDecisionModel(default=lambda call: call["label"] == "yes")
        assert j.yes_no("q", "c", label="yes").answer is True
        assert j.yes_no("q", "c", label="no").answer is False

    def test_records_what_was_asked(self):
        j = MockDecisionModel(default="a")
        j.choose("Which?", ["a", "b"], "the context", label="t")
        call = j.asked("choose")[0]
        assert call["options"] == ["a", "b"]
        assert call["context"] == "the context"
        assert call["label"] == "t"

    def test_assert_not_called(self):
        j = MockDecisionModel()
        j.assert_not_called()
        j.yes_no("q", "c")
        with pytest.raises(AssertionError):
            j.assert_not_called()

    def test_raises_on_demand(self):
        j = MockDecisionModel(raises=DecisionError("nope"))
        with pytest.raises(DecisionError):
            j.yes_no("q", "c")


# ---------------------------------------------------------------------------
# judge_or_fallback — the property that makes the layer safe
# ---------------------------------------------------------------------------

class TestJudgeOrFallback:
    def test_no_judge_means_the_heuristic_unchanged(self):
        v = judge_or_fallback(None, "heuristic", lambda j: j.yes_no("q", "c"))
        assert v.answer == "heuristic" and v.fell_back

    def test_a_confident_judge_wins(self):
        j = MockDecisionModel(default="judged", confidence=0.95)
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"))
        assert v.answer == "judged" and not v.fell_back

    def test_a_failing_judge_falls_back(self):
        j = MockDecisionModel(raises=DecisionError("down"))
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"))
        assert v.answer == "heuristic" and v.fell_back

    def test_a_model_call_error_falls_back(self):
        j = MockDecisionModel(raises=ModelCallError("transport"))
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"))
        assert v.answer == "heuristic" and v.fell_back

    def test_an_abstaining_judge_falls_back(self):
        j = MockDecisionModel(default=None)
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"))
        assert v.answer == "heuristic" and v.fell_back

    def test_a_low_confidence_judge_falls_back(self):
        j = MockDecisionModel(default="judged", confidence=0.4)
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"),
                              min_confidence=0.6)
        assert v.answer == "heuristic" and v.fell_back
        assert v.confidence == 0.4   # the judge's number is kept for auditing

    def test_the_threshold_is_inclusive(self):
        j = MockDecisionModel(default="judged", confidence=DEFAULT_MIN_CONFIDENCE)
        v = judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"))
        assert v.answer == "judged"

    def test_fallbacks_are_archived(self):
        arc = DecisionArchive()
        j = MockDecisionModel(default="judged", confidence=0.1)
        judge_or_fallback(j, "heuristic", lambda jj: jj.yes_no("q", "c"),
                          archive=arc, label="t")
        assert any(e.get("below_threshold") for e in arc.entries)

    def test_every_failure_mode_yields_the_heuristic(self):
        """The whole safety argument, enumerated."""
        for judge in (None,
                      MockDecisionModel(default=None),
                      MockDecisionModel(default="x", confidence=0.0),
                      MockDecisionModel(raises=DecisionError("e")),
                      MockDecisionModel(raises=ModelCallError("e"))):
            v = judge_or_fallback(judge, "heuristic", lambda jj: jj.yes_no("q", "c"))
            assert v.answer == "heuristic", judge
