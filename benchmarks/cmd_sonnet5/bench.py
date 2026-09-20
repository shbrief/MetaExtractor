#!/usr/bin/env python
"""MetaExtractor benchmark harness against curatedMetagenomicData gold tables.

Subcommands:

  run        OUTDIR [--model M]    extract every manifest study by PMID (ad hoc;
                                   the frozen benchmark uses run_frozen.py)
  run-tables OUTDIR [--model M]    deterministic path: feed the study's raw
                                   *_sra_meta.tsv as a local supplementary file
  eval       OUTDIR                score OUTDIR/<study>.json against gold

Scoring (``eval``) compares values **after harmonization**: every field with a
MetaHarmonizer crosswalk in ``TREE/crosswalks/`` is compared as ontology codes
(against the curated ``<field>_ontology_term_id`` where the gold row has one);
every other field is compared as extracted (``evaluation.values_match``: case and
surrounding whitespace ignored, 5% numeric tolerance, no synonyms). See
``harmonize/crosswalk.py`` for the exact rule. Two joins are reported:

* **all curated** (``end_to_end``) — extracted records are aligned to gold rows
  one-to-one on a shared identifier (:func:`metaextractor.alignment.align_by_identity`);
  every gold row is scored, so unmatched, pooled, or ambiguous gold rows count
  their populated cells as false negatives, and a failed extraction counts as
  producing no records. Extra extracted records are reported separately.
* **matched** (``conditional``) — the same alignment, restricted to matched gold rows.

Precision = TPc / (TPc + TPw + FP); recall = TPc / (TPc + TPw + FN), where TPc is a
cell whose harmonized value is correct.

Gold tables are resolved via ``$CMD_CURATION_DIR`` (see bench_paths.py).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from bench_paths import (HERE, SCHEMA, curation_dir, gold_paths, load_manifest,
                         schema_fields)

from metaextractor.alignment import align_by_identity
from metaextractor.evaluation import evaluate, load_extraction, load_gold_tsv

sys.path.insert(0, str(HERE / "harmonize"))
from crosswalk import Harmonizer  # noqa: E402

# Fields that are identifiers / provenance rather than scientific content.
# Evaluated but reported in a separate bucket from the headline content metric.
META_FIELDS = {
    "study_name", "sample_id", "subject_id", "pmid",
    "curator", "ncbi_accession", "host_species", "uncurated_metadata",
}
UNIT_FIELDS_ALL = {"age": "age_unit", "age_min": "age_unit", "age_max": "age_unit"}
DEFAULT_ALIGN_KEY = "ncbi_accession,sample_id,subject_id"
COUNT_KEYS = ("tn", "tp_correct", "tp_wrong", "fn", "fp")


def _zero() -> dict:
    return dict.fromkeys(COUNT_KEYS, 0)


def _add(dst: dict, src: dict) -> dict:
    for k in COUNT_KEYS:
        dst[k] += src[k]
    return dst


def agg_over(per_field, keys) -> dict:
    a = _zero()
    for k in keys:
        fm = per_field.get(k)
        if fm is not None:
            a["tn"] += fm.tn; a["tp_correct"] += fm.tp_correct; a["tp_wrong"] += fm.tp_wrong
            a["fn"] += fm.fn; a["fp"] += fm.fp
    return a


def metrics(a: dict) -> dict:
    """Post-harmonization precision, recall, and F1 from pooled cell counts."""
    tp = a["tp_correct"] + a["tp_wrong"]
    def ratio(n, d):
        return n / d if d else None
    p, r = ratio(a["tp_correct"], tp + a["fp"]), ratio(a["tp_correct"], tp + a["fn"])
    f1 = 2 * p * r / (p + r) if p is not None and r is not None and (p + r) else None
    return {"precision": p, "recall": r, "f1": f1, **a}


def build_field_map(gold_cols: list[str]) -> dict[str, str]:
    gc = set(gold_cols)
    return {f: f for f in schema_fields() if f in gc}


# --------------------------------------------------------------------------- run
def _extract_cmd(pmid: str, out_json: Path, model: str, extra: list[str]) -> list[str]:
    return ["metaextract", "--paper-id", pmid, "--schema", str(SCHEMA), "--model", model,
            "--out", str(out_json), "--csv", str(out_json.with_suffix(".csv")),
            "--csv-provenance", *extra]


def _run_one(cmd: list[str], logfile: Path) -> str:
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    logfile.write_text(f"cmd: {' '.join(cmd)}\nreturncode: {proc.returncode}\n"
                       f"elapsed_s: {dt:.1f}\n--- stderr ---\n{proc.stderr}\n")
    tail = (proc.stderr.strip().splitlines() or ["<no stderr>"])[-1]
    return f"{'ok' if proc.returncode == 0 else f'FAIL rc={proc.returncode}'} in {dt:.0f}s | {tail}"


def cmd_run(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(load_manifest(limit=args.limit), 1):
        out_json = outdir / f"{m['study']}.json"
        if out_json.exists() and not args.force:
            print(f"[{i}] {m['study']}: exists, skip"); continue
        print(f"[{i}] {m['study']} pmid={m['pmid']} ...", flush=True)
        print("   ->", _run_one(_extract_cmd(m["pmid"], out_json, args.model, []),
                                 outdir / f"{m['study']}.runlog.txt"))


def cmd_run_tables(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(load_manifest(limit=args.limit), 1):
        sra = curation_dir() / "inst/curated" / m["study"] / f"{m['study']}_sra_meta.tsv"
        out_json = outdir / f"{m['study']}.json"
        if not sra.exists():
            print(f"[{i}] {m['study']}: no sra_meta table, skip"); continue
        if out_json.exists() and not args.force:
            print(f"[{i}] {m['study']}: exists, skip"); continue
        extra = ["--supplementary", str(sra), "--no-supplementary"]
        print(f"[{i}] {m['study']} (tables path) ...", flush=True)
        print("   ->", _run_one(_extract_cmd(m["pmid"], out_json, args.model, extra),
                                 outdir / f"{m['study']}.runlog.txt"))


# -------------------------------------------------------------------------- eval
def _source_kind(prov: list, ext_idx: int | None, field: str) -> str:
    if ext_idx is None:
        return "no_record"
    if ext_idx >= len(prov):
        return "unrecorded"
    src = (prov[ext_idx] or {}).get(field)
    return src.split(":", 1)[0] if src else "unrecorded"


def load_gold_rows(m: dict) -> list[dict]:
    """The manifest entry's curated rows, concatenating a split-table study.

    Columns are unioned across the tables and a row missing a column reads as blank, the
    same as any uncurated cell: ``TettAJ_2019_c`` carries ``sex``/``sex_ontology_term_id``
    and the other two tables do not.
    """
    tables = [load_gold_tsv(p) for p in gold_paths(m)]
    cols: list[str] = []
    for t in tables:
        for c in (t[0].keys() if t else []):
            if c not in cols:
                cols.append(c)
    return [{c: row.get(c, "") for c in cols} for t in tables for row in t]


def score_study(m: dict, rj: Path, harm: Harmonizer, align_key: str = DEFAULT_ALIGN_KEY) -> dict:
    """Score one extraction after harmonization on both joins. Returns a JSON-able
    record plus private ``_e2e``/``_gold``/``_alignment``/``_data`` handles (``_gold`` is
    in the order of the all-curated join's cells).

    A missing extraction (the run failed) is scored as an empty result, so in the
    all-curated join every populated gold cell of the study is a false negative.
    """
    failed = not rj.exists()
    data = ({"granularity": "study_level", "fields": {}, "samples": []} if failed
            else load_extraction(rj).model_dump())
    samples = data.get("samples", [])
    prov = data.get("sample_provenance") or []
    gold = load_gold_rows(m)
    gold_h = harm.gold_rows(gold)
    gold_cols = list(gold[0].keys()) if gold else []
    fmap = build_field_map(gold_cols)
    ufields = {k: v for k, v in UNIT_FIELDS_ALL.items() if k in fmap and v in gold_cols}
    content = [k for k in fmap if k not in META_FIELDS]
    meta = [k for k in fmap if k in META_FIELDS]
    text_path = rj.with_suffix(".text.txt")
    paper_text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else None

    al = align_by_identity(samples, gold_h, [k for k in align_key.split(",")
                                             if all(p in gold_cols for p in k.strip().split("+"))])
    kw = dict(unit_fields=ufields, canonicalize=harm.canonicalize)
    g_all, e_all = al.end_to_end_lists(gold_h, samples)
    e2e = evaluate({**data, "samples": e_all}, g_all, fmap, paper_text=paper_text, **kw)
    g_m, e_m = al.matched_lists(gold_h, samples)
    cond = evaluate({**data, "samples": e_m}, g_m, fmap, **kw)

    # Cell decisions by the provenance of the extracted value (all-curated join).
    by_gold = dict(al.pairs)
    by_source: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(_zero))
    fp_audit: dict[str, dict] = defaultdict(lambda: {"fp": 0, "value_in_text": 0,
                                                     "study_evidence_in_text": 0})
    harm_diag: dict[str, dict] = {f: {"reported_cells": 0, "gold_curated_id": 0,
                                      "extracted_unmapped": 0, "unqueried_terms": set()}
                                  for f in harm.fields if f in fmap}
    text_lc = paper_text.lower() if paper_text else None
    decision_key = {"TN": "tn", "TP_correct": "tp_correct", "TP_wrong": "tp_wrong",
                    "FN": "fn", "FP": "fp"}
    for c in e2e.per_cell:
        kind = _source_kind(prov, by_gold.get(c.sample_idx), c.field)
        by_source[c.field][kind][decision_key[c.decision]] += 1
        if c.field in harm_diag and c.decision in ("TP_correct", "TP_wrong", "FP"):
            d = harm_diag[c.field]
            d["reported_cells"] += 1
            d["gold_curated_id"] += Harmonizer.display(c.gold) != c.gold
            d["extracted_unmapped"] += harm.codes(c.extracted, c.field) is None
            d["unqueried_terms"].update(harm.unqueried_terms(c.extracted, c.field))
        if c.decision == "FP" and c.field in content:
            a = fp_audit[c.field]
            a["fp"] += 1
            if text_lc is not None:
                v = str(c.extracted).strip().lower()
                if len(v) >= 3 and v in text_lc:
                    a["value_in_text"] += 1
                ev = ((data.get("fields") or {}).get(c.field) or {}).get("evidence_quote") or ""
                if ev.strip() and ev.strip().lower() in text_lc:
                    a["study_evidence_in_text"] += 1
    for d in harm_diag.values():
        d["unqueried_terms"] = sorted(d["unqueried_terms"])

    rec = {
        "study": m["study"], "pmid": m["pmid"], "n_gold": len(gold), "n_extracted": len(samples),
        "extraction_failed": failed,
        "granularity": data.get("granularity"),
        "alignment": al.to_dict(),
        "end_to_end": {"content": agg_over(e2e.per_field, content), "meta": agg_over(e2e.per_field, meta)},
        "conditional": {"content": agg_over(cond.per_field, content), "meta": agg_over(cond.per_field, meta)},
        "fields_end_to_end": {k: agg_over(e2e.per_field, [k]) for k in fmap},
        "fields_conditional": {k: agg_over(cond.per_field, [k]) for k in fmap},
        "harmonized_fields": sorted(harm_diag),
        "harmonization": harm_diag,
        "by_source_end_to_end": {f: dict(v) for f, v in by_source.items()},
        "fp_source_check": dict(fp_audit) if paper_text is not None else None,
        "faithfulness": {
            "contract_violations": len(e2e.faithfulness.contract_violations),
            "evidence_checked": e2e.faithfulness.evidence_checked,
            "evidence_matched": e2e.faithfulness.evidence_matched,
            "paper_text_available": paper_text is not None,
        },
        "n_content_fields": len(content),
    }
    rec["_e2e"], rec["_gold"], rec["_alignment"], rec["_data"] = e2e, gold, al, data
    return rec


def _public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def write_cells_tsv(rec: dict, harm: Harmonizer, path: Path) -> None:
    """Per-cell decisions (all-curated join) with the harmonized values compared."""
    import csv
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["sample_idx", "ext_sample_id", "gold_sample_id", "field", "extracted", "gold",
                    "extracted_harmonized", "gold_harmonized", "decision"])
        for c in rec["_e2e"].per_cell:
            harmonized = c.field in harm.crosswalks
            w.writerow([c.sample_idx, c.ext_sample_id or "", c.gold_sample_id or "", c.field,
                        "" if c.extracted is None else c.extracted,
                        rec["_gold"][c.sample_idx].get(c.field, ""),
                        harm.canonicalize(c.extracted, c.field) if harmonized and c.extracted is not None else "",
                        harm.canonicalize(c.gold, c.field) if harmonized and c.gold not in (None, "") else "",
                        c.decision])


def cmd_eval(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir)
    harm = Harmonizer(Path(args.crosswalks) if args.crosswalks else outdir.parent / "crosswalks",
                      min_score=args.min_score)
    if harm.below_threshold:
        n = sum(len(v) for v in harm.below_threshold.values())
        print(f"min-score {harm.min_score}: {n} term(s) left unmapped (compared as strings):",
              file=sys.stderr)
        for f, rows in sorted(harm.below_threshold.items()):
            for term, match, score in rows[:5]:
                print(f"  {f}: {term!r} -> {match!r} ({score:.3f})", file=sys.stderr)
    per_study = []
    for m in load_manifest(limit=args.limit):
        rj = outdir / f"{m['study']}.json"
        rec = score_study(m, rj, harm, args.align_key)
        if rec["_e2e"].per_cell:
            write_cells_tsv(rec, harm, outdir / f"{m['study']}.cells.tsv")
        per_study.append(_public(rec))
    unqueried = sorted({(s["study"], f, t) for s in per_study
                        for f, d in s["harmonization"].items() for t in d["unqueried_terms"]})
    if unqueried:
        print(f"WARNING: {len(unqueried)} extracted term(s) were never sent to MetaHarmonizer "
              f"(stale crosswalks; they score as unmapped): {unqueried[:10]}", file=sys.stderr)
    summary = {"align_key": args.align_key, "crosswalks": str(harm.directory),
               "harmonized_fields": harm.fields, "min_score": harm.min_score,
               "below_threshold": {f: [list(r) for r in rows]
                                   for f, rows in harm.below_threshold.items()},
               "per_study": per_study}
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(outdir, per_study, harm.fields)
    print(f"wrote {outdir/'summary.json'} and {outdir/'REPORT.md'}")


def _fmt(x, nd: int = 3) -> str:
    if x is None:
        return "–"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def write_report(outdir: Path, per_study: list[dict], harmonized: list[str]) -> None:
    ok = [s for s in per_study if "error" not in s]
    L = ["# MetaExtractor × curatedMetagenomicData — evaluation\n",
         f"Run dir: `{outdir.name}`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged. "
         f"Values compared after harmonization; harmonized fields: "
         f"{', '.join(harmonized) or 'none'} (other fields as extracted).\n",
         "| score | precision | recall | F1 | TPc | TPw | FN | FP |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for label, join in (("all curated", "end_to_end"), ("matched", "conditional")):
        a = _zero()
        for s in ok:
            _add(a, s[join]["content"])
        x = metrics(a)
        L.append(f"| {label} | {_fmt(x['precision'])} | {_fmt(x['recall'])} | {_fmt(x['f1'])} | "
                 f"{a['tp_correct']} | {a['tp_wrong']} | {a['fn']} | {a['fp']} |")
    L += ["\n## Per study (all curated)\n",
          "| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |",
          "|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for s in per_study:
        al, c = s["alignment"], s["end_to_end"]["content"]
        L.append(f"| {s['study']}{' (extraction failed)' if s.get('extraction_failed') else ''} | {s['n_gold']} | {s['n_extracted']} | {al['key_used'] or '–'} | "
                 f"{al['matched']} | {al['unmatched_gold']} | {al['pooled_gold']} | "
                 f"{al['ambiguous_gold']} | {al['unmatched_ext_with_key']} | "
                 f"{al['unmatched_ext_without_key']} | {c['tp_correct']} | {c['tp_wrong']} | "
                 f"{c['fn']} | {c['fp']} |")
    L.append("\nTPc = both reported, harmonized values match · TPw = both reported, harmonized "
             "values differ · FN = gold reported, extraction did not · FP = extraction reported, "
             "gold blank. A gold-blank cell is not by itself evidence of fabrication.\n")
    (outdir / "REPORT.md").write_text("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "run-tables", "eval"):
        s = sub.add_parser(name)
        s.add_argument("outdir")
        s.add_argument("--limit", type=int, default=None)
        if name in ("run", "run-tables"):
            s.add_argument("--model", default="claude-haiku-4-5")
            s.add_argument("--force", action="store_true")
        if name == "eval":
            s.add_argument("--align-key", default=DEFAULT_ALIGN_KEY,
                           help="Ordered identifier candidates (comma-separated; '+' joins a "
                                "compound key). The candidate with the most one-to-one matches "
                                "is used per study.")
            s.add_argument("--crosswalks", default=None,
                           help="MetaHarmonizer crosswalk directory (default: OUTDIR/../crosswalks).")
            s.add_argument("--min-score", type=float, default=0.0,
                           help="OntologyMapper similarity below which a term is left unmapped "
                                "and compared as its surface string. The corpora are closed and "
                                "the mapping has no threshold of its own, so every term is "
                                "otherwise assigned its nearest concept. Default 0.0 (no "
                                "threshold), which reproduces the frozen runs; exact-stage "
                                "matches are never dropped.")
    args = ap.parse_args()
    {"run": cmd_run, "run-tables": cmd_run_tables, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    main()
