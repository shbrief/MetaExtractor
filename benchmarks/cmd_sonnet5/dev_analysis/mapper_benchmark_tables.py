"""Historical analysis: uses ``metaextractor.schema_mapping.SchemaMapperColumnMapper``, which
was removed from MetaExtractor afterwards (SchemaMapper now runs in MetaHarmonizer on the
saved extraction table). Run it from a checkout of commit ``bc3b00b``.

Final scored tables (samples x schema attributes) for each column mapper, development studies.

For every mapper -- ``lexical`` (lexical cascade), ``sm_stage1`` (SchemaMapper name
dictionaries), ``sm_stages12`` (+ value matching), ``sm_stages123`` (+ embedding matching;
MetaHarmonizer default thresholds, LLM stage and NCI ontology matcher off) -- this writes the
table that ``bench.py`` scores against the curated ``*_sample.tsv``: one row per extracted
record, one column per schema field with a value, after table mapping, joining, fan-out, and
the age rules. No model calls; out_v3 is read only.

Two sets:

``manifest_studies/``
    The four single-manifest studies (Bengtsson-PalmeJ_2015, NayakRR_2021,
    Heitz-BuschartA_2016, ContevilleLC_2019). Records come from each study's ENA run
    manifest with BioSample attributes (fetched live from ENA / EBI BioSamples); the
    study-level answers are those of each out_v3 extraction (2 models x 3 repeats).

``smoke_haiku45/``
    PasolliE_2019, TettAJ_2019_b, LiJ_2017 from the Haiku 4.5 smoke run
    (``smoke_haiku45/run``, lexical mapper). The run's frozen retrieval and saved structure
    plans are replayed with each mapper; study-level answers are the run's own.

Each set has ``<mapper>/[<run>/]<study>.csv`` and ``scores.tsv`` (content fields, both joins,
out_v3 crosswalks; terms absent from them score as unmapped strings).

  CMD_CURATION_DIR=... HF_HUB_OFFLINE=1 python dev_analysis/mapper_benchmark_tables.py
"""
from __future__ import annotations

import copy
import csv
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))
import bench  # noqa: E402
from bench_paths import AGE_RULES, SCHEMA, SCHEMAMAPPER_DICTS, load_manifest  # noqa: E402
from crosswalk import Harmonizer  # noqa: E402

from metaextractor import sample_rules as sr  # noqa: E402
from metaextractor.extractor import MetaExtractor  # noqa: E402
from metaextractor.fetcher import load_fetched  # noqa: E402
from metaextractor.output import ExtractionResult  # noqa: E402
from metaextractor.schema_loader import load_schema_file  # noqa: E402
from metaextractor.schema_mapping import LexicalColumnMapper, SchemaMapperColumnMapper  # noqa: E402
from metaextractor.sra_manifest import manifest_for_paper  # noqa: E402

OUT = HERE / "mapper_benchmark_tables"
SMOKE = HERE / "smoke_haiku45"


class NoCall:
    class messages:
        @staticmethod
        def create(*a, **k):
            raise AssertionError("no model call")


class PlanReplay:
    """Answers table-plan requests with the plans saved in a run's ``.meta.json``."""

    def __init__(self, meta: dict):
        self.plans = {c["table"]: c["plan"] for c in meta["calls"]
                      if c["purpose"] == "table_plan" and "plan" in c}
        outer = self

        class messages:
            @staticmethod
            def create(**kw):
                name = re.search(r"Table name: (.*)\n", kw["messages"][0]["content"]).group(1)
                if name not in outer.plans:
                    raise AssertionError(f"no saved plan for {name!r}")
                return SimpleNamespace(
                    stop_reason="end_turn", model="replay",
                    content=[SimpleNamespace(type="text", text=json.dumps(outer.plans[name]))],
                    usage=SimpleNamespace(input_tokens=0, output_tokens=0,
                                          cache_creation_input_tokens=0, cache_read_input_tokens=0))
        self.messages = messages


def finalize(study_level: ExtractionResult, ex: MetaExtractor, samples: list[dict],
             schema, rules) -> ExtractionResult:
    """The extractor's post-table steps: sample records, provenance, fan-out, age rules."""
    res = study_level.model_copy(deep=True)
    res.granularity, res.samples = "sample_level", copy.deepcopy(samples)
    res.sample_provenance = [{k: ex.last_table_sources.get(k, "table") for k, v in s.items()
                              if not k.startswith("__") and v not in (None, "")}
                             for s in res.samples]
    if res.samples and res.fields:
        sr.fan_out_fields_to_samples(res, schema)
    sr.normalize_age_bounds(res, rules, schema)
    return res


