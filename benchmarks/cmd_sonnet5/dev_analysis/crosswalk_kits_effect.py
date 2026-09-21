#!/usr/bin/env python
"""What giving ``sequencing_platform`` and ``dna_extraction_kit`` a crosswalk does.

Both fields declare ``corpus.type = custom_enum`` in the registry, so until now neither
was harmonized: their values were compared as surface strings. That made the schema's
display vocabulary ("Illumina HiSeq") score wrong against cMD's curated vocabulary
("IlluminaHiSeq") even when the extraction named the right instrument. This scores each
tree with and without the two new crosswalks so the effect is attributable.

out_v3 is scored through ``scoring_addendum``'s comparable configuration -- the TettAJ
gold union and a fan-out replay under the current rules -- so the out_v3/out_v4 rows
differ only in the run, not in the scoring conventions.

Usage: CMD_CURATION_DIR=... CMD_BODYSITE_CORPUS=.../bodysite_corpus_uberon_full.csv \
         python dev_analysis/crosswalk_kits_effect.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))

import bench                                                    # noqa: E402
from crosswalk import Harmonizer                                # noqa: E402
from bench_paths import AGE_RULES, SCHEMA                      # noqa: E402
from metaextractor import sample_rules as sr                    # noqa: E402
from metaextractor.schema_loader import load_schema_file        # noqa: E402
from scoring_addendum import RUNS, MODELS, replay               # noqa: E402

NEW = ("sequencing_platform", "dna_extraction_kit")


def band(vals):
    return f"{statistics.median(vals):.3f} [{min(vals):.3f}-{max(vals):.3f}]"


def score(tree: pathlib.Path, manifest, harm, *, schema=None, rules=None, tmpdir):
    """Pooled content counts per run, plus per-field tp_wrong pooled over all runs."""
    out, wrong = {}, collections.Counter()
    for run in RUNS:
        e2e, cond = bench._zero(), bench._zero()
        for m in manifest:
            rj = tree / run / f"{m['study']}.json"
            if not rj.exists():
                continue
            scored = rj
            if schema is not None:
                scored = replay(rj, schema, rules, tmpdir / f"{run}_{m['study']}.json")
            rec = bench.score_study(m, scored, harm)
            bench._add(e2e, rec["end_to_end"]["content"])
            bench._add(cond, rec["conditional"]["content"])
            for f, c in rec["fields_end_to_end"].items():
                wrong[f] += c["tp_wrong"]
            if scored is not rj:
                scored.unlink(missing_ok=True)
        out[run] = {"all_curated": bench.metrics(e2e), "matched": bench.metrics(cond)}
    return out, wrong


def main() -> None:
    manifest = bench.load_manifest()
    schema = load_schema_file(SCHEMA)
    rules = sr.AgeBoundRules.from_json(AGE_RULES)
    rows, wrongs = {}, {}
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        cases = [
            ("out_v3", "3 fields", BENCH / "out_v3", BENCH / "crosswalks_uberon", 0.0, True),
            ("out_v3", "5 fields", BENCH / "out_v3", BENCH / "crosswalks_uberon_kits", 0.0, True),
            ("out_v3", "5 fields, t=.80", BENCH / "out_v3", BENCH / "crosswalks_uberon_kits", 0.80, True),
            ("out_v4", "3 fields", BENCH / "out_v4", BENCH / "out_v4" / "crosswalks_3field", 0.0, False),
            ("out_v4", "5 fields", BENCH / "out_v4", BENCH / "out_v4" / "crosswalks", 0.0, False),
            ("out_v4", "5 fields, t=.80", BENCH / "out_v4", BENCH / "out_v4" / "crosswalks", 0.80, False),
        ]
        for tree_name, label, tree, cw, ms, needs_replay in cases:
            print(f"scoring {tree_name} / {label}", flush=True)
            harm = Harmonizer(cw, min_score=ms)
            res, wrong = score(tree, manifest, harm,
                               schema=schema if needs_replay else None,
                               rules=rules if needs_replay else None, tmpdir=tmp)
            rows[(tree_name, label)] = res
            wrongs[(tree_name, label)] = wrong

    hdr = "| tree | crosswalks | model | all-curated P | all-curated R | all-curated F1 | matched F1 |"
    lines = [hdr, "|---|---|---|--:|--:|--:|--:|"]
    for (tree_name, label), res in rows.items():
        for model, runs in MODELS.items():
            g = lambda key, met: band([res[r][key][met] for r in runs])
            lines.append(f"| {tree_name} | {label} | {model} | {g('all_curated','precision')} | "
                         f"{g('all_curated','recall')} | {g('all_curated','f1')} | {g('matched','f1')} |")
    table = "\n".join(lines)
    print("\n" + table)

    print("\n=== tp_wrong on the two newly harmonized fields (pooled over 6 runs) ===")
    wl = ["| tree | field | 3 fields | 5 fields | 5 fields, t=.80 |", "|---|---|--:|--:|--:|"]
    for tree_name in ("out_v3", "out_v4"):
        for f in NEW:
            a = wrongs[(tree_name, "3 fields")][f]
            b = wrongs[(tree_name, "5 fields")][f]
            c = wrongs[(tree_name, "5 fields, t=.80")][f]
            wl.append(f"| {tree_name} | `{f}` | {a} | {b} | {c} |")
    wtable = "\n".join(wl)
    print(wtable)

    out = HERE / "crosswalk_kits_effect.md"
    out.write_text("# Crosswalks for the two custom-enum fields\n\n" + table +
                   "\n\n## tp_wrong on the two newly harmonized fields (pooled over 6 runs)\n\n" +
                   wtable + "\n")
    (HERE / "crosswalk_kits_effect.json").write_text(json.dumps(
        {f"{t}|{l}": r for (t, l), r in rows.items()}, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
