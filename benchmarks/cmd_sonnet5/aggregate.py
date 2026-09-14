#!/usr/bin/env python
"""Aggregate a multi-repeat run tree into the tables the manuscript reports.

Reads ``TREE/<model>_r<k>/summary.json`` (written by ``bench.py eval``) and, when
present, ``TREE/ledger.jsonl`` (written by ``run_frozen.py``). Writes
``TREE/aggregate_v2.json`` and ``TREE/AGGREGATE.md`` with:

* post-harmonization precision / recall / F1 of content fields for the two scores —
  all curated samples (``end_to_end``) and matched samples (``conditional``) —
  median [min–max] across repeats;
* the same per harmonized field (MetaHarmonizer crosswalk fields);
* a per-study × per-repeat error table (TPc / TPw / FN / FP / extra records);
* identity-alignment diagnostics and per-study enumeration counts;
* a study-cluster bootstrap CI for the paired model difference in all-curated F1
  (studies resampled with replacement; repeats pooled within study);
* cell decisions for age_min/age_max split by value provenance (age rule vs other);
* false-positive source checks and the attempt ledger summary.

  python aggregate.py out_v2 [--models sonnet haiku] [--boot 2000]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

from bench import _add, _zero, metrics

JOINS = ("end_to_end", "conditional")
RENDER_JOINS = (("end_to_end", "Score all curated"), ("conditional", "Score matched"),
                ("end_to_end_successful_only", "Sensitivity: all curated, successful extractions only"))
HEADLINE = ("precision", "recall", "f1", "tp_correct", "tp_wrong", "fp", "fn")


def _mmm(vals):
    vals = [v for v in vals if v is not None]
    return [st.median(vals), min(vals), max(vals)] if vals else None


def load_runs(tree: Path, model: str) -> dict[str, dict]:
    runs = {}
    for d in sorted(tree.glob(f"{model}_r*")):
        sj = d / "summary.json"
        if sj.exists():
            runs[d.name] = json.loads(sj.read_text())
    return runs


def pooled(per_study: list[dict], join: str, part: str = "content",
           skip_failed: bool = False) -> dict:
    a = _zero()
    for s in per_study:
        if "error" in s or (skip_failed and s.get("extraction_failed")):
            continue
        _add(a, s[join][part])
    return a


def bootstrap_diff(runs_a: dict, runs_b: dict, B: int, seed: int = 0) -> dict:
    """Paired study-cluster bootstrap of F1(a) − F1(b), all curated."""
    def study_counts(runs):
        out = defaultdict(_zero)
        for summ in runs.values():
            for s in summ["per_study"]:
                if "error" not in s:
                    _add(out[s["study"]], s["end_to_end"]["content"])
        return out
    ca, cb = study_counts(runs_a), study_counts(runs_b)
    studies = sorted(set(ca) & set(cb))
    def f1(counts, sample):
        a = _zero()
        for s in sample:
            _add(a, counts[s])
        return metrics(a)["f1"] or 0.0
    point = f1(ca, studies) - f1(cb, studies)
    rng = random.Random(seed)
    diffs = []
    for _ in range(B):
        sample = [rng.choice(studies) for _ in studies]
        diffs.append(f1(ca, sample) - f1(cb, sample))
    diffs.sort()
    return {"point": point, "ci95": [diffs[int(0.025 * B)], diffs[int(0.975 * B) - 1]],
            "B": B, "n_studies": len(studies), "seed": seed}


def ledger_summary(tree: Path) -> dict | None:
    lp = tree / "ledger.jsonl"
    if not lp.exists():
        return None
    rows = [json.loads(l) for l in lp.read_text().splitlines() if l.strip()]
    by_task = defaultdict(list)
    for r in rows:
        by_task[(r["model_key"], r["repeat"], r["study"])].append(r)
    final_ok = sum(1 for att in by_task.values() if att[-1]["status"] == "ok")
    first_fail = [k for k, att in by_task.items() if att[0]["status"] != "ok"]
    return {
        "tasks": len(by_task), "attempts": len(rows),
        "failed_attempts": sum(1 for r in rows if r["status"] != "ok"),
        "initial_failures": len(first_fail),
        "initial_failures_detail": [
            {"task": "/".join(map(str, k)), "status": by_task[k][0]["status"],
             "error_tail": by_task[k][0].get("stderr_tail", "")[-300:]} for k in first_fail],
        "final_successes": final_ok,
        "started": min(r["start_utc"] for r in rows), "ended": max(r["end_utc"] for r in rows),
        "commits": sorted({r["git"]["commit"] for r in rows}),
        "dirty_any": any(r["git"]["dirty"] for r in rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree")
    ap.add_argument("--models", nargs="+", default=["sonnet", "haiku"])
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()
    tree = Path(args.tree)

    agg: dict = {"tree": str(tree), "models": {}}
    runs_by_model = {m: load_runs(tree, m) for m in args.models}
    for model, runs in runs_by_model.items():
        md: dict = {"runs": list(runs), "headline": {}, "per_run": {}, "per_study": {}}
        for join in JOINS:
            per_run = {r: metrics(pooled(s["per_study"], join)) for r, s in runs.items()}
            md["per_run"][join] = per_run
            md["headline"][join] = {k: _mmm([pr[k] for pr in per_run.values()]) for k in HEADLINE}
        # Sensitivity: end-to-end over successful extractions only (failed runs excluded).
        ok_only = {r: metrics(pooled(s["per_study"], "end_to_end", skip_failed=True))
                   for r, s in runs.items()}
        md["per_run"]["end_to_end_successful_only"] = ok_only
        md["headline"]["end_to_end_successful_only"] = {
            k: _mmm([pr[k] for pr in ok_only.values()]) for k in HEADLINE}
        md["failed_extractions"] = sorted(
            f"{r}/{s['study']}" for r, summ in runs.items() for s in summ["per_study"]
            if s.get("extraction_failed"))
        harmonized = sorted({f for s in runs.values() for f in s.get("harmonized_fields", [])})
        md["harmonized_fields"] = harmonized
        md["per_field"] = {}
        for f in harmonized:
            md["per_field"][f] = {}
            for join in JOINS:
                per_run = {}
                for r, summ in runs.items():
                    a = _zero()
                    for s in summ["per_study"]:
                        if "error" not in s and f in s.get(f"fields_{join}", {}):
                            _add(a, s[f"fields_{join}"][f])
                    per_run[r] = metrics(a)
                md["per_field"][f][join] = {k: _mmm([pr[k] for pr in per_run.values()])
                                            for k in HEADLINE}
        md["unqueried_terms"] = sorted({t for summ in runs.values() for s in summ["per_study"]
                                        for d in (s.get("harmonization") or {}).values()
                                        for t in d["unqueried_terms"]})

        age_by_source = defaultdict(_zero)
        fp_check = defaultdict(lambda: defaultdict(int))
        for r, summ in runs.items():
            for s in summ["per_study"]:
                ps = md["per_study"].setdefault(s["study"], {"n_gold": s.get("n_gold"), "runs": {}})
                if "error" in s:
                    ps["runs"][r] = {"error": s["error"]}
                    continue
                al = s["alignment"]
                ps["runs"][r] = {
                    "n_extracted": s["n_extracted"], "granularity": s.get("granularity"),
                    "extraction_failed": s.get("extraction_failed", False),
                    "alignment": al,
                    "end_to_end": s["end_to_end"]["content"],
                    "conditional": s["conditional"]["content"],
                    "extra_records": al["unmatched_ext_with_key"] + al["unmatched_ext_without_key"],
                }
                for f in ("age_min", "age_max"):
                    for kind, c in (s.get("by_source_end_to_end") or {}).get(f, {}).items():
                        bucket = "age_rule" if kind == "age_rule" else "other"
                        _add(age_by_source[f"{f}:{bucket}"], c)
                for f, c in (s.get("fp_source_check") or {}).items():
                    for k, v in c.items():
                        fp_check[f][k] += v
        md["age_by_source"] = {k: {**v, **metrics(v)} for k, v in age_by_source.items()}
        md["fp_source_check"] = {f: dict(v) for f, v in fp_check.items()}
        agg["models"][model] = md

    if len(args.models) == 2 and all(runs_by_model.values()):
        a, b = args.models
        agg["paired_f1_difference"] = {"a": a, "b": b,
                                             **bootstrap_diff(runs_by_model[a], runs_by_model[b], args.boot)}
    agg["ledger"] = ledger_summary(tree)
    (tree / "aggregate_v2.json").write_text(json.dumps(agg, indent=2, default=str))
    (tree / "AGGREGATE.md").write_text(render(agg))
    print(render(agg))


def _f(v, nd=3):
    if v is None:
        return "–"
    if isinstance(v, list):
        if nd == 0:
            return f"{v[0]:.0f} [{v[1]:.0f}–{v[2]:.0f}]"
        return f"{v[0]:.{nd}f} [{v[1]:.{nd}f}–{v[2]:.{nd}f}]"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def render(agg: dict) -> str:
    L = [f"# Aggregate — `{agg['tree']}`\n",
         "Content fields, micro-averaged; median [min–max] across repeats. Values are compared "
         "after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against "
         "the curated ontology id where present), other fields as extracted. Precision = "
         "TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).\n"]
    for model, md in agg["models"].items():
        if md.get("harmonized_fields"):
            L.append(f"Harmonized fields ({model}): {', '.join(md['harmonized_fields'])}.")
        if md.get("unqueried_terms"):
            L.append(f"\n**Warning ({model}):** extracted terms missing from the crosswalks "
                     f"(scored as unmapped): {', '.join(md['unqueried_terms'])}")
    for join, title in RENDER_JOINS:
        L += [f"\n## {title}\n",
              "| model | precision | recall | F1 | TPc | TPw | FP | FN |",
              "|---|--:|--:|--:|--:|--:|--:|--:|"]
        for model, md in agg["models"].items():
            h = md["headline"][join]
            L.append(f"| {model} | {_f(h['precision'])} | {_f(h['recall'])} | {_f(h['f1'])} | "
                     f"{_f(h['tp_correct'], 0)} | {_f(h['tp_wrong'], 0)} | {_f(h['fp'], 0)} | "
                     f"{_f(h['fn'], 0)} |")
    pd_ = agg.get("paired_f1_difference")
    if pd_:
        L.append(f"\nPaired all-curated F1 difference ({pd_['a']} − {pd_['b']}): "
                 f"{pd_['point']:+.3f}, 95% study-cluster bootstrap CI "
                 f"[{pd_['ci95'][0]:+.3f}, {pd_['ci95'][1]:+.3f}] "
                 f"({pd_['n_studies']} studies, B={pd_['B']}).\n")
    if any(md.get("per_field") for md in agg["models"].values()):
        L += ["\n## Harmonized fields\n",
              "| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |",
              "|---|---|---|--:|--:|--:|--:|--:|--:|--:|"]
        for model, md in agg["models"].items():
            for f, joins in md.get("per_field", {}).items():
                for join, title in (("end_to_end", "all curated"), ("conditional", "matched")):
                    h = joins[join]
                    L.append(f"| {f} | {model} | {title} | {_f(h['precision'])} | {_f(h['recall'])} | "
                             f"{_f(h['f1'])} | {_f(h['tp_correct'], 0)} | {_f(h['tp_wrong'], 0)} | "
                             f"{_f(h['fp'], 0)} | {_f(h['fn'], 0)} |")
    for model, md in agg["models"].items():
        if md.get("failed_extractions"):
            L.append(f"\n{model}: extractions with no output after the retry "
                     f"(scored as producing no records): {', '.join(md['failed_extractions'])}")
    for model, md in agg["models"].items():
        L += [f"\n## {model}: per study × repeat (content cells)\n",
              "| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |",
              "|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for study, ps in md["per_study"].items():
            for r, x in ps["runs"].items():
                if "error" in x:
                    L.append(f"| {study} | {ps['n_gold']} | {r} | {x['error']} |" + " |" * 11)
                    continue
                al, c, cm = x["alignment"], x["end_to_end"], x["conditional"]
                tag = " (failed)" if x.get("extraction_failed") else ""
                L.append(f"| {study} | {ps['n_gold']} | {r}{tag} | {x['n_extracted']} | "
                         f"{al['key_used'] or '–'} | {al['matched']} | {al['unmatched_gold']} | "
                         f"{al['pooled_gold']} | {al['ambiguous_gold']} | {x['extra_records']} | "
                         f"{c['tp_correct']} | {c['tp_wrong']} | {c['fn']} | {cm['fn']} | {c['fp']} |")
        if md["age_by_source"]:
            L += [f"\n### {model}: age bounds by provenance (all curated, pooled over repeats)\n",
                  "| field:source | TPc | TPw | FN | FP | precision |", "|---|--:|--:|--:|--:|--:|"]
            for k, v in sorted(md["age_by_source"].items()):
                L.append(f"| {k} | {v['tp_correct']} | {v['tp_wrong']} | {v['fn']} | {v['fp']} | "
                         f"{_f(v['precision'])} |")
        if md["fp_source_check"]:
            L += [f"\n### {model}: false-positive source check (pooled over repeats)\n",
                  "Partial check only: whether the asserted value string, or the study-level "
                  "evidence quote, occurs verbatim in the saved retrieved text. It does not "
                  "establish fabrication or gold incompleteness.\n",
                  "| field | FP cells | value in text | study evidence in text |", "|---|--:|--:|--:|"]
            for f, v in sorted(md["fp_source_check"].items(), key=lambda kv: -kv[1]["fp"]):
                L.append(f"| {f} | {v['fp']} | {v['value_in_text']} | {v['study_evidence_in_text']} |")
    led = agg.get("ledger")
    if led:
        L += ["\n## Attempt ledger\n",
              f"- tasks {led['tasks']}, attempts {led['attempts']}, failed attempts "
              f"{led['failed_attempts']}, initial failures {led['initial_failures']}, "
              f"final successes {led['final_successes']}",
              f"- window {led['started']} → {led['ended']} (UTC); commits {led['commits']}; "
              f"dirty tree: {led['dirty_any']}"]
        for d in led["initial_failures_detail"]:
            L.append(f"  - {d['task']}: {d['status']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
