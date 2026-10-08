"""Tests for metaextractor.review — packet rendering, verdict pinning, aggregation.

``build_packet`` is a pure function, so these assert on the returned HTML string.
No browser, no network, no filesystem.
"""
from __future__ import annotations

import json

import pytest

from metaextractor.output import ExtractionResult, FieldResult, TableSelection
from metaextractor.review.packet import (
    ADJUDICATION_VERDICTS,
    DRAFT_VERDICTS,
    MAX_SAMPLE_ROWS,
    PacketMeta,
    build_packet,
    draft_sha256,
)
from metaextractor.review.report import aggregate_verdicts, cohens_kappa
from metaextractor.review.verdicts import VerdictError, load_verdicts, validate_verdicts

PAPER = (
    "Methods. We enrolled 42 adults in Italy. Stool samples were collected and "
    "DNA was extracted with the QIAamp DNA Stool Mini Kit. Sequencing used an "
    "Illumina HiSeq 2000."
)


def _result(**over) -> ExtractionResult:
    base = dict(
        paper_id="PMID:28144631",
        granularity="sample_level",
        subgroups=[],
        fields={
            "n_participants": FieldResult(
                value=42, extraction_type="directly_stated", confidence="high",
                evidence_quote="We enrolled 42 adults in Italy.", section="Methods"),
            "body_site": FieldResult(
                value="stool", extraction_type="directly_stated", confidence="high",
                evidence_quote="Stool samples were collected", section="Methods"),
            "dna_extraction_kit": FieldResult(
                value="QIAamp DNA Stool Mini Kit", extraction_type="directly_stated",
                confidence="medium",
                evidence_quote="DNA was extracted with the QIAamp DNA Stool Mini Kit",
                section="Methods"),
            "tumor_size": FieldResult(
                value="not_reported", extraction_type="not_reported",
                confidence="high", evidence_quote=None, section=None),
        },
        samples=[
            {"sample_id": "S1", "body_site": "stool", "country": "Italy"},
            {"sample_id": "S2", "body_site": "stool", "country": "Italy"},
        ],
        sample_provenance=[
            {"sample_id": "table:s1.tsv:ID", "body_site": "study_fanout",
             "country": "manifest:ena.tsv:country"},
            {"sample_id": "table:s1.tsv:ID", "body_site": "study_fanout",
             "country": "manifest:ena.tsv:country"},
        ],
        table_selection=[
            TableSelection(name="s1.tsv", selected=True, score=0.82,
                           matched_fields={"sample_id": "ID"}, reasons=["id column"]),
            TableSelection(name="abund.tsv", selected=False, score=0.0, is_matrix=True,
                           reasons=["dense numeric measurement grid"]),
        ],
        extraction_warnings=["Table 'abund.tsv': skipped as measurement matrix"],
    )
    base.update(over)
    return ExtractionResult(**base)


# ---------------------------------------------------------------------------
# draft_sha256
# ---------------------------------------------------------------------------

class TestDraftDigest:
    def test_is_stable_across_serialisations(self):
        r = _result()
        other = ExtractionResult.model_validate_json(r.model_dump_json())
        assert draft_sha256(r) == draft_sha256(other)

    def test_changes_when_a_value_changes(self):
        a = _result()
        b = _result()
        b.fields["body_site"].value = "oral cavity"
        assert draft_sha256(a) != draft_sha256(b)

    def test_is_64_hex_characters(self):
        sha = draft_sha256(_result())
        assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)


# ---------------------------------------------------------------------------
# build_packet — draft mode
# ---------------------------------------------------------------------------

