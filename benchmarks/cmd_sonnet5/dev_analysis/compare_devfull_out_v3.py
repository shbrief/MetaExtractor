"""Full development-set run at revision-v4 HEAD vs out_v3, per model.

Both trees hold the same ten development studies x {Haiku 4.5, Sonnet 5} x 3 repeats,
scored post-harmonization against each tree's own crosswalks. Writes
``dev_analysis/devfull/COMPARISON.md``:

* pooled content F1 per repeat and per model, for both joins;
* per study, the mean F1 over the repeats of each model;
* a per-field account of the correct cells gained and lost. Repeats whose extraction
  failed carry no signal and are excluded; a field whose surviving repeats disagree is
  repeat-to-repeat model variance rather than a consequence of the code changes, and is
  counted separately.

  CMD_CURATION_DIR=... python dev_analysis/compare_devfull_out_v3.py
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from bench import metrics                                   # noqa: E402
from bench_paths import gold_path, load_manifest            # noqa: E402

TREES = {"out_v3": BENCH / "out_v3", "devfull": HERE / "devfull"}
MODELS = ("haiku", "sonnet")
REPEATS = (1, 2, 3)
KEYS = ("tp_correct", "tp_wrong", "fn", "fp")


def per_study(run: Path) -> dict[str, dict]:
    return {s["study"]: s for s in json.loads((run / "summary.json").read_text())["per_study"]}


def f1(study: dict, join: str) -> float | None:
    c = study[join]["content"]
    return metrics(c)["f1"] if sum(c[k] for k in KEYS) else None


def pooled(run: dict[str, dict], join: str) -> tuple[float, dict]:
    t = {k: sum(s[join]["content"][k] for s in run.values()) for k in KEYS}
    return metrics(t)["f1"], t


def gold_distinct(mani: dict, study: str, field: str) -> int:
    vals = {(r.get(field) or "").strip()
            for r in csv.DictReader(gold_path(mani[study]).open(), delimiter="\t")}
    return len({v for v in vals if v and v.lower() not in ("na", "nan")})


def fmt(x: float | None) -> str:
    return f"{x:.3f}" if isinstance(x, float) else "–"


def main() -> None:
    mani = {m["study"]: m for m in load_manifest()}
    runs = {(t, m, k): per_study(TREES[t] / f"{m}_r{k}")
            for t in TREES for m in MODELS for k in REPEATS
            if (TREES[t] / f"{m}_r{k}" / "summary.json").exists()}
    studies = list(next(iter(runs.values())))

    out = ["# Full development-set run (commit 5ace970) vs out_v3", "",
           "Ten development studies x {Haiku 4.5, Sonnet 5} x 3 repeats in both trees,",
           "scored post-harmonization against each tree's own crosswalks.", "",
           "## Pooled content F1", "",
           "| join | model | out_v3 (r1/r2/r3) | devfull (r1/r2/r3) | out_v3 mean | devfull mean |",
           "|---|---|---|---|---|---|"]
    for join in ("end_to_end", "conditional"):
        label = "all curated" if join == "end_to_end" else "matched"
        for m in MODELS:
            cells = {}
            for t in TREES:
                vals = [pooled(runs[(t, m, k)], join)[0] for k in REPEATS if (t, m, k) in runs]
                cells[t] = vals
            out.append(f"| {label} | {m} | {'/'.join(f'{v:.4f}' for v in cells['out_v3'])} "
                       f"| {'/'.join(f'{v:.4f}' for v in cells['devfull'])} "
                       f"| {statistics.mean(cells['out_v3']):.4f} "
                       f"| **{statistics.mean(cells['devfull']):.4f}** |")

    out += ["", "## Per study, mean content F1 over the three repeats", "",
            "| study | join | haiku out_v3 | haiku devfull | sonnet out_v3 | sonnet devfull |",
            "|---|---|---|---|---|---|"]
    for st in studies:
        for join in ("end_to_end", "conditional"):
            label = "all curated" if join == "end_to_end" else "matched"
            cells = []
            for m in MODELS:
                for t in ("out_v3", "devfull"):
                    vals = [f1(runs[(t, m, k)][st], join) for k in REPEATS if (t, m, k) in runs]
                    vals = [v for v in vals if v is not None]
                    cells.append(fmt(statistics.mean(vals)) if vals else "–")
            if set(cells) == {"–"}:
                continue
            out.append(f"| {st} | {label} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")

    out += ["", "## Correct cells gained and lost, by field", "",
            "Per model, over fields where the two trees differ. A field whose surviving out_v3 "
            "repeats disagree is counted as model variance.", "",
            "| model | study | field | out_v3 TPc | devfull TPc | gold distinct | out_v3 agrees |",
            "|---|---|---|---|---|---|---|"]
    totals = {}
    for m in MODELS:
        gained = lost = variance = 0
        for st in studies:
            ok = [k for k in REPEATS
                  if ("out_v3", m, k) in runs and not runs[("out_v3", m, k)][st].get("extraction_failed")]
            new = [k for k in REPEATS if ("devfull", m, k) in runs]
            if not ok or not new:
                continue
            fields = set()
            for k in new:
                fields |= set(runs[("devfull", m, k)][st]["fields_end_to_end"])
            for field in sorted(fields):
                a = [(runs[("out_v3", m, k)][st]["fields_end_to_end"].get(field) or {}).get("tp_correct", 0)
                     for k in ok]
                b = [(runs[("devfull", m, k)][st]["fields_end_to_end"].get(field) or {}).get("tp_correct", 0)
                     for k in new]
                ref, cur = int(statistics.median(a)), int(statistics.median(b))
                if ref == cur:
                    continue
                varies = len(set(a)) > 1
                nd = gold_distinct(mani, st, field)
                out.append(f"| {m} | {st} | {field} | {'/'.join(map(str, a))} | {'/'.join(map(str, b))} "
                           f"| {nd}{' (constant)' if nd == 1 else ''} | {'no' if varies else 'yes'} |")
                if cur > ref:
                    gained += cur - ref
                elif varies:
                    variance += ref - cur
                else:
                    lost += ref - cur
        totals[m] = (gained, lost, variance)
    out.append("")
    for m, (g, l, v) in totals.items():
        out.append(f"- **{m}**: {g} correct cells gained, {l} lost to the code changes, "
                   f"{v} lost where the out_v3 repeats disagreed (model variance)")
    out.append("")
    (HERE / "devfull" / "COMPARISON.md").write_text("\n".join(out))
    print(f"wrote {HERE / 'devfull' / 'COMPARISON.md'}")


if __name__ == "__main__":
    main()
