"""Column mapping backends: SchemaMapper acceptance rules (fake engine) and, when
MetaHarmonizer is installed, the real engine on the benchmark's cMD dictionaries."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from metaextractor.schema_mapping import LexicalColumnMapper, SchemaMapperColumnMapper

SCHEMA = ["sample_id", "sex", "body_site", "country", "treatment", "age", "disease"]


class _FakeEngine:
    """Returns a canned SchemaMapper row per column (stage 1 only)."""

    def __init__(self, rows):
        self.rows = rows
        self.settings = SimpleNamespace(fuzzy_thresh=92, value_percentage_thresh=0.2,
                                        numeric_thresh=0.6, field_alias_thresh=0.5)

    def stage1_match(self, col):
        return self.rows.get(col, {})

    def stage2_match(self, col):
        return {}

    def stage3_match(self, col):
        return {}


def _mapper(rows):
    m = object.__new__(SchemaMapperColumnMapper)
    m.engine = _FakeEngine(rows)
    m.paths = {}
    m.stages = (1, 2, 3)
    st = m.engine.settings
    m.thresholds = {"std_exact": 1.0, "alias_exact": 1.0, "std_fuzzy": 0.92, "alias_fuzzy": 0.92,
                    "value": st.value_percentage_thresh, "ontology": 0.2,
                    "numeric": st.numeric_thresh, "semantic": st.field_alias_thresh}
    return m


def _row(field, score, method, stage="stage1"):
    return {"match1": field, "match1_score": score, "method": method, "stage": stage}


def test_candidate_accepted_only_at_its_methods_threshold():
    m = _mapper({"Gender": _row("sex", 1.0, "alias_exact"),
                 "Sampling site": _row("body_site", 0.62, "semantic", "stage3"),
                 "Cage": _row("country", 0.31, "semantic", "stage3"),     # below 0.5
                 "Nation": _row("country", 0.90, "std_fuzzy")})          # below 0.92
    cols = ["Gender", "Sampling site", "Cage", "Nation"]
    res = m.map_table(cols, [{c: "x" for c in cols}], SCHEMA)
    assert res.mapped == {"Gender": "sex", "Sampling site": "body_site"}
    assert res.unmapped == ["Cage", "Nation"]
    assert res.tier_used["Sampling site"] == "schemamapper:stage3:semantic(0.620)"


def test_collision_keeps_higher_score_and_excluded_targets_are_not_used():
    m = _mapper({"geo": _row("country", 0.7, "semantic", "stage3"),
                 "Country of origin": _row("country", 1.0, "alias_exact"),
                 "Treatment": _row("treatment", 1.0, "std_exact")})
    cols = ["geo", "Country of origin", "Treatment"]
    res = m.map_table(cols, [{c: "" for c in cols}], SCHEMA, exclude_targets={"treatment"})
    assert res.mapped == {"Country of origin": "country"}
    assert res.collisions == [("geo", "country")]
    assert set(res.unmapped) == {"geo", "Treatment"}


def test_lexical_backend_is_the_cascade():
    res = LexicalColumnMapper().map_table(["Gender", "Body Site"], [], SCHEMA)
    assert res.mapped == {"Gender": "sex", "Body Site": "body_site"}


DICTS = Path(__file__).resolve().parents[1] / "benchmarks" / "cmd_sonnet5" / "schemamapper"


@pytest.mark.skipif(importlib.util.find_spec("metaharmonizer") is None,
                    reason="MetaHarmonizer not installed")
def test_real_schemamapper_on_cmd_dictionaries_is_offline():
    m = SchemaMapperColumnMapper(DICTS / "cmd_target_attrs.csv",
                                 DICTS / "cmd_target_attrs_alias_haiku.csv",
                                 DICTS / "cmd_target_attrs_allowed_values.json")
    m.engine.nci_client = None     # any NCI lookup would now raise
    cols = ["Gender", "Country", "Treatment", "Cage"]
    rows = [{"Gender": g, "Country": "USA", "Treatment": t, "Cage": str(i)}
            for i, (g, t) in enumerate([("male", "MTX"), ("female", "naive")] * 3)]
    names = [l.split(",")[0] for l in (DICTS / "cmd_target_attrs.csv").read_text().splitlines()[1:]]
    res = m.map_table(cols, rows, names)
    assert res.mapped.get("Gender") == "sex"
    assert res.mapped.get("Country") == "country"
    assert res.mapped.get("Treatment") == "treatment"
    d = m.describe()
    assert d["backend"] == "schemamapper" and d["target_schema_sha256"]
