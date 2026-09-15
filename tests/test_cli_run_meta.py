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
        self.last_calls = [{"purpose": "fields", "max_tokens": 16384, "stop_reason": "end_turn"}]

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


class _FailingExtractor(_FakeExtractor):
    def extract(self, paper_text, schema, paper_id=None, tables=None):
        from metaextractor.extractor import ExtractionError
        raise ExtractionError("Model response truncated at max_tokens=64000", raw_response="{")


def _schema(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"fields": [{"name": "body_site", "description": "site",
                                              "type": "string"}]}))
    return schema


def test_run_meta_written_for_failed_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MetaExtractor", _FailingExtractor)
    paper = tmp_path / "paper.txt"
    paper.write_text("Methods.")
    meta = tmp_path / "meta.json"
    rc = cli.main(["--paper", str(paper), "--schema", str(_schema(tmp_path)), "--api-key",
                   "sk-test", "--model", "claude-sonnet-5", "--run-meta", str(meta)])
    assert rc == 2
    m = json.loads(meta.read_text())
    assert m["status"] == "failed" and "truncated" in m["error"]
    assert m["usage"]["output_tokens"] == 5 and m["cost_estimate"]["total_usd"] > 0
    assert m["calls"][0]["stop_reason"] == "end_turn"
    assert m["output"] is None


def test_fetch_cache_written_then_reused_without_network(tmp_path, monkeypatch):
    from metaextractor.fetcher import FetchedPaper
    from metaextractor.supplementary import Table

    fetches = []

    def fake_fetch(identifier, **kw):
        fetches.append(identifier)
        return FetchedPaper(text="BODY PRJEB7369", source="pmc_html", pmid="1", pmcid="2",
                            has_body=True,
                            supplementary_tables=[Table(name="m", source="ena", columns=["run"],
                                                        rows=[{"run": "ERR1"}],
                                                        raw_rows=[["run"], ["ERR1"]])])
    monkeypatch.setattr(cli, "fetch_paper", fake_fetch)
    monkeypatch.setattr(cli, "MetaExtractor", _FakeExtractor)
    cache = tmp_path / "frozen"
    args = ["--paper-id", "1", "--schema", str(_schema(tmp_path)), "--api-key", "sk-test",
            "--out", str(tmp_path / "o.json"), "--fetch-cache", str(cache)]
    assert cli.main(args) == 0
    assert (cache / "fetched.json").exists() and fetches == ["1"]
    meta = tmp_path / "meta.json"
    assert cli.main(args + ["--require-fetch-cache", "--run-meta", str(meta)]) == 0
    assert fetches == ["1"]  # second run read the frozen retrieval
    r = json.loads(meta.read_text())["retrieval"]
    assert r["frozen_retrieval"] == str(cache) and r["source"] == "pmc_html"
    assert json.loads(meta.read_text())["n_tables"] == 1


def test_require_fetch_cache_refuses_to_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "fetch_paper", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    rc = cli.main(["--paper-id", "1", "--schema", str(_schema(tmp_path)), "--api-key", "sk-test",
                   "--fetch-cache", str(tmp_path / "missing"), "--require-fetch-cache"])
    assert rc == 2
