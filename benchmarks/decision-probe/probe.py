#!/usr/bin/env python3
"""Measure the pipeline's bounded judgments offline, before replacing any of them.

``src/metaextractor/decision.py`` is a seam for cheap bounded judgments that is
deliberately wired to nothing. This script is why: a judgment should not be
handed to a model before anyone knows how often the current heuristic is right.

Everything here reads committed run artifacts and makes no API calls.

Probe A -- the structure-plan decision
--------------------------------------

``table_plan.needs_structure_plan`` decides, from six hand-written rules, whether
a supplementary table can be read with "row 0 is the header" or needs an LLM call
to propose a structure. It is the pipeline's *cost* router.

The label is the plan the model actually returned, recorded in each run's
``extraction_warnings``. A plan of ``header_rows=[0]`` with no melt is
structurally identical to the default parse, so the call bought nothing: the
detector was wrong to spend it. That makes **precision measurable**.

**Recall is not measurable from these runs**, and that asymmetry is the main
caveat: when the detector said "read as is", no plan was requested, so there is
no label saying whether one was needed. Measuring recall would need a run that
asks for a plan on every table -- a deliberate, paid experiment.

Probe B -- project resolution
-----------------------------

``sra_manifest.resolve_projects`` picks the study's own BioProject by three
ordered rules over a term-count score. It is now instrumented (``audit=``), so
this counts how often the confident branch was in fact a contested tie -- the
cases where the tie-break could silently pick the wrong study's runs.

Usage::

    python benchmarks/decision-probe/probe.py                 # out_v4 and out_v3
    python benchmarks/decision-probe/probe.py --out out_v4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BENCH = REPO / "benchmarks" / "cmd_sonnet5"
sys.path.insert(0, str(REPO / "src"))

from metaextractor.fetcher import FETCH_RECORD, load_fetched  # noqa: E402
from metaextractor.sra_manifest import (  # noqa: E402
    extract_dataset_accessions,
    resolve_projects,
)
from metaextractor.table_plan import needs_structure_plan  # noqa: E402

#: Both warning spellings:
#:   out_v3  "Table 'x': plan applied (header_rows=[0], melt=no, ...)"
#:   out_v4  "Table 'x': structure plan applied (<reason>; header_rows=[0], melt=no, ...)"
_PLAN_APPLIED = re.compile(
    r"Table '(.+?)': (?:structure )?plan applied \((?:.*?; )?"
    r"header_rows=(\[[^\]]*\]), melt=(\w+)")


def _studies() -> list[str]:
    m = json.loads((BENCH / "manifest.json").read_text())
    entries = m if isinstance(m, list) else m.get("studies", [])
    return [e["study"] for e in entries]


# ---------------------------------------------------------------------------
# Probe A
# ---------------------------------------------------------------------------

def probe_structure_plan(tree: Path) -> dict:
    """Of the tables a plan was requested for, how many needed one?"""
    # (study, table) -> {"flat", "structured"} as the model actually planned it
    observed: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(tree.glob("*_r*/*.json")):
        if path.name.endswith(".meta.json") or path.name == "summary.json":
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for w in payload.get("extraction_warnings") or []:
            m = _PLAN_APPLIED.search(w)
            if m:
                kind = ("flat" if m.group(2) == "[0]" and m.group(3) == "no"
                        else "structured")
                observed[(path.stem, m.group(1))].add(kind)

    rows = []
    for study in _studies():
        fdir = tree / "_fetch" / study
        if not (fdir / FETCH_RECORD).exists():
            continue
        for t in load_fetched(fdir).supplementary_tables or []:
            if getattr(t, "source", None) == "ena":
                continue          # manifests bypass the plan path entirely
            kinds = observed.get((study, t.name))
            if not kinds:
                continue          # no plan was requested: no label (see docstring)
            need, why = needs_structure_plan(t)
            label = ("flat" if kinds == {"flat"}
                     else "structured" if "flat" not in kinds
                     else "runs disagree")
            rows.append({"study": study, "table": t.name, "detector": need,
                         "reason": why, "label": label})

    planned = [r for r in rows if r["detector"]]
    needed = [r for r in planned if r["label"] == "structured"]
    wasted = [r for r in planned if r["label"] == "flat"]
    disagreed = [r for r in planned if r["label"] == "runs disagree"]
    return {
        "rows": rows,
        "n_labelled": len(rows),
        "n_planned": len(planned),
        "n_needed": len(needed),
        "n_wasted": len(wasted),
        "n_disagreed": len(disagreed),
        "precision": (len(needed) / len(planned)) if planned else None,
        "by_reason": Counter((r["reason"][:46], r["label"]) for r in planned),
    }


# ---------------------------------------------------------------------------
# Probe B
# ---------------------------------------------------------------------------

def probe_project_resolution(tree: Path) -> dict:
    """How often was the confident project choice actually a contested tie?"""
    def refuse(url: str) -> bytes:
        raise RuntimeError("ENA resolution not attempted in the probe")

    rows = []
    for study in _studies():
        tp = tree / "_fetch" / study / "text.txt"
        if not tp.exists():
            continue
        audit: dict = {}
        try:
            projects, _ = resolve_projects(
                extract_dataset_accessions(tp.read_text(errors="replace")),
                refuse, audit=audit)
        except RuntimeError:
            projects = ["(ena lookup not attempted)"]
        rows.append({"study": study, "rule": audit.get("rule", "?"),
                     "contested": bool(audit.get("contested")),
                     "n_projects": len(projects),
                     "top_score": audit.get("top_score"),
                     "margin": audit.get("margin"),
                     "projects": projects})
    confident = [r for r in rows if r["rule"] in
                 ("bioproject_in_context", "single_bioproject_no_context")]
    return {"rows": rows, "n": len(rows), "n_confident": len(confident),
            "n_contested": sum(1 for r in confident if r["contested"]),
            "by_rule": Counter(r["rule"] for r in rows)}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def render(tree_name: str, a: dict, b: dict) -> str:
    L = [f"## `{tree_name}`\n"]

    L.append("### Probe A — the structure-plan decision\n")
    if not a["n_planned"]:
        L.append("No labelled tables in this tree.\n")
    else:
        p = a["precision"]
        L.append(f"- tables with a label (a plan was requested): **{a['n_labelled']}**")
        L.append(f"- the model's plan was non-trivial, so the call was warranted: "
                 f"**{a['n_needed']}**")
        L.append(f"- the model's plan was `header_rows=[0]`, no melt — "
                 f"structurally the default parse, so the call bought nothing: "
                 f"**{a['n_wasted']}**")
        L.append(f"- repeats disagreed on the same table: **{a['n_disagreed']}**")
        L.append(f"- **precision = {p:.3f}** ({a['n_needed']}/{a['n_planned']})\n")
        L.append("Recall is not measurable here: a table the detector read as is was "
                 "never shown to a model, so nothing says whether a plan was needed. "
                 "Measuring it requires a paid run that plans every table.\n")
        L.append("By the rule that fired:\n")
        L.append("| detector reason | plan non-trivial | plan trivial | disagreed |")
        L.append("|---|--:|--:|--:|")
        reasons = sorted({r for r, _ in a["by_reason"]})
        for reason in reasons:
            L.append(f"| {reason} | {a['by_reason'][(reason, 'structured')]} "
                     f"| {a['by_reason'][(reason, 'flat')]} "
                     f"| {a['by_reason'][(reason, 'runs disagree')]} |")
        L.append("")

    L.append("### Probe B — project resolution\n")
    L.append(f"- studies probed: **{b['n']}**")
    L.append(f"- resolved by a confident rule: **{b['n_confident']}**")
    L.append(f"- of those, the choice was a **contested tie**: "
             f"**{b['n_contested']}**\n")
    L.append("| study | rule | contested | top score | margin | projects |")
    L.append("|---|---|:-:|--:|--:|---|")
    for r in b["rows"]:
        L.append(f"| {r['study']} | `{r['rule']}` | "
                 f"{'yes' if r['contested'] else ''} | "
                 f"{r['top_score'] if r['top_score'] is not None else ''} | "
                 f"{r['margin'] if r['margin'] is not None else ''} | "
                 f"{', '.join(r['projects'][:4]) or '—'} |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", nargs="+", default=["out_v4", "out_v3"])
    ap.add_argument("--write", type=Path, default=None,
                    help="append the rendered report to this file")
    args = ap.parse_args()

    parts = []
    for name in args.out:
        tree = BENCH / name
        if not tree.is_dir():
            print(f"[skip] no tree {tree}", file=sys.stderr)
            continue
        parts.append(render(name, probe_structure_plan(tree),
                            probe_project_resolution(tree)))
    report = "\n".join(parts)
    if args.write:
        args.write.write_text(report, encoding="utf-8")
        print(f"wrote {args.write}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