class TestDraftPacket:
    def test_is_self_contained(self):
        """No external reference of any kind: a reviewer can work offline."""
        html = build_packet(_result())
        for forbidden in ("http://", "https://cdn", "<link", "<img", "@import",
                          "src=\"//"):
            assert forbidden not in html, f"packet references {forbidden!r}"
        assert "<style>" in html and "<script>" in html

    def test_source_links_are_the_one_allowed_outbound_reference(self):
        """The reviewer must be able to reach the paper; nothing else may be remote."""
        html = build_packet(_result(), meta=PacketMeta(
            source_links={"PubMed": "https://pubmed.ncbi.nlm.nih.gov/28144631/"}))
        assert "https://pubmed.ncbi.nlm.nih.gov/28144631/" in html
        assert html.count("https://") == 1

    def test_one_unit_per_reported_field_and_none_for_absent(self):
        html = build_packet(_result())
        assert 'data-unit="field:n_participants"' in html
        assert 'data-unit="field:body_site"' in html
        assert 'data-unit="field:tumor_size"' not in html, \
            "a not_reported field is not a unit to judge"
        assert html.count('data-unit="') == 3

    def test_every_unit_offers_the_draft_verdicts(self):
        html = build_packet(_result())
        for v in DRAFT_VERDICTS:
            assert f'value="{v}"' in html
        assert 'value="gold_wrong"' not in html, \
            "gold_wrong is adjudication-only: there is no gold in draft mode"

    def test_shows_the_machine_draft_banner(self):
        html = build_packet(_result())
        assert "machine output that no one has" in html

    def test_evidence_quote_is_shown(self):
        html = build_packet(_result())
        assert "We enrolled 42 adults in Italy." in html

    def test_verbatim_check_flags_a_quote_present_in_the_paper(self):
        html = build_packet(_result(), paper_text=PAPER)
        assert "quote found in the paper text" in html
        assert "quote NOT found in the paper text" not in html

    def test_verbatim_check_flags_a_quote_absent_from_the_paper(self):
        r = _result()
        r.fields["body_site"].evidence_quote = "a sentence the paper does not contain"
        html = build_packet(r, paper_text=PAPER)
        assert "quote NOT found in the paper text" in html

    def test_no_verbatim_flag_without_paper_text(self):
        html = build_packet(_result())
        assert "in the paper text" not in html

    def test_sample_cells_show_their_source_descriptor(self):
        html = build_packet(_result())
        assert "table:s1.tsv:ID" in html
        assert "manifest:ena.tsv:country" in html
        assert "study_fanout" in html

    def test_says_the_descriptor_is_a_column_not_a_row(self):
        """The packet must not imply precision the provenance does not have."""
        html = build_packet(_result())
        assert "not the row" in html or "not a row" in html

    def test_table_selection_shows_rejections_and_reasons(self):
        html = build_packet(_result())
        assert "abund.tsv" in html
        assert "dense numeric measurement grid" in html

    def test_escapes_html_in_values_and_quotes(self):
        r = _result()
        r.fields["body_site"].value = "<script>alert(1)</script>"
        r.fields["body_site"].evidence_quote = 'quote with "quotes" & <b>tags</b>'
        html = build_packet(r)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "&amp;" in html and "&lt;b&gt;" in html

    def test_embeds_the_draft_digest_for_localstorage_keying(self):
        r = _result()
        html = build_packet(r)
        assert draft_sha256(r) in html

    def test_long_sample_tables_are_cut_with_a_note(self):
        many = [{"sample_id": f"S{i}"} for i in range(MAX_SAMPLE_ROWS + 50)]
        html = build_packet(_result(samples=many, sample_provenance=[]))
        assert f"Showing the first {MAX_SAMPLE_ROWS} of {len(many)}" in html

    def test_handles_an_extraction_with_no_samples(self):
        html = build_packet(_result(samples=[], sample_provenance=[],
                                    granularity="study_level"))
        assert "Sample records" not in html
        assert html.count('data-unit="') == 3

    def test_handles_an_extraction_with_no_reported_fields(self):
        bare = _result(fields={"x": FieldResult(
            value="not_reported", extraction_type="not_reported", confidence="high")})
        html = build_packet(bare)
        assert "No units." in html

    def test_sample_fields_restricts_the_table(self):
        html = build_packet(_result(), sample_fields=["sample_id"])
        assert "manifest:ena.tsv:country" not in html


# ---------------------------------------------------------------------------
# build_packet — adjudication mode
# ---------------------------------------------------------------------------

class TestAdjudicationPacket:
    CELLS = [
        {"sample_idx": 0, "field": "body_site", "extracted": "stool",
         "gold": "feces", "decision": "TP_wrong"},
        {"sample_idx": 1, "field": "country", "extracted": "Italy",
         "gold": "not_reported", "decision": "FP"},
        {"sample_idx": 2, "field": "body_site", "extracted": "stool",
         "gold": "stool", "decision": "TP_correct"},
    ]

    def test_units_are_the_cells_not_the_fields(self):
        html = build_packet(_result(), cells=self.CELLS)
        assert html.count('data-unit="') == 3
        assert 'data-unit="cell:0:body_site"' in html
        assert 'data-unit="cell:1:country"' in html
        assert 'data-unit="field:n_participants"' not in html

    def test_offers_gold_wrong(self):
        html = build_packet(_result(), cells=self.CELLS)
        for v in ADJUDICATION_VERDICTS:
            assert f'value="{v}"' in html

    def test_shows_the_curated_value_and_the_scored_decision(self):
        html = build_packet(_result(), cells=self.CELLS)
        assert "feces" in html
        assert "TP_wrong" in html and "FP" in html

    def test_warns_that_some_units_are_controls(self):
        """A TP_correct control must not be flagged as such in the packet."""
        html = build_packet(_result(), cells=self.CELLS)
        assert "controls" in html

    def test_empty_cell_list_renders(self):
        html = build_packet(_result(), cells=[])
        assert "No units." in html
        assert 'mode": "adjudication"' in html or '"adjudication"' in html


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------

