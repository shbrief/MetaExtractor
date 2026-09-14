"""metaextract --save-text / --run-meta write audit artifacts."""
import json

from metaextractor import cli
from metaextractor.output import ExtractionResult


class _FakeExtractor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.last_usage = {"input_tokens": 10, "cache_creation_input_tokens": 0,
                           "cache_read_input_tokens": 0, "output_tokens": 5, "n_calls": 1}
        self.last_response_models = {"claude-sonnet-5"}

    def extract(self, paper_text, schema, paper_id=None, tables=None):
        return ExtractionResult(granularity="study_level", fields={})


def test_run_meta_and_saved_text(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MetaExtractor", _FakeExtractor)
    paper = tmp_path / "paper.txt"
    paper.write_text("Methods: stool samples were sequenced.")
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"fields": [{"name": "body_site", "description": "site",
                                              "type": "string"}]}))
    rules = tmp_path / "age.json"
    rules.write_text(json.dumps({"group_bounds": {"Adult": [18, 65]}}))
    meta, text, out = tmp_path / "meta.json", tmp_path / "text.txt", tmp_path / "out.json"
    rc = cli.main(["--paper", str(paper), "--schema", str(schema), "--api-key", "sk-test",
                   "--model", "claude-sonnet-5", "--out", str(out), "--save-text", str(text),
                   "--run-meta", str(meta), "--age-rules", str(rules)])
    assert rc == 0
    assert text.read_text() == paper.read_text()
    m = json.loads(meta.read_text())
    assert m["request"]["models_returned"] == ["claude-sonnet-5"]
    assert m["request"]["sampling_and_thinking"].startswith("not set")
    assert m["cost_estimate"]["pricing_as_of"]
    assert m["cost_estimate"]["total_usd"] > 0
    assert m["retrieval"] is None
