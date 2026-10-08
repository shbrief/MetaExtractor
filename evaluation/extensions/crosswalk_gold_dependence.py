#!/usr/bin/env python3
"""How many correct cells depended on a crosswalk entry that only gold supplied?

`harmonize/crosswalk.py:load_field_crosswalk` returns the **union** of two maps::

    {**crosswalk_map(crosswalk_gold_<field>.csv), **crosswalk_map(crosswalk_<field>.csv)}

and `Harmonizer.canonicalize` applies that union to *extracted* values as well as
gold ones. So a surface form that only the curated vocabulary was mapped for is
nonetheless available to harmonize an extraction that happens to produce the same
surface form. It cannot invent a code for a string the extractor never produced,
but it does mean the extracted side's mapping table is partly populated from gold.

This script quantifies the exposure instead of arguing about it. For each
harmonized field it finds the *gold-only* crosswalk keys -- query terms present in
`crosswalk_gold_<field>.csv` and absent from `crosswalk_<field>.csv` -- and counts
the committed `TP_correct` cells whose extracted value depends on one.

"Depends on" is exact, not approximate: `Harmonizer.codes` returns a code set only
when **every** term of a value maps, so one gold-only term is enough to make the
whole value unharmonizable without the gold map. Those cells would fall back to a
raw string comparison and almost all of them would stop being TP_correct.

Scoring-only, and read-only with respect to the run trees: it reads the committed
`*.cells.tsv` and `crosswalks/` of a tree and writes a report of its own. It never
re-runs an extraction and never rewrites `out_v3/`.

Usage::

    python evaluation/extensions/crosswalk_gold_dependence.py            # out_v3
    python evaluation/extensions/crosswalk_gold_dependence.py --tree out_v4 \
        --crosswalks crosswalks_3field
    python evaluation/extensions/crosswalk_gold_dependence.py --out REPORT.md
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO / "benchmarks" / "cmd_sonnet5"
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(REPO / "src"))

from harmonize.crosswalk import (  # noqa: E402
    corpus_code_map,
    crosswalk_map,
    norm,
    terms_of,
)


def gold_only_keys(field: str, directory: Path) -> tuple[dict[str, str], dict[str, str]]:
    """``(gold_only, extracted)`` crosswalk maps for ``field``.

    ``gold_only`` holds the entries the union would contribute that the extracted
    crosswalk does not have on its own.
    """
    code_map = corpus_code_map(field)
    gold = crosswalk_map(directory / f"crosswalk_gold_{field}.csv", code_map)
    ext = crosswalk_map(directory / f"crosswalk_{field}.csv", code_map)
    return {k: v for k, v in gold.items() if k not in ext}, ext


def harmonized_fields(directory: Path) -> list[str]:
    return sorted(
        p.stem[len("crosswalk_"):]
        for p in directory.glob("crosswalk_*.csv")
        if not p.stem.startswith("crosswalk_gold_")
    )


def scan(tree: Path, crosswalk_dir: Path) -> dict:
    fields = harmonized_fields(crosswalk_dir)
    gold_only = {}
    ext_maps = {}
    for f in fields:
        gold_only[f], ext_maps[f] = gold_only_keys(f, crosswalk_dir)

    # counters[field] = {"tpc": n, "dependent": n, "terms": {term: n}}
    counters: dict[str, dict] = {
        f: {"tpc": 0, "dependent": 0, "terms": defaultdict(int)} for f in fields
    }
    runs = sorted(d for d in tree.iterdir() if d.is_dir() and "_r" in d.name)
    n_files = 0
    for run in runs:
        for cells in sorted(run.glob("*.cells.tsv")):
            n_files += 1
            with cells.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh, delimiter="\t"):
                    field = row["field"]
                    if field not in counters or row["decision"] != "TP_correct":
                        continue
                    counters[field]["tpc"] += 1
                    hits = [t for t in terms_of(row["extracted"])
                            if norm(t) in gold_only[field]]
                    if hits:
                        counters[field]["dependent"] += 1
                        for t in hits:
                            counters[field]["terms"][norm(t)] += 1
    return {
        "tree": tree.name,
        "crosswalks": crosswalk_dir.name,
        "runs": [r.name for r in runs],
        "n_cells_files": n_files,
        "fields": fields,
        "gold_only": {f: gold_only[f] for f in fields},
        "extracted_size": {f: len(ext_maps[f]) for f in fields},
        "counters": counters,
    }


def render(res: dict) -> str:
    L: list[str] = []
    L.append(f"# Gold-only crosswalk dependence — `{res['tree']}` "
             f"(`{res['crosswalks']}`)\n")
    L.append(f"{len(res['runs'])} runs, {res['n_cells_files']} `cells.tsv` files, "
             f"{len(res['fields'])} harmonized field(s): "
             f"{', '.join(f'`{f}`' for f in res['fields'])}.\n")
    L.append("A `TP_correct` cell is **dependent** when some term of its extracted "
             "value is mapped only by `crosswalk_gold_<field>.csv`. Because "
             "`Harmonizer.codes` requires every term of a value to map, one such "
             "term would leave the whole value unharmonized.\n")

    L.append("| field | gold-only entries | extracted entries | TP_correct | dependent | share |")
    L.append("|---|--:|--:|--:|--:|--:|")
    tot_tpc = tot_dep = 0
    for f in res["fields"]:
        c = res["counters"][f]
        tot_tpc += c["tpc"]
        tot_dep += c["dependent"]
        share = f"{c['dependent'] / c['tpc']:.3%}" if c["tpc"] else "—"
        L.append(f"| `{f}` | {len(res['gold_only'][f])} | {res['extracted_size'][f]} "
                 f"| {c['tpc']} | **{c['dependent']}** | {share} |")
    share = f"{tot_dep / tot_tpc:.3%}" if tot_tpc else "—"
    L.append(f"| **all** | | | {tot_tpc} | **{tot_dep}** | {share} |")
    L.append("")

    if tot_dep == 0:
        L.append("## Verdict\n")
        L.append("**No correct cell depended on a gold-only crosswalk entry.** The union "
                 "in `load_field_crosswalk` is therefore inert for these runs: every "
                 "extracted surface form that harmonized was mapped by the extracted "
                 "crosswalk on its own. The exposure is real in the code and empty in "
                 "the data, and can be stated that way.\n")
    else:
        L.append("## Verdict\n")
        L.append(f"**{tot_dep} of {tot_tpc} correct cells ({share}) depended on a "
                 "gold-only crosswalk entry.** Post-harmonization accuracy is to that "
                 "extent underwritten by the curated vocabulary, and the limitation "
                 "belongs in the manuscript rather than in a build script's docstring.\n")
        L.append("### The terms responsible\n")
        L.append("| field | term | code | dependent cells |")
        L.append("|---|---|---|--:|")
        for f in res["fields"]:
            for term, n in sorted(res["counters"][f]["terms"].items(),
                                  key=lambda kv: -kv[1]):
                L.append(f"| `{f}` | {term} | `{res['gold_only'][f][term]}` | {n} |")
        L.append("")

    nonempty = [f for f in res["fields"] if res["gold_only"][f]]
    if nonempty:
        L.append("### Gold-only entries, for reference\n")
        for f in nonempty:
            items = sorted(res["gold_only"][f].items())
            L.append(f"`{f}` ({len(items)}): "
                     + ", ".join(f"{k} → `{v}`" for k, v in items[:40])
                     + (" …" if len(items) > 40 else ""))
            L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tree", default="out_v3",
                    help="run tree under benchmarks/cmd_sonnet5 (default out_v3)")
    ap.add_argument("--crosswalks", default="crosswalks",
                    help="crosswalk directory inside the tree (default crosswalks)")
    ap.add_argument("--out", default=None,
                    help="write the report here instead of stdout")
    args = ap.parse_args()

    tree = BENCH / args.tree
    cwd = tree / args.crosswalks
    if not tree.is_dir():
        raise SystemExit(f"no run tree {tree}")
    if not cwd.is_dir():
        raise SystemExit(f"no crosswalk directory {cwd}")

    report = render(scan(tree, cwd))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
