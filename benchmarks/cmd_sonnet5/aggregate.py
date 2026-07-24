#!/usr/bin/env python
"""Aggregate the multi-seed benchmark (out_ms/<model>_r<k>) into per-study
enumeration stability + per-model headline distributions, so run-to-run LLM
variance is separated from the (now-fixed) fetch-source table-loss effect.

Writes out_ms/AGGREGATE.md and out_ms/aggregate.json. Run after `multiseed.py eval`.
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Optional first CLI arg selects the output tree (e.g. out_ms_refined); default out_ms.
MS = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else HERE / "out_ms"
if not MS.is_absolute():
    MS = HERE / MS
MODELS = ["sonnet", "haiku"]
RUNS = 3
ORDER = ["Bengtsson-PalmeJ_2015", "TettAJ_2019_b", "LiJ_2017", "NayakRR_2021",
         "PasolliE_2019", "Heitz-BuschartA_2016", "FanY_2023", "QinJ_2012",
         "ContevilleLC_2019", "LiSS_2016"]


def _prf(a: dict):
    tp = a["tp_correct"] + a["tp_wrong"]
    P = tp / (tp + a["fp"]) if tp + a["fp"] else None
    R = tp / (tp + a["fn"]) if tp + a["fn"] else None
    F = 2 * P * R / (P + R) if P and R else None
    V = a["tp_correct"] / tp if tp else None
    return P, R, F, V


def _content_agg(per_study: list[dict], key: str = "content") -> dict:
    c = dict(tn=0, tp_correct=0, tp_wrong=0, fn=0, fp=0)
    for s in per_study:
        block = s.get(key)
        if block:
            for k in c:
                c[k] += block[k]
    return c


def _fetch_source(runlog: Path) -> str:
    if not runlog.exists():
        return "?"
    m = re.search(r"fetched (\w+)", runlog.read_text(errors="ignore"))
    return m.group(1) if m else "?"


def _run_dir(model: str, k: int) -> Path:
    return MS / f"{model}_r{k}"


def _fmt(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, float) else "–"


def _rng(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, None
    return (st.median(vals), min(vals), max(vals))


def load_counts(model: str):
    """study -> {'gold':g, 'runs':[n1,n2,n3], 'src':[s1,s2,s3], 'status':[...]}"""
    out: dict[str, dict] = {}
    for k in range(1, RUNS + 1):
        d = _run_dir(model, k)
        for study in ORDER:
            rec = out.setdefault(study, {"gold": None, "runs": [], "src": [], "status": []})
            j = d / f"{study}.json"
            if j.exists():
                data = json.loads(j.read_text())
                rec["runs"].append(len(data.get("samples", [])))
                rec["status"].append("ok")
            else:
                rec["runs"].append(None)
                rec["status"].append("fail")
            rec["src"].append(_fetch_source(d / f"{study}.runlog.txt"))
    # gold counts from any summary
    for k in range(1, RUNS + 1):
        sj = _run_dir(model, k) / "summary.json"
        if sj.exists():
            for s in json.loads(sj.read_text())["per_study"]:
                if "n_gold" in s and s["study"] in out:
                    out[s["study"]]["gold"] = s["n_gold"]
    return out


def headline_dist(model: str):
    """Per-run content P/R/F1/vacc across the RUNS repeats -> (median,min,max) each."""
    Ps, Rs, Fs, Vs, fps, Rcovs = [], [], [], [], [], []
    per_run = []
    for k in range(1, RUNS + 1):
        sj = _run_dir(model, k) / "summary.json"
        if not sj.exists():
            continue
        ps = json.loads(sj.read_text())["per_study"]
        c = _content_agg(ps)
        P, R, F, V = _prf(c)
        # Coverage-aware recall (un/under-enumerated gold rows counted as FN);
        # None on older summaries that predate the content_coverage block.
        ccov = _content_agg(ps, "content_coverage")
        _, Rcov, _, _ = _prf(ccov)
        Ps.append(P); Rs.append(R); Fs.append(F); Vs.append(V); fps.append(c["fp"])
        Rcovs.append(Rcov)
        per_run.append({"run": k, "P": P, "R": R, "F1": F, "vacc": V,
                        "R_cov": Rcov, "cells": c})
    return {"P": _rng(Ps), "R": _rng(Rs), "F1": _rng(Fs), "vacc": _rng(Vs),
            "fp": _rng(fps), "R_cov": _rng(Rcovs), "per_run": per_run}


def main() -> None:
    agg = {"models": {}}
    L = ["# Multi-seed benchmark — enumeration stability & headline distributions\n"]
    L.append(f"Each study run **{RUNS}×** per model on the **fixed** fetcher "
             "(Europe PMC fallback is strictly additive: S3 supplementary recovered "
             "regardless of body source). Spread below is genuine LLM/pipeline "
             "run-to-run variance.\n")

    for model in MODELS:
        counts = load_counts(model)
        hd = headline_dist(model)
        agg["models"][model] = {"counts": counts, "headline": hd}

        L.append(f"\n## {model}\n")
        pr = hd["per_run"]
        L.append("Headline content metrics per repeat (median [min–max] across "
                 f"{len(pr)} run(s)):\n")
        for key in ("P", "R", "F1", "vacc", "fp", "R_cov"):
            med, lo, hi = hd[key]
            if key == "R_cov" and med is None:
                continue  # older summaries without the content_coverage block
            nd = 0 if key == "fp" else 3
            label = ("R_cov (coverage-aware recall; un/under-enumerated gold rows "
                     "counted as FN)") if key == "R_cov" else key
            L.append(f"- **{label}**: {_fmt(med, nd)} [{_fmt(lo, nd)}–{_fmt(hi, nd)}]")
        L.append("\n### Per-study sample enumeration across repeats\n")
        L.append("| study | gold | run1 | run2 | run3 | median | range | fetch src |")
        L.append("|---|--:|--:|--:|--:|--:|--:|---|")
        for study in ORDER:
            rec = counts[study]
            r = rec["runs"] + [None] * (RUNS - len(rec["runs"]))
            med, lo, hi = _rng(rec["runs"])
            rng = f"{lo}–{hi}" if lo is not None else "–"
            srcs = ",".join(sorted(set(s[:4] for s in rec["src"])))
            cells = " | ".join("fail" if x is None else str(x) for x in r[:RUNS])
            L.append(f"| {study} | {rec['gold']} | {cells} | "
                     f"{'' if med is None else int(med)} | {rng} | {srcs} |")

    (MS / "AGGREGATE.md").write_text("\n".join(L))
    (MS / "aggregate.json").write_text(json.dumps(agg, indent=2, default=str))
    print(f"wrote {MS/'AGGREGATE.md'} and {MS/'aggregate.json'}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
