"""extract() records a source for every sample cell and applies scoped fan-out."""
from metaextractor.extractor import MetaExtractor
from metaextractor.model import (
    STAGE_FIELDS,
    STAGE_SAMPLE_DISCOVERY,
    STAGE_TABLE_PLAN,
    MockModel,
    ModelCallError,
)
from metaextractor.sample_rules import AgeBoundRules
from metaextractor.schema import Field, Schema
from metaextractor.supplementary import Table


def _llm(payload) -> MockModel:
    """Answers the extraction stages with ``payload``; fails the plan call.

    The plan failure is deliberate and is the fallback path, not a prohibition.
    """
    return MockModel(
        responses={STAGE_FIELDS: payload, STAGE_SAMPLE_DISCOVERY: payload},
        raises={STAGE_TABLE_PLAN: ModelCallError("plan call disabled in this test")},
        response_model="claude-test-returned",
    )


def _fr(value):
    return {"value": value, "extraction_type": "directly_stated", "confidence": "high",
            "evidence_quote": "q", "section": "Methods"}


SCHEMA = Schema(fields=[
    Field(name="sample_id", description="id", type="string", scope="sample"),
    Field(name="disease", description="disease", type="string", scope="sample"),
    Field(name="sequencing_platform", description="platform", type="string", scope="study"),
    Field(name="age", description="age", type="string", scope="sample"),
    Field(name="age_min", description="min", type="string", scope="sample"),
    Field(name="age_max", description="max", type="string", scope="sample"),
])


def _table():
    raw = [["sample_id", "age"], ["S1", "40"], ["S2", "51"], ["S3", ""], ["S4", "33"]]
    cols = raw[0]
    rows = [dict(zip(cols, r)) for r in raw[1:]]
    return Table(name="samples.tsv", source="test", columns=cols, rows=rows, raw_rows=raw)


def test_table_path_provenance_fanout_and_age_rules():
    payload = {
        "granularity": "study_level",
        "fields": {"disease": _fr("Healthy; Hypertension"),
                   "sequencing_platform": _fr("Illumina HiSeq 2000"),
                   "age": _fr("45 ± 10")},
        "samples": [],
    }
    ex = MetaExtractor(llm=_llm(payload), age_rules=AgeBoundRules())
    r = ex.extract("paper text", SCHEMA, paper_id="1", tables=[_table()])
    assert len(r.samples) == 4 and len(r.sample_provenance) == 4
    s1, p1 = r.samples[0], r.sample_provenance[0]
    assert p1["sample_id"] == "table:samples.tsv:sample_id"
    assert p1["age"] == "table:samples.tsv:age"
    assert s1["sequencing_platform"] == "Illumina HiSeq 2000"
    assert p1["sequencing_platform"] == "study_fanout"
    assert "disease" not in s1                      # cohort list not propagated
    assert r.samples[2].get("age") in ("", None)    # aggregate study age not propagated
    assert "age" not in r.sample_provenance[2] and "age_min" not in r.samples[2]
    assert (s1["age_min"], s1["age_max"]) == ("40", "40")
    assert p1["age_min"] == "age_rule:specific_age"
    assert ex.last_response_models == {"claude-test-returned"}
    assert any("blocked_multi_valued" in w for w in r.extraction_warnings)


def test_llm_sample_rows_are_attributed_to_the_model():
    payload = {
        "granularity": "sample_level",
        "fields": {"sequencing_platform": _fr("Illumina")},
        "samples": [{"sample_id": "a", "disease": "RA"}, {"sample_id": "b", "disease": ""}],
    }
    r = MetaExtractor(llm=_llm(payload), sample_discovery=False).extract(
        "paper text", SCHEMA, paper_id="1")
    assert r.sample_provenance[0] == {"sample_id": "llm_sample", "disease": "llm_sample",
                                      "sequencing_platform": "study_fanout"}
    assert "disease" not in r.sample_provenance[1]
