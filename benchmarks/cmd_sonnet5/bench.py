#!/usr/bin/env python
"""MetaExtractor benchmark harness against curatedMetagenomicData gold tables.

Subcommands:

  run        OUTDIR [--model M]    extract every manifest study by PMID (ad hoc;
                                   the frozen benchmark uses run_frozen.py)
  run-tables OUTDIR [--model M]    deterministic path: feed the study's raw
                                   *_sra_meta.tsv as a local supplementary file
  eval       OUTDIR                score OUTDIR/<study>.json against gold
  harmonize  TREE                  ontology-harmonization scoring over run dirs

Scoring (``eval``) reports three joins, most to least rigorous:

* **end-to-end** (primary) — extracted records are aligned to gold rows one-to-one
  on a shared identifier (:func:`metaextractor.alignment.align_by_identity`);
  every gold row is scored, so unmatched, pooled, or ambiguous gold rows count
  their populated cells as false negatives. Extra extracted records are reported
  separately and are not scored as cells.
* **conditional** — the same alignment, restricted to matched gold rows.
* **positional** (supplementary, legacy) — sample *i* ↔ gold row *i* over
  ``min(n_extracted, n_gold)``; kept only for comparison with earlier reports.

Each join reports value-aware and presence precision/recall (see
:class:`metaextractor.evaluation.FieldMetrics`).

Gold tables are resolved via ``$CMD_CURATION_DIR`` (see bench_paths.py).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from bench_paths import (HERE, SCHEMA, curation_dir, gold_path, load_manifest,
                         schema_fields)

from metaextractor.alignment import align_by_identity
from metaextractor.evaluation import (evaluate, evaluate_both, is_not_reported,
                                      load_extraction, load_gold_tsv)

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
    """Value-aware and presence metrics from pooled counts."""
    tp = a["tp_correct"] + a["tp_wrong"]
    def ratio(n, d):
        return n / d if d else None
    def f1(p, r):
        return 2 * p * r / (p + r) if p is not None and r is not None and (p + r) else None
    vp, vr = ratio(a["tp_correct"], tp + a["fp"]), ratio(a["tp_correct"], tp + a["fn"])
    pp, pr = ratio(tp, tp + a["fp"]), ratio(tp, tp + a["fn"])
    return {"value_precision": vp, "value_recall": vr, "value_f1": f1(vp, vr),
            "presence_precision": pp, "presence_recall": pr, "presence_f1": f1(pp, pr),
            "value_accuracy": ratio(a["tp_correct"], tp), **a}


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


def score_study(m: dict, rj: Path, align_key: str = DEFAULT_ALIGN_KEY) -> dict:
    """Score one extraction on all three joins. Returns a JSON-able record plus
    private ``_e2e``/``_gold``/``_alignment``/``_data`` handles for callers.

    A missing extraction (the run failed) is scored as an empty result, so in the
    end-to-end join every populated gold cell of the study is a false negative.
    """
    failed = not rj.exists()
    data = ({"granularity": "study_level", "fields": {}, "samples": []} if failed
            else load_extraction(rj).model_dump())
    samples = data.get("samples", [])
    prov = data.get("sample_provenance") or []
    gold = load_gold_tsv(gold_path(m))
    gold_cols = list(gold[0].keys()) if gold else []
    fmap = build_field_map(gold_cols)
    ufields = {k: v for k, v in UNIT_FIELDS_ALL.items() if k in fmap and v in gold_cols}
    content = [k for k in fmap if k not in META_FIELDS]
    meta = [k for k in fmap if k in META_FIELDS]
    text_path = rj.with_suffix(".text.txt")
    paper_text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else None

    al = align_by_identity(samples, gold, [k for k in align_key.split(",")
                                           if all(p in gold_cols for p in k.strip().split("+"))])
    g_all, e_all = al.end_to_end_lists(gold, samples)
    e2e = evaluate({**data, "samples": e_all}, g_all, fmap, unit_fields=ufields,
                   paper_text=paper_text)
    g_m, e_m = al.matched_lists(gold, samples)
    cond = evaluate({**data, "samples": e_m}, g_m, fmap, unit_fields=ufields)
    pos = evaluate(data, gold, fmap, unit_fields=ufields)
    pos_cov = evaluate(data, gold, fmap, unit_fields=ufields, count_missing_gold_as_fn=True)

    # Cell decisions by the provenance of the extracted value (end-to-end join).
    by_gold = dict(al.pairs)
    by_source: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(_zero))
    fp_audit: dict[str, dict] = defaultdict(lambda: {"fp": 0, "value_in_text": 0,
                                                     "study_evidence_in_text": 0})
    text_lc = paper_text.lower() if paper_text else None
    for c in e2e.per_cell:
        kind = _source_kind(prov, by_gold.get(c.sample_idx), c.field)
        by_source[c.field][kind][{"TN": "tn", "TP_correct": "tp_correct", "TP_wrong": "tp_wrong",
                                  "FN": "fn", "FP": "fp"}[c.decision]] += 1
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

    fr = e2e.faithfulness
    rec = {
        "study": m["study"], "pmid": m["pmid"], "n_gold": len(gold), "n_extracted": len(samples),
        "extraction_failed": failed,
        "granularity": data.get("granularity"),
        "alignment": al.to_dict(),
        "end_to_end": {"content": agg_over(e2e.per_field, content), "meta": agg_over(e2e.per_field, meta)},
        "conditional": {"content": agg_over(cond.per_field, content), "meta": agg_over(cond.per_field, meta)},
        "positional": {"content": agg_over(pos.per_field, content), "meta": agg_over(pos.per_field, meta),
                       "content_coverage": agg_over(pos_cov.per_field, content)},
        "fields_end_to_end": {k: agg_over(e2e.per_field, [k]) for k in fmap},
        "by_source_end_to_end": {f: dict(v) for f, v in by_source.items()},
        "fp_source_check": dict(fp_audit) if paper_text is not None else None,
        "faithfulness": {
            "contract_violations": len(fr.contract_violations),
            "evidence_checked": fr.evidence_checked,
            "evidence_matched": fr.evidence_matched,
            "paper_text_available": paper_text is not None,
        },
        "n_content_fields": len(content),
    }
    rec["_e2e"], rec["_gold"], rec["_alignment"], rec["_data"] = e2e, gold, al, data
    return rec


def _public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def cmd_eval(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir)
    per_study = []
    for m in load_manifest(limit=args.limit):
        rj = outdir / f"{m['study']}.json"
        rec = score_study(m, rj, args.align_key)
        if rec["_e2e"].per_cell:
            rec["_e2e"].to_cells_tsv(str(outdir / f"{m['study']}.cells.tsv"))
        per_study.append(_public(rec))
    summary = {"align_key": args.align_key, "per_study": per_study}
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(outdir, per_study)
    print(f"wrote {outdir/'summary.json'} and {outdir/'REPORT.md'}")


def _fmt(x, nd: int = 3) -> str:
    if x is None:
        return "–"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def write_report(outdir: Path, per_study: list[dict]) -> None:
    ok = [s for s in per_study if "error" not in s]
    L = ["# MetaExtractor × curatedMetagenomicData — evaluation\n",
         f"Run dir: `{outdir.name}`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged.\n",
         "| join | value P | value R | value F1 | presence P | presence R | TPc | TPw | FN | FP |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for label, path in (("end-to-end (primary)", ("end_to_end", "content")),
                        ("conditional (matched rows)", ("conditional", "content")),
                        ("positional (supplementary)", ("positional", "content"))):
        a = _zero()
        for s in ok:
            _add(a, s[path[0]][path[1]])
        x = metrics(a)
        L.append(f"| {label} | {_fmt(x['value_precision'])} | {_fmt(x['value_recall'])} | "
                 f"{_fmt(x['value_f1'])} | {_fmt(x['presence_precision'])} | "
                 f"{_fmt(x['presence_recall'])} | {a['tp_correct']} | {a['tp_wrong']} | "
                 f"{a['fn']} | {a['fp']} |")
    L += ["\n## Per study (end-to-end)\n",
          "| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |",
          "|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for s in per_study:
        al, c = s["alignment"], s["end_to_end"]["content"]
        L.append(f"| {s['study']}{' (extraction failed)' if s.get('extraction_failed') else ''} | {s['n_gold']} | {s['n_extracted']} | {al['key_used'] or '–'} | "
                 f"{al['matched']} | {al['unmatched_gold']} | {al['pooled_gold']} | "
                 f"{al['ambiguous_gold']} | {al['unmatched_ext_with_key']} | "
                 f"{al['unmatched_ext_without_key']} | {c['tp_correct']} | {c['tp_wrong']} | "
                 f"{c['fn']} | {c['fp']} |")
    L.append("\nTPc = both reported, values match · TPw = both reported, values differ · "
             "FN = gold reported, extraction did not · FP = extraction reported, gold blank. "
             "A gold-blank cell is not by itself evidence of fabrication.\n")
    (outdir / "REPORT.md").write_text("\n".join(L))


# --------------------------------------------------------------------- harmonize
HARM_FIELDS = ("disease", "body_site", "treatment")


def _canon_factory(cw, crosswalk):
    def canon(value, _field):
        codes = crosswalk.codes_of(value, cw)
        return "|".join(sorted(codes)) if codes else crosswalk.norm(value)
    return canon


def harmonize_run(run_dir: Path, manifest: list[dict], field: str, cw, crosswalk,
                  align_key: str) -> dict:
    """Score one field on one run dir, on identity-matched cells only."""
    idcol = crosswalk.GOLD_IDCOL[field]
    canon = _canon_factory(cw, crosswalk)
    tot = Counter()
    terms, gold_codes, studies = Counter(), Counter(), Counter()
    for m in manifest:
        rj = run_dir / f"{m['study']}.json"
        if not rj.exists():
            continue
        gold = load_gold_tsv(gold_path(m))
        if not gold or field not in gold[0]:
            continue
        data = load_extraction(rj).model_dump()
        samples = data.get("samples", [])
        al = align_by_identity(samples, gold, [k for k in align_key.split(",")
                                               if all(p in gold[0] for p in k.split("+"))])
        g_m, e_m = al.matched_lists(gold, samples)
        if not g_m:
            continue
        comp = evaluate_both({**data, "samples": e_m}, g_m, {field: field}, canonicalize=canon)
        for rc, hc in zip(comp.raw.per_cell, comp.harmonized.per_cell):
            if rc.decision not in ("TP_correct", "TP_wrong"):
                continue
            tot["tp"] += 1
            tot["raw_correct_tp"] += rc.decision == "TP_correct"
            tot["agree_exact_tp"] += hc.decision == "TP_correct"
            gid = crosswalk.gold_id_codes(g_m[rc.sample_idx].get(idcol, ""))
            if not gid:
                continue
            e = crosswalk.codes_of(rc.extracted, cw)
            tot["coded"] += 1
            tot["raw_correct_coded"] += rc.decision == "TP_correct"
            tot["exact_correct"] += e == gid
            tot["any_hit"] += bool(e & gid)
            tot["ext_unmapped"] += not e
            tot["inter"] += len(e & gid)
            tot["ext_codes"] += len(e)
            tot["gold_codes"] += len(gid)
            terms[str(rc.extracted)] += 1
            gold_codes.update(gid)
            studies[m["study"]] += 1

    def r(n, d):
        return tot[n] / tot[d] if tot[d] else None
    return {
        "tp": tot["tp"], "coded": tot["coded"],
        "raw_acc_tp": r("raw_correct_tp", "tp"),
        "agree_exact_tp": r("agree_exact_tp", "tp"),
        "raw_acc_coded": r("raw_correct_coded", "coded"),
        "exact_correct": r("exact_correct", "coded"),
        "any_hit": r("any_hit", "coded"),
        "concept_precision": r("inter", "ext_codes"),
        "concept_recall": r("inter", "gold_codes"),
        "ext_unmapped": tot["ext_unmapped"],
        "distinct_ext_terms": len(terms), "distinct_gold_codes": len(gold_codes),
        "studies": dict(studies), "gold_code_freq": dict(gold_codes.most_common()),
        "ext_term_freq": dict(terms.most_common()),
    }


def _mmm(vals):
    vals = [v for v in vals if v is not None]
    return [st.median(vals), min(vals), max(vals)] if vals else None


def cmd_harmonize(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(HERE / "harmonize"))
    import crosswalk  # noqa: E402

    tree = Path(args.tree)
    manifest = load_manifest(limit=args.limit)
    out = {"tree": str(tree), "align_key": args.align_key, "semantics": {
        "raw_acc": "string match after lowercase/strip (evaluation.values_match)",
        "agree_exact_tp": "extracted and gold values map to the identical OntologyMapper code set",
        "exact_correct": "extracted code set == gold's curated *_ontology_term_id set",
        "any_hit": "SUPPLEMENTARY: extracted code set shares >=1 code with gold ids",
        "concept_precision": "sum|E∩G| / sum|E| over coded cells",
        "concept_recall": "sum|E∩G| / sum|G| over coded cells",
        "population": "identity-matched rows; both sides reported; coded = gold id present"},
        "fields": {}}
    for field in HARM_FIELDS:
        cw = crosswalk.load_field_crosswalk(field)
        out["fields"][field] = {"crosswalk_terms": len(cw), "models": {}}
        for model in args.models:
            runs = sorted(tree.glob(f"{model}_r*"))
            per_run = {d.name: harmonize_run(d, manifest, field, cw, crosswalk, args.align_key)
                       for d in runs if d.is_dir()}
            keys = ("tp", "coded", "raw_acc_tp", "agree_exact_tp", "raw_acc_coded",
                    "exact_correct", "any_hit", "concept_precision", "concept_recall")
            out["fields"][field]["models"][model] = {
                "per_run": per_run,
                "summary": {k: _mmm([pr[k] for pr in per_run.values()]) for k in keys},
                # Ratios are undefined for a run with no cells; say how many runs contribute.
                "runs_with_coded": sum(1 for pr in per_run.values() if pr["coded"]),
                "runs": len(per_run),
                "distinct_ext_terms": sorted({t for pr in per_run.values() for t in pr["ext_term_freq"]}),
                "distinct_gold_codes": sorted({c for pr in per_run.values() for c in pr["gold_code_freq"]}),
                "studies": sorted({st_ for pr in per_run.values() for st_ in pr["studies"]}),
            }
    (tree / "harmonization.json").write_text(json.dumps(out, indent=2))
    L = ["# Ontology harmonization (identity-matched cells)\n",
         "Median [min–max] over repeats. `raw` and `exact` on the **same coded cells** "
         "(both reported, gold carries a curated ontology id). `any-hit` is supplementary.\n",
         "Ratios are over runs with at least one coded cell (`runs coded`).\n",
         "| field | model | TP cells | coded cells | runs coded | raw acc (coded) | exact code-set correct | any-hit (suppl.) | concept P | concept R | agree (TP, exact) | coded terms → curated codes | studies |",
         "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|---|"]
    for field, fd in out["fields"].items():
        for model, md in fd["models"].items():
            s = md["summary"]
            def cell(k, nd=3):
                v = s.get(k)
                if not v:
                    return "–"
                return (f"{v[0]:.{nd}f} [{v[1]:.{nd}f}–{v[2]:.{nd}f}]" if nd
                        else f"{v[0]:.0f} [{v[1]:.0f}–{v[2]:.0f}]")
            L.append(f"| {field} | {model} | {cell('tp', 0)} | {cell('coded', 0)} | "
                     f"{md['runs_with_coded']}/{md['runs']} | "
                     f"{cell('raw_acc_coded')} | {cell('exact_correct')} | {cell('any_hit')} | "
                     f"{cell('concept_precision')} | {cell('concept_recall')} | "
                     f"{cell('agree_exact_tp')} | "
                     f"{', '.join(md['distinct_ext_terms']) or '–'} → "
                     f"{', '.join(md['distinct_gold_codes']) or '–'} | "
                     f"{', '.join(md['studies']) or '–'} |")
    (tree / "harmonization.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {tree/'harmonization.json'} and {tree/'harmonization.md'}")


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
    sh = sub.add_parser("harmonize")
    sh.add_argument("tree", help="Directory holding <model>_r<k>/ run dirs.")
    sh.add_argument("--models", nargs="+", default=["sonnet", "haiku"])
    sh.add_argument("--align-key", default=DEFAULT_ALIGN_KEY)
    sh.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    {"run": cmd_run, "run-tables": cmd_run_tables, "eval": cmd_eval,
     "harmonize": cmd_harmonize}[args.cmd](args)


if __name__ == "__main__":
    main()
