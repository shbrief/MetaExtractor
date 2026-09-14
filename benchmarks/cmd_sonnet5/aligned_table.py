#!/usr/bin/env python
"""Produce the identity-aligned content headline (MANUSCRIPT Section 3.1 table).

Value-accuracy is reported ONLY on samples we can identity-match to gold: each
study is aligned on the first available shared unique id (``ncbi_accession`` →
``sample_id`` → ``subject_id``) via ``bench.align_samples``. Studies that carry
no gold-overlapping id — QinJ (study-level, 0 samples), TettAJ / FanY (no shared
id), LiJ (6/196 enumerated), LiSS (per-run extraction vs per-subject gold pooled
under ``;``) — contribute nothing; their exclusion is the ingestion-ceiling
result, not a scoring gap. This is the deliberate, rigor-driven counterpart to
the positional join, which scores all ten studies for P/R/F1/FP but is NOT used
for value-accuracy.

For each (model, run) it pools matched-row content cells across studies, then
reports median [min–max] across the RUNS repeats. Run from the benchmark dir:

    python aligned_table.py out_ms_refined
    python aligned_table.py out_ms_refined --align-key ncbi_accession   # legacy 4-study

Writes <TREE>/aligned_aggregate.json and prints the manuscript table rows.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path.home() / "OmicsMLRepo/MetaExtractor/src"))

import bench  # noqa: E402  (align_samples, build_field_map, META_FIELDS, UNIT_FIELDS_ALL)
from metaextractor.evaluation import evaluate, load_extraction, load_gold_tsv  # noqa: E402

MODELS = ["sonnet", "haiku"]
RUNS = 3
DEFAULT_KEY = "ncbi_accession,sample_id,subject_id"


def _prf(a: dict):
    tp = a["tp_correct"] + a["tp_wrong"]
    P = tp / (tp + a["fp"]) if tp + a["fp"] else None
    R = tp / (tp + a["fn"]) if tp + a["fn"] else None
    F = 2 * P * R / (P + R) if P and R else None
    V = a["tp_correct"] / tp if tp else None
    return P, R, F, V


def _rng(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, None
    return st.median(vals), min(vals), max(vals)


def _score_run(run_dir: Path, manifest: list[dict], align_key: str):
    """Pool matched-row content cells across studies for one run dir.
    Returns (pooled_cells, matched_studies)."""
    pooled = dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0)
    matched: list[tuple[str, str, int]] = []
    keys = [k.strip() for k in align_key.split(",") if k.strip()]
    for m in manifest:
        rj = run_dir / f"{m['study']}.json"
        if not rj.exists():
            continue
        ext = load_extraction(rj)
        gold = load_gold_tsv(m["gold_tsv"])
        if not gold:
            continue
        gcols = list(gold[0].keys())
        fmap = bench.build_field_map(gcols)
        ufields = {k: v for k, v in bench.UNIT_FIELDS_ALL.items() if k in fmap and v in gcols}
        content_keys = [k for k in fmap if k not in bench.META_FIELDS]
        on = [k for k in keys if k in gcols]
        data = ext.model_dump() if hasattr(ext, "model_dump") else dict(ext)
        a_ext, a_gold, nmatch, ngold, _next, used = bench.align_samples(
            data.get("samples", []), gold, on)
        if nmatch == 0:
            continue
        res = evaluate(extraction={**data, "samples": a_ext}, gold_rows=a_gold,
                       field_map=fmap, unit_fields=ufields)
        for k in content_keys:
            fm = res.per_field.get(k)
            if fm is None:
                continue
            pooled["tp_correct"] += fm.tp_correct
            pooled["tp_wrong"] += fm.tp_wrong
            pooled["fn"] += fm.fn
            pooled["fp"] += fm.fp
        matched.append((m["study"], used, nmatch))
    return pooled, matched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", nargs="?", default="out_ms_refined")
    ap.add_argument("--manifest", default=str(HERE / "manifest.json"))
    ap.add_argument("--align-key", default=DEFAULT_KEY)
    args = ap.parse_args()

    tree = Path(args.tree)
    tree = tree if tree.is_absolute() else HERE / tree
    manifest = json.loads(Path(args.manifest).read_text())

    out = {"align_key": args.align_key, "models": {}}
    print(f"identity-aligned headline — tree={tree.name}  key={args.align_key}\n")
    print("| model | P | R | F1 | val-acc | fp | studies |")
    print("|---|---|---|---|---|---|---|")
    for model in MODELS:
        Ps, Rs, Fs, Vs, fps = [], [], [], [], []
        study_set: dict[str, str] = {}
        for k in range(1, RUNS + 1):
            rd = tree / f"{model}_r{k}"
            if not rd.exists():
                continue
            pooled, matched = _score_run(rd, manifest, args.align_key)
            P, R, F, V = _prf(pooled)
            Ps.append(P); Rs.append(R); Fs.append(F); Vs.append(V); fps.append(pooled["fp"])
            for stu, used, _n in matched:
                study_set[stu] = used
        def cell(rng, nd=3):
            med, lo, hi = rng
            if med is None:
                return "–"
            f = (lambda x: f"{x:.0f}") if nd == 0 else (lambda x: f"{x:.{nd}f}")
            return f"{f(med)} [{f(lo)}–{f(hi)}]"
        out["models"][model] = {
            "P": _rng(Ps), "R": _rng(Rs), "F1": _rng(Fs), "vacc": _rng(Vs),
            "fp": _rng(fps), "studies": study_set,
        }
        studies_str = ", ".join(f"{s}({u})" for s, u in study_set.items())
        print(f"| {model} | {cell(_rng(Ps))} | {cell(_rng(Rs))} | {cell(_rng(Fs))} | "
              f"{cell(_rng(Vs))} | {cell(_rng(fps), 0)} | {len(study_set)} |")
        print(f"|   ↳ matched: {studies_str}")

    (tree / "aligned_aggregate.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {tree/'aligned_aggregate.json'}")


if __name__ == "__main__":
    main()
