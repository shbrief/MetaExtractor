#!/usr/bin/env python
"""Scoring-only addendum on ``out_v3``: what changes without re-extracting.

Three corrections were made after ``out_v3`` was scored, none of which touches the model:

1. **Gold set.** cMD splits PMID 31607556 across ``TettAJ_2019_a``/``_b``/``_c``; the
   manifest named only ``_b``, and the extraction enumerated ``_c``'s samples, so that
   study matched nothing. ``manifest.json`` now lists all three tables.
2. **Fan-out annotations.** ``scope``, ``propagate_study_value`` and ``unit_of`` moved into
   the registry schema table, adding ``ancestry``, ``country``, ``lifestyle``, ``location``
   and ``westernized`` to the propagation allowlist, and a heterogeneity sentinel now
   blocks a cohort-variety value ("Mixed", "Multiple countries") from reaching samples.
3. **Harmonization threshold.** ``Harmonizer(min_score=...)`` leaves a below-threshold
   OntologyMapper match unmapped instead of assigning a term its nearest concept.

Each is applied cumulatively so its own contribution is visible. ``out_v3`` is read-only
here: records are replayed in memory and results are written under ``--outdir``.

**Replaying a block, not just an addition.** ``fan_out_fields_to_samples`` never overwrites
a filled cell, so replaying it over saved records can only *add* cells — a value the old
rules propagated is already written and would survive. Cells written by fan-out are
therefore stripped first, using each cell's recorded ``sample_provenance``, so the current
rules decide every propagated cell from scratch. Without this the sentinel is invisible.

  CMD_CURATION_DIR=... python dev_analysis/scoring_addendum.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))
import bench                                                  # noqa: E402
from bench_paths import AGE_RULES, SCHEMA, load_manifest      # noqa: E402
from crosswalk import Harmonizer                              # noqa: E402

from metaextractor import sample_rules as sr                  # noqa: E402
from metaextractor.output import ExtractionResult             # noqa: E402
from metaextractor.schema_loader import load_schema_file      # noqa: E402

RUNS = ("sonnet_r1", "sonnet_r2", "sonnet_r3", "haiku_r1", "haiku_r2", "haiku_r3")
MODELS = {"Sonnet 5": RUNS[:3], "Haiku 4.5": RUNS[3:]}
FANOUT_SOURCES = ("study_fanout", "subgroup_fanout")


def strip_fanout(result: ExtractionResult) -> int:
    """Remove every cell a previous fan-out wrote, so the current rules decide it afresh."""
    sr.ensure_provenance(result)
    removed = 0
    for sample, prov in zip(result.samples, result.sample_provenance):
        for field, source in list(prov.items()):
            if str(source).split(":", 1)[0] in FANOUT_SOURCES:
                sample.pop(field, None)
                prov.pop(field, None)
                removed += 1
    return removed


def replay(path: Path, schema, rules, tmp: Path) -> Path:
    """Saved records re-fanned under the current schema; returns a path to score."""
    res = ExtractionResult.model_validate_json(path.read_text())
    strip_fanout(res)
    sr.fan_out_fields_to_samples(res, schema)
    sr.normalize_age_bounds(res, rules, schema)
    tmp.write_text(res.model_dump_json())
    return tmp


def score_tree(manifest, harm, *, schema=None, rules=None, runs=RUNS, tmpdir: Path,
               tally: dict | None = None) -> dict:
    """Pooled content counts per run. ``schema`` given => replay fan-out first.

    ``tally`` collects fan-out cell counts before/after the replay and the reasons the
    current rules gave for blocking, so the stage's effect is attributable.
    """
    out = {}
    for run in runs:
        e2e, cond = bench._zero(), bench._zero()
        for m in manifest:
            rj = BENCH / "out_v3" / run / f"{m['study']}.json"
            scored = rj
            if schema is not None and rj.exists():
                if tally is not None:
                    res = ExtractionResult.model_validate_json(rj.read_text())
                    sr.ensure_provenance(res)
                    tally["before"] += sum(
                        1 for prov in res.sample_provenance for src in prov.values()
                        if str(src).split(":", 1)[0] in FANOUT_SOURCES)
                    strip_fanout(res)
                    for k, v in sr.fan_out_fields_to_samples(res, schema).items():
                        tally[k] = tally.get(k, 0) + v
                    tally["after"] += sum(
                        1 for prov in res.sample_provenance for src in prov.values()
                        if str(src).split(":", 1)[0] in FANOUT_SOURCES)
                scored = replay(rj, schema, rules, tmpdir / f"{run}_{m['study']}.json")
            rec = bench.score_study(m, scored, harm)
            bench._add(e2e, rec["end_to_end"]["content"])
            bench._add(cond, rec["conditional"]["content"])
            if scored is not rj:
                scored.unlink(missing_ok=True)
        out[run] = {"all_curated": bench.metrics(e2e), "matched": bench.metrics(cond)}
    return out


def band(vals: list[float]) -> str:
    return f"{statistics.median(vals):.3f} [{min(vals):.3f}-{max(vals):.3f}]"


def summarise(res: dict, key: str, metric: str) -> dict[str, str]:
    return {model: band([res[r][key][metric] for r in runs]) for model, runs in MODELS.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outdir", default=str(BENCH / "addendum_v3"))
    ap.add_argument("--min-score", type=float, default=0.80,
                    help="threshold for stage 3 (default 0.80)")
    ap.add_argument("--crosswalks", default=None,
                    help="crosswalk directory (default: out_v3/crosswalks). Point it at a "
                         "directory regenerated against a different corpus to rescore on that "
                         "corpus; set $CMD_BODYSITE_CORPUS to the matching body_site corpus.")
    ap.add_argument("--kit-crosswalks", default=None,
                    help="crosswalk directory that additionally covers the two custom_enum "
                         "fields (sequencing_platform, dna_extraction_kit), for stage 5. "
                         "Default: crosswalks_uberon_kits. Pass '' to skip stage 5.")
    args = ap.parse_args()
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    tmpdir = outdir / "_replay"; tmpdir.mkdir(exist_ok=True)

    manifest = load_manifest()
    schema = load_schema_file(SCHEMA)
    rules = sr.AgeBoundRules.from_json(AGE_RULES)
    cw = Path(args.crosswalks) if args.crosswalks else BENCH / "out_v3" / "crosswalks"
    if not cw.is_absolute():
        cw = BENCH / cw

    # The baseline is out_v3 as published: TettAJ scored against `_b` alone. Select that
    # table by name — `gold_rel[0]` is `_a`, which would silently score a different study.
    def as_published(m: dict) -> dict:
        rel = m["gold_rel"]
        if isinstance(rel, str):
            return m
        only = [r for r in rel if f"/{m['study']}/" in r]
        assert len(only) == 1, f"cannot identify the published gold table for {m['study']}"
        return dict(m, gold_rel=only[0])

    single = [as_published(m) for m in manifest]

    kit_cw = (BENCH / "crosswalks_uberon_kits" if args.kit_crosswalks is None
              else Path(args.kit_crosswalks) if args.kit_crosswalks else None)
    if kit_cw is not None and not kit_cw.is_absolute():
        kit_cw = BENCH / kit_cw
    n = 5 if kit_cw is not None else 4

    stages = {}
    print(f"stage 1/{n}  baseline (gold = TettAJ_2019_b only, records as saved)", flush=True)
    stages["baseline"] = score_tree(single, Harmonizer(cw), tmpdir=tmpdir)
    print(f"stage 2/{n}  + TettAJ gold union", flush=True)
    stages["gold_union"] = score_tree(manifest, Harmonizer(cw), tmpdir=tmpdir)
    print(f"stage 3/{n}  + fan-out under the current rules", flush=True)
    tally = {"before": 0, "after": 0}
    stages["fanout"] = score_tree(manifest, Harmonizer(cw), schema=schema, rules=rules,
                                  tmpdir=tmpdir, tally=tally)
    print(f"stage 4/{n}  + harmonization threshold (min_score={args.min_score})", flush=True)
    harm_t = Harmonizer(cw, min_score=args.min_score)
    stages["threshold"] = score_tree(manifest, harm_t, schema=schema, rules=rules,
                                     tmpdir=tmpdir)
    if kit_cw is not None:
        # The two corpus.type = custom_enum fields were compared as surface strings, so the
        # schema's display vocabulary scored wrong against cMD's curated tokens even when the
        # extraction named the right instrument. Same threshold, five harmonized fields.
        print(f"stage 5/{n}  + crosswalks for the two custom_enum fields", flush=True)
        harm_k = Harmonizer(kit_cw, min_score=args.min_score)
        assert {"sequencing_platform", "dna_extraction_kit"} <= set(harm_k.fields), harm_k.fields
        stages["custom_enum_crosswalks"] = score_tree(
            manifest, harm_k, schema=schema, rules=rules, tmpdir=tmpdir)

    payload = {
        "source_tree": str(BENCH / "out_v3"),
        "crosswalks": str(cw),
        "kit_crosswalks": str(kit_cw) if kit_cw else None,
        "min_score": args.min_score,
        "below_threshold": {f: [list(r) for r in rows]
                            for f, rows in harm_t.below_threshold.items()},
        "fanout_tally": tally,
        "stages": stages,
    }
    (outdir / "addendum.json").write_text(json.dumps(payload, indent=2, default=str))

    labels = {"baseline": "out_v3 as published", "gold_union": "+ TettAJ gold union",
              "fanout": "+ current fan-out rules", "threshold": f"+ threshold {args.min_score}",
              "custom_enum_crosswalks": "+ custom-enum crosswalks"}
    labels = {k: v for k, v in labels.items() if k in stages}
    lines = ["| stage | model | all-curated P | all-curated R | all-curated F1 | matched F1 |",
             "|---|---|---|---|---|---|"]
    for key, label in labels.items():
        for model in MODELS:
            r = stages[key]
            lines.append(
                f"| {label} | {model} | {summarise(r, 'all_curated', 'precision')[model]} "
                f"| {summarise(r, 'all_curated', 'recall')[model]} "
                f"| {summarise(r, 'all_curated', 'f1')[model]} "
                f"| {summarise(r, 'matched', 'f1')[model]} |")
    table = "\n".join(lines)
    blocked = {k: v for k, v in tally.items() if k.startswith("blocked")}
    notes = (
        "\n## Notes\n\n"
        f"**Fan-out.** Replaying the current rules over the saved records rewrites "
        f"{tally['before']} propagated cells as {tally['after']}. The reduction is not the\n"
        "heterogeneity sentinel: the seven slots that were unannotated when `out_v3` ran are\n"
        "now `scope: sample`, which subjects them to both the propagation allowlist and the\n"
        "subgroup gate, and `uncurated_metadata` became sample-scoped after `bench-v3`. So\n"
        "this stage measures every fan-out annotation change since that tag, not only the\n"
        "sentinel. Block reasons under the current rules: "
        + ", ".join(f"`{k}` {v}" for k, v in sorted(blocked.items())) + ".\n\n"
        "**The sentinel fires but never decides.** It blocks "
        f"{blocked.get('blocked_heterogeneous', 0)} cells, yet forcing\n"
        "`sample_rules.is_heterogeneous` to `False` reproduces this stage exactly, and not one\n"
        "sample cell differs. The gate sits ahead of the allowlist and subgroup checks, so every\n"
        "value it blocks would have been blocked by one of those anyway: the only study reporting\n"
        "cohort variety (`PasolliE_2019`: `Mixed`, `Multiple countries`, `Multiple ancestries`)\n"
        "declares subgroups, which stops a sample-scoped value on its own. The gate is therefore\n"
        "a guard for a case these ten studies do not contain -- a cohort-variety value on an\n"
        "allowlisted field in a study that declares no subgroups -- and it currently changes the\n"
        "reason a cell is withheld, not whether it is.\n")
    (outdir / "ADDENDUM.md").write_text(
        "# Scoring-only addendum on `out_v3`\n\n"
        "Median [min-max] over three repeats. No re-extraction: the same saved model\n"
        "responses are re-scored, with the fan-out replayed under the current schema.\n\n"
        + table + "\n" + notes)
    print("\n" + table)
    tmpdir.rmdir()
    print(f"\nwrote {outdir/'addendum.json'} and {outdir/'ADDENDUM.md'}")


if __name__ == "__main__":
    main()