def _verdict_payload(sha: str, reviewer="rev1", **over) -> dict:
    payload = {
        "schema_version": 1,
        "draft_sha256": sha,
        "paper_id": "PMID:28144631",
        "mode": "draft",
        "reviewer": reviewer,
        "verdicts": [
            {"unit_id": "field:n_participants", "verdict": "supported"},
            {"unit_id": "field:body_site", "verdict": "wrong_value",
             "corrected_value": "feces"},
            {"unit_id": "field:dna_extraction_kit", "verdict": "cannot_determine"},
        ],
    }
    payload.update(over)
    return payload


class TestVerdictValidation:
    def test_accepts_a_well_formed_file(self):
        validate_verdicts(_verdict_payload("a" * 64))

    @pytest.mark.parametrize("drop", ["schema_version", "draft_sha256", "mode",
                                      "reviewer", "verdicts"])
    def test_rejects_a_missing_required_key(self, drop):
        p = _verdict_payload("a" * 64)
        del p[drop]
        with pytest.raises(VerdictError):
            validate_verdicts(p)

    def test_rejects_an_unknown_verdict_value(self):
        p = _verdict_payload("a" * 64)
        p["verdicts"][0]["verdict"] = "looks_fine_to_me"
        with pytest.raises(VerdictError):
            validate_verdicts(p)

    def test_rejects_a_malformed_digest(self):
        with pytest.raises(VerdictError):
            validate_verdicts(_verdict_payload("not-a-sha"))

    def test_rejects_an_unknown_mode(self):
        with pytest.raises(VerdictError):
            validate_verdicts(_verdict_payload("a" * 64, mode="vibes"))

    def test_validation_is_not_a_noop_without_jsonschema(self, monkeypatch):
        """The hand-written fallback must reject what the schema would."""
        import builtins
        real = builtins.__import__

        def no_jsonschema(name, *a, **k):
            if name == "jsonschema":
                raise ImportError("simulated")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", no_jsonschema)
        p = _verdict_payload("a" * 64)
        p["verdicts"][0]["verdict"] = "nonsense"
        with pytest.raises(VerdictError):
            validate_verdicts(p)


class TestVerdictPinning:
    def test_loads_a_file_pinned_to_the_right_draft(self, tmp_path):
        r = _result()
        sha = draft_sha256(r)
        p = tmp_path / "v.json"
        p.write_text(json.dumps(_verdict_payload(sha)))
        vf = load_verdicts(p, expect_sha256=sha)
        assert vf.reviewer == "rev1"
        assert vf.judged == 3
        assert vf.verdict_of("field:body_site") == "wrong_value"

    def test_refuses_a_file_pinned_to_a_different_draft(self, tmp_path):
        r = _result()
        other = _result()
        other.fields["body_site"].value = "oral cavity"
        p = tmp_path / "v.json"
        p.write_text(json.dumps(_verdict_payload(draft_sha256(other))))
        with pytest.raises(VerdictError, match="pinned to draft"):
            load_verdicts(p, expect_sha256=draft_sha256(r))

    def test_rejects_duplicate_units(self, tmp_path):
        payload = _verdict_payload("a" * 64)
        payload["verdicts"].append({"unit_id": "field:body_site", "verdict": "supported"})
        p = tmp_path / "v.json"
        p.write_text(json.dumps(payload))
        with pytest.raises(VerdictError, match="duplicate"):
            load_verdicts(p)

    def test_rejects_invalid_json(self, tmp_path):
        p = tmp_path / "v.json"
        p.write_text("{not json")
        with pytest.raises(VerdictError, match="not valid JSON"):
            load_verdicts(p)


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    def _files(self, tmp_path, *payloads):
        out = []
        for i, p in enumerate(payloads):
            f = tmp_path / f"v{i}.json"
            f.write_text(json.dumps(p))
            out.append(load_verdicts(f))
        return out

    def test_support_rate_excludes_cannot_determine(self, tmp_path):
        """2 determinable (1 supported), 1 abstention -> rate 0.5, not 0.333."""
        rep = aggregate_verdicts(self._files(tmp_path, _verdict_payload("a" * 64)))
        assert rep.n_judged == 3
        assert rep.n_determinable == 2
        assert rep.support_rate == pytest.approx(0.5)
        assert rep.abstention_rate == pytest.approx(1 / 3)

    def test_gold_wrong_counts_against_neither_side(self, tmp_path):
        p = _verdict_payload("a" * 64, mode="adjudication")
        p["verdicts"] = [
            {"unit_id": "cell:0:a", "verdict": "supported"},
            {"unit_id": "cell:1:b", "verdict": "gold_wrong"},
        ]
        rep = aggregate_verdicts(self._files(tmp_path, p))
        assert rep.n_determinable == 1
        assert rep.support_rate == pytest.approx(1.0)
        assert rep.counts["gold_wrong"] == 1

    def test_unjudged_units_are_reported_not_imputed(self, tmp_path):
        rep = aggregate_verdicts(self._files(tmp_path, _verdict_payload("a" * 64)),
                                 n_units_total=10)
        assert rep.n_expected == 10
        assert rep.n_unjudged == 7
        assert "7 unjudged" in rep.summary()

    def test_coverage_scales_with_the_number_of_reviewer_passes(self, tmp_path):
        """Two reviewers judging 3 units each is 6 of a possible 6, not 6 of 3."""
        a = _verdict_payload("a" * 64, reviewer="alice")
        b = _verdict_payload("a" * 64, reviewer="bob")
        rep = aggregate_verdicts(self._files(tmp_path, a, b), n_units_total=3)
        assert rep.n_judged == 6
        assert rep.n_expected == 6
        assert rep.n_unjudged == 0
        assert "-" not in rep.summary().split("judged     :")[1].split("\n")[0]

    def test_never_reports_negative_unjudged(self, tmp_path):
        """A miscounted unit total must warn, not print a negative."""
        rep = aggregate_verdicts(self._files(tmp_path, _verdict_payload("a" * 64)),
                                 n_units_total=1)
        assert rep.n_unjudged == 0
        assert "more judgments than units" in rep.summary()

    def test_per_field_breakdown(self, tmp_path):
        rep = aggregate_verdicts(self._files(tmp_path, _verdict_payload("a" * 64)))
        assert rep.per_field["n_participants"]["supported"] == 1
        assert rep.per_field["body_site"]["wrong_value"] == 1

    def test_summary_renders(self, tmp_path):
        rep = aggregate_verdicts(self._files(tmp_path, _verdict_payload("a" * 64)))
        text = rep.summary()
        assert "HUMAN REVIEW" in text and "support rate" in text


