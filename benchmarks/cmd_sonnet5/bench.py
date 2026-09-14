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


def align_samples(ext_samples: list[dict], gold_rows: list[dict], key):
    """Reorder extracted samples to gold order by a shared unique-id key.

    ``key`` may be a single column name or an ordered fallback of candidates
    (a list, or a comma-separated string). The first candidate that yields any
    match is used to align the whole study — so a study whose runs are keyed on
    ``ncbi_accession`` and one keyed on ``sample_id`` are each aligned on their
    own available id (e.g. PasolliE shares no accession with gold but matches
    perfectly on ``sample_id``). Candidates that no study can match on (the
    ingestion-ceiling studies carry no gold-overlapping id at all) simply
    contribute nothing. Returns
    (aligned_ext, matched_gold, n_matched, n_gold, n_ext, used_key)."""
    keys = [k.strip() for k in key.split(",")] if isinstance(key, str) else list(key)
    keys = [k for k in keys if k]
    for kcol in keys:
        idx: dict[str, dict] = {}
        for s in ext_samples:
            k = _acc_key(s.get(kcol))
            if k and k not in idx:
                idx[k] = s
        aligned_ext, matched_gold = [], []
        for g in gold_rows:
            k = _acc_key(g.get(kcol))
            if k and k in idx:
                aligned_ext.append(idx[k]); matched_gold.append(g)
        if matched_gold:  # first candidate with any overlap wins for this study
            return aligned_ext, matched_gold, len(matched_gold), len(gold_rows), len(ext_samples), kcol
    return [], [], 0, len(gold_rows), len(ext_samples), None


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
        # ``--align-key`` may name a single id column or an ordered fallback
        # chain (comma-separated); a study aligns on the first candidate present
        # in gold that it can match on.
        align_keys = [k.strip() for k in (args.align_key or "").split(",") if k.strip()]
        align_on = [k for k in align_keys if k in gold_cols]
        if align_on:
            a_ext, a_gold, nmatch, ngold, next_, used = align_samples(
                data0.get("samples", []), gold, align_on)
            data0 = {**data0, "samples": a_ext}
            eval_ext = data0
            eval_gold = a_gold
            align_note = (f"aligned on {used}: {nmatch}/{ngold} gold matched (ext={next_})"
                          if used else f"aligned: 0/{ngold} gold matched (ext={next_})")

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
        # Coverage-aware recall: score over ALL gold rows (un/under-enumerated
        # samples count as FN, not dropped). Only meaningful for the positional
        # join — the accession-aligned pass already restricts to matched gold.
        content_coverage = None
        if not align_on:
            res_cov = evaluate(extraction=ext, gold_rows=gold, field_map=fmap,
                               unit_fields=ufields, count_missing_gold_as_fn=True)
            content_coverage = agg_over(res_cov.per_field, content_keys)
        per_study.append({
            "study": study, "pmid": m["pmid"],
            "n_gold": len(gold), "n_extracted": n_ext,
            "sample_align": align_note or ("match" if n_ext == len(gold)
                                           else f"MISMATCH ({n_ext} vs {len(gold)})"),
            "content": agg_over(res.per_field, content_keys),
            "content_coverage": content_coverage,
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


# --------------------------------------------------------------------- harmonize
def _resolve_dir(d: str) -> Path:
    """Model output dir, relative to the benchmark root unless absolute."""
    p = Path(d)
    return p if p.is_absolute() else (_HERE / p)


def cmd_harmonize(args: argparse.Namespace) -> None:
    """Regenerate the ontology-harmonization table (MANUSCRIPT Section 3.6).

    For disease / body_site / treatment, score each TP cell three ways on a
    single code path built on ``evaluate_both``:

      raw value-acc  — verbatim string match (the raw pass; = content TPc rate)
      agree_acc      — extracted and gold values canonicalize to the SAME
                       OntologyMapper code set (the harmonized pass; self-
                       consistency, NOT correctness)
      recoverable    — TP cells the harmonized pass flips TP_wrong -> TP_correct
                       (== the raw->agree gain; surfaced natively by evaluate_both)
      correct_acc    — OM code of the *extracted* value intersects the gold's own
                       curated ``*_ontology_term_id`` (true correctness), over the
                       cells carrying a gold identifier. Deliberately separate from
                       agree_acc: agreement is not correctness (MANUSCRIPT 4.1).

    The canonicalizer is built from the same crosswalk_<field>.csv /
    crosswalk_gold_<field>.csv the standalone rescore.py used, so this is a
    drop-in, library-backed replacement for that script.
    """
    sys.path.insert(0, str(_HERE / "harmonize"))
    sys.path.insert(0, str(Path.home() / "OmicsMLRepo/MetaExtractor/src"))
    from metaextractor.evaluation import evaluate_both, load_extraction, load_gold_tsv
    import rescore  # crosswalk / corpus helpers — single source of truth

    FIELDS = ("disease", "body_site", "treatment")
    models = [("Sonnet5", args.sonnet_dir), ("Haiku", args.haiku_dir)]
    manifest = load_manifest(args.manifest, args.limit)

    def build_crosswalk(field: str) -> dict:
        cm = rescore.corpus_code_map(field)
        ext_cw = rescore.HERE / f"crosswalk_{field}.csv"
        if not ext_cw.exists():
            print(f"  WARNING: {ext_cw.name} missing — extracted values have no OM codes, so "
                  f"agree_acc/correct_acc for '{field}' collapse toward the raw value-acc. "
                  f"Re-run OntologyMapper (harmonize/run_om*.py) to regenerate it before "
                  f"trusting the harmonized columns.", file=sys.stderr)
        return {**rescore.crosswalk_map(rescore.HERE / f"crosswalk_gold_{field}.csv", cm),
                **rescore.crosswalk_map(ext_cw, cm)}

    def make_canon(cw: dict):
        # Value -> stable string of its sorted OM code set; identical code sets
        # compare equal under the evaluator's string comparator, so "agree" ==
        # "both sides map to the same code(s)". Fall back to the normalized
        # surface form when no code is found (so unmapped != spuriously equal).
        def canon(value, _field):
            codes = rescore.codes_of(value, cw)
            return "|".join(sorted(codes)) if codes else rescore.norm(value)
        return canon

    rows = []
    for field in FIELDS:
        cw = build_crosswalk(field)
        canon = make_canon(cw)
        idcol = rescore.GOLD_IDCOL[field]
        for label, mdir in models:
            mroot = _resolve_dir(mdir)
            tp = raw_correct = agree_correct = recover = n_gid = correct = 0
            for m in manifest:
                sj = mroot / f"{m['study']}.json"
                if not sj.exists():
                    continue
                gold = load_gold_tsv(m["gold_tsv"])
                gcols = list(gold[0].keys()) if gold else []
                if field not in gcols:
                    continue
                comp = evaluate_both(load_extraction(sj), gold, {field: field}, canonicalize=canon)
                rfm, hfm = comp.raw.per_field[field], comp.harmonized.per_field[field]
                tp += rfm.tp
                raw_correct += rfm.tp_correct
                agree_correct += hfm.tp_correct
                recover += comp.recoverable_count
                # correct_acc: extracted OM code vs gold's own curated ontology id.
                for c in comp.raw.per_cell:
                    if c.decision not in ("TP_correct", "TP_wrong"):
                        continue
                    gid = (rescore.gold_id_codes(gold[c.sample_idx].get(idcol, ""))
                           if c.sample_idx < len(gold) else set())
                    if gid:
                        n_gid += 1
                        if rescore.codes_of(c.extracted, cw) & gid:
                            correct += 1
            rows.append(dict(
                field=field, model=label, tp=tp,
                raw_value_acc=round(raw_correct / tp, 3) if tp else None,
                agree_acc=round(agree_correct / tp, 3) if tp else None,
                recoverable=recover,
                correct_acc=round(correct / n_gid, 3) if n_gid else None,
                n_gold_id=n_gid,
            ))

    outdir = _resolve_dir(args.sonnet_dir).parent if not Path(args.sonnet_dir).is_absolute() else Path.cwd()
    (outdir / "harmonization.json").write_text(json.dumps(rows, indent=2))
    _write_harmonization_md(outdir / "harmonization.md", rows)
    _print_harmonization(rows)
    print(f"\nwrote {outdir/'harmonization.json'} and {outdir/'harmonization.md'}")


def _harm_row_str(r: dict) -> str:
    def f(x):
        return f"{x:.3f}" if isinstance(x, float) else ("—" if x is None else str(x))
    return (f"| {r['model']} | {r['field']} | {f(r['raw_value_acc'])} | {f(r['agree_acc'])} | "
            f"{r['recoverable']} | {f(r['correct_acc'])} | {r['n_gold_id']} | {r['tp']} |")


def _write_harmonization_md(path: Path, rows: list[dict]) -> None:
    L = ["# Ontology harmonization — value-accuracy (MANUSCRIPT Section 3.6)\n",
         "Scored on TP cells via `metaextractor.evaluation.evaluate_both`. "
         "`raw value-acc` = verbatim string match; `agree_acc` = extracted and gold "
         "canonicalize to the same OntologyMapper code (self-consistency, **not** "
         "correctness); `recoverable` = TP cells harmonization flips to correct "
         "(raw→agree); `correct_acc` = extracted OM code matches the gold's own "
         "`*_ontology_term_id`, over `n with gold ID` cells.\n",
         "| model | field | raw value-acc | `agree_acc` | recoverable | `correct_acc` | n with gold ID | TP cells |",
         "|---|---|--:|--:|--:|--:|--:|--:|"]
    L += [_harm_row_str(r) for r in rows]
    path.write_text("\n".join(L) + "\n")


def _print_harmonization(rows: list[dict]) -> None:
    print(f"\n{'model':<8} {'field':<10} {'raw':>6} {'agree':>6} {'recov':>6} {'correct':>8} {'nGID':>5} {'TP':>5}")
    for r in rows:
        def f(x):
            return f"{x:.3f}" if isinstance(x, float) else ("  –  " if x is None else str(x))
        print(f"{r['model']:<8} {r['field']:<10} {f(r['raw_value_acc']):>6} {f(r['agree_acc']):>6} "
              f"{str(r['recoverable']):>6} {f(r['correct_acc']):>8} {r['n_gold_id']:>5} {r['tp']:>5}")


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
    # Coverage-aware recall: counts gold rows the extraction never enumerated as FN.
    ccov = dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0)
    have_cov = False
    for s in per_study:
        cc = s.get("content_coverage")
        if cc:
            have_cov = True
            for k in ccov:
                ccov[k] += cc[k]
    if have_cov:
        _, rcov, _, _ = _prf(ccov)
        L.append(f"- **Coverage-aware recall {_fmt(rcov)}** — recall when un/under-enumerated "
                 f"gold rows are counted as FN rather than dropped. The positional recall "
                 f"above ({_fmt(r)}) scores only the overlap `min(n_extracted, n_gold)`, so "
                 f"samples a study never enumerated do not enter the denominator.\n")
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
                           help="Reorder extracted samples to gold order by a shared unique-id "
                                "column before scoring. Accepts a comma-separated fallback chain "
                                "(e.g. 'ncbi_accession,sample_id,subject_id'); each study aligns on "
                                "the first candidate it can match on.")
    # harmonize: regenerate the Section 3.6 ontology-harmonization table via evaluate_both.
    sh = sub.add_parser("harmonize")
    sh.add_argument("manifest")
    sh.add_argument("--sonnet-dir", dest="sonnet_dir", default="out_ms/sonnet_r1",
                    help="Sonnet extraction dir (relative to benchmark root unless absolute).")
    sh.add_argument("--haiku-dir", dest="haiku_dir", default="out_ms/haiku_r1",
                    help="Haiku extraction dir (relative to benchmark root unless absolute).")
    sh.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    dispatch = {"run": cmd_run, "run-tables": cmd_run_tables, "eval": cmd_eval,
                "harmonize": cmd_harmonize}
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
