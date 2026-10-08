#!/usr/bin/env python3
"""Re-run the deterministic pipeline over the frozen retrievals, with no API calls.

What this is for
----------------

A refactor of the extraction path has to be shown not to have changed anything.
The real gate is a fresh benchmark run (``run_frozen.py run``), which costs about
70 minutes and US$22 and is the only thing that can speak to the model's own
behaviour or to cache hit rates. This script is the cheap, offline half of that
check, and it runs in seconds:

* the frozen retrieval supplies the paper text and parsed tables;
* the frozen run's own study-level fields are replayed as the canned model reply;
* the frozen run's own recorded table plans are replayed per table, by name, via
  ``MockModel(by_label=...)``.

Everything else runs for real -- relevance scoring, matrix rejection, the
structure-plan decision, column mapping, joining, scope-aware fan-out and the age
rules -- so a change in how records are assembled shows up as a different sample
count or a different provenance mix.

What it cannot tell you: whether the model would answer the same way, what the
cache hit rate is, or what the scores are. Those need the paid run.

Usage::

    python benchmarks/cmd_sonnet5/replay_frozen_offline.py                  # out_v4
    python benchmarks/cmd_sonnet5/replay_frozen_offline.py --out out_v3 --model-dir haiku_r1
    python benchmarks/cmd_sonnet5/replay_frozen_offline.py --verbose

Exit status is non-zero if any study's sample count or provenance mix differs
from the frozen run, so it is usable as a pre-merge check.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))

from metaextractor.extractor import MetaExtractor  # noqa: E402
from metaextractor.fetcher import FETCH_RECORD, load_fetched  # noqa: E402
from metaextractor.model import (  # noqa: E402
    STAGE_FIELDS,
    STAGE_SAMPLE_DISCOVERY,
    MockModel,
)
from metaextractor.sample_rules import AgeBoundRules  # noqa: E402
from metaextractor.schema_loader import load_schema_file  # noqa: E402

SCHEMA = HERE / "cmd.clean.linkml.yaml"
AGE_RULES = HERE / "age_rules_cmd.json"
MANIFEST = HERE / "manifest.json"


def _studies() -> list[str]:
    m = json.loads(MANIFEST.read_text())
    entries = m if isinstance(m, list) else m.get("studies", [])
    return [e["study"] for e in entries]


def _source_kinds(provenance: list[dict]) -> Counter:
    """How many cells came from each kind of source."""
    c: Counter = Counter()
    for row in provenance:
        for value in row.values():
            c[str(value).split(":")[0]] += 1
    return c


def replay(tree: Path, model_dir: str, study: str, schema, rules) -> dict:
    fetch_dir = tree / "_fetch" / study
    result_json = tree / model_dir / f"{study}.json"
    meta_json = tree / model_dir / f"{study}.meta.json"
    if not (fetch_dir / FETCH_RECORD).exists():
        return {"study": study, "skipped": "no frozen retrieval"}
    if not result_json.exists():
        return {"study": study, "skipped": "no frozen result"}

    fetched = load_fetched(fetch_dir)
    frozen = json.loads(result_json.read_text())
    plans: dict[str, dict] = {}
    if meta_json.exists():
        meta = json.loads(meta_json.read_text())
        plans = {c["table"]: c["plan"] for c in meta.get("calls", [])
                 if c.get("purpose") == "table_plan" and "plan" in c}

    reply = {"granularity": frozen["granularity"], "fields": frozen["fields"],
             "subgroups": frozen.get("subgroups", [])}
    llm = MockModel(responses={STAGE_FIELDS: reply, STAGE_SAMPLE_DISCOVERY: reply},
                    by_label=plans, model_id="replay")
    ex = MetaExtractor(llm=llm, age_rules=rules, batch_size=30)
    res = ex.extract(fetched.text, schema,
                     paper_id=str(frozen.get("paper_id") or ""),
                     tables=fetched.supplementary_tables or [])

    frozen_prov = frozen.get("sample_provenance") or []
    return {
        "study": study,
        "samples": len(res.samples),
        "frozen_samples": len(frozen.get("samples") or []),
        "sources": _source_kinds(res.sample_provenance),
        "frozen_sources": _source_kinds(frozen_prov),
        "plans_replayed": len(plans),
        "model_calls": len(llm.calls),
        "tables_selected": sum(1 for t in res.table_selection if t.selected),
        "tables_seen": len(res.table_selection),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="out_v4", help="run tree (default out_v4)")
    ap.add_argument("--model-dir", default="sonnet_r1",
                    help="which repeat inside the tree to replay (default sonnet_r1)")
    ap.add_argument("--studies", nargs="+", default=None)
    ap.add_argument("--verbose", action="store_true",
                    help="also print the per-source cell counts")
    args = ap.parse_args()

    tree = HERE / args.out
    if not tree.is_dir():
        raise SystemExit(f"no run tree {tree}")
    schema = load_schema_file(SCHEMA)
    rules = AgeBoundRules.from_dict(json.loads(AGE_RULES.read_text()))

    rows = [replay(tree, args.model_dir, s, schema, rules)
            for s in (args.studies or _studies())]

    print(f"replaying {args.out}/{args.model_dir} offline "
          f"(frozen retrieval + recorded plans, no API calls)\n")
    print(f"{'study':<26}{'samples':>9}{'frozen':>8}{'plans':>7}{'calls':>7}"
          f"{'tables':>8}  match")
    print("-" * 78)
    mismatched = []
    skipped = []
    for r in rows:
        if "skipped" in r:
            skipped.append(r)
            print(f"{r['study']:<26}{'-- ' + r['skipped']:>30}")
            continue
        same_n = r["samples"] == r["frozen_samples"]
        same_src = r["sources"] == r["frozen_sources"]
        if not (same_n and same_src):
            mismatched.append(r)
        flag = "yes" if same_n and same_src else ("count" if not same_n else "sources")
        tables = f"{r['tables_selected']}/{r['tables_seen']}"
        print(f"{r['study']:<26}{r['samples']:>9}{r['frozen_samples']:>8}"
              f"{r['plans_replayed']:>7}{r['model_calls']:>7}{tables:>8}  {flag}")
        if args.verbose:
            print(f"{'':<26}sources  {dict(r['sources'])}")
            if not same_src:
                print(f"{'':<26}frozen   {dict(r['frozen_sources'])}")
    print("-" * 78)

    compared = [r for r in rows if "skipped" not in r]
    print(f"{len(compared) - len(mismatched)} of {len(compared)} studies reproduce the "
          f"frozen run's sample count and provenance mix exactly"
          + (f"; {len(skipped)} skipped" if skipped else ""))
    if mismatched:
        print("\nMISMATCHED -- the deterministic path changed for:")
        for r in mismatched:
            print(f"  {r['study']}: {r['samples']} vs {r['frozen_samples']} samples")
        print("\nThis is what a behaviour-preserving refactor must not do. Bisect "
              "before running the paid benchmark.")
        return 1
    print("\nNote: this says nothing about model behaviour, cache hit rates or "
          "scores. Those need `run_frozen.py run`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