class TestKappa:
    def test_suppressed_below_the_overlap_floor(self):
        a = {"u1": "supported", "u2": "unsupported"}
        k = cohens_kappa(a, a, min_overlap=10)
        assert k.kappa is None and "fewer than 10" in k.note

    def test_perfect_agreement_with_two_categories(self):
        a = {f"u{i}": ("supported" if i % 2 else "unsupported") for i in range(20)}
        k = cohens_kappa(a, dict(a), min_overlap=10)
        assert k.kappa == pytest.approx(1.0)
        assert k.observed_agreement == pytest.approx(1.0)

    def test_single_category_is_undefined_not_perfect(self):
        """Both reviewers saying 'supported' to everything is not kappa=1."""
        a = {f"u{i}": "supported" for i in range(20)}
        k = cohens_kappa(a, dict(a), min_overlap=10)
        assert k.kappa is None
        assert "single category" in k.note

    def test_disagreement_lowers_kappa(self):
        a = {f"u{i}": ("supported" if i < 10 else "unsupported") for i in range(20)}
        b = dict(a)
        for i in range(5):
            b[f"u{i}"] = "unsupported"
        k = cohens_kappa(a, b, min_overlap=10)
        assert k.kappa is not None and 0.0 < k.kappa < 1.0

    def test_two_reviewers_produce_one_pair(self, tmp_path):
        sha = "a" * 64
        files = []
        for name in ("alice", "bob"):
            payload = _verdict_payload(sha, reviewer=name)
            payload["verdicts"] = [
                {"unit_id": f"field:f{i}",
                 "verdict": "supported" if (i % 2 == 0 or name == "alice")
                 else "unsupported"}
                for i in range(12)
            ]
            f = tmp_path / f"{name}.json"
            f.write_text(json.dumps(payload))
            files.append(load_verdicts(f))
        rep = aggregate_verdicts(files, min_overlap=10)
        assert len(rep.kappas) == 1
        k = rep.kappas[0]
        assert (k.reviewer_a, k.reviewer_b) == ("alice", "bob")
        assert k.n_overlap == 12

    def test_units_are_namespaced_by_draft(self, tmp_path):
        """The same unit id in two different drafts must not be treated as shared."""
        files = []
        for name, sha in (("alice", "a" * 64), ("bob", "b" * 64)):
            payload = _verdict_payload(sha, reviewer=name)
            payload["verdicts"] = [{"unit_id": f"field:f{i}", "verdict": "supported"}
                                   for i in range(12)]
            f = tmp_path / f"{name}.json"
            f.write_text(json.dumps(payload))
            files.append(load_verdicts(f))
        rep = aggregate_verdicts(files, min_overlap=1)
        assert rep.kappas[0].n_overlap == 0
