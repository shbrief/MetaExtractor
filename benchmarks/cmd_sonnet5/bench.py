#!/usr/bin/env python
"""MetaExtractor benchmark harness against curatedMetagenomicData gold tables.

Two subcommands:

  run   manifest.json OUTDIR [--limit N] [--model M]
        For each study, fetch by PMID and extract sample-level metadata against
        the curatedmetagenomicdata LinkML target schema. Writes OUTDIR/<study>.json,
        OUTDIR/<study>.csv, and OUTDIR/<study>.runlog.txt (token usage / cost).

  eval  manifest.json OUTDIR [--limit N]
        Score each OUTDIR/<study>.json against its gold *_sample.tsv using an
        identity field crosswalk over (target-schema fields) ∩ (gold columns).
        Writes per-study cell TSVs, OUTDIR/summary.json and OUTDIR/REPORT.md.

Evaluation joins extracted samples to gold rows POSITIONALLY (samples[i] ↔ gold[i]),
so sample count / ordering alignment is itself a measured outcome.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SCHEMA = _HERE / "cmd.clean.linkml.yaml"  # produced by make_clean_schema.py
ATTRS = Path.home() / "OmicsMLRepo/MetaHarmonizerSchemaRegistry/schema/curatedmetagenomicdata/cmd_target_attrs.csv"

# Fields that are identifiers / provenance rather than scientific content.
# Evaluated but reported in a separate bucket from the headline content metric.
META_FIELDS = {
    "study_name", "sample_id", "subject_id", "pmid",
    "curator", "ncbi_accession", "host_species", "uncurated_metadata",
}
UNIT_FIELDS_ALL = {"age": "age_unit", "age_min": "age_unit", "age_max": "age_unit"}


def schema_fields() -> list[str]:
    with ATTRS.open() as fh:
        return [r["field_name"] for r in csv.DictReader(fh)]


def load_manifest(path: Path, limit: int | None) -> list[dict]:
    m = json.loads(Path(path).read_text())
    return m[:limit] if limit else m


# --------------------------------------------------------------------------- run
def cmd_run(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(args.manifest, args.limit)
    print(f"running {len(manifest)} studies, model={args.model}, schema={SCHEMA.name}\n")
    for i, m in enumerate(manifest, 1):
        study, pmid = m["study"], m["pmid"]
        out_json = outdir / f"{study}.json"
        if out_json.exists() and not args.force:
            print(f"[{i}/{len(manifest)}] {study}: exists, skip"); continue
        cmd = [
            "metaextract", "--paper-id", pmid, "--schema", str(SCHEMA),
            "--model", args.model, "--out", str(out_json),
            "--csv", str(outdir / f"{study}.csv"), "--csv-provenance",
        ]
        print(f"[{i}/{len(manifest)}] {study} pmid={pmid} (expect {m['n_samples']} samples) ...", flush=True)
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        dt = time.time() - t0
        (outdir / f"{study}.runlog.txt").write_text(
            f"cmd: {' '.join(cmd)}\nreturncode: {proc.returncode}\nelapsed_s: {dt:.1f}\n"
            f"--- stderr ---\n{proc.stderr}\n--- stdout(head) ---\n{proc.stdout[:2000]}\n"
        )
        tail = (proc.stderr.strip().splitlines() or ["<no stderr>"])[-1]
        status = "ok" if proc.returncode == 0 and out_json.exists() else f"FAIL rc={proc.returncode}"
        print(f"      -> {status} in {dt:.0f}s | {tail}")


# --------------------------------------------------------------------- run-tables
def _sra_meta_path(study: str) -> Path | None:
    p = (Path.home() / "Projects/cMD_architecture/curatedMetagenomicDataCuration/inst/curated"
         / study / f"{study}_sra_meta.tsv")
    return p if p.exists() else None


def cmd_run_tables(args: argparse.Namespace) -> None:
    """Deterministic tables= path: feed the study's raw SRA metadata table as a
    local supplementary file, skip the Europe PMC fetch. Per-sample rows come
    from the column-map+join pipeline; the LLM only does prose study-level fields."""
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(args.manifest, args.limit)
    print(f"running {len(manifest)} studies (tables= path), model={args.model}\n")
    for i, m in enumerate(manifest, 1):
        study, pmid = m["study"], m["pmid"]
        sra = _sra_meta_path(study)
        out_json = outdir / f"{study}.json"
        if out_json.exists() and not args.force:
            print(f"[{i}/{len(manifest)}] {study}: exists, skip"); continue
        if sra is None:
            print(f"[{i}/{len(manifest)}] {study}: NO sra_meta table, skip"); continue
        cmd = [
            "metaextract", "--paper-id", pmid, "--schema", str(SCHEMA),
            "--model", args.model, "--supplementary", str(sra), "--no-supplementary",
            "--out", str(out_json), "--csv", str(outdir / f"{study}.csv"), "--csv-provenance",
        ]
        print(f"[{i}/{len(manifest)}] {study} pmid={pmid} sra={sra.name} ...", flush=True)
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        dt = time.time() - t0
        (outdir / f"{study}.runlog.txt").write_text(
            f"cmd: {' '.join(cmd)}\nreturncode: {proc.returncode}\nelapsed_s: {dt:.1f}\n"
            f"--- stderr ---\n{proc.stderr}\n"
        )
        tail = (proc.stderr.strip().splitlines() or ["<no stderr>"])[-1]
        status = "ok" if proc.returncode == 0 and out_json.exists() else f"FAIL rc={proc.returncode}"
        print(f"      -> {status} in {dt:.0f}s | {tail}")


# -------------------------------------------------------------------------- eval
def _acc_key(v) -> str | None:
    """Normalize an ncbi_accession cell to its first run/sample token for joining."""
    if not v or str(v).strip().lower() in {"na", "nan", "not_reported", ""}:
        return None
    import re
    tok = re.split(r"[;,\s]+", str(v).strip())[0]
    return tok or None


def align_samples(ext_samples: list[dict], gold_rows: list[dict], key: str):
    """Reorder extracted samples to gold order by a shared accession key.
    Returns (aligned_ext, matched_gold, n_matched, n_gold, n_ext)."""
    idx: dict[str, dict] = {}
    for s in ext_samples:
        k = _acc_key(s.get(key))
        if k and k not in idx:
            idx[k] = s
    aligned_ext, matched_gold = [], []
    for g in gold_rows:
        k = _acc_key(g.get(key))
        if k and k in idx:
            aligned_ext.append(idx[k]); matched_gold.append(g)
    return aligned_ext, matched_gold, len(matched_gold), len(gold_rows), len(ext_samples)


def build_field_map(gold_cols: list[str]) -> dict[str, str]:
    fields = schema_fields()
    gc = set(gold_cols)
    return {f: f for f in fields if f in gc}


def cmd_eval(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(Path.home() / "OmicsMLRepo/MetaExtractor/src"))
    from metaextractor.evaluation import evaluate, load_extraction, load_gold_tsv

    outdir = Path(args.outdir)
    manifest = load_manifest(args.manifest, args.limit)

    def agg_over(fms, keys):
        a = dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0)
        for k in keys:
            fm = fms.get(k)
            if not fm:
                continue
            a["tn"] += fm.tn; a["tp_correct"] += fm.tp_correct; a["tp_wrong"] += fm.tp_wrong
            a["fn"] += fm.fn; a["fp"] += fm.fp
        return a

    per_study = []
    field_totals: dict[str, dict] = {}
    for m in manifest:
        study = m["study"]
        rj = outdir / f"{study}.json"
        if not rj.exists():
            per_study.append({"study": study, "error": "no extraction output"}); continue
        ext = load_extraction(rj)
        gold = load_gold_tsv(m["gold_tsv"])
        gold_cols = list(gold[0].keys()) if gold else []
        fmap = build_field_map(gold_cols)
        ufields = {k: v for k, v in UNIT_FIELDS_ALL.items() if k in fmap and v in gold_cols}

        data0 = ext.model_dump() if hasattr(ext, "model_dump") else dict(ext)
        n_ext_raw = len(data0.get("samples", []))
        align_note = None
        eval_ext = ext
        eval_gold = gold
        if args.align_key and args.align_key in gold_cols:
            a_ext, a_gold, nmatch, ngold, next_ = align_samples(
                data0.get("samples", []), gold, args.align_key)
            data0 = {**data0, "samples": a_ext}
            eval_ext = data0
            eval_gold = a_gold
            align_note = f"aligned on {args.align_key}: {nmatch}/{ngold} gold matched (ext={next_})"

        res = evaluate(extraction=eval_ext, gold_rows=eval_gold, field_map=fmap, unit_fields=ufields)
        if res.per_cell:
            res.to_cells_tsv(str(outdir / f"{study}.cells.tsv"))

        n_ext = n_ext_raw
        content_keys = [k for k in fmap if k not in META_FIELDS]
        meta_keys = [k for k in fmap if k in META_FIELDS]
        for k, fm in res.per_field.items():
            ft = field_totals.setdefault(k, dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0))
            ft["tn"] += fm.tn; ft["tp_correct"] += fm.tp_correct; ft["tp_wrong"] += fm.tp_wrong
            ft["fn"] += fm.fn; ft["fp"] += fm.fp
        per_study.append({
            "study": study, "pmid": m["pmid"],
            "n_gold": len(gold), "n_extracted": n_ext,
            "sample_align": align_note or ("match" if n_ext == len(gold)
                                           else f"MISMATCH ({n_ext} vs {len(gold)})"),
            "content": agg_over(res.per_field, content_keys),
            "meta": agg_over(res.per_field, meta_keys),
            "n_content_fields": len(content_keys),
            "faithfulness": {
                "contract_violations": len(res.faithfulness.get("contract_violations", []))
                if isinstance(res.faithfulness, dict) else None,
            },
        })

    summary = {"per_study": per_study, "field_totals": field_totals}
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(outdir, per_study, field_totals)
    print(f"wrote {outdir/'summary.json'} and {outdir/'REPORT.md'}")


def _prf(a: dict) -> tuple[float | None, float | None, float | None, float | None]:
    tp = a["tp_correct"] + a["tp_wrong"]
    prec = tp / (tp + a["fp"]) if (tp + a["fp"]) else None
    rec = tp / (tp + a["fn"]) if (tp + a["fn"]) else None
    f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
    vacc = a["tp_correct"] / tp if tp else None
    return prec, rec, f1, vacc


def _fmt(x): return f"{x:.2f}" if isinstance(x, float) else "  – "


def write_report(outdir: Path, per_study: list[dict], field_totals: dict) -> None:
    L = ["# MetaExtractor × curatedMetagenomicData — pilot evaluation\n"]
    L.append("Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. "
             "Gold: cMD `*_sample.tsv`. Samples joined **positionally**.\n")
    # content aggregate
    cagg = dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0)
    for s in per_study:
        if "content" in s:
            for k in cagg: cagg[k] += s["content"][k]
    p, r, f1, v = _prf(cagg)
    L.append("## Headline (content fields, micro-averaged)\n")
    L.append(f"- Precision **{_fmt(p)}**, Recall **{_fmt(r)}**, F1 **{_fmt(f1)}**, "
             f"value-accuracy-on-attempted **{_fmt(v)}**")
    L.append(f"- cells: TN={cagg['tn']} TPc={cagg['tp_correct']} TPw={cagg['tp_wrong']} "
             f"FN={cagg['fn']} FP={cagg['fp']}\n")
    # per study
    L.append("## Per study\n")
    L.append("| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |")
    L.append("|---|---|--:|--:|---|--:|--:|--:|--:|")
    for s in per_study:
        if "error" in s:
            L.append(f"| {s['study']} | – | – | – | {s['error']} | – | – | – | – |"); continue
        p, r, f1, v = _prf(s["content"])
        L.append(f"| {s['study']} | {s['pmid']} | {s['n_gold']} | {s['n_extracted']} | "
                 f"{s['sample_align']} | {_fmt(p)} | {_fmt(r)} | {_fmt(f1)} | {_fmt(v)} |")
    # per field
    L.append("\n## Per field (all studies, micro)\n")
    L.append("| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |")
    L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for k in sorted(field_totals, key=lambda x: (x in META_FIELDS, x)):
        a = field_totals[k]
        N = sum(a.values())
        if N == 0:
            continue
        p, r, f1, v = _prf(a)
        kind = "id/prov" if k in META_FIELDS else "content"
        L.append(f"| {k} | {kind} | {N} | {a['tn']} | {a['tp_correct']} | {a['tp_wrong']} | "
                 f"{a['fn']} | {a['fp']} | {_fmt(p)} | {_fmt(r)} | {_fmt(f1)} | {_fmt(v)} |")
    L.append("\n### Decision legend\n"
             "TN=both not-reported · TPc=both reported & match · TPw=both reported but differ "
             "(often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · "
             "FP=extractor claims it, gold blank.\n")
    (outdir / "REPORT.md").write_text("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "run-tables", "eval"):
        s = sub.add_parser(name)
        s.add_argument("manifest")
        s.add_argument("outdir")
        s.add_argument("--limit", type=int, default=None)
        if name in ("run", "run-tables"):
            s.add_argument("--model", default="claude-haiku-4-5")
            s.add_argument("--force", action="store_true")
        if name == "eval":
            s.add_argument("--align-key", default=None,
                           help="Reorder extracted samples to gold order by this shared "
                                "column (e.g. ncbi_accession) before the positional join.")
    args = ap.parse_args()
    dispatch = {"run": cmd_run, "run-tables": cmd_run_tables, "eval": cmd_eval}
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