def write_table(res: ExtractionResult, names: list[str], path: Path) -> None:
    """Samples x schema attributes: the fields the scorer compares, in schema order."""
    cols = [f for f in names if any(not sr.is_nr(s.get(f)) for s in res.samples)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for s in res.samples:
            w.writerow([sr.stringify(s.get(f)) if not sr.is_nr(s.get(f)) else "" for f in cols])


def score(mf: dict, res: ExtractionResult | None, harm, tmp: Path) -> dict:
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if res is None:
        tmp.unlink(missing_ok=True)
    else:
        tmp.write_text(res.model_dump_json())
    r = bench.score_study(mf, tmp, harm)
    tmp.unlink(missing_ok=True)
    e, c = r["end_to_end"]["content"], r["conditional"]["content"]
    return {"n_records": r["n_extracted"], "matched_rows": r["alignment"]["matched"],
            **{f"all_{k}": e[k] for k in ("tp_correct", "tp_wrong", "fp", "fn")},
            "f1_all_curated": bench.metrics(e)["f1"], "fn_matched": c["fn"],
            "f1_matched": bench.metrics(c)["f1"]}


def main() -> None:
    schema = load_schema_file(SCHEMA)
    names = [f.name for f in schema.fields]
    rules = sr.AgeBoundRules.from_json(AGE_RULES)
    harm = Harmonizer(BENCH / "out_v3" / "crosswalks")
    manifest = {m["study"]: m for m in load_manifest()}
    sm = SchemaMapperColumnMapper(SCHEMAMAPPER_DICTS["target"], SCHEMAMAPPER_DICTS["alias"],
                                  SCHEMAMAPPER_DICTS["values"])
    sm.engine.nci_client = None   # any NCI lookup would raise

    def staged(stages):
        m = copy.copy(sm)
        m.stages = stages
        return m

    mappers = {"lexical": LexicalColumnMapper(), "sm_stage1": staged((1,)),
               "sm_stages12": staged((1, 2)), "sm_stages123": staged((1, 2, 3))}
    tmp = OUT / "_score.json"

    # Manifest studies x out_v3 extractions.
    rows = []
    for study, mf in manifest.items():
        rec = json.loads((BENCH / "out_v3" / "_fetch" / study / "fetched.json").read_text())
        projects = re.findall(r"PRJ[A-Z]+\d+", (rec.get("sra_manifest_source") or "").split(" ")[0])
        if len(projects) != 1 or rec["n_tables"] != 1:
            continue
        man = manifest_for_paper("", explicit_project=projects[0]).table
        for mname, mapper in mappers.items():
            ex = MetaExtractor(client=NoCall(), column_mapper=mapper)
            samples, _, _ = ex._build_samples_from_tables([man], schema)
            for run in sorted(p for p in (BENCH / "out_v3").glob("*_r*") if p.is_dir()):
                rj = run / f"{study}.json"
                res = None
                if rj.exists():
                    res = finalize(ExtractionResult.model_validate_json(rj.read_text()), ex, samples,
                                   schema, rules)
                    write_table(res, names, OUT / "manifest_studies" / mname / run.name / f"{study}.csv")
                rows.append({"mapper": mname, "study": study, "run": run.name,
                             **score(mf, res, harm, tmp)})
    _write_scores(OUT / "manifest_studies" / "scores.tsv", rows)

    # Smoke run: replay saved structure plans with each mapper.
    rows = []
    for meta_path in sorted((SMOKE / "run").glob("*.meta.json")):
        study = meta_path.name.replace(".meta.json", "")
        meta = json.loads(meta_path.read_text())
        study_level = ExtractionResult.model_validate_json((SMOKE / "run" / f"{study}.json").read_text())
        tables = load_fetched(SMOKE / "_fetch" / study).supplementary_tables
        for mname, mapper in mappers.items():
            ex = MetaExtractor(client=PlanReplay(meta), column_mapper=mapper)
            samples, _, _ = ex._build_samples_from_tables(tables, schema)
            res = finalize(study_level, ex, samples, schema, rules)
            if mname == "lexical":   # the replay reproduces the run's own final records
                assert (res.samples, res.sample_provenance) == (
                    study_level.samples, study_level.sample_provenance), \
                    f"{study}: lexical replay differs from the run"
            write_table(res, names, OUT / "smoke_haiku45" / mname / f"{study}.csv")
            rows.append({"mapper": mname, "study": study, "run": "haiku45_smoke",
                         **score(manifest[study], res, harm, tmp)})
    _write_scores(OUT / "smoke_haiku45" / "scores.tsv", rows)
    print(f"wrote {OUT}")


def _write_scores(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else ("" if v is None else v))
                        for k, v in r.items()})


if __name__ == "__main__":
    main()
